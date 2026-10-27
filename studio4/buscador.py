"""Biblioteca con chat: pides guiones en lenguaje normal («misterios del mar», «mitos nórdicos poco contados») y el
estudio busca en las BASES (las fuentes de tu canal + bases abiertas y gratis), y propone guiones con su gancho y
las fuentes reales de donde saldría cada dato. Nada se inventa: cada propuesta cita solo fuentes que se encontraron.

Bases abiertas (sin clave ni pago): Wikipedia (es/en), Wikisource (textos antiguos de dominio público: crónicas,
mitos), Internet Archive y Project Gutenberg (libros antiguos).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

import requests

from . import canales, config, deepseek

logger = logging.getLogger("studio4.buscador")
CABECERAS = {"User-Agent": "Studio4/1.0 (buscador de guiones; uso personal)"}
MAX_HISTORIA = 30
_cerrojo = threading.Lock()

BASES_ABIERTAS = [
    {"id": "wikipedia", "nombre": "Wikipedia (español e inglés)", "para": "hechos, fechas y contexto"},
    {"id": "wikisource", "nombre": "Wikisource", "para": "crónicas y mitos antiguos en su texto original"},
    {"id": "archive", "nombre": "Internet Archive", "para": "libros, documentos y periódicos antiguos"},
    {"id": "gutenberg", "nombre": "Project Gutenberg", "para": "clásicos de dominio público (mitología, historia)"},
]


def _archivo(cid: str):
    c = config.PRODUCCIONES / "_canales" / cid
    c.mkdir(parents=True, exist_ok=True)
    return c / "biblioteca_chat.json"


def leer(cid: str) -> dict[str, Any]:
    f = _archivo(cid)
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return {"chat": d.get("chat", []), "guardadas": d.get("guardadas", [])}


def _escribir(cid: str, d: dict[str, Any]) -> None:
    _archivo(cid).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def bases(cid: str) -> dict[str, Any]:
    return {"canal": canales.obtener(cid).get("fuentes") or [], "abiertas": BASES_ABIERTAS}


def guardar_bases(cid: str, urls: list[str]) -> list[str]:
    c = canales.guardar({"id": cid, "fuentes": [str(u).strip() for u in urls if str(u).strip()]})
    return c["fuentes"]


# --- búsqueda en las bases abiertas --------------------------------------------------------------------------------
def _mediawiki(sitio: str, consulta: str, n: int) -> list[dict[str, str]]:
    r = requests.get(f"https://{sitio}/w/api.php", headers=CABECERAS, timeout=20, params={
        "action": "query", "list": "search", "srsearch": consulta, "srlimit": n, "format": "json"})
    r.raise_for_status()
    return [{"base": sitio, "titulo": x["title"], "resumen": re.sub(r"<[^>]+>", "", x.get("snippet", ""))[:240],
             "url": f"https://{sitio}/wiki/{x['title'].replace(' ', '_')}"} for x in r.json().get("query", {}).get("search", [])]


def _archive(consulta: str, n: int) -> list[dict[str, str]]:
    r = requests.get("https://archive.org/advancedsearch.php", headers=CABECERAS, timeout=20, params={
        "q": f"({consulta}) AND mediatype:texts", "fl[]": ["identifier", "title", "year"], "rows": n, "output": "json"})
    r.raise_for_status()
    return [{"base": "archive.org", "titulo": f"{x.get('title', '')} ({x.get('year', 's. f.')})"[:160], "resumen": "",
             "url": f"https://archive.org/details/{x['identifier']}"} for x in r.json().get("response", {}).get("docs", [])]


def _gutenberg(consulta: str, n: int) -> list[dict[str, str]]:
    r = requests.get("https://gutendex.com/books", headers=CABECERAS, timeout=20, params={"search": consulta})
    r.raise_for_status()
    return [{"base": "gutenberg.org", "titulo": f"{x['title']} · {', '.join(a['name'] for a in x.get('authors', [])[:1])}"[:160],
             "resumen": "", "url": f"https://www.gutenberg.org/ebooks/{x['id']}"} for x in r.json().get("results", [])[:n]]


def buscar_en_bases(consultas: list[str]) -> list[dict[str, str]]:
    """Lo que hay en las bases abiertas sobre las consultas (lo que falle se salta: nunca bloquea)."""
    hallado: list[dict[str, str]] = []
    for q in consultas[:3]:
        for fn in (lambda: _mediawiki("es.wikipedia.org", q, 4), lambda: _mediawiki("en.wikipedia.org", q, 3),
                   lambda: _mediawiki("es.wikisource.org", q, 2), lambda: _archive(q, 2), lambda: _gutenberg(q, 2)):
            try:
                hallado += fn()
            except Exception as e:  # noqa: BLE001 - una base caída no frena las demás
                logger.info("Base sin respuesta (%s): %s", q, e)
    vistos, unicos = set(), []
    for h in hallado:
        if h["url"] not in vistos:
            vistos.add(h["url"])
            unicos.append(h)
    return unicos[:30]


SISTEMA_CONSULTAS = """Eres el documentalista de un canal de YouTube. Convierte lo que pide el autor en 3 búsquedas
cortas para bases como Wikipedia o Wikisource (2-5 palabras cada una; mezcla español e inglés si ayuda).
Devuelve JSON: {"consultas": ["...", "...", "..."]}"""

SISTEMA_IDEAS = """Eres el jefe de guiones de un canal de YouTube. Con lo que pide el autor, la identidad del canal y
lo ENCONTRADO en las bases, propón de 4 a 6 guiones distintos. Reglas: cada idea sale de lo encontrado y cita SOLO
urls de esa lista (nunca inventes fuentes); el protagonista es el caso, el mito o el juego, no personas desconocidas;
gancho de 1 frase con un dato concreto; nada de clichés de IA. Devuelve JSON:
{"respuesta": "1-2 frases para el autor", "ideas": [{"titulo": "máx. 70 caracteres", "gancho": "primera frase del
vídeo", "angulo": "qué lo hace distinto en 1 frase", "formato": "corto|largo", "fuentes": ["url", "..."]}]}"""


def conversar(cid: str, mensaje: str) -> dict[str, Any]:
    """Un mensaje del chat de la Biblioteca → búsqueda en las bases → propuestas de guion con sus fuentes."""
    mensaje = (mensaje or "").strip()[:600]
    if not mensaje:
        raise ValueError("Escribe qué guiones buscas.")
    if not deepseek.disponible():
        raise ValueError("El chat de la Biblioteca necesita DeepSeek conectado.")
    canal = canales.obtener(cid)
    d = leer(cid)
    previos = "\n".join(f"{m['quien']}: {m['texto']}" for m in d["chat"][-6:])
    consultas = deepseek.generar_json(SISTEMA_CONSULTAS, f"CONVERSACIÓN:\n{previos}\n\nPIDE: {mensaje}",
                                      temperatura=0.3, detalle="biblioteca: búsquedas").get("consultas") or [mensaje]
    hallado = buscar_en_bases([str(q)[:80] for q in consultas])
    propias = [{"base": "tu canal", "titulo": u, "resumen": "fuente de confianza del canal", "url": u} for u in canal.get("fuentes") or []]
    encontrado = hallado + propias
    lista = "\n".join(f"- [{h['base']}] {h['titulo']} — {h['resumen']} ({h['url']})" for h in encontrado)
    identidad = f"Canal {canal['nombre']}: {canal.get('nicho', '')}. Tono: {canal.get('tono', '')}. Público: {canal.get('publico', '')}."
    r = deepseek.generar_json(SISTEMA_IDEAS, f"{identidad}\n\nCONVERSACIÓN:\n{previos}\n\nPIDE: {mensaje}\n\nENCONTRADO EN LAS BASES:\n{lista}",
                              temperatura=0.7, detalle="biblioteca: propuestas")
    validas = {h["url"] for h in encontrado}
    ideas = []
    for k, i in enumerate(r.get("ideas") or []):
        fuentes = [u for u in (i.get("fuentes") or []) if u in validas]
        if not fuentes:   # una idea sin fuente encontrada no se propone
            continue
        ideas.append({"id": f"{int(time.time())}{k}", "titulo": str(i.get("titulo", ""))[:100], "gancho": str(i.get("gancho", ""))[:240],
                      "angulo": str(i.get("angulo", ""))[:200], "formato": "largo" if i.get("formato") == "largo" else "corto",
                      "fuentes": fuentes[:4]})
    ahora = time.strftime("%H:%M")
    respuesta = str(r.get("respuesta") or "").strip() or (f"{len(ideas)} guiones posibles." if ideas else "No encontré nada sólido sobre eso.")
    with _cerrojo:
        d = leer(cid)
        d["chat"] = (d["chat"] + [{"quien": "tú", "texto": mensaje, "hora": ahora},
                                  {"quien": "IA", "texto": respuesta, "hora": ahora, "ideas": ideas,
                                   "bases": sorted({h["base"] for h in hallado})}])[-MAX_HISTORIA:]
        _escribir(cid, d)
    return {"respuesta": respuesta, "ideas": ideas}


def _idea(cid: str, idea_id: str) -> dict[str, Any]:
    d = leer(cid)
    for i in d["guardadas"] + [i for m in d["chat"] for i in (m.get("ideas") or [])]:
        if i["id"] == idea_id:
            return i
    raise ValueError("Esa propuesta ya no está.")


def guardar_idea(cid: str, idea_id: str) -> None:
    with _cerrojo:
        i = _idea(cid, idea_id)
        d = leer(cid)
        if not any(x["id"] == idea_id for x in d["guardadas"]):
            d["guardadas"].append(i)
            _escribir(cid, d)


def quitar_idea(cid: str, idea_id: str) -> None:
    with _cerrojo:
        d = leer(cid)
        d["guardadas"] = [x for x in d["guardadas"] if x["id"] != idea_id]
        _escribir(cid, d)


def crear_video(cid: str, idea_id: str) -> str:
    """La propuesta → vídeo nuevo: la IA escribe el guion con esas fuentes delante (y busca material si hace falta)."""
    from . import montaje
    i = _idea(cid, idea_id)
    tema = f"{i['titulo']}. Ángulo: {i['angulo']}. Gancho: {i['gancho']}"
    return montaje.crear_con_ia(tema, {"duracion": 300 if i["formato"] == "largo" else 60, "fuentes": i["fuentes"],
                                       "formato": "16:9"})
