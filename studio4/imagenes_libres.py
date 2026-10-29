"""Imágenes REALES y gratis para cada frase, buscadas en varias fuentes a la vez (no solo Wikimedia): Openverse
(cientos de millones de imágenes con licencia libre), Wikimedia Commons, la Biblioteca del Congreso de EE. UU.
(fotos históricas de dominio público), el Museo Metropolitano (arte de dominio público) y la NASA; y Pixabay si hay
clave (PIXABAY_API_KEY). Cada resultado lleva su licencia, autor y tamaño: solo se usan licencias que permiten uso
comercial (dominio público, CC0, CC BY, CC BY-SA) y se cita el crédito.

Con respeto por cada servicio: una petición a la vez, con pausa, identificándose y reintentando si piden calma.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

import requests

logger = logging.getLogger("studio4.imagenes_libres")
UA = {"User-Agent": "Studio4/1.0 (estudio de video personal; imagenes con licencia libre)"}
LICENCIAS_OK = ("pdm", "cc0", "by", "by-sa", "dominio público", "public domain", "cc by", "cc by-sa", "pixabay")


def _get(url: str, params: dict[str, Any] | None = None, intentos: int = 3, espera: int = 25) -> requests.Response:
    for k in range(intentos):
        r = requests.get(url, params=params, headers=UA, timeout=espera)
        if r.status_code not in (429, 503):
            r.raise_for_status()
            return r
        espera = r.headers.get("Retry-After", "")
        time.sleep(min(20, int(espera)) if espera.isdigit() else 3 * (k + 1))
    r.raise_for_status()
    return r


def _openverse(q: str, n: int) -> list[dict[str, Any]]:
    d = _get("https://api.openverse.org/v1/images/", {"q": q, "license_type": "commercial", "page_size": n, "mature": "false"}, espera=60).json()
    return [{"fuente": "Openverse", "url": x["url"], "miniatura": x.get("thumbnail") or x["url"], "titulo": x.get("title") or "",
             "autor": x.get("creator") or "", "licencia": f"{x.get('license', '')} {x.get('license_version') or ''}".strip(),
             "ancho": x.get("width") or 0, "alto": x.get("height") or 0, "pagina": x.get("foreign_landing_url") or ""}
            for x in d.get("results", [])]


def _commons(q: str, n: int) -> list[dict[str, Any]]:
    d = _get("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": n,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1920, "format": "json"}).json()
    salida = []
    for p in (d.get("query", {}).get("pages", {}) or {}).values():
        i = p["imageinfo"][0]
        m = i.get("extmetadata", {})
        salida.append({"fuente": "Wikimedia Commons", "url": i.get("thumburl") or i["url"], "miniatura": i.get("thumburl") or i["url"],
                       "titulo": p["title"].replace("File:", ""), "autor": re.sub("<[^>]+>", "", m.get("Artist", {}).get("value", ""))[:80].strip(),
                       "licencia": m.get("LicenseShortName", {}).get("value", ""), "ancho": i.get("width") or 0,
                       "alto": i.get("height") or 0, "pagina": i.get("descriptionurl", "")})
    return salida


def _congreso(q: str, n: int) -> list[dict[str, Any]]:
    d = _get("https://www.loc.gov/photos/", {"q": q, "fo": "json", "c": n, "fa": "online-format:image"}).json()
    salida = []
    for x in d.get("results", []):
        imgs = [u for u in (x.get("image_url") or []) if u.startswith("http")]
        if not imgs:
            continue
        salida.append({"fuente": "Biblioteca del Congreso (EE. UU.)", "url": imgs[-1].split("#")[0], "miniatura": imgs[0].split("#")[0],
                       "titulo": x.get("title", ""), "autor": ", ".join(x.get("contributor", [])[:1]) if isinstance(x.get("contributor"), list) else "",
                       "licencia": "Sin restricciones conocidas (LOC)" if "no known restrictions" in str(x.get("rights", "")).lower()
                       else str(x.get("rights", ""))[:60], "ancho": 0, "alto": 0, "pagina": x.get("url", "")})
    return salida


def _met(q: str, n: int) -> list[dict[str, Any]]:
    ids = (_get("https://collectionapi.metmuseum.org/public/collection/v1/search", {"q": q, "hasImages": "true"}).json().get("objectIDs") or [])[:n]
    salida = []
    for i in ids:
        o = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{i}").json()
        if o.get("isPublicDomain") and o.get("primaryImage"):
            salida.append({"fuente": "The Met", "url": o["primaryImage"], "miniatura": o.get("primaryImageSmall") or o["primaryImage"],
                           "titulo": o.get("title", ""), "autor": o.get("artistDisplayName", ""), "licencia": "Dominio público (CC0, The Met)",
                           "ancho": 0, "alto": 0, "pagina": o.get("objectURL", "")})
        time.sleep(0.3)
    return salida


def _nasa(q: str, n: int) -> list[dict[str, Any]]:
    d = _get("https://images-api.nasa.gov/search", {"q": q, "media_type": "image"}).json()
    salida = []
    for x in d.get("collection", {}).get("items", [])[:n]:
        meta = (x.get("data") or [{}])[0]
        enlace = next((l["href"] for l in x.get("links", []) if l.get("render") == "image"), "")
        if enlace:
            salida.append({"fuente": "NASA", "url": enlace.replace("~thumb", "~large"), "miniatura": enlace, "titulo": meta.get("title", ""),
                           "autor": meta.get("photographer") or meta.get("center", "NASA"), "licencia": "Dominio público (NASA)",
                           "ancho": 0, "alto": 0, "pagina": f"https://images.nasa.gov/details/{meta.get('nasa_id', '')}"})
    return salida


def _pixabay(q: str, n: int) -> list[dict[str, Any]]:
    from . import secretos
    clave = secretos.leer("PIXABAY_API_KEY")
    if not clave:
        return []
    d = _get("https://pixabay.com/api/", {"key": clave, "q": q, "image_type": "photo", "per_page": max(3, n), "safesearch": "true"}).json()
    return [{"fuente": "Pixabay", "url": x.get("largeImageURL") or x["webformatURL"], "miniatura": x["previewURL"], "titulo": x.get("tags", ""),
             "autor": x.get("user", ""), "licencia": "Licencia de Pixabay (uso comercial, sin atribución obligatoria)",
             "ancho": x.get("imageWidth") or 0, "alto": x.get("imageHeight") or 0, "pagina": x.get("pageURL", "")} for x in d.get("hits", [])]


def videos_pixabay(q: str, n: int = 4, max_mb: float = 25.0) -> list[dict[str, Any]]:
    """Clips de vídeo de stock gratis (licencia de Pixabay: uso comercial, sin atribución obligatoria). Se elige la
    versión 1080p (o la más cercana) que no pase de `max_mb`."""
    from . import secretos
    clave = secretos.leer("PIXABAY_API_KEY")
    if not clave:
        return []
    d = _get("https://pixabay.com/api/videos/", {"key": clave, "q": q, "per_page": max(3, n), "safesearch": "true"}).json()
    salida = []
    for h in d.get("hits", []):
        versiones = [v for v in h.get("videos", {}).values() if v.get("url") and v.get("size", 0) / 1e6 <= max_mb
                     and v.get("width", 0) >= v.get("height", 1) * 1.3]   # solo horizontales (los verticales no caben en 16:9)
        if not versiones:
            continue
        v = min(versiones, key=lambda v: abs(v.get("height", 0) - 1080))
        salida.append({"fuente": "Pixabay", "url": v["url"], "titulo": h.get("tags", ""), "autor": h.get("user", ""),
                       "licencia": "Licencia de Pixabay (uso comercial, sin atribución obligatoria)", "ancho": v.get("width", 0),
                       "alto": v.get("height", 0), "duracion": h.get("duration", 0), "pagina": h.get("pageURL", ""), "video": True})
    return salida[:n]


FUENTES: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "openverse": _openverse, "commons": _commons, "congreso": _congreso, "met": _met, "nasa": _nasa, "pixabay": _pixabay}


def licencia_ok(c: dict[str, Any]) -> bool:
    l = (c.get("licencia") or "").lower()
    return not re.search(r"\bnc\b|non-?commercial|nd\b|no deriv", l) and any(x in l for x in LICENCIAS_OK + ("sin restricciones",))


POR_DEFECTO = ("pixabay", "commons", "nasa", "openverse")   # la Biblioteca del Congreso (403) y The Met (410) no responden hoy


def buscar(consulta: str, por_fuente: int = 4, fuentes: tuple[str, ...] = POR_DEFECTO) -> list[dict[str, Any]]:
    """Imágenes reales de varias fuentes para una consulta (mejor en inglés), solo con licencia apta, de la más
    grande a la más pequeña. Una fuente que falla se salta: nunca bloquea."""
    hallado: list[dict[str, Any]] = []
    for nombre in fuentes:
        try:
            hallado += FUENTES[nombre](consulta, por_fuente)
        except Exception as e:  # noqa: BLE001 - una fuente caída no frena las demás
            logger.info("Imágenes en %s («%s»): %s", nombre, consulta, e)
        time.sleep(0.6)
    vistas, unicas = set(), []
    for c in hallado:
        if c["url"] not in vistas and licencia_ok(c):
            vistas.add(c["url"])
            unicas.append(c)
    return sorted(unicas, key=lambda c: -(c["ancho"] * c["alto"]))


def credito(c: dict[str, Any]) -> str:
    """El crédito que se pone en la descripción (y que la foto lleva en el marco de archivo)."""
    autor = f"{c['autor']}, " if c.get("autor") else ""
    return f"Foto: {autor}«{c['titulo'][:80]}», {c['licencia']} ({c['fuente']})"
