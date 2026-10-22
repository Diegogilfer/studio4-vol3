"""Material primero: antes de escribir un guion, qué clips reales existen del tema.

El guion sale de donde salen las imágenes. Studio decide qué juegos y escenas pide el tema, busca en YouTube
(yt-dlp, gratis y sin gastar cuota de la API) tráilers oficiales y gameplay sin comentario, y descarta los vídeos
de análisis, reacciones o listas de otros canales (su trabajo y su voz no se usan). Lo que queda es el inventario:
el guionista solo cuenta lo que se puede enseñar con él, y el paso Material lo ofrece con un clic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import extractor, gemini

logger = logging.getLogger("studio4.material")

# Títulos que delatan el trabajo de otro creador (análisis, reacción, listas, teorías) o material con voz encima
FUERA = re.compile(
    r"\b(reacci[oó]n|reaccion|react(s|ing|ion)?|an[aá]lisis|analysis|explicad[oa]|explained|teor[ií]as?|theor(y|ies)|"
    r"detalles|details|secretos|secrets|curiosidades|easter eggs?|top \d+|\d+ (cosas|things|detalles|details)|"
    r"review|rese[ñn]a|opini[oó]n|podcast|noticias|news|rumou?rs?|rumores|leaks?|filtraci[oó]n|vs\.?|versus|"
    r"comparaci[oó]n|comparison|everything|todo lo que|lo que (nadie|no)|why|por qu[eé]|ranking|tier list|"
    r"what happens|qu[eé] pasa si|for me|my (favou?rite|first|thoughts)|mi (opini[oó]n|favorito)|meme|funny|gracioso|fails?|shorts?|tiktok|en vivo|live|stream|directo|parodia|parody|fan ?made|concept|mod)\b",
    re.IGNORECASE)
# Lo que buscamos: material original del juego, sin voz de nadie
BUENO = re.compile(r"\b(tr[aá]iler|trailer|gameplay|walkthrough|no commentary|sin comentarios?|longplay|full game|"
                   r"juego completo|cinem[aá]tica|cinematic|cutscenes?|intro|mission|misi[oó]n|4k|60 ?fps)\b", re.IGNORECASE)
SIN_VOZ = re.compile(r"no comment(ary)?|sin comentarios?|longplay|cutscenes?|cinem[aá]tic|movie|pel[ií]cula", re.IGNORECASE)
OFICIAL = re.compile(r"official|oficial", re.IGNORECASE)
CANALES_OFICIALES = re.compile(r"^(rockstar games|playstation|xbox|nintendo|ubisoft|ea|bethesda|capcom|bandai namco|"
                               r"square enix|sega|cd projekt red|naughty dog|insomniac games|ign|gamespot|the game awards)",
                               re.IGNORECASE)

SISTEMA = """Eres el documentalista visual de un canal de videojuegos. Para el tema que te den, di qué material
de vídeo REAL hace falta para enseñarlo: qué juegos (título exacto y año) y qué escenas o misiones concretas.
Devuelve solo JSON:
{"escenas": [{"juego": "...", "que": "escena, misión o momento concreto", "busqueda": "consulta para YouTube"}]}
Reglas: 4-10 escenas, en el orden en que el vídeo las necesitaría. La consulta busca material original: el tráiler
oficial («<juego> official trailer») o gameplay sin comentario («<juego> <misión> gameplay no commentary»), en inglés.
Nunca busques análisis, reacciones, listas ni vídeos de otros creadores. Si el tema es inventado (una secuela
que no existe, un «qué pasaría si»), pide el material de los juegos reales de los que habla."""


def _segundos(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def apto(v: dict[str, Any]) -> bool:
    """¿Es material original (tráiler o gameplay) y no el vídeo de otro creador?"""
    titulo, canal = str(v.get("titulo", "")), str(v.get("canal", ""))
    if FUERA.search(titulo):
        return False
    d = _segundos(v.get("duracion"))
    if d and d < 25:   # Shorts y clips sueltos
        return False
    return bool(BUENO.search(titulo) or CANALES_OFICIALES.match(canal.strip()))


def puntos(v: dict[str, Any]) -> int:
    """Orden dentro de una escena: oficial y sin voz primero."""
    titulo, canal = str(v.get("titulo", "")), str(v.get("canal", "")).strip()
    return (3 * bool(CANALES_OFICIALES.match(canal)) + 2 * bool(OFICIAL.search(titulo)) + 2 * bool(SIN_VOZ.search(titulo))
            + bool(re.search(r"4k|2160|1080", titulo, re.IGNORECASE))
            - 2 * bool(re.search(r"mobile|android|ios|psp|m[oó]vil", titulo, re.IGNORECASE)))   # peor imagen


def buscar(consulta: str, n: int = 8) -> list[dict[str, Any]]:
    """Resultados de YouTube para una consulta (sin descargar nada)."""
    import yt_dlp
    with yt_dlp.YoutubeDL(extractor.opciones_ytdlp(extract_flat=True, skip_download=True)) as y:
        info = y.extract_info(f"ytsearch{n}:{consulta}", download=False) or {}
    salida = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        salida.append({"id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}", "titulo": e.get("title") or "",
                       "canal": e.get("channel") or e.get("uploader") or "", "duracion": _segundos(e.get("duration"))})
    return salida


def escenas(tema: str, dossier: str = "", produccion: str = "") -> list[dict[str, str]]:
    """Qué juegos y escenas pide el tema (Gemini, gratis). Si no responde, una búsqueda con el tema tal cual."""
    try:
        crudo = gemini.generar(f"TEMA: {tema}\n\nLO QUE SE SABE DEL TEMA:\n{dossier[:6000]}\n\nResponde solo con el JSON.",
                               sistema=SISTEMA, temperatura=0.3, detalle="material del tema", produccion=produccion)
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        lista = json.loads(m.group(0) if m else crudo).get("escenas") or []
        lista = [{"juego": str(e.get("juego", "")).strip()[:80], "que": str(e.get("que", "")).strip()[:160],
                  "busqueda": str(e.get("busqueda", "")).strip()[:120]} for e in lista if isinstance(e, dict) and e.get("busqueda")]
        if lista:
            return lista[:10]
    except (RuntimeError, ValueError) as e:
        logger.warning("Escenas del tema: %s", e)
    return [{"juego": "", "que": tema[:160], "busqueda": f"{tema[:90]} gameplay no commentary"},
            {"juego": "", "que": "tráiler oficial", "busqueda": f"{tema[:90]} official trailer"}]


def inventario(tema: str, dossier: str = "", produccion: str = "", por_escena: int = 3) -> list[dict[str, Any]]:
    """[{juego, que, busqueda, videos: [{id, url, titulo, canal, duracion}]}]: solo material apto, sin repetir vídeos."""
    vistos: set[str] = set()
    salida = []
    for e in escenas(tema, dossier, produccion):
        try:
            resultados = buscar(e["busqueda"])
        except Exception as err:  # noqa: BLE001 - una búsqueda caída no tumba el resto
            logger.warning("Búsqueda «%s»: %s", e["busqueda"], err)
            resultados = []
        buenos = sorted((v for v in resultados if apto(v) and v["id"] not in vistos), key=lambda v: -puntos(v))[:por_escena]
        vistos.update(v["id"] for v in buenos)
        salida.append({**e, "videos": buenos})
    return salida


def para_guion(inv: list[dict[str, Any]]) -> str:
    """El inventario como texto para el guionista: solo se cuenta lo que esto puede enseñar."""
    lineas = []
    for e in inv:
        if not e.get("videos"):
            continue
        cab = " · ".join(x for x in (e.get("juego"), e.get("que")) if x)
        lineas.append(f"- {cab}: " + "; ".join(f"«{v['titulo'][:90]}» ({v['duracion'] // 60} min)" for v in e["videos"]))
    if not lineas:
        return ""
    return ("MATERIAL QUE EXISTE (el vídeo se monta SOLO con esto: cuenta únicamente lo que estas imágenes pueden "
            "enseñar; lo que no salga aquí, quítalo o conviértelo en un dato corto para un panel):\n" + "\n".join(lineas))
