"""Fuentes de confianza de cada canal (p. ej. gtabase.com/gta-6/ para un canal de videojuegos).

Al investigar un tema, STUDIO busca en esas webs las páginas que hablan de él y pasa sus datos al guion como
material de primera mano, citando de dónde sale cada cosa. Con respeto por el sitio:
- se obedece su robots.txt (nunca se entra en lo que bloquea, como su buscador interno);
- las páginas se encuentran por su mapa del sitio (sitemap) y por los enlaces de la sección, sin rastrear todo;
- como mucho 1 petición por segundo y 4 páginas por investigación; el índice se guarda 24 h.
"""

from __future__ import annotations

import html
import os
import json
import logging
import re
import time
import unicodedata
import urllib.parse
import urllib.robotparser
from typing import Any

import requests
from pydantic import BaseModel, Field

from . import config, gemini

logger = logging.getLogger("studio4.fuentes")

AGENTE = "Mozilla/5.0 (compatible; STUDIO4-investigacion; uso personal)"
PAGINAS_POR_TEMA = 4
MAX_URLS_INDICE = 4000
CADUCA = 24 * 3600
_ultima_peticion = 0.0
_robots: dict[str, urllib.robotparser.RobotFileParser] = {}


def _cache():
    return config.PRODUCCIONES / "_fuentes"


def _get(url: str) -> requests.Response:
    """GET pausado (1 por segundo) y solo si el robots.txt del sitio lo permite."""
    global _ultima_peticion
    partes = urllib.parse.urlparse(url)
    base = f"{partes.scheme}://{partes.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(f"{base}/robots.txt", headers={"User-Agent": AGENTE}, timeout=15)
            rp.parse(r.text.splitlines() if r.ok else [])
        except requests.RequestException:
            rp.parse([])
        _robots[base] = rp
    if not _robots[base].can_fetch(AGENTE, url):
        raise PermissionError(f"El robots.txt de {partes.netloc} no permite leer {partes.path}")
    espera = 1.0 - (time.time() - _ultima_peticion)
    if espera > 0:
        time.sleep(espera)
    _ultima_peticion = time.time()
    r = requests.get(url, headers={"User-Agent": AGENTE}, timeout=20)
    r.raise_for_status()
    return r


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def indice(fuente: str) -> list[str]:
    """Las páginas de la fuente (mismo sitio y dentro de su ruta), por su sitemap y por los enlaces de la sección.
    Se guarda 24 h."""
    partes = urllib.parse.urlparse(fuente)
    prefijo = partes.path if partes.path.endswith("/") else partes.path + "/"
    archivo = _cache() / (re.sub(r"[^\w.-]+", "_", partes.netloc + prefijo) + ".json")
    try:
        d = json.loads(archivo.read_text(encoding="utf-8"))
        if time.time() - d["t"] < CADUCA:
            return d["urls"]
    except (OSError, ValueError, KeyError):
        pass
    base = f"{partes.scheme}://{partes.netloc}"
    urls: set[str] = set()

    def enlaces(pagina: str) -> set[str]:
        try:
            texto = _get(pagina).text
        except (requests.RequestException, PermissionError) as e:
            logger.info("Fuente %s: %s", pagina, e)
            return set()
        hallados = set()
        for h in re.findall(r'href="([^"#?]+)"', texto):
            u = urllib.parse.urljoin(base, h)
            if urllib.parse.urlparse(u).netloc == partes.netloc and urllib.parse.urlparse(u).path.startswith(prefijo):
                hallados.add(u.rstrip("/"))
        return hallados

    # 1) Mapa del sitio (si lo declara su robots.txt): solo las URL de la sección.
    try:
        robots = _get(f"{base}/robots.txt").text
        for mapa in re.findall(r"(?im)^sitemap:\s*(\S+)", robots)[:2]:
            hijos = re.findall(r"<loc>([^<]+)</loc>", _get(mapa).text)
            for loc in hijos[:15]:
                if loc.endswith(".xml"):
                    for u in re.findall(r"<loc>([^<]+)</loc>", _get(loc).text):
                        if urllib.parse.urlparse(u).path.startswith(prefijo):
                            urls.add(u.rstrip("/"))
                elif urllib.parse.urlparse(loc).path.startswith(prefijo):
                    urls.add(loc.rstrip("/"))
                if len(urls) >= MAX_URLS_INDICE:
                    break
    except (requests.RequestException, PermissionError) as e:
        logger.info("Sin sitemap en %s: %s", partes.netloc, e)
    # 2) La portada de la sección y sus apartados (por si el sitemap no los tiene todos).
    secciones = enlaces(fuente)
    urls |= secciones
    if len(urls) < 200:
        for s in sorted(secciones)[:20]:
            urls |= enlaces(s)
    lista = sorted(u for u in urls if "?" not in u and "&" not in u)[:MAX_URLS_INDICE]   # sin comparadores ni filtros
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps({"t": time.time(), "urls": lista}), encoding="utf-8")
    return lista


class Claves(BaseModel):
    claves: list[str] = Field(description="3 a 8 palabras clave en inglés y nombres propios del tema, en minúsculas.")


def claves(idea: str, produccion: str = "") -> list[str]:
    """Palabras para buscar en webs en inglés: la idea traducida y sus nombres propios."""
    crudo = gemini.generar(f"Tema de un vídeo: {idea}\nDame las palabras clave para encontrar páginas sobre él en una web "
                           "de videojuegos en inglés (nombres de juegos, personajes, lugares, vehículos, misiones).",
                           esquema=Claves, temperatura=0.1, detalle="claves de búsqueda en fuentes", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    salida = [_normal(c).strip() for c in Claves.model_validate_json(m.group(0) if m else crudo).claves if c.strip()]
    return salida + [w for w in re.findall(r"[a-z0-9]{3,}", _normal(idea)) if w not in salida]


def elegir(urls: list[str], palabras: list[str], n: int = PAGINAS_POR_TEMA) -> list[str]:
    """Las URL cuyo nombre más se parece al tema (cada palabra clave que aparece en la ruta suma)."""
    puntos = []
    rutas = [urllib.parse.unquote(urllib.parse.urlparse(u).path) for u in urls]
    comun = re.sub(r"[^/]*$", "", os.path.commonprefix(rutas)) if len(rutas) > 1 else ""   # «/gta-6/» no distingue
    for u, r in zip(urls, rutas):
        ruta = " " + _normal(r[len(comun):]).replace("-", " ").replace("_", " ").replace("/", " ") + " "
        p = sum((2 if " " in k else 1) for k in palabras if k and k in ruta)
        if p:
            puntos.append((p, -len(ruta), u))
    return [u for _, _, u in sorted(puntos, reverse=True)[:n]]


def texto_de(url: str) -> str:
    t = _get(url).text
    cuerpo = re.search(r"(?is)<(main|article)[^>]*>(.*?)</\1>", t)
    t = cuerpo.group(2) if cuerpo else t
    t = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header|aside|form)[^>]*>.*?</\1>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))).strip()[:9000]


DATOS = """Extrae de estas páginas los datos útiles para un guion de vídeo sobre el tema: hechos, nombres, lugares,
fechas, cifras y detalles concretos. En español, en viñetas breves, cada una terminada con [n] (el número de la página
de donde sale). Máximo 20 viñetas. Solo lo que dicen las páginas; nada inventado."""


def investigar(idea: str, fuentes: list[str], produccion: str = "", paginas: int = PAGINAS_POR_TEMA) -> dict[str, Any]:
    """{texto, fuentes: [{titulo, url}]} con lo que dicen las fuentes del canal sobre la idea (vacío si nada encaja)."""
    if not fuentes:
        return {"texto": "", "fuentes": []}
    palabras = claves(idea, produccion)
    elegidas: list[str] = []
    for f in fuentes:
        try:
            elegidas += elegir(indice(f), palabras, n=paginas)
        except Exception as e:  # noqa: BLE001 - una fuente caída no frena la investigación
            logger.warning("Fuente %s: %s", f, e)
    paginas = []
    for u in elegidas[:paginas]:
        try:
            paginas.append((u, texto_de(u)))
        except Exception as e:  # noqa: BLE001
            logger.info("No pude leer %s: %s", u, e)
    paginas = [(u, t) for u, t in paginas if len(t) > 300]
    if not paginas:
        return {"texto": "", "fuentes": []}
    material = "\n\n".join(f"--- PÁGINA [{i}] {u} ---\n{t}" for i, (u, t) in enumerate(paginas, 1))
    texto = gemini.generar(f"TEMA: {idea}\n\n{DATOS}\n\n{material}", temperatura=0.2, detalle="datos de tus fuentes",
                           produccion=produccion)
    return {"texto": texto.strip(),
            "fuentes": [{"titulo": urllib.parse.urlparse(u).path.strip("/").split("/")[-1].replace("-", " "), "url": u}
                        for u, _ in paginas]}
