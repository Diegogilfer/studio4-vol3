"""Ideas en tendencia: lo que funciona HOY en el nicho, leído de verdad, convertido en una idea original.

1. En vivo: los vídeos del nicho más vistos de la última semana (YouTube, 100 unidades del cupo diario).
2. «Inspirarme»: se leen sus subtítulos (gratis, sin descargar el vídeo) y se propone una idea ORIGINAL para el
   canal —otro juego, otro caso u otro ángulo, nunca la misma— con todo lo que hace falta para ejecutarla bien:
   de qué trata el original y en qué orden, el gancho, la estructura y los datos y momentos visuales clave.
"""

from __future__ import annotations

import logging
from typing import Any

from . import aprender, canales, registro, tendencias, youtube

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
    """El detalle para «Datos que no pueden faltar»: lo que el guionista recibe como material prioritario."""
    f = d.get("fuente") or {}
    lineas = [f"Inspirada en «{f.get('titulo', '')}» ({f.get('canal', '')}), sin copiarla: {d.get('por_que', '')}",
              f"De qué trata el original: {d.get('original', '')}", f"Gancho: {d.get('gancho', '')}",
              "Estructura: " + " → ".join(d.get("estructura") or [])]
    lineas += [f"- {x}" for x in d.get("detalles") or []]
    return "\n".join(x for x in lineas if x.split(":", 1)[-1].strip())
