"""Ideas en tendencia: lo que funciona HOY en el nicho, leído de verdad, convertido en una idea original.

1. En vivo: los vídeos del nicho más vistos de la última semana (YouTube, 100 unidades del cupo diario).
2. «Inspirarme»: se leen sus subtítulos (gratis, sin descargar el vídeo) y se propone una idea ORIGINAL para el
   canal —otro juego, otro caso u otro ángulo, nunca la misma— con todo lo que hace falta para ejecutarla bien:
   de qué trata el original y en qué orden, el gancho, la estructura y los datos y momentos visuales clave.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
from typing import Any

from . import aprender, archivo, canales, config, galeria, registro, tendencias, youtube

logger = logging.getLogger("studio4.ideas")

SISTEMA = """Eres jefe de contenidos de un canal de vídeo en español. Te doy un vídeo que está funcionando AHORA en el
nicho del canal (con sus vistas y, si la hay, su transcripción). NO copies su tema exacto, su título ni sus frases:
propón una idea ORIGINAL para el canal (otro juego, otro caso, otro personaje u otro ángulo) que aproveche lo que hace
funcionar al vídeo. Todo concreto y verdadero: si no sabes un dato, no lo inventes. Devuelve JSON:
{"idea": "la idea en una frase concreta, con nombre propio", "por_que": "por qué va a funcionar, apoyado en el vídeo",
 "original": "de qué trata el vídeo original, con pelos y detalles: qué cuenta y en qué orden",
 "gancho": "la primera frase propuesta para nuestro vídeo", "estructura": ["paso 1", "paso 2", "..."],
 "detalles": ["datos, nombres y momentos visuales que no pueden faltar"], "formato": "corto o largo"}"""


def en_vivo(cid: str, n: int = 8) -> list[dict[str, Any]]:
    """Los vídeos del nicho del canal que más crecen esta semana."""
    canal = canales.obtener(cid)
    if not youtube.disponible():
        raise RuntimeError("Hace falta la conexión con YouTube para buscar tendencias en vivo.")
    if not canal.get("nicho"):
        raise ValueError("Pon el nicho del canal (Canales) para saber qué buscar.")
    videos = tendencias._del_nicho(canal["nicho"])
    registro.apuntar("YouTube (lectura)", f"tendencias en vivo · {canal['nicho']}", unidad="consultas")
    return [{k: v[k] for k in ("id", "titulo", "canal", "vistas", "vistas_hora", "segundos", "url")}
            for v in sorted(videos, key=lambda v: -v["vistas_hora"])[:n]]


def inspirar(cid: str, video: dict[str, Any]) -> dict[str, Any]:
    """Una idea original a partir de un vídeo en tendencia, con todo lo necesario para ejecutarla."""
    canal = canales.obtener(cid)
    t = None
    try:
        t = aprender.transcripcion(str(video.get("url", "")))
    except Exception as e:  # noqa: BLE001 - sin subtítulos se trabaja con el título y las cifras
        logger.warning("Sin subtítulos de %s: %s", video.get("url"), e)
    texto = " ".join(t["texto"].split()[:2500]) if t else "(sin subtítulos: usa el título y las cifras)"
    manual = aprender.para_guion(cid)
    prompt = (f"Canal: {canal['nombre']} · nicho: {canal.get('nicho') or '—'}\n"
              + (f"\n{manual}\n" if manual else "")
              + f"\nVÍDEO QUE FUNCIONA AHORA: «{video.get('titulo', '')}» de {video.get('canal', '')} · "
              f"{int(video.get('vistas') or 0):,} vistas · {int(video.get('vistas_hora') or 0):,} por hora · "
              f"{video.get('segundos', 0)} s".replace(",", ".") + f"\n\nTRANSCRIPCIÓN:\n{texto}")
    d = aprender._generar_json(SISTEMA, prompt, temperatura=0.7, detalle="idea en tendencia", produccion=cid)
    d["fuente"] = {k: video.get(k) for k in ("titulo", "canal", "vistas", "url")}
    d["leido"] = bool(t)
    return d


def como_texto(d: dict[str, Any]) -> str:
    """El detalle para «Datos que no pueden faltar»: lo que el guionista recibe como material prioritario.
    Nunca nombra el vídeo ni el canal que la inspiró (eso solo lo ve el autor en el panel)."""
    lineas = ["Idea original del canal (no menciones ni copies ningún vídeo ni canal ajeno).",
              f"Por qué puede funcionar: {d.get('por_que', '')}",
              f"Tipo de vídeo que está funcionando (solo como referencia de forma): {d.get('original', '')}",
              f"Gancho: {d.get('gancho', '')}", "Estructura: " + " → ".join(d.get("estructura") or [])]
    lineas += [f"- {x}" for x in d.get("detalles") or []]
    return "\n".join(x for x in lineas if x.split(":", 1)[-1].strip())


# --- 3 ideas listas cada día ---------------------------------------------------------------------
IDEAS_AL_DIA = 3
_estado: dict[str, dict[str, Any]] = {}
_cerrojo = threading.Lock()


def _archivo(cid: str):
    return config.PRODUCCIONES / f"ideas_dia_{cid}.json"


def _hoy() -> str:
    return time.strftime("%Y-%m-%d")


def imagen_de(cid: str, idea: str) -> dict[str, str]:
    """La imagen de la tarjeta: una imagen REAL del tema de la idea, de las fuentes de confianza del canal o, si no
    hay, una foto de dominio público. Nunca la miniatura del vídeo ajeno que la inspiró (no es nuestro contenido y
    no muestra lo que propone la idea). {} si no hay ninguna que encaje."""
    try:
        img = galeria.buscar(cid, idea, n=1, paginas_por_fuente=2, minimo=2)
        if img:
            return {"url": img[0]["url"], "fuente": urllib.parse.urlparse(img[0].get("pagina") or img[0]["url"]).netloc}
    except Exception as e:  # noqa: BLE001 - sin fuentes o caídas se prueba con las fotos de archivo
        logger.info("Imagen de la idea en las fuentes: %s", e)
    try:
        foto = archivo.buscar(idea, cuantas=1)
        if foto:
            return {"url": foto[0]["url"], "fuente": "Wikimedia Commons (dominio público)"}
    except Exception as e:  # noqa: BLE001
        logger.info("Imagen de la idea en el archivo: %s", e)
    return {}


def _con_imagen(cid: str, d: dict[str, Any]) -> None:
    img = imagen_de(cid, d.get("idea", ""))
    d["miniatura"], d["miniatura_fuente"] = img.get("url", ""), img.get("fuente", "")


def generar_diarias(cid: str, avisar=lambda _f: None) -> dict[str, Any]:
    """Lo que más crece hoy en el nicho → 3 ideas originales con todo el detalle y una imagen real de su tema
    (cada una inspirada en un canal distinto)."""
    videos = en_vivo(cid, n=12)
    ideas, canales_vistos = [], set()
    for v in videos:
        if len(ideas) >= IDEAS_AL_DIA:
            break
        if v["canal"] in canales_vistos:
            continue
        avisar(f"Leyendo «{v['titulo'][:40]}» ({len(ideas) + 1} de {IDEAS_AL_DIA})")
        try:
            d = inspirar(cid, v)
        except Exception as e:  # noqa: BLE001 - un vídeo que no se puede leer deja paso al siguiente
            logger.warning("Idea desde %s: %s", v.get("url"), e)
            continue
        canales_vistos.add(v["canal"])
        avisar(f"Buscando una imagen real para la idea {len(ideas) + 1} de {IDEAS_AL_DIA}")
        _con_imagen(cid, d)
        d["fuente"] = {**d.get("fuente", {}), "vistas_hora": v.get("vistas_hora"), "segundos": v.get("segundos")}
        d["texto"] = como_texto(d)
        ideas.append(d)
    datos = {"fecha": _hoy(), "generadas": time.strftime("%H:%M"), "ideas": ideas}
    _guardar(cid, datos)
    return datos


def _guardar(cid: str, datos: dict[str, Any]) -> None:
    ruta = _archivo(cid)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


def _ajena(d: dict[str, Any]) -> bool:
    """¿La tarjeta aún lleva la miniatura del vídeo que la inspiró (ideas guardadas antes de este cambio)?"""
    return "ytimg.com" in str(d.get("miniatura", ""))


def _reponer_imagenes(cid: str) -> None:
    """Cambia las miniaturas ajenas de las ideas ya guardadas por imágenes reales de su tema."""
    with _cerrojo:
        if _estado.get(cid, {}).get("ocupado"):
            return
        _estado[cid] = {"ocupado": True, "fase": "Buscando imágenes reales para las ideas de hoy", "error": ""}

    def correr():
        try:
            datos = json.loads(_archivo(cid).read_text(encoding="utf-8"))
            for d in datos.get("ideas") or []:
                if _ajena(d):
                    _con_imagen(cid, d)
            _guardar(cid, datos)
        except Exception:  # noqa: BLE001
            logger.exception("Imágenes de las ideas de %s", cid)
        _estado[cid].update(ocupado=False, fase="")
    threading.Thread(target=correr, name=f"studio4-ideas-img-{cid}", daemon=True).start()


def lanzar_diarias(cid: str) -> None:
    with _cerrojo:
        if _estado.get(cid, {}).get("ocupado"):
            return
        _estado[cid] = {"ocupado": True, "fase": "Buscando lo que más crece hoy en tu nicho", "error": ""}

    def correr():
        try:
            generar_diarias(cid, avisar=lambda f: _estado[cid].update(fase=f))
            _estado[cid].update(ocupado=False, fase="")
        except Exception as e:  # noqa: BLE001
            logger.exception("Ideas del día de %s", cid)
            _estado[cid].update(ocupado=False, error=str(e)[:200], fecha_error=_hoy())
    threading.Thread(target=correr, name=f"studio4-ideas-{cid}", daemon=True).start()


def diarias(cid: str) -> dict[str, Any]:
    """Las ideas de hoy. Si aún no hay (primera visita del día), se preparan solas en segundo plano."""
    try:
        datos = json.loads(_archivo(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = {"fecha": "", "ideas": []}
    est = _estado.get(cid, {})
    if datos.get("fecha") != _hoy() and not est.get("ocupado") and est.get("fecha_error") != _hoy() and youtube.disponible():
        lanzar_diarias(cid)   # una vez al día; si falló hoy, se reintenta con el botón
        est = _estado.get(cid, {})
    elif any(_ajena(d) for d in datos.get("ideas") or []) and not est.get("ocupado"):
        _reponer_imagenes(cid)
        est = _estado.get(cid, {})
    for d in datos.get("ideas") or []:
        if _ajena(d):
            d["miniatura"] = ""   # mientras se busca la imagen real, la tarjeta va sin imagen
    return {**datos, "hoy": datos.get("fecha") == _hoy(), "ocupado": bool(est.get("ocupado")), "fase": est.get("fase", ""),
            "error": est.get("error", "")}
