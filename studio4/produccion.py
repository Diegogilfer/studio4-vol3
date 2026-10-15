"""Una producción = una carpeta en producciones/<id>/ con su proyecto.json, la voz, las tomas de Flow y el vídeo final.

Secuencia:
  1. crear()  → Gemini escribe el guion y el plan de escenas, y en seguida se genera la voz.
  2. Flow     → tú generas cada escena en Flow; la extensión trae los clips (flow.py).
  3. render() → FFmpeg ajusta cada clip a su trozo de voz y monta el vídeo final.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

from . import (canales, carpetas, config, director, entregas, fuentes, guion, importar, investigacion, miniaturas, referencias, render,
               subtitulos, tendencias, visuales_api, voz, youtube)

logger = logging.getLogger("studio4.produccion")
_lock = threading.RLock()
_ACTIVA = config.PRODUCCIONES / "activa.txt"


# --- Disco ------------------------------------------------------------------------------------
def carpeta(pid: str) -> Path:
    if not re.fullmatch(r"[\w-]+", pid or ""):
        raise ValueError("Identificador de producción no válido")
    return config.PRODUCCIONES / pid


def cargar(pid: str) -> dict[str, Any]:
    with _lock:
        p = json.loads((carpeta(pid) / "proyecto.json").read_text(encoding="utf-8"))
    # Producciones de antes del paso «Guion»: si ya tenían escenas, su guion cuenta como aprobado.
    p.setdefault("guion_aprobado", bool(p.get("escenas")))
    for campo, vacio in (("version", ""), ("familia", ""), ("investigacion", None), ("ganchos", []),
                         ("avisos", []), ("autor_guion", "")):
        p.setdefault(campo, vacio)
    p.setdefault("canal", canales.listar()[0]["id"])   # las de antes de los canales son del primero
    if p.get("escenas") and any("segundos" not in e for e in p["escenas"]):   # de antes de las duraciones por escena
        tiempos = (p.get("voz") or {}).get("escenas") or []
        if len(tiempos) == len(p["escenas"]):
            director.poner_duraciones(p["escenas"], tiempos, p.get("biblia") or {}, p.get("estilo_en", ""),
                                      config.FORMATOS[p["formato"]]["aspecto"])
        else:
            for e in p["escenas"]:
                e.setdefault("segundos", round(len(e["texto_voz"].split()) / guion.PALABRAS_POR_SEGUNDO, 1))
    if p.get("escenas") and p.get("biblia"):
        aspecto = config.FORMATOS[p["formato"]]["aspecto"]
        for e in p["escenas"]:
            if not e.get("prompt_editado") and e.get("plano_en") and e.get("accion_en"):
                e["prompt_flow"] = director._prompt_flow(e, p["biblia"], p.get("estilo_en", ""), aspecto)
        p["fichas"] = director.fichas(p["biblia"], p.get("estilo_en", ""))
    return p


def guardar(p: dict[str, Any]) -> None:
    with _lock:
        p["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
        destino = carpeta(p["id"]) / "proyecto.json"
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(destino)


def modificar(pid: str, cambio: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Lee, aplica `cambio` y guarda de forma atómica (los hilos de fondo y el servidor escriben a la vez)."""
    with _lock:
        p = cargar(pid)
        cambio(p)
        guardar(p)
        return p


def activa() -> Optional[str]:
    """La producción abierta, siempre del canal activo (al cambiar de canal se abre la última de ese canal)."""
    canal = canales.activo()["id"]
    try:
        pid = _ACTIVA.read_text(encoding="utf-8").strip()
        if (carpeta(pid) / "proyecto.json").exists() and cargar(pid)["canal"] == canal:
            return pid
    except (OSError, ValueError):
        pass
    del_canal = listar(canal)
    return del_canal[0]["id"] if del_canal else None


def activar(pid: str) -> None:
    carpeta(pid)
    _ACTIVA.write_text(pid, encoding="utf-8")


def listar(canal: str | None = None) -> list[dict[str, Any]]:
    """Las producciones, de la más nueva a la más vieja; con `canal`, solo las de ese canal."""
    primero = canales.listar()[0]["id"]
    salida = []
    for f in sorted(config.PRODUCCIONES.glob("*/proyecto.json"), reverse=True):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            salida.append({"id": p["id"], "tema": p["tema"], "titulo": p.get("titulo", ""), "estado": p["estado"],
                           "creado": p["creado"], "formato": p["formato"], "version": p.get("version", ""),
                           "familia": p.get("familia", ""), "canal": p.get("canal") or primero,
                           "portada": _portada(p), "escenas": len(p.get("escenas", [])),
                           "con_clip": sum(e.get("elegida") is not None for e in p.get("escenas", []))})
        except (OSError, ValueError, KeyError):
            continue
    return [x for x in salida if canal is None or x["canal"] == canal]


def _portada(p: dict[str, Any]) -> str:
    """Una imagen para la tarjeta de la producción: su miniatura elegida o la primera toma en imagen."""
    m = p.get("miniaturas") or {}
    if m.get("candidatos"):
        return m["candidatos"][m.get("elegido", 0)]["archivo"]
    for e in p.get("escenas", []):
        for t in e.get("tomas", []):
            if t.get("tipo") == "imagen":
                return t["archivo"]
    return ""


def recuperar_trabajos_colgados() -> int:
    """Al arrancar, ninguna fase puede estar en marcha: si el servidor se cerró a mitad, se libera."""
    n = 0
    for f in config.PRODUCCIONES.glob("*/proyecto.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = p.get("trabajo") or {}
        if t.get("error") and not t.get("ocupado") and "reintentable" not in t:   # errores de antes: frase clara
            t.update(error=_error_legible(t.get("nombre", ""), RuntimeError(t["error"])), reintentable=True)
            guardar(p)
        if p.get("trabajo", {}).get("ocupado"):
            p["trabajo"].update(ocupado=False, error=f"Se interrumpió «{p['trabajo'].get('fase', '')}» al cerrar STUDIO: vuelve a lanzarlo.")
            if p.get("estado") in ("investigando", "escribiendo", "escenas", "renderizando"):
                p["estado"] = "rodando" if p.get("escenas") else ("guion_listo" if p.get("guion") else "error")
            guardar(p)
            n += 1
    return n


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "video"


# --- Trabajos en segundo plano ------------------------------------------------------------------
def _avisar(pid: str | list[str], fase: str, progreso: int) -> None:
    for uno in [pid] if isinstance(pid, str) else pid:
        modificar(uno, lambda p: p["trabajo"].update(fase=fase, progreso=progreso))


# Lo que ve la persona cuando un trabajo falla: qué no se pudo hacer, sin jerga ni nombres de servicios.
# El detalle técnico queda en el registro del servidor.
_QUE_FALLO = {
    "Investigación y guion": "No se pudo escribir el guion",
    "Guion": "No se pudo escribir la otra versión del guion",
    "Escenas y voz": "No se pudieron crear las escenas y la voz",
    "Voz": "No se pudo grabar la voz",
    "Muestras de voz": "No se pudieron grabar las muestras de voz",
    "Render": "No se pudo montar el vídeo",
    "Entregas": "No se pudieron preparar los 3 formatos",
    "Vídeo o imagen": "No se pudo decidir qué escenas van en vídeo o imagen",
    "Miniaturas": "No se pudieron crear las miniaturas",
    "Imágenes por API": "No se pudieron generar las escenas",
    "Personajes": "No se pudieron afinar los personajes",
    "Importar vídeo": "No se pudo importar el vídeo",
}


def _error_legible(nombre: str, e: Exception) -> str:
    texto = str(e)
    motivo = ("el servicio está saturado o sin conexión; suele bastar con esperar un minuto"
              if any(k in texto for k in ("429", "503", "ocupado", "Timeout", "timed out", "Connection", "no respondió", "vacía", "cortada"))
              else "")
    if "facturación" in texto or "presupuesto" in texto.lower() or "ya van" in texto:
        return texto   # sin facturación o tope alcanzado: el motivo exacto es lo útil
    if isinstance(e, ValueError) and len(texto) < 160 and "Expecting" not in texto:
        return texto   # los ValueError propios ya están escritos para la persona («Primero renderiza…»)
    return f"{_QUE_FALLO.get(nombre, f'No se pudo completar «{nombre}»')}{f': {motivo}' if motivo else ''}. Pulsa «Reintentar»."


def _en_fondo(pid: str | list[str], nombre: str, fn: Callable[[], None]) -> None:
    """Lanza `fn` en un hilo. Con varias producciones (corto y largo de la misma idea), todas quedan ocupadas."""
    pids = [pid] if isinstance(pid, str) else pid

    def correr():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - el error se muestra en el panel
            logger.exception("%s falló", nombre)
            for uno in pids:
                modificar(uno, lambda p: p["trabajo"].update(ocupado=False, error=_error_legible(nombre, e), fase=nombre,
                                                             reintentable=True))
        else:
            for uno in pids:
                modificar(uno, lambda p: p["trabajo"].update(ocupado=False, error="", progreso=100, reintentable=False))

    with _lock:
        for uno in pids:
            p = cargar(uno)
            if p["trabajo"].get("ocupado"):
                raise RuntimeError(f"Esta producción está ocupada: {p['trabajo'].get('fase')}")
        for uno in pids:
            p = cargar(uno)
            p["trabajo"] = {"ocupado": True, "nombre": nombre, "fase": nombre, "progreso": 0, "error": ""}
            guardar(p)
    threading.Thread(target=correr, name=f"studio4-{nombre}", daemon=True).start()


# --- Fases ------------------------------------------------------------------------------------
def _nueva(pid: str, **campos: Any) -> dict[str, Any]:
    carpeta(pid).mkdir(parents=True)
    p = {
        "id": pid, "creado": time.strftime("%Y-%m-%d %H:%M:%S"), "tema": "", "segundos": 0, "formato": "vertical",
        "version": "", "familia": "", "estilo": "cinematografico", "proveedor_voz": "gemini", "estado": "guion_listo",
        "trabajo": {}, "investigacion": None, "guion": "", "ganchos": [], "autor_guion": "", "guion_aprobado": False,
        "titulo": "", "descripcion": "", "hashtags": [], "biblia": {}, "avisos": [],
        "escenas": [], "escena_activa": 1, "voz": None, "subtitulos": dict(subtitulos.POR_DEFECTO), "final": None,
        "miniaturas": None, "recoger_para": "escenas", "canal": canales.activo()["id"],
    }
    p.update(campos)
    guardar(p)
    return p


def crear(idea: str, versiones: list[str], estilo: str, proveedor_voz: str,
          segundos: dict[str, int] | None = None, guion_propio: str = "", formato_propio: str = "vertical",
          tono: str = "", publico: str = "", voz_nombre: str = "", refs: dict[str, Any] | None = None,
          reparto: list[dict[str, str]] | None = None) -> list[str]:
    """Desde una idea: una producción por versión (corto y/o largo), investigadas y escritas juntas.
    Con tu guion: una sola producción, con tu texto tal cual, lista para aprobar."""
    if proveedor_voz not in voz.PROVEEDORES:
        raise ValueError(f"Voz desconocida: {proveedor_voz}")
    sello = time.strftime("%Y%m%d-%H%M%S")
    voz_nombre = voz_nombre if voz_nombre in config.VOCES_GEMINI else config.VOZ_GEMINI
    if guion_propio.strip():
        if formato_propio not in config.FORMATOS:
            raise ValueError(f"Formato desconocido: {formato_propio}")
        texto = " ".join(guion_propio.split())
        pid = f"{sello}-{_slug(idea or texto[:40])}"
        _nueva(pid, tema=idea.strip() or texto[:80], formato=formato_propio, estilo=estilo, proveedor_voz=proveedor_voz,
               voz_nombre=voz_nombre,
               version="propio", guion=texto, autor_guion="Tú", reparto=list(reparto or [])[:6],
               segundos=int(len(texto.split()) / guion.PALABRAS_POR_SEGUNDO))
        _guardar_referencias([pid], refs)
        activar(pid)
        return [pid]

    tono = tono or canales.activo().get("tono", "")   # sin elegir: el del canal, o el que pida el tema
    versiones = [v for v in config.VERSIONES if v in versiones]
    if not versiones:
        raise ValueError("Elige al menos una versión: corto o largo.")
    segundos = {v: int((segundos or {}).get(v) or config.VERSIONES[v]["segundos"]) for v in versiones}
    pids = []
    for v in versiones:
        pid = f"{sello}-{v}-{_slug(idea)}"
        _nueva(pid, tema=idea.strip(), formato=config.VERSIONES[v]["formato"], version=v, familia=sello,
               estilo=estilo, proveedor_voz=proveedor_voz, segundos=segundos[v], estado="investigando", voz_nombre=voz_nombre,
               tono=tono.strip()[:80], publico=publico.strip()[:80])
        pids.append(pid)
    _guardar_referencias(pids, refs)
    activar(pids[0])
    _en_fondo(pids, "Investigación y guion", lambda: _investigar_y_escribir(pids, idea, segundos))
    return pids


def crear_rapido(idea: str, version: str = "corto") -> list[str]:
    """Un clic: la idea pasa a producción con lo de siempre del canal (su voz, su estilo y su tono) y la duración
    por defecto. Lo demás se puede cambiar después, al revisar el guion."""
    if len(idea.strip()) < 3:
        raise ValueError("Falta la idea.")
    if version not in config.VERSIONES:
        raise ValueError(f"Versión desconocida: {version}")
    c = canales.activo()
    return crear(idea.strip(), [version], c.get("estilo") or "cinematografico", "gemini",
                 tono=c.get("tono", ""), publico=c.get("publico", ""), voz_nombre=c.get("voz_nombre", ""))


def importar_video(url: str = "", archivo: Path | None = None, nombre: str = "") -> str:
    """Un vídeo ya hecho (enlace o archivo) pasa a ser una producción: escenas con su texto y su trozo de vídeo,
    lista para revisar, renderizar con subtítulos y sacar los 3 formatos."""
    if not url and not archivo:
        raise ValueError("Pega el enlace del vídeo o sube el archivo.")
    titulo = nombre.rsplit(".", 1)[0] if nombre else "Vídeo importado"
    pid = f"{time.strftime('%Y%m%d-%H%M%S')}-importado-{_slug(titulo if not url else 'video')}"
    _nueva(pid, tema=titulo, version="importado", estado="importando", guion_aprobado=True, autor_guion="Vídeo original",
           subtitulos={**subtitulos.POR_DEFECTO, "sonidos": False}, origen={"url": url, "archivo": nombre})
    if archivo:
        importar.subida_a_origen(archivo, carpeta(pid))
    activar(pid)

    def fase():
        datos = {}
        if url:
            _avisar(pid, "Leyendo el enlace", 3)
            datos = importar.descargar(url, carpeta(pid), lambda f: _avisar(pid, f, 8))
        campos = importar.preparar(carpeta(pid), lambda f, n: _avisar(pid, f, n))
        modificar(pid, lambda q: q.update(**campos, estado="rodando", titulo=datos.get("titulo") or q["tema"],
                                          tema=datos.get("titulo") or q["tema"],
                                          origen={**q["origen"], **{k: datos[k] for k in ("canal",) if k in datos}}))
        preparar_carpeta(pid)
    _en_fondo(pid, "Importar vídeo", fase)
    return pid


def _guardar_referencias(pids: list[str], refs: dict[str, Any] | None) -> None:
    if not refs or not (refs["items"] or refs["enlaces"] or refs["datos"]):
        return
    for pid in pids:
        modificar(pid, lambda p: p.update(referencias={**refs, "items": referencias.copiar_a(carpeta(pid), refs["items"])}))
    referencias.soltar_espera(refs["items"])


def _material(pids: list[str]) -> dict[str, Any] | None:
    """Gemini estudia las referencias una sola vez (corto y largo comparten el resultado)."""
    r = cargar(pids[0]).get("referencias")
    if not r or r.get("material") is not None:
        return r
    _avisar(pids, "Estudiando tus referencias", 5)
    material = referencias.estudiar(carpeta(pids[0]), r, produccion=pids[0])
    for pid in pids:
        modificar(pid, lambda p: p["referencias"].update(material=material))
    return cargar(pids[0])["referencias"]


def _investigar_y_escribir(pids: list[str], idea: str, segundos: dict[str, int], dossier: dict | None = None) -> None:
    refs = _material(pids)
    if dossier is None:
        _avisar(pids, "Investigando el tema", 10)
        dossier = investigacion.investigar(idea, produccion=pids[0])
        propias = canales.de_produccion(cargar(pids[0])).get("fuentes") or []
        if propias:   # las webs de confianza del canal: datos de primera mano, por delante de lo general
            _avisar(pids, "Leyendo tus fuentes de confianza", 28)
            try:
                extra = fuentes.investigar(idea, propias, produccion=pids[0])
            except Exception as e:  # noqa: BLE001 - sin fuentes el guion sale igual
                logger.warning("Fuentes del canal: %s", e)
                extra = {"texto": "", "fuentes": []}
            if extra["texto"]:
                dossier["dossier"] = (f"DE TUS FUENTES DE CONFIANZA (datos de primera mano):\n{extra['texto']}\n\n"
                                      + dossier.get("dossier", ""))
                dossier["fuentes"] = extra["fuentes"] + list(dossier.get("fuentes") or [])
    if youtube.disponible() and not dossier.get("youtube"):   # también al reescribir con una investigación vieja
        _avisar(pids, "Mirando qué hay en YouTube y qué funciona en tu canal", 35)
        usuario = canales.de_produccion(cargar(pids[0]))["redes"].get("youtube") or config.YOUTUBE_CANAL
        dossier["youtube"] = youtube.contexto_para_guion(idea, usuario)
    if t := tendencias.para_guion(cargar(pids[0])["canal"]):   # pautas del día del canal, si ya se pidieron
        dossier.setdefault("youtube", {})["tendencias"] = t
    for pid in pids:
        modificar(pid, lambda p: p.update(investigacion=dossier, estado="escribiendo"))
    _avisar(pids, "Escribiendo el guion", 45)
    versiones = {cargar(pid)["version"]: segundos[cargar(pid)["version"]] for pid in pids}
    p0 = cargar(pids[0])
    escrito = guion.escribir(idea, dossier.get("dossier", ""), versiones, produccion=pids[0],
                             tono=p0.get("tono", ""), publico=p0.get("publico", ""), youtube=dossier.get("youtube"),
                             referencias=referencias.para_guion(refs))
    for pid in pids:
        v = cargar(pid)["version"]
        modificar(pid, lambda p: p.update(
            guion=escrito[v]["guion"], ganchos=escrito[v]["ganchos"], autor_guion=escrito["autor"], reparto=escrito["reparto"],
            titulo=p.get("titulo") or escrito["titulo_provisional"], estado="guion_listo", guion_aprobado=False))


def eliminar(pid: str) -> None:
    """Quita una producción del estudio: deja de estar abierta, de verse y de recibir clips de Flow o de la carpeta.
    Sus datos van a producciones/_papelera (por si fue sin querer); tus archivos en Vídeos\\STUDIO 4 no se tocan."""
    p = cargar(pid)
    if p["trabajo"].get("ocupado"):
        raise ValueError("Esta producción está trabajando: espera a que termine para eliminarla.")
    with _lock:
        papelera = config.PRODUCCIONES / "_papelera"
        papelera.mkdir(exist_ok=True)
        destino = papelera / pid
        if destino.exists():
            shutil.rmtree(destino)
        shutil.move(str(carpeta(pid)), str(destino))
        try:
            if _ACTIVA.read_text(encoding="utf-8").strip() == pid:
                _ACTIVA.unlink()   # sin abierta: el panel abre la siguiente del canal o empieza de cero
        except OSError:
            pass


def reintentar(pid: str) -> None:
    """Vuelve a lanzar el último trabajo que falló, con lo que ya se tenía (no repite lo que salió bien)."""
    p = cargar(pid)
    t = p.get("trabajo") or {}
    if t.get("ocupado"):
        raise ValueError("Esta producción ya está trabajando.")
    if not t.get("error"):
        raise ValueError("No hay nada que reintentar.")
    nombre = t.get("nombre", "")
    if nombre in ("Investigación y guion", "Guion"):
        # Corto y largo de la misma idea fallan juntos: se reintentan juntos, aprovechando la investigación si ya estaba.
        pids = [x["id"] for x in listar() if p.get("familia") and x["familia"] == p["familia"]
                and not cargar(x["id"]).get("guion")] or [pid]
        segundos = {cargar(x)["version"]: cargar(x)["segundos"] for x in pids}
        _en_fondo(pids, nombre, lambda: _investigar_y_escribir(pids, p["tema"], segundos, dossier=p.get("investigacion")))
    elif nombre == "Escenas y voz" and p.get("escenas"):
        _en_fondo(pid, "Voz", lambda: _generar_voz(pid))   # las escenas ya estaban: falta solo la voz
    elif nombre == "Escenas y voz":
        aprobar_guion(pid)
    elif nombre == "Voz":
        _en_fondo(pid, "Voz", lambda: _generar_voz(pid))
    elif nombre == "Render":
        renderizar(pid)
    elif nombre == "Entregas":
        preparar_entregas(pid)
    elif nombre == "Miniaturas":
        generar_miniaturas(pid)
    elif nombre == "Vídeo o imagen":
        recomendar_tipos(pid)
    else:
        raise ValueError("Ese paso se relanza desde su propio botón.")


def afinar_personajes(pid: str) -> None:
    """Fichas de personaje más precisas para una producción ya planificada (no toca escenas ni clips)."""
    p = cargar(pid)
    if not (p.get("biblia") or {}).get("personajes"):
        raise ValueError("Esta producción no tiene personajes.")

    def fase():
        _avisar(pid, "Afinando los personajes", 30)
        nuevos = director.afinar_personajes(p["guion"], p["biblia"], p.get("reparto"), produccion=pid)
        modificar(pid, lambda q: q["biblia"].update(personajes=nuevos))
    _en_fondo(pid, "Personajes", fase)


def reescribir_guion(pid: str) -> None:
    """Otra versión del guion con la misma investigación (no vuelve a buscar en Google)."""
    p = cargar(pid)
    if p.get("version") not in config.VERSIONES:
        raise ValueError("Este guion es tuyo: edítalo directamente.")
    if any(e["tomas"] for e in p["escenas"]):
        raise ValueError("Ya hay clips de Flow en esta producción: reescribir el guion los dejaría sin sentido.")
    _en_fondo(pid, "Guion", lambda: _investigar_y_escribir([pid], p["tema"], {p["version"]: p["segundos"]},
                                                           dossier=p.get("investigacion")))


def guardar_guion(pid: str, texto: str) -> None:
    texto = " ".join(str(texto).split())
    if len(texto.split()) < 10:
        raise ValueError("El guion es demasiado corto.")

    def cambio(p):
        if p.get("guion_aprobado"):
            raise ValueError("El guion ya está aprobado y tiene escenas: usa «Rehacer escenas» para cambiarlo.")
        p["guion"] = texto
    modificar(pid, cambio)


def reabrir_guion(pid: str, forzar: bool = False) -> None:
    """Vuelve a dejar el guion editable. Las escenas siguen ahí hasta que lo apruebes otra vez."""
    p = cargar(pid)
    if p["trabajo"].get("ocupado"):
        raise RuntimeError("Espera a que termine la fase en curso.")
    if any(e["tomas"] for e in p["escenas"]) and not forzar:
        raise ValueError("Esta producción ya tiene clips de Flow: cambiar el guion obligará a rehacer las escenas.")
    modificar(pid, lambda q: q.update(guion_aprobado=False, estado="guion_listo"))


def aprobar_guion(pid: str, texto: str | None = None, forzar: bool = False) -> None:
    """Tu guion aprobado pasa a Gemini, que lo convierte en escenas para Flow; luego se graba la voz."""
    p = cargar(pid)
    if texto is not None:
        p["guion"] = " ".join(str(texto).split())
    if len(p["guion"].split()) < 10:
        raise ValueError("Escribe o genera el guion antes de aprobarlo.")
    if any(e["tomas"] for e in p["escenas"]) and not forzar:
        raise ValueError("Esta producción ya tiene clips de Flow: rehacer las escenas los descarta.")
    modificar(pid, lambda q: q.update(guion=p["guion"], guion_aprobado=True, estado="escenas", escenas=[], voz=None,
                                      final=None, miniaturas=None, avisos=[]))

    def fases():
        refs = _material([pid])   # con tu propio guion, las referencias se estudian aquí
        _avisar(pid, "Creando las escenas para Flow", 20)
        q = cargar(pid)
        competencia = ((q.get("investigacion") or {}).get("youtube") or {}).get("competencia") or []
        plan = director.planificar(q["guion"], q["estilo"], q["formato"], produccion=pid,
                                   titulos_existentes=[v["titulo"] for v in competencia],
                                   referencias_visuales=referencias.visuales(refs), reparto=q.get("reparto") or [])

        def aplicar(r):
            r.update(titulo=plan["titulo"], descripcion=plan["descripcion"], hashtags=plan["hashtags"],
                     biblia=plan["biblia"], estilo_en=plan["estilo_en"], avisos=plan.get("avisos", []),
                     estado="rodando", escena_activa=1, recoger_para="escenas")
            r["escenas"] = [{**e, "tomas": [], "elegida": None} for e in plan["escenas"]]
        modificar(pid, aplicar)
        preparar_carpeta(pid)
        _generar_voz(pid)

    _en_fondo(pid, "Escenas y voz", fases)


def _generar_voz(pid: str) -> None:
    p = cargar(pid)
    _avisar(pid, f"Locución con {voz.PROVEEDORES[p['proveedor_voz']]}", 70)
    segmentos = [e["texto_voz"] for e in p["escenas"]]
    direcciones = [{"tono": e.get("tono_voz", "narrativo"), "ritmo": e.get("ritmo_voz", "normal")} for e in p["escenas"]]
    try:
        tiempos = voz.locutar(segmentos, carpeta(pid) / "voz.wav", p["proveedor_voz"], produccion=pid,
                              direcciones=direcciones, voz_nombre=p.get("voz_nombre"))
    except RuntimeError as e:
        # Cupo diario de Gemini TTS agotado (o ElevenLabs sin créditos): se prueba con la otra voz si existe.
        otra = voz.reserva(p["proveedor_voz"])
        if not otra:
            raise
        logger.warning("Voz %s falló (%s); probando %s", p["proveedor_voz"], e, otra)
        _avisar(pid, f"{voz.PROVEEDORES[p['proveedor_voz']]} falló; uso {voz.PROVEEDORES[otra]}", 75)
        tiempos = voz.locutar(segmentos, carpeta(pid) / "voz.wav", otra, produccion=pid, direcciones=direcciones,
                              voz_nombre=p.get("voz_nombre"))
    def con_voz(q):
        q.update(voz={**tiempos, "archivo": "voz.wav", "generada": time.strftime("%H:%M:%S")})
        director.poner_duraciones(q["escenas"], tiempos["escenas"], q.get("biblia") or {}, q.get("estilo_en", ""),
                                  config.FORMATOS[q["formato"]]["aspecto"])
    modificar(pid, con_voz)


def muestras_voz(pid: str, voces: list[str]) -> None:
    """Graba el arranque del guion con 1 a 3 voces para escucharlas y elegir."""
    voces = [v for v in dict.fromkeys(voces) if v in config.VOCES_GEMINI][:3]
    if not voces:
        raise ValueError("Elige de 1 a 3 voces.")
    p = cargar(pid)
    texto = " ".join(" ".join(e["texto_voz"] for e in p["escenas"][:3]).split()[:40]) if p["escenas"] else p["guion"][:260]
    if not texto:
        raise ValueError("Hace falta el guion para grabar las muestras.")

    def fase():
        hechas = []
        for i, v in enumerate(voces):
            _avisar(pid, f"Grabando la muestra con la voz {v}", 10 + 80 * i // len(voces))
            archivo = carpeta(pid) / "muestras" / f"{v}.wav"
            voz.muestra(texto, v, archivo, produccion=pid)
            hechas.append({"voz": v, "descripcion": config.VOCES_GEMINI[v], "archivo": f"muestras/{v}.wav",
                           "generada": time.strftime("%H%M%S")})
        modificar(pid, lambda q: q.update(muestras_voz=hechas))
    _en_fondo(pid, "Muestras de voz", fase)


def elegir_voz(pid: str, voz_nombre: str) -> None:
    """Fija la voz elegida y vuelve a grabar la locución completa con ella."""
    if voz_nombre not in config.VOCES_GEMINI:
        raise ValueError(f"Voz desconocida: {voz_nombre}")
    modificar(pid, lambda p: p.update(voz_nombre=voz_nombre, proveedor_voz="gemini"))
    if cargar(pid)["escenas"]:
        _en_fondo(pid, "Voz", lambda: _generar_voz(pid))


def rehacer_voz(pid: str, proveedor: str) -> None:
    if proveedor not in voz.PROVEEDORES:
        raise ValueError(f"Voz desconocida: {proveedor}")
    modificar(pid, lambda p: p.update(proveedor_voz=proveedor))
    _en_fondo(pid, "Voz", lambda: _generar_voz(pid))


def renderizar(pid: str) -> None:
    def fase():
        p = cargar(pid)
        modificar(pid, lambda q: q.update(estado="renderizando"))
        try:
            final = render.renderizar(p, carpeta(pid), avisar=lambda f, n: _avisar(pid, f, n))
        except Exception:
            modificar(pid, lambda q: q.update(estado="rodando"))
            raise
        modificar(pid, lambda q: q.update(estado="terminado", final={
            "archivo": final.name, "renderizado": time.strftime("%Y-%m-%d %H:%M:%S")}))
        # Siempre se entregan los 3 formatos: completo, Reels y Shorts, sin pulsar nada más.
        _avisar(pid, "Preparando Reels y Shorts para publicar", 92)
        try:
            res = entregas.preparar(cargar(pid), carpeta(pid), avisar=lambda f, n: _avisar(pid, f, 92 + n // 13))
            modificar(pid, lambda q: q.update(entregas=res, entregas_error=""))
        except Exception as e:  # noqa: BLE001 - el vídeo completo ya está hecho; los recortes se pueden repetir
            logger.exception("Entregas tras el render")
            modificar(pid, lambda q: q.update(entregas_error=str(e)))
    _en_fondo(pid, "Render", fase)


# --- Carpeta de la producción en tu PC -------------------------------------------------------------
def preparar_carpeta(pid: str) -> Path:
    p = cargar(pid)
    base = carpetas.preparar(p)
    if p.get("carpeta") != str(base):
        modificar(pid, lambda q: q.update(carpeta=str(base)))
    return base


def importar_carpeta(pid: str) -> int:
    """Clips nuevos en «1 Clips de Flow» → a su escena. Lo llama el vigilante del servidor cada pocos segundos."""
    from . import flow
    p = cargar(pid)
    if not p.get("guion_aprobado") or not p.get("escenas") or p["trabajo"].get("ocupado"):
        return 0
    if (not p.get("carpeta") or carpetas.ruta(p) != Path(p["carpeta"])
            or not (Path(p["carpeta"]) / carpetas.subcarpeta(p, carpetas.CLIPS)).is_dir()):
        preparar_carpeta(pid)   # crea la carpeta o la pone al día (nombres con el título del vídeo)
        p = cargar(pid)
    nuevas = carpetas.importar(p, lambda archivo, mime, orden: flow.recibir(archivo, mime, pista=orden, origen="carpeta"))
    if nuevas:
        modificar(pid, lambda q: q.update(importados=[*q.get("importados", []), *nuevas]))
    return len(nuevas)


# --- Entregas: vídeo completo, Reels y Shorts --------------------------------------------------------
def preparar_entregas(pid: str) -> None:
    if not cargar(pid).get("final"):
        raise ValueError("Primero renderiza el vídeo completo (pestaña Render).")

    def fase():
        res = entregas.preparar(cargar(pid), carpeta(pid), avisar=lambda f, n: _avisar(pid, f, n))
        modificar(pid, lambda q: q.update(entregas=res))
    _en_fondo(pid, "Entregas", fase)


def recomendar_tipos(pid: str) -> None:
    """Vídeo o imagen por escena para producciones creadas antes de esta recomendación."""
    def fase():
        p = cargar(pid)
        escenas = p["escenas"]
        _avisar(pid, "Decidiendo qué escenas van en vídeo y cuáles en imagen", 30)
        director.recomendar_tipos(escenas, p.get("biblia") or {}, p.get("estilo_en", ""),
                                  config.FORMATOS[p["formato"]]["aspecto"], produccion=pid)
        modificar(pid, lambda q: q.update(escenas=[{**viejo, **{k: nuevo[k] for k in ("tipo_clip", "motivo_tipo", "prompt_flow")}}
                                                   for viejo, nuevo in zip(q["escenas"], escenas)]))
    _en_fondo(pid, "Vídeo o imagen", fase)


# --- Imágenes y vídeo por la API de Google (de pago, con presupuesto) ---------------------------
def estimar_visuales_api(pid: str) -> dict[str, Any]:
    p = cargar(pid)
    return visuales_api.estimar(p["escenas"], personajes=len(p.get("fichas") or []))


def generar_visuales_api(pid: str, limite_usd: float, con_video: list[int] | None = None, solo_imagenes: bool = False) -> None:
    """Rellena TODAS las escenas sin clip de una vez: retratos de los personajes, una imagen por escena y vídeo Veo
    en las que el plan marcó como vídeo (salvo `solo_imagenes`). Nunca pasa de `limite_usd`."""
    from . import flow
    p = cargar(pid)
    if not p["escenas"]:
        raise ValueError("Primero aprueba el guion: hacen falta las escenas.")
    aspecto = config.FORMATOS[p["formato"]]["aspecto"]
    presupuesto = visuales_api.Presupuesto(limite_usd)

    if con_video is None:
        con_video = [] if solo_imagenes else [e["orden"] for e in p["escenas"] if e.get("tipo_clip") == "video"]

    def fase():
        res = visuales_api.generar_escenas(
            cargar(pid)["escenas"], aspecto, presupuesto,
            recibir=lambda archivo, mime, orden: flow.recibir(archivo, mime, pista=orden, origen="api"),
            con_video=set(con_video), produccion=pid, avisar=lambda f, n: _avisar(pid, f, n),
            fichas=cargar(pid).get("fichas"), retratos=carpeta(pid) / "retratos")
        modificar(pid, lambda q: q.update(gasto_api=round(q.get("gasto_api", 0.0) + res["gastado"], 4)))
    _en_fondo(pid, "Imágenes por API", fase)


# --- Miniaturas --------------------------------------------------------------------------------
def generar_miniaturas(pid: str) -> None:
    def fase():
        p = cargar(pid)
        base = carpeta(pid)
        _avisar(pid, "Sacando fotogramas de tus clips", 15)
        candidatos = miniaturas.extraer_candidatos(p, base)
        # Las imágenes que subiste o generaste en Flow para la miniatura siguen siendo candidatas.
        previas = [c for c in (p.get("miniaturas") or {}).get("candidatos", []) if c.get("origen")]
        candidatos += [c for c in previas if (base / c["archivo"]).exists()]
        _avisar(pid, "Eligiendo el fotograma y el texto", 45)
        e = miniaturas.analizar(p, base, candidatos)
        _avisar(pid, "Componiendo las miniaturas", 85)

        def aplicar(q):
            q["miniaturas"] = {"candidatos": candidatos, "elegido": e["mejor"], "texto": e["texto"],
                               "resalte": e["resalte"], "alternativas": e["alternativas"],
                               "prompt_flow": e["prompt_flow_en"], "foco_x": e["foco_x"], "foco_y": e["foco_y"]}
            miniaturas.componer_todas(q, base)
        modificar(pid, aplicar)
    _en_fondo(pid, "Miniaturas", fase)


def ajustar_miniatura(pid: str, datos: dict[str, Any]) -> dict[str, Any]:
    def cambio(p):
        m = p.get("miniaturas")
        if not m:
            raise ValueError("Primero genera las miniaturas")
        if "elegido" in datos:
            i = int(datos["elegido"])
            if not 0 <= i < len(m["candidatos"]):
                raise ValueError("Esa imagen no existe")
            if i != m["elegido"]:
                m.update(elegido=i, foco_x=0.5, foco_y=0.5)
        if "texto" in datos:
            m["texto"] = " ".join(str(datos["texto"]).split())[:60]
        if "resalte" in datos:
            m["resalte"] = str(datos["resalte"]).strip()[:30]
        for k in ("foco_x", "foco_y"):
            if k in datos:
                m[k] = min(max(float(datos[k]), 0.0), 1.0)
        miniaturas.componer_todas(p, carpeta(pid))
    return modificar(pid, cambio)


def anadir_fuente_miniatura(pid: str, archivo: str, origen: str) -> None:
    """Una imagen subida o generada en Flow para la miniatura: pasa a ser la elegida."""
    def cambio(p):
        m = p.get("miniaturas") or {"candidatos": [], "texto": " ".join((p.get("titulo") or p["tema"]).split()[:3]),
                                    "resalte": "", "alternativas": [], "prompt_flow": ""}
        m["candidatos"].append({"archivo": archivo, "escena": 0, "origen": origen})
        m.update(elegido=len(m["candidatos"]) - 1, foco_x=0.5, foco_y=0.5)
        p["miniaturas"] = m
        miniaturas.componer_todas(p, carpeta(pid))
    modificar(pid, cambio)


# --- Ediciones desde el panel -------------------------------------------------------------------
def editar_escena(pid: str, orden: int, datos: dict[str, Any]) -> dict[str, Any]:
    def cambio(p):
        if not 1 <= orden <= len(p["escenas"]):
            raise ValueError(f"No existe la escena {orden}")
        esc = p["escenas"][orden - 1]
        if "prompt_flow" in datos:
            esc["prompt_flow"] = str(datos["prompt_flow"]).strip()
            esc["prompt_editado"] = True   # tu versión manda: ya no se reescribe sola
        if "texto_pantalla" in datos:
            esc["texto_pantalla"] = str(datos["texto_pantalla"]).strip()[:60]
        if "texto_voz" in datos and str(datos["texto_voz"]).strip() != esc["texto_voz"]:
            esc["texto_voz"] = " ".join(str(datos["texto_voz"]).split())
            if p.get("version") == "importado" and p.get("voz"):
                # Vídeo importado: el audio es el original; solo cambian los subtítulos de esa escena.
                t = p["voz"]["escenas"][orden - 1]
                p["voz"]["palabras"] = importar.retemporizar(p["voz"]["palabras"], t["ini"], t["fin"], esc["texto_voz"])
                p["guion"] = " ".join(e["texto_voz"] for e in p["escenas"])
                p["final"] = None
            else:
                p["voz"] = None  # la locución ya no corresponde: hay que rehacerla
        if "elegida" in datos:
            i = int(datos["elegida"])
            if not 0 <= i < len(esc["tomas"]):
                raise ValueError("Esa toma no existe")
            esc["elegida"] = i
        if "borrar_toma" in datos:
            i = int(datos["borrar_toma"])
            if not 0 <= i < len(esc["tomas"]):
                raise ValueError("Esa toma no existe")
            toma = esc["tomas"].pop(i)
            (carpeta(pid) / toma["archivo"]).unlink(missing_ok=True)
            if esc["elegida"] is not None:
                esc["elegida"] = None if not esc["tomas"] else min(esc["elegida"] - (esc["elegida"] > i), len(esc["tomas"]) - 1)
    return modificar(pid, cambio)


def ajustar_subtitulos(pid: str, ajustes: dict[str, Any]) -> dict[str, Any]:
    validos = {k: v for k, v in ajustes.items() if k in subtitulos.POR_DEFECTO}
    if validos.get("estilo", "viral") not in subtitulos.ESTILOS:
        raise ValueError("Estilo de subtítulos desconocido.")
    if "sonidos" in validos:
        validos["sonidos"] = bool(validos["sonidos"])
    return modificar(pid, lambda p: p["subtitulos"].update(validos))
