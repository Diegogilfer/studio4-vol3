"""Fase 0 · Investigación: hechos comprobables, cifras, nombres, fechas y ángulos poco conocidos, con fuentes.
DeepSeek escribe a partir de esto: así el guion cuenta cosas concretas y verdaderas, no generalidades de IA.

1. Búsqueda de Google desde Gemini, si tu proyecto la tiene (en el nivel gratis sin facturación da 429).
2. Si no, Wikipedia (gratis, sin clave): Gemini decide qué buscar, se descargan los artículos en español
   e inglés y Gemini arma el dossier SOLO con lo que dicen, citándolos.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from google.genai import types

from . import config, gemini, registro

logger = logging.getLogger("studio4.investigacion")
CABECERAS = {"User-Agent": "STUDIO4-Vol3/1.0 (investigacion de guiones; uso personal)"}
MAX_CARACTERES_ARTICULO = 12000

SISTEMA = """Eres documentalista de un canal de divulgación. Entrega un dossier en español, en texto plano,
con estos apartados:

HECHOS CLAVE: 8-15 hechos concretos y comprobables (cifras, fechas, nombres, lugares, mecanismos).
LO QUE CASI NADIE SABE: 3-5 datos sorprendentes o contraintuitivos, con su porqué.
MITOS Y ERRORES COMUNES: lo que la gente cree y no es así.
HISTORIA O CASO REAL: una anécdota concreta (personas, lugar, momento) que sirva de hilo narrativo.
IMÁGENES POTENTES: momentos o detalles muy visuales que se podrían filmar.
DUDAS: lo que no está claro o las fuentes discuten (para no afirmarlo como cierto).

No inventes. Si un dato no aparece en las fuentes, no lo pongas."""


def _con_google(idea: str, produccion: str) -> dict[str, Any]:
    cfg = types.GenerateContentConfig(system_instruction=SISTEMA, temperature=0.3,
                                      tools=[types.Tool(google_search=types.GoogleSearch())])
    r = gemini.cliente().models.generate_content(model=config.MODELO_TEXTO, contents=f"Tema: {idea}", config=cfg)
    texto = (r.text or "").strip()
    if not texto:
        raise RuntimeError("la búsqueda de Google devolvió una respuesta vacía")
    fuentes: list[dict[str, str]] = []
    meta = getattr(r.candidates[0], "grounding_metadata", None)
    for trozo in (getattr(meta, "grounding_chunks", None) or []):
        web = getattr(trozo, "web", None)
        if web and web.uri and not any(f["url"] == web.uri for f in fuentes):
            fuentes.append({"titulo": web.title or web.uri, "url": web.uri})
    registro.apuntar("Gemini + Google (investigación)", f"{len(fuentes)} fuentes", produccion=produccion)
    return {"dossier": texto, "fuentes": fuentes[:15], "metodo": "Búsqueda de Google"}


def _buscar_wikipedia(lang: str, consulta: str, n: int = 2) -> list[str]:
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=CABECERAS, timeout=20, params={
        "action": "query", "list": "search", "srsearch": consulta, "srlimit": n, "format": "json"})
    r.raise_for_status()
    return [x["title"] for x in r.json().get("query", {}).get("search", [])]


def _articulo(lang: str, titulo: str) -> dict[str, str] | None:
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=CABECERAS, timeout=20, params={
        "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": titulo, "format": "json"})
    r.raise_for_status()
    for pagina in r.json().get("query", {}).get("pages", {}).values():
        texto = re.sub(r"\n{3,}", "\n\n", pagina.get("extract") or "").strip()
        if len(texto) > 400:
            return {"titulo": f"{pagina['title']} (Wikipedia {lang})", "texto": texto[:MAX_CARACTERES_ARTICULO],
                    "url": f"https://{lang}.wikipedia.org/wiki/{pagina['title'].replace(' ', '_')}"}
    return None


def _con_wikipedia(idea: str, produccion: str) -> dict[str, Any]:
    crudo = gemini.generar(
        f"Tema de un vídeo: {idea}\n\nDame las consultas para buscar en Wikipedia los artículos que más datos aportan. "
        'Responde solo JSON: {"es": ["consulta 1", "consulta 2"], "en": ["query 1", "query 2"]}. Consultas cortas (1-4 palabras).',
        temperatura=0.2, detalle="consultas de investigación", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    consultas = json.loads(m.group(0) if m else crudo)

    articulos: list[dict[str, str]] = []
    for lang in ("es", "en"):
        for consulta in (consultas.get(lang) or [])[:2]:
            try:
                for titulo in _buscar_wikipedia(lang, consulta):
                    if any(a["url"].endswith(titulo.replace(" ", "_")) for a in articulos):
                        continue
                    art = _articulo(lang, titulo)
                    if art:
                        articulos.append(art)
            except requests.RequestException as e:
                logger.warning("Wikipedia %s «%s»: %s", lang, consulta, e)
            if len(articulos) >= 5:
                break
    if not articulos:
        raise RuntimeError("Wikipedia no devolvió artículos útiles para este tema.")

    fuentes_txt = "\n\n".join(f"### FUENTE {i}: {a['titulo']}\n{a['texto']}" for i, a in enumerate(articulos, 1))
    dossier = gemini.generar(
        f"Tema: {idea}\n\nArma el dossier usando SOLO estas fuentes; al final de cada hecho indica [F1], [F2]...\n\n{fuentes_txt}",
        sistema=SISTEMA, temperatura=0.3, detalle="dossier de investigación", produccion=produccion)
    registro.apuntar("Wikipedia (investigación)", f"{len(articulos)} artículos", unidad="artículos",
                     cantidad=len(articulos), produccion=produccion)
    return {"dossier": dossier.strip(), "fuentes": [{"titulo": a["titulo"], "url": a["url"]} for a in articulos],
            "metodo": "Wikipedia"}


def investigar(idea: str, produccion: str = "") -> dict[str, Any]:
    try:
        return _con_google(idea, produccion)
    except Exception as e:  # noqa: BLE001 - 429 sin facturación, modelo sin búsqueda, red...
        logger.info("Búsqueda de Google no disponible (%s): investigo en Wikipedia.", str(e)[:120])
    return _con_wikipedia(idea, produccion)
