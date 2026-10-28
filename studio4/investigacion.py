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
CABECERAS = {"User-Agent": "STUDIO4-Vol3/1.0 (investigacion de guiones; uso personal; https://github.com/)"}


def _wiki_get(url: str, params: dict[str, Any]) -> requests.Response:
    """Wikipedia contesta 429 (demasiadas peticiones) o 503 (ocupada) si se le pide rápido: se espera lo que pida
    (Retry-After) y se reintenta hasta 4 veces, en vez de dar el tema por perdido."""
    import time
    for intento in range(4):
        r = requests.get(url, headers=CABECERAS, timeout=20, params={**params, "maxlag": 5})
        if r.status_code not in (429, 503):
            r.raise_for_status()
            return r
        espera = r.headers.get("Retry-After", "")
        time.sleep(min(30, int(espera)) if espera.isdigit() else 2 * (intento + 1) ** 2)
    r.raise_for_status()
    return r
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
    r = _wiki_get(f"https://{lang}.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": consulta, "srlimit": n, "format": "json"})
    return [x["title"] for x in r.json().get("query", {}).get("search", [])]


def _articulo(lang: str, titulo: str) -> dict[str, str] | None:
    r = _wiki_get(f"https://{lang}.wikipedia.org/w/api.php", {
        "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": titulo, "format": "json"})
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


# --- Búsqueda web de DeepSeek (Search & Fetch). De pago (~0,75 $ / 1.000 llamadas): solo con STUDIO4_BUSQUEDA_WEB=1 ---
DEEPSEEK_TOOLS = "https://api.deepseek.com/v1/tools"
MIN_AUTORIDAD, MIN_RELEVANCIA = 2, 1.5


def _deepseek_tool(nombre: str, cuerpo: dict[str, Any], produccion: str) -> dict[str, Any]:
    r = requests.post(f"{DEEPSEEK_TOOLS}/{nombre}", json=cuerpo, timeout=45,
                      headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"})
    r.raise_for_status()
    registro.apuntar("DeepSeek (búsqueda web)", f"{nombre}", cantidad=1, unidad="llamadas", produccion=produccion)
    return r.json()


def _con_deepseek_web(idea: str, produccion: str) -> dict[str, Any]:
    """Busca en toda la web con la API de DeepSeek, se queda con las fuentes de autoridad, lee las mejores enteras y
    arma el dossier SOLO con ellas (citando [F1]…), como con Wikipedia."""
    crudo = gemini.generar(
        f"Tema de un vídeo de videojuegos: {idea}\n\nDame 3 búsquedas web para encontrar datos oficiales y verificables "
        "(webs oficiales, wikis del juego, prensa de videojuegos). Responde solo JSON: {\"consultas\": [\"...\", \"...\", \"...\"]}",
        temperatura=0.2, detalle="consultas web", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    consultas = (json.loads(m.group(0) if m else crudo).get("consultas") or [idea])[:3]
    fuentes: list[dict[str, Any]] = []
    for q in consultas:
        res = _deepseek_tool("search", {"query": str(q)[:128], "count": 8, "need_content": True}, produccion)
        for x in res.get("results") or []:
            if (float(x.get("rerank_score") or 0) >= MIN_RELEVANCIA and int(x.get("authority") or 0) >= MIN_AUTORIDAD
                    and x.get("url") and all(f["url"] != x["url"] for f in fuentes)):
                fuentes.append(x)
    fuentes.sort(key=lambda x: (-int(x.get("authority") or 0), -float(x.get("rerank_score") or 0)))
    fuentes = fuentes[:6]
    for f in fuentes[:2]:   # las dos mejores, enteras
        if len(f.get("content") or "") < 1500:
            try:
                f["content"] = _deepseek_tool("fetch", {"url": f["url"]}, produccion).get("content") or f.get("content", "")
            except requests.RequestException as e:
                logger.warning("Fetch %s: %s", f["url"], e)
    if not fuentes:
        raise RuntimeError("La búsqueda web no devolvió fuentes con autoridad suficiente.")
    fuentes_txt = "\n\n".join(f"### FUENTE {i}: {f.get('title', '')} ({f['url']})\n{(f.get('content') or f.get('summary') or '')[:MAX_CARACTERES_ARTICULO]}"
                              for i, f in enumerate(fuentes, 1))
    dossier = gemini.generar(
        f"Tema: {idea}\n\nArma el dossier usando SOLO estas fuentes; al final de cada hecho indica [F1], [F2]...\n\n{fuentes_txt}",
        sistema=SISTEMA, temperatura=0.3, detalle="dossier de investigación (web)", produccion=produccion)
    return {"dossier": dossier.strip(), "fuentes": [{"titulo": f.get("title", ""), "url": f["url"]} for f in fuentes],
            "metodo": "DeepSeek (web)"}


def investigar(idea: str, produccion: str = "") -> dict[str, Any]:
    if config.BUSQUEDA_WEB and config.DEEPSEEK_API_KEY:   # toda la web, fuentes con autoridad (de pago, activado a mano)
        try:
            return _con_deepseek_web(idea, produccion)
        except Exception as e:  # noqa: BLE001 - sin saldo, red, sin resultados: sigue lo gratis
            logger.info("Búsqueda web de DeepSeek no disponible (%s): sigo con Google/Wikipedia.", str(e)[:120])
    if gemini.bloqueado() or not config.GEMINI_API_KEY:   # Gemini en pausa: directo a Wikipedia (con la reserva)
        return _con_wikipedia(idea, produccion)
    try:
        return _con_google(idea, produccion)
    except Exception as e:  # noqa: BLE001 - 429 sin facturación, modelo sin búsqueda, red...
        logger.info("Búsqueda de Google no disponible (%s): investigo en Wikipedia.", str(e)[:120])
    return _con_wikipedia(idea, produccion)
