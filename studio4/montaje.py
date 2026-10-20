"""Montaje 16:9 con material real: el flujo con el que se hizo el primer vídeo, en 5 pasos y en orden.

1. GUION     el guion del autor (o de la Biblioteca) se parte en bloques (párrafos) y frases.
2. MATERIAL  enlaces de fuentes seguras (tráilers oficiales, gameplay sin comentario): se bajan en BAJA calidad
             solo para ver sus planos; el banco de clips guarda todo para otros vídeos.
3. MONTAJE   cada frase lleva un plano (Studio propone, el autor cambia) y, si quiere, un rótulo.
4. PREVIA    vídeo en silencio con los efectos, rápido y gratis, para revisar antes de gastar nada.
5. FINAL     voz del canal → los planos elegidos se bajan en ALTA (1080p, solo esos segundos) → 16:9 a
             pantalla completa, rejilla con tarjetas SOLO entre bloques, subtítulos, logo, efectos y música →
             Short vertical sacado del 16:9 → textos para publicar y miniatura.

Calidad: el gameplay va directo de la fuente a FFmpeg (sin capturas de pantalla); el navegador solo dibuja la
rejilla de las transiciones, los paneles de texto y la miniatura.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import animacion, canales, config, extractor, medios, subtitulos, voz

logger = logging.getLogger("studio4.montaje")

ANCHO, ALTO = 1920, 1080
ANCHO_PREVIA, ALTO_PREVIA = 960, 540
TRANSICION = 1.2        # segundos de rejilla con la tarjeta del bloque siguiente
ENTRADA = 0.25          # respiro antes de la primera palabra
PALABRAS_POR_SEGUNDO = 2.5
ESTILO_VOZ = ("Narra en español latino neutro, con acento latinoamericano (nunca de España), como un youtuber de "
              "videojuegos: cercano, con energía y ritmo ágil, dando datos con seguridad")
_lock = threading.RLock()
# Un trabajo pesado a la vez (render, voz, descargas en alta): el PC no tiene tarjeta gráfica y dos montajes a la
# par se ahogan. Los demás esperan su turno y el panel lo dice.
_turno = threading.Lock()
PESADOS = {"Previa", "Vídeo final", "Short"}


# --- Guardado -----------------------------------------------------------------------------------------------------
def raiz() -> Path:
    return config.PRODUCCIONES / "_montajes"


def carpeta(mid: str) -> Path:
    if not re.fullmatch(r"[\w-]{3,80}", mid or ""):
        raise ValueError("Montaje desconocido.")
    return raiz() / mid


def cargar(mid: str) -> dict[str, Any]:
    ruta = carpeta(mid) / "proyecto.json"
    if not ruta.exists():
        raise ValueError("Ese vídeo ya no existe.")
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(p: dict[str, Any]) -> None:
    ruta = carpeta(p["id"]) / "proyecto.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    p["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def modificar(mid: str, cambio: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    with _lock:
        p = cargar(mid)
        cambio(p)
        guardar(p)
        return p


def listar() -> list[dict[str, Any]]:
    salida = []
    for f in sorted(raiz().glob("*/proyecto.json"), reverse=True) if raiz().exists() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        salida.append({"id": p["id"], "titulo": p["titulo"], "creado": p["creado"], "paso": paso_actual(p),
                       "frases": len(p["frases"]), "con_clip": sum(1 for x in p["frases"] if x.get("clip") or x.get("panel")),
                       "final": bool(p.get("final"))})
    return salida


def paso_actual(p: dict[str, Any]) -> int:
    """En qué paso va el vídeo (1 a 5), para la lista y para abrir el panel donde toca."""
    if not p["frases"]:
        return 1
    if not p["fuentes"]:
        return 2
    if any(not (x.get("clip") or x.get("panel")) for x in p["frases"]):
        return 3
    if not p.get("previa"):
        return 4
    return 5


# --- 1 · Guion ----------------------------------------------------------------------------------------------------
def partir(guion: str) -> list[dict[str, Any]]:
    """Bloques = párrafos; frases = oraciones (las de menos de 6 palabras se juntan con la siguiente).
    Cada frase es lo que se ve con un mismo plano."""
    frases = []
    bloques = [b.strip() for b in re.split(r"\n\s*\n", (guion or "").replace("\r\n", "\n")) if b.strip()]
    for nb, bloque in enumerate(bloques):
        oraciones = [o.strip() for o in re.split(r"(?<=[.!?…])\s+", " ".join(bloque.split())) if o.strip()]
        pendiente = ""
        for o in oraciones:
            pendiente = f"{pendiente} {o}".strip()
            if len(pendiente.split()) >= 6:
                frases.append({"bloque": nb, "texto": pendiente})
                pendiente = ""
        if pendiente:
            if frases and frases[-1]["bloque"] == nb:
                frases[-1]["texto"] += " " + pendiente
            else:
                frases.append({"bloque": nb, "texto": pendiente})
    if len(bloques) == 1 and len(frases) > 8:
        for k, f in enumerate(frases):
            f["bloque"] = k // 4
    for k, f in enumerate(frases):
        f["n"] = k + 1
    return frases


def revisar(guion: str) -> list[str]:
    """Avisos gratis antes de montar: frases que suenan a IA y datos de GTA 6 que deberían ir como avance."""
    from .guion import frases_prohibidas
    avisos = [f"Suena a IA: «{x}»" for x in frases_prohibidas(guion)]
    if re.search(r"GTA\s*(6|VI)", guion, re.I) and not re.search(r"(seg[uú]n|avance|tr[aá]iler|rumor|filtraci)", guion, re.I):
        avisos.append("Habla de GTA 6 sin decir de dónde sale el dato (tráiler, avances): todavía no se puede jugar.")
    return avisos


def crear(titulo: str, guion: str, canal: str = "", sin_guion: bool = False) -> str:
    """`sin_guion`: el vídeo nace vacío porque Studio está escribiendo su guion (desde una idea del día)."""
    frases = partir(guion)
    if not frases and not sin_guion:
        raise ValueError("Pega el guion (lo que dirá la voz).")
    base = re.sub(r"[^a-z0-9]+", "-", titulo.lower())[:40].strip("-") or "video"
    mid = f"{time.strftime('%Y%m%d-%H%M%S')}-{base}"
    with _lock:
        while (raiz() / mid).exists():
            mid += "-b"
        c = canales.obtener(canal) if canal else canales.activo()
        guardar({"id": mid, "titulo": titulo.strip()[:120] or "Vídeo sin título", "canal": c["id"],
                 "creado": time.strftime("%Y-%m-%d %H:%M"), "guion": guion.strip(), "frases": frases,
                 "avisos": revisar(guion), "fuentes": [], "voz_nombre": c.get("voz_nombre") or "Sadaltager",
                 "previa": "", "final": None, "short": None, "textos": None, "miniatura": "",
                 "trabajo": {"ocupado": False, "fase": "", "progreso": 0, "error": ""}})
    return mid


def desde_biblioteca(item_id: str) -> str:
    """Un guion de la Biblioteca (los de Agron) → un vídeo nuevo con su título, descripción y hashtags."""
    from . import biblioteca
    cid = canales.activo()["id"]
    item = next((x for x in biblioteca.leer(cid) if x["id"] == item_id), None)
    if not item:
        raise ValueError("Ese guion ya no está en la biblioteca.")
    mid = crear(item.get("titulo") or item["guion"][:60], item["guion"], cid)
    modificar(mid, lambda p: p.update(textos_autor={"titulo": item.get("titulo", ""), "descripcion": item.get("descripcion", ""),
                                                    "hashtags": item.get("hashtags", [])}, biblioteca=item_id))
    biblioteca.marcar(cid, item_id, mid)
    return mid


def desde_idea(n: int) -> str:
    """Una idea del día → vídeo nuevo; Studio investiga (fuentes del canal + web) y escribe el guion de ~5 min con la
    metodología del estudio. El vídeo se abre ya y el guion aparece en el paso 1 al terminar."""
    from . import fuentes as fuentes_web
    from . import guion as guionista
    from . import ideas, investigacion
    cid = canales.activo()["id"]
    lista = ideas.diarias(cid).get("ideas") or []
    if not 0 <= n < len(lista):
        raise ValueError("Esa idea ya no está.")
    idea = lista[n]
    mid = crear(idea["idea"][:90], "", cid, sin_guion=True)

    def fase():
        _avisar(mid, "Investigando el tema", 10)
        dossier = investigacion.investigar(idea["idea"], produccion=mid)
        propias = canales.obtener(cid).get("fuentes") or []
        if propias:
            _avisar(mid, "Leyendo tus fuentes de confianza", 35)
            try:
                extra = fuentes_web.investigar(idea["idea"], propias, produccion=mid)
                if extra["texto"]:
                    dossier["dossier"] = f"DE TUS FUENTES DE CONFIANZA:\n{extra['texto']}\n\n" + dossier.get("dossier", "")
            except Exception as e:  # noqa: BLE001 - sin sus fuentes el guion sale igual
                logger.warning("Fuentes del canal: %s", e)
        _avisar(mid, "Escribiendo el guion", 60)
        escrito = guionista.escribir(idea["idea"], dossier.get("dossier", ""), {"largo": 300}, produccion=mid,
                                     referencias=idea.get("texto", ""), identidad=guionista.identidad_del_canal(canales.obtener(cid)))
        cambiar_guion(mid, escrito["largo"]["guion"])
        modificar(mid, lambda p: p.update(titulo=escrito.get("titulo_provisional") or p["titulo"]))
    _en_fondo(mid, "Guion", fase)
    return mid


def cambiar_guion(mid: str, guion: str) -> None:
    """Un guion nuevo conserva los planos de las frases que no cambiaron."""
    nuevas = partir(guion)

    def cambio(p):
        viejas = {f["texto"]: f for f in p["frases"]}
        for f in nuevas:
            v = viejas.get(f["texto"])
            if v:
                f.update({k: v[k] for k in ("clip", "rotulo", "panel") if v.get(k)})
        p.update(guion=guion.strip(), frases=nuevas, avisos=revisar(guion), previa="", final=None, short=None)
    modificar(mid, cambio)


# --- 2 · Material -------------------------------------------------------------------------------------------------
def _fid(url: str, desde: float | None, hasta: float | None) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", url)
    base = m.group(1) if m else re.sub(r"[^\w-]+", "_", url)[-40:]
    return f"{base}_{int(desde)}-{int(hasta)}" if desde is not None and hasta is not None else base


def preparar_fuente(url: str, desde: float | None = None, hasta: float | None = None, nombre: str = "",
                    avisar: Callable[[str, int], None] = lambda *_: None) -> dict[str, Any]:
    """Una fuente en el banco de clips: su versión en baja (para ver), sus planos y una miniatura por plano.
    Si ya estaba, no se vuelve a bajar nada."""
    fid = _fid(url, desde, hasta)
    meta_ruta = extractor.CACHE / f"{fid}.banco.json"
    if meta_ruta.exists():
        return json.loads(meta_ruta.read_text(encoding="utf-8"))
    avisar("Bajando en baja calidad para ver sus planos", 10)
    import yt_dlp
    with yt_dlp.YoutubeDL(extractor.opciones_ytdlp(skip_download=True)) as y:
        info = y.extract_info(url, download=False)
    ini = float(desde or 0)
    fin = float(hasta) if hasta is not None else float(info.get("duration") or 0)
    if fin - ini > 45 * 60:
        raise ValueError("Es muy largo: indica el tramo que te interesa (desde y hasta, como mucho 45 min), "
                         "por ejemplo el capítulo de la misión.")
    baja = extractor.descargar_tramo(info["webpage_url"], ini, fin, alto=360, nombre=f"{fid}_360p")
    avisar("Buscando los cambios de plano", 60)
    planos = extractor.planos(baja)
    if len(planos) < max(3, (fin - ini) / 30):   # gameplay sin cortes: tramos fijos de 6 s
        tot = medios.duracion(baja)
        planos = [(round(a, 2), round(min(a + 6, tot), 2)) for a in [i * 6.0 for i in range(int(tot // 6))]]
    miniaturas = extractor.CACHE / f"{fid}_planos"
    miniaturas.mkdir(exist_ok=True)
    for k, (a, b) in enumerate(planos):
        medios.ffmpeg("-ss", f"{(a + b) / 2:.2f}", "-i", str(baja), "-frames:v", "1", "-vf", "scale=320:180",
                      str(miniaturas / f"{k + 1:03d}.jpg"))
        if k % 10 == 0:
            avisar(f"Miniaturas de los planos: {k + 1} de {len(planos)}", 60 + int(35 * k / len(planos)))
    meta = {"id": fid, "url": info["webpage_url"], "titulo": info.get("title", ""), "nombre": nombre or info.get("title", "")[:60],
            "canal": info.get("channel") or info.get("uploader", ""), "desde": ini, "hasta": fin, "baja": baja.name,
            "planos": [{"n": k + 1, "ini": a, "fin": b} for k, (a, b) in enumerate(planos)],
            "fecha": time.strftime("%Y-%m-%d")}
    _marcar_pobres(meta)
    meta_ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def _marcar_pobres(meta: dict[str, Any]) -> dict[str, Any]:
    """Marca los planos que no sirven como imagen: negros, fundidos, lisos (rótulos de clasificación, logos sobre
    negro) o de menos de 0,8 s. La propuesta automática se los salta; el autor aún puede elegirlos a mano."""
    from PIL import Image, ImageStat
    carpeta_m = extractor.CACHE / f"{meta['id']}_planos"
    for pl in meta["planos"]:
        if "pobre" in pl:
            continue
        try:
            st = ImageStat.Stat(Image.open(carpeta_m / f"{pl['n']:03d}.jpg").convert("L"))
            media, desv = st.mean[0], st.stddev[0]
        except OSError:   # sin miniatura no se puede juzgar la imagen: solo cuenta la duración
            media, desv = 255.0, 255.0
        pl["pobre"] = media < 28 or desv < 22 or (pl["fin"] - pl["ini"]) < 0.8
    if meta["planos"] and meta["hasta"] - meta["desde"] < 600:   # tráilers: clasificación de edad al principio, logo al final
        if meta["planos"][0]["fin"] - meta["planos"][0]["ini"] < 4:
            meta["planos"][0]["pobre"] = True
        meta["planos"][-1]["pobre"] = True
    return meta


def banco() -> list[dict[str, Any]]:
    """Todas las fuentes ya preparadas (para reutilizarlas en otros vídeos)."""
    salida = []
    for f in sorted(extractor.CACHE.glob("*.banco.json")) if extractor.CACHE.exists() else []:
        try:
            salida.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return salida


def fuente(fid: str) -> dict[str, Any]:
    ruta = extractor.CACHE / f"{fid}.banco.json"
    if not re.fullmatch(r"[\w.-]{3,120}", fid or "") or not ruta.exists():
        raise ValueError("Esa fuente no está en el banco.")
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    if any("pobre" not in pl for pl in meta["planos"]):   # fuentes preparadas antes de esta marca
        _marcar_pobres(meta)
        ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def anadir_fuente(mid: str, url: str, desde: float | None = None, hasta: float | None = None, nombre: str = "") -> None:
    def fase():
        meta = preparar_fuente(url, desde, hasta, nombre, avisar=lambda f, n: _avisar(mid, f, n))
        modificar(mid, lambda p: p["fuentes"].append(meta["id"]) if meta["id"] not in p["fuentes"] else None)
    _en_fondo(mid, "Material", fase)


def usar_fuente(mid: str, fid: str) -> None:
    """Una fuente del banco en este vídeo (sin bajar nada)."""
    fuente(fid)
    modificar(mid, lambda p: p["fuentes"].append(fid) if fid not in p["fuentes"] else None)


# --- 3 · Montaje --------------------------------------------------------------------------------------------------
def asignar(mid: str, n: int, fid: str = "", plano: int = 0, rotulo: str | None = None,
            panel: dict[str, Any] | None = None) -> None:
    """El plano de una frase (o un panel de texto en su lugar) y su rótulo."""
    if fid:
        meta = fuente(fid)
        if not 1 <= plano <= len(meta["planos"]):
            raise ValueError("Ese plano no existe.")

    def cambio(p):
        f = next((x for x in p["frases"] if x["n"] == n), None)
        if not f:
            raise ValueError("Esa frase no existe.")
        if fid:
            f["clip"] = {"fuente": fid, "plano": plano}
            f.pop("panel", None)
        if panel is not None:
            items = [str(i).strip()[:80] for i in panel.get("items", []) if str(i).strip()][:5]
            f["panel"] = {"titulo": str(panel.get("titulo", ""))[:60], "items": items, "nota": str(panel.get("nota", ""))[:90]} \
                if items or panel.get("titulo") else None
            if not f["panel"]:
                f.pop("panel")
        if rotulo is not None:
            f["rotulo"] = rotulo.strip()[:40]
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)


def proponer(mid: str) -> int:
    """A cada frase sin plano, el siguiente plano sin usar de las fuentes del vídeo (por turnos entre fuentes).
    Es un punto de partida: el autor cambia los que no encajen. Devuelve cuántas propuso."""
    p = cargar(mid)
    if not p["fuentes"]:
        raise ValueError("Primero añade material (paso 2).")
    usados = {(f["clip"]["fuente"], f["clip"]["plano"]) for f in p["frases"] if f.get("clip")}
    colas = {fid: [pl["n"] for pl in fuente(fid)["planos"] if (fid, pl["n"]) not in usados and not pl.get("pobre")]
             for fid in p["fuentes"]}
    hechas, turno = 0, 0

    def cambio(q):
        nonlocal hechas, turno
        for f in q["frases"]:
            if f.get("clip") or f.get("panel"):
                continue
            for _ in range(len(q["fuentes"])):
                fid = q["fuentes"][turno % len(q["fuentes"])]
                turno += 1
                if colas[fid]:
                    f["clip"] = {"fuente": fid, "plano": colas[fid].pop(0)}
                    hechas += 1
                    break
        q.update(previa="", final=None, short=None)
    modificar(mid, cambio)
    return hechas


# --- Trabajo en segundo plano ---------------------------------------------------------------------------------------
def _avisar(mid: str, fase: str, progreso: int) -> None:
    modificar(mid, lambda p: p["trabajo"].update(fase=fase, progreso=max(0, min(100, progreso))))


def _en_fondo(mid: str, nombre: str, fn: Callable[[], None]) -> None:
    with _lock:
        p = cargar(mid)
        if p["trabajo"].get("ocupado"):
            raise RuntimeError(f"Este vídeo ya está trabajando: {p['trabajo'].get('fase')}")
        p["trabajo"] = {"ocupado": True, "nombre": nombre, "fase": nombre, "progreso": 0, "error": ""}
        guardar(p)

    def correr():
        try:
            if nombre in PESADOS:
                if not _turno.acquire(blocking=False):
                    _avisar(mid, "En cola: espera a que termine el otro vídeo", 0)
                    _turno.acquire()
                try:
                    fn()
                finally:
                    _turno.release()
            else:
                fn()
        except Exception as e:  # noqa: BLE001 - el motivo se ve en el panel
            logger.exception("%s falló", nombre)
            modificar(mid, lambda p: p["trabajo"].update(ocupado=False, error=f"{nombre}: {str(e)[:300]}"))
        else:
            modificar(mid, lambda p: p["trabajo"].update(ocupado=False, error="", progreso=100, fase=f"{nombre}: listo"))
    threading.Thread(target=correr, name=f"montaje-{nombre}", daemon=True).start()


def _tamano(ruta: Path) -> int:
    return sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file()) if ruta.exists() else 0


def espacio() -> dict[str, Any]:
    """Cuánto ocupa cada cosa y cuánto se puede liberar sin perder nada que se vea en el panel."""
    temporales = sum(_tamano(d) for d in raiz().glob("*/render_previa")) + sum(_tamano(d) for d in raiz().glob("*/render_miniatura")) \
        + sum(f.stat().st_size for d in raiz().glob("*/render") for f in d.glob("*") if f.is_file() and f.name not in ("cuerpo.mp4", "subs.ass"))
    return {"montajes": _tamano(raiz()), "banco": _tamano(extractor.CACHE), "papelera": _tamano(config.PRODUCCIONES / "_papelera"),
            "liberable": temporales}


def liberar() -> int:
    """Borra solo lo temporal de los renders (trozos ya unidos). El vídeo final, la previa, el Short, la miniatura,
    la voz y lo necesario para rehacer el Short se quedan. Devuelve los bytes liberados."""
    antes = espacio()["liberable"]
    for d in list(raiz().glob("*/render_previa")) + list(raiz().glob("*/render_miniatura")):
        shutil.rmtree(d, ignore_errors=True)
    for d in raiz().glob("*/render"):
        for f in d.glob("*"):
            if f.is_file() and f.name not in ("cuerpo.mp4", "subs.ass"):
                f.unlink(missing_ok=True)
    return antes


def recuperar_colgados() -> None:
    """Al arrancar el servidor ningún montaje puede seguir «trabajando»: se libera para poder repetirlo."""
    for f in raiz().glob("*/proyecto.json") if raiz().exists() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if p["trabajo"].get("ocupado"):
                p["trabajo"].update(ocupado=False, error=f"{p['trabajo'].get('nombre', 'Trabajo')}: se cortó al cerrar Studio 4; vuelve a pulsarlo.")
                guardar(p)
        except (ValueError, KeyError, OSError):
            continue


# --- 4 y 5 · Render -------------------------------------------------------------------------------------------------
def _tiempos_estimados(p: dict[str, Any]) -> list[tuple[float, float]]:
    t, salida = ENTRADA, []
    for f in p["frases"]:
        d = max(1.6, len(f["texto"].split()) / PALABRAS_POR_SEGUNDO)
        salida.append((t, t + d))
        t += d
    return salida


def _segmento(fuente_video: Path, ini: float, fin: float, d: float, ancho: int, alto: int, destino: Path) -> None:
    """Un plano a pantalla completa durante `d` s: si el plano es más corto, va más lento (hasta la mitad) y después
    se queda en su último fotograma. Nunca se cuela el plano siguiente del vídeo de origen."""
    largo = max(0.3, fin - ini)
    lento = min(2.0, max(1.0, d / largo))
    vf = (f"setpts={lento:.4f}*PTS,scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
          f"fps={config.FPS},tpad=stop_mode=clone:stop_duration={d + 1:.3f},setsar=1")
    medios.ffmpeg("-ss", f"{ini:.3f}", "-t", f"{largo:.3f}", "-i", str(fuente_video), "-an", "-vf", vf,
                  "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(destino))


def _rotulo_png(texto: str, color: str, destino: Path, escala: float) -> Path:
    """El rótulo neón (pastilla) como PNG transparente, para superponerlo sin tocar la calidad del plano."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    fuente_ttf = ImageFont.truetype("arialbd.ttf", int(46 * escala))
    caja = fuente_ttf.getbbox(texto)
    w, h = caja[2] - caja[0] + int(80 * escala), caja[3] - caja[1] + int(44 * escala)
    img = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    brillo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(brillo).rounded_rectangle([30, 30, 30 + w, 30 + h], radius=h // 2, outline=color, width=int(10 * escala))
    img.alpha_composite(brillo.filter(ImageFilter.GaussianBlur(10 * escala)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([30, 30, 30 + w, 30 + h], radius=h // 2, fill=(5, 5, 8, 215), outline=color, width=int(4 * escala))
    d.text((30 + w / 2, 30 + h / 2), texto, fill=color, font=fuente_ttf, anchor="mm")
    img.save(destino)
    return destino


def _render(mid: str, final: bool, avisar: Callable[[str, int], None]) -> Path:
    p = cargar(mid)
    base = carpeta(mid)
    ancho, alto = (ANCHO, ALTO) if final else (ANCHO_PREVIA, ALTO_PREVIA)
    escala = ancho / ANCHO
    trabajo = base / ("render" if final else "render_previa")
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir(parents=True)
    if final:
        segmentos = [f["texto"] for f in p["frases"]]
        wav = base / "voz.wav"
        firma_voz = hashlib.sha1(json.dumps([segmentos, p["voz_nombre"], ESTILO_VOZ]).encode("utf-8")).hexdigest()
        previa_voz = p.get("voz") or {}
        if previa_voz.get("firma") == firma_voz and wav.exists():   # mismo texto y misma voz: no se regraba
            avisar("Voz ya grabada (mismo guion)", 10)
            tiempos, palabras = [tuple(x) for x in previa_voz["tiempos"]], previa_voz["palabras"]
        else:
            avisar("Grabando la voz", 5)
            t = voz.locutar(segmentos, wav, "gemini", produccion=mid, voz_nombre=p["voz_nombre"], estilo_voz=ESTILO_VOZ)
            tiempos = [(e["ini"] + ENTRADA, e["fin"] + ENTRADA) for e in t["escenas"]]
            palabras = [{**w, "ini": w["ini"] + ENTRADA, "fin": w["fin"] + ENTRADA} for w in t["palabras"]]
            modificar(mid, lambda q: q.update(voz={"archivo": "voz.wav", "duracion": t["duracion"], "palabras": palabras,
                                                   "tiempos": tiempos, "firma": firma_voz}))
    else:
        tiempos = _tiempos_estimados(p)
    # cada frase dura desde su inicio hasta el inicio de la siguiente (sin huecos); la primera empieza en 0
    tramos = [(0.0 if k == 0 else a, tiempos[k + 1][0] if k + 1 < len(tiempos) else b + 1.2) for k, (a, b) in enumerate(tiempos)]
    piezas: list[Path] = []
    fx_escenas: list[dict[str, Any]] = []
    usados: list[dict[str, Any]] = []
    fuentes_ok = {fid: fuente(fid) for fid in p["fuentes"]}
    colores = {fid: list(animacion.COLORES.values())[k % len(animacion.COLORES)] for k, fid in enumerate(p["fuentes"])}
    cursor = 0.0
    for k, (f, (a, b)) in enumerate(zip(p["frases"], tramos)):
        avisar(f"Plano {k + 1} de {len(p['frases'])}", 15 + int(60 * k / len(p["frases"])))
        d = b - a
        nuevo_bloque = k > 0 and f["bloque"] != p["frases"][k - 1]["bloque"]
        seg = trabajo / f"s{k:03d}.mp4"
        if f.get("panel"):   # un panel de texto (lista, recreación) sobre la rejilla, dibujado en el navegador
            esc = [{"ini": 0, "fin": d, "panel": f["panel"]}]
            animacion.renderizar(esc, d, seg, ancho, alto)
            fx_escenas.append({"ini": cursor, "fin": cursor + d, "panel": f["panel"]})
        else:
            clip = f["clip"]
            meta = fuentes_ok[clip["fuente"]]
            pl = meta["planos"][clip["plano"] - 1]
            usados.append({"frase": f["n"], "fuente": meta["titulo"], "canal": meta.get("canal", ""), "url": meta["url"],
                           "desde": round(meta["desde"] + pl["ini"], 2), "hasta": round(meta["desde"] + pl["fin"], 2)})
            if final:   # en alta solo los segundos de este plano
                origen = extractor.descargar_tramo(meta["url"], meta["desde"] + pl["ini"], meta["desde"] + pl["fin"], alto=1080)
                ini_local, fin_local = 0.0, pl["fin"] - pl["ini"]
            else:
                origen = extractor.CACHE / meta["baja"]
                ini_local, fin_local = pl["ini"], pl["fin"]
            if nuevo_bloque and d > TRANSICION + 0.8:
                # la transición: rejilla y la primera imagen del bloque nuevo entrando como tarjeta
                foto = trabajo / f"t{k:03d}.jpg"
                medios.ffmpeg("-ss", f"{ini_local + 0.2:.3f}", "-i", str(origen), "-frames:v", "1", str(foto))
                tr = trabajo / f"t{k:03d}.mp4"
                escena_tr = {"ini": 0, "fin": TRANSICION, "imagenes": [{"archivo": str(foto), "etiqueta": f.get("rotulo", ""),
                                                                        "color": colores[clip["fuente"]]}]}
                animacion.renderizar([escena_tr], TRANSICION, tr, ancho, alto)
                piezas.append(_sin_audio(tr, trabajo / f"t{k:03d}b.mp4"))
                fx_escenas.append({**escena_tr, "ini": cursor, "fin": cursor + TRANSICION})
                cursor += TRANSICION
                d -= TRANSICION
            _segmento(origen, ini_local, fin_local, d, ancho, alto, seg)
            if f.get("rotulo"):   # rótulo neón abajo a la izquierda los primeros segundos
                png = _rotulo_png(f["rotulo"], colores[clip["fuente"]], trabajo / f"r{k:03d}.png", escala)
                con = trabajo / f"s{k:03d}r.mp4"
                medios.ffmpeg("-i", str(seg), "-loop", "1", "-i", str(png), "-filter_complex",
                              f"[1:v]format=rgba,fade=t=in:st=0.2:d=0.3:alpha=1,fade=t=out:st={min(3.2, d - 0.4):.2f}:d=0.3:alpha=1[r];"
                              f"[0:v][r]overlay=x={int(70 * escala)}:y=H-h-{int(150 * escala)}:shortest=1",
                              "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(con))
                seg = con
                fx_escenas.append({"ini": cursor, "fin": cursor + d, "imagenes": [{"etiqueta": f["rotulo"]}]})
        piezas.append(seg)
        cursor += d
    if final:   # «Fuentes y créditos»: cada fragmento con su segundo exacto, por si hay una reclamación
        _creditos(base, p, usados)
    avisar("Uniendo los planos", 78)
    lista = trabajo / "lista.txt"
    lista.write_text("".join(f"file '{x.as_posix()}'\n" for x in piezas), encoding="utf-8")
    cuerpo = trabajo / "cuerpo.mp4"
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(cuerpo))
    total = medios.duracion(cuerpo)
    fx = animacion.pista_de_efectos(fx_escenas, total, trabajo / "fx.wav")
    logo = logo_de(p["canal"])
    destino = base / ("final_16x9.mp4" if final else "previa.mp4")
    entradas = ["-i", str(cuerpo), "-i", str(fx)]
    filtros, mezcla_v = [], "[0:v]"
    if logo:   # el logo del canal, discreto arriba a la derecha en todo el vídeo
        entradas += ["-loop", "1", "-i", str(logo)]
        lado = int(130 * escala)
        filtros.append(f"[2:v]scale={lado}:{lado},format=rgba,colorchannelmixer=aa=0.55[logo];"
                       f"{mezcla_v}[logo]overlay=W-w-{int(40 * escala)}:{int(36 * escala)}:shortest=1[v1]")
        mezcla_v = "[v1]"
    if final:
        avisar("Subtítulos, voz y efectos", 88)
        ass = subtitulos.construir(cargar(mid)["voz"]["palabras"], trabajo / "subs.ass", ancho, alto, {"posicion": "abajo"})
        filtros.append(f"{mezcla_v}ass={ass.name}[v]")
        n_voz = len([e for e in entradas if e == "-i"])
        entradas += ["-i", str(base / "voz.wav")]
        musica = _musica(p)
        n_mus = n_voz + 1
        if musica:
            entradas += ["-stream_loop", "-1", "-i", str(musica)]
        retraso = int(ENTRADA * 1000)
        audio = (f"[{n_voz}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={retraso}:all=1,asplit=2[voz][llave];"
                 f"[1:a]volume=0.35[fx];")
        if musica:
            audio += (f"[{n_mus}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={config.VOLUMEN_MUSICA},"
                      f"afade=t=out:st={max(0, total - 2):.3f}:d=2[m0];[m0][llave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus];"
                      f"[voz][fx][mus]amix=inputs=3:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        else:
            audio += "[llave]anullsink;[voz][fx]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        filtros.append(audio)
        crf = "17"
    else:
        filtros.append(f"{mezcla_v}null[v]")
        filtros.append("[1:a]volume=0.5[a]")
        crf = "23"
    medios.ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
                  "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                  "-ar", "48000", "-movflags", "+faststart", str(destino), cwd=trabajo)
    return destino


def logo_de(canal: str) -> Path | None:
    """El logo del canal recortado en círculo con fondo transparente (el PNG original trae un cuadrado negro).
    Se prepara una vez y se reutiliza."""
    from PIL import Image, ImageDraw
    base = config.PRODUCCIONES / "_canales" / canal
    original, redondo = base / "logo.png", base / "logo_redondo.png"
    if not original.exists():
        return None
    if not redondo.exists() or redondo.stat().st_mtime < original.stat().st_mtime:
        im = Image.open(original).convert("RGBA")
        lado = min(im.size)
        im = im.crop(((im.width - lado) // 2, (im.height - lado) // 2, (im.width + lado) // 2, (im.height + lado) // 2))
        mascara = Image.new("L", (lado * 4, lado * 4), 0)
        ImageDraw.Draw(mascara).ellipse([8, 8, lado * 4 - 8, lado * 4 - 8], fill=255)   # borde suave: se dibuja a 4x
        im.putalpha(mascara.resize((lado, lado), Image.LANCZOS))
        im.save(redondo)
    return redondo


def _creditos(base: Path, p: dict[str, Any], usados: list[dict[str, Any]]) -> None:
    reloj = lambda s: f"{int(s) // 3600}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}"  # noqa: E731
    lineas = [f"Fuentes y créditos · {p['titulo']}", "Fragmentos cortos, sin su audio, con comentario y edición propios.", ""]
    lineas += [f"Frase {u['frase']}: {u['fuente']} ({u['canal']}) · {reloj(u['desde'])}–{reloj(u['hasta'])} · {u['url']}"
               for u in usados]
    (base / "Fuentes y créditos.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    modificar(p["id"], lambda q: q.update(creditos=usados))


def _sin_audio(origen: Path, destino: Path) -> Path:
    medios.ffmpeg("-i", str(origen), "-an", "-c:v", "copy", str(destino))
    return destino


def _musica(p: dict[str, Any]) -> Path | None:
    from . import carpetas
    return carpetas.elegir_musica(f"{p['titulo']} {p['guion'][:300]}")


def previa(mid: str) -> None:
    def fase():
        destino = _render(mid, False, lambda f, n: _avisar(mid, f, n))
        modificar(mid, lambda p: p.update(previa=destino.name))
    _en_fondo(mid, "Previa", fase)


def montar_final(mid: str) -> None:
    def fase():
        destino = _render(mid, True, lambda f, n: _avisar(mid, f, n))
        modificar(mid, lambda p: p.update(final={"archivo": destino.name, "hecho": time.strftime("%Y-%m-%d %H:%M")}))
        from . import linea   # la línea de tiempo por pistas, junto al vídeo (para abrirla en otro editor o revisarla)
        q = cargar(mid)
        (carpeta(mid) / "linea_de_tiempo.json").write_text(
            json.dumps(linea.desde_montaje(q, {fid: fuente(fid) for fid in q["fuentes"]}), ensure_ascii=False, indent=1), encoding="utf-8")
        _avisar(mid, "Textos para publicar", 97)
        try:
            hacer_textos(mid)
        except Exception as e:  # noqa: BLE001 - el vídeo ya está; los textos se pueden repetir
            logger.warning("Textos: %s", e)
    _en_fondo(mid, "Vídeo final", fase)


# --- Short vertical sacado del 16:9 ---------------------------------------------------------------------------------
def montar_short(mid: str, desde: float, hasta: float) -> None:
    """Un tramo del vídeo final (≤ 60 s) en vertical: el 16:9 entero en el centro sobre su versión desenfocada,
    con sus subtítulos rehechos para el formato vertical. No se recorta el gameplay."""
    p = cargar(mid)
    if not p.get("final"):
        raise ValueError("Primero monta el vídeo final.")
    if not 5 <= hasta - desde <= 60:
        raise ValueError("Un Short dura entre 5 y 60 segundos.")

    def fase():
        q = cargar(mid)
        base = carpeta(mid)
        trabajo = base / "render_short"
        shutil.rmtree(trabajo, ignore_errors=True)
        trabajo.mkdir()
        _avisar(mid, "Encuadrando en vertical", 20)
        # el vídeo final ya lleva subtítulos horizontales: se parte del cuerpo sin subtítulos + la misma mezcla
        palabras = [{**w, "ini": w["ini"] - desde, "fin": w["fin"] - desde} for w in q["voz"]["palabras"]
                    if desde <= w["ini"] < hasta]
        ass = subtitulos.construir(palabras, trabajo / "subs.ass", 1080, 1920, {"posicion": "abajo"})
        medios.ffmpeg("-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / "render" / "cuerpo.mp4"),
                      "-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / q["final"]["archivo"]),
                      "-filter_complex",
                      "[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                      "gblur=sigma=30,eq=brightness=-0.12[fondo];[b]scale=1080:-2[centro];"
                      f"[fondo][centro]overlay=0:(H-h)/2-120,ass={ass.name}[v]",
                      "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                      "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                      str(base / "short_9x16.mp4"), cwd=trabajo)
        modificar(mid, lambda r: r.update(short={"archivo": "short_9x16.mp4", "desde": desde, "hasta": hasta}))
    _en_fondo(mid, "Short", fase)


# --- Textos para publicar y miniatura -------------------------------------------------------------------------------
SISTEMA_TEXTOS = """Eres editor de un canal de YouTube de videojuegos en español latino. Con el guion de un vídeo
escribe lo necesario para publicarlo. Reglas: nada de clickbait engañoso; lo no confirmado se presenta como avance
o rumor; nunca menciones a otros youtubers ni canales. Devuelve JSON:
{"titulos": ["3 títulos de máx. 70 caracteres, distintos"], "descripcion": "3-5 frases, primera línea con gancho",
 "hashtags": ["5 a 8, con #"], "texto_miniatura": "2 a 4 palabras en mayúsculas para la miniatura"}"""


def hacer_textos(mid: str) -> dict[str, Any]:
    from . import deepseek
    p = cargar(mid)
    d = deepseek.generar_json(SISTEMA_TEXTOS, f"Título de trabajo: {p['titulo']}\n\nGUION:\n{p['guion']}",
                              temperatura=0.6, detalle="textos para publicar", produccion=mid)
    capitulos = []
    if p.get("voz"):   # un capítulo por bloque, en el minuto en que empieza (la primera línea siempre 0:00)
        vistos = set()
        for f, (a, _b) in zip(p["frases"], p["voz"]["tiempos"]):
            if f["bloque"] not in vistos:
                vistos.add(f["bloque"])
                seg = 0 if not capitulos else int(a)
                capitulos.append(f"{seg // 60}:{seg % 60:02d} {' '.join(f['texto'].split()[:6]).rstrip('.,:;')}")
    creditos = sorted({fuente(fid)["titulo"] for fid in p["fuentes"] if fid})
    textos = {"titulos": [str(t)[:100] for t in d.get("titulos", [])][:3], "descripcion": str(d.get("descripcion", "")),
              "hashtags": [h for h in d.get("hashtags", []) if str(h).startswith("#")][:8],
              "texto_miniatura": str(d.get("texto_miniatura", ""))[:40], "capitulos": capitulos,
              "creditos": "Imágenes de los juegos con comentario y edición propios."}
    modificar(mid, lambda q: q.update(textos=textos, fuentes_titulos=creditos))
    return textos


def miniatura(mid: str, texto: str, fotos: list[dict[str, Any]]) -> Path:
    """Miniatura 1280×720: una o dos imágenes de los planos (pantalla dividida) y el texto grande, con el logo."""
    from playwright.sync_api import sync_playwright
    p = cargar(mid)
    base = carpeta(mid)
    trabajo = base / "render_miniatura"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir()
    imgs = []
    for k, ft in enumerate(fotos[:2]):
        meta = fuente(ft["fuente"])
        pl = meta["planos"][int(ft["plano"]) - 1]
        origen = extractor.descargar_tramo(meta["url"], meta["desde"] + pl["ini"], meta["desde"] + pl["fin"], alto=1080)
        medios.ffmpeg("-ss", f"{(pl['fin'] - pl['ini']) / 2:.2f}", "-i", str(origen), "-frames:v", "1", str(trabajo / f"m{k}.jpg"))
        imgs.append(f"m{k}.jpg")
    logo = logo_de(p["canal"])
    if logo:
        shutil.copy(logo, trabajo / "logo.png")
    shutil.copy(animacion.FUENTES / "geist-latin-wght-normal.woff2", trabajo / "geist.woff2")
    paneles = "".join(f'<div class="f" style="background-image:url({i})"></div>' for i in imgs)
    html = f"""<!doctype html><meta charset="utf-8"><style>
@font-face {{ font-family: S4; src: url(geist.woff2); font-weight: 100 900; }}
body {{ margin: 0; width: 1280px; height: 720px; overflow: hidden; background: #050508; font-family: S4, sans-serif; }}
.fotos {{ position: absolute; inset: 0; display: flex; gap: 10px; }}
.f {{ flex: 1; background-size: cover; background-position: center; filter: saturate(1.25) contrast(1.08); }}
.velo {{ position: absolute; inset: 0; background: linear-gradient(to top, rgba(0,0,0,.85), rgba(0,0,0,.05) 55%); }}
h1 {{ position: absolute; left: 0; right: 0; bottom: 36px; margin: 0; text-align: center; color: #fff; font-size: 118px;
  font-weight: 900; line-height: .95; letter-spacing: -.02em; text-shadow: 0 0 30px #ff3ea5, 0 8px 0 #000; padding: 0 40px; }}
.logo {{ position: absolute; top: 22px; right: 22px; width: 120px; opacity: .9; }}
</style><div class="fotos">{paneles}</div><div class="velo"></div><h1>{texto}</h1>
{'<img class="logo" src="logo.png">' if logo else ''}"""
    (trabajo / "m.html").write_text(html, encoding="utf-8")
    destino = base / "miniatura.jpg"
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": 1280, "height": 720})
        pag.goto((trabajo / "m.html").as_uri())
        pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
        pag.screenshot(path=str(destino), type="jpeg", quality=92)
        nav.close()
    modificar(mid, lambda q: q.update(miniatura=destino.name))
    return destino
