"""Imágenes de referencia por escena (gratis, sin clave): fotos reales con licencia libre que encajan con lo
que se ve en cada momento de la secuencia. Son la portada de la escena hasta que llega su clip de Flow, y
también sirven como referencia para pegar en Flow.

1. Gemini lee las escenas en orden y escribe una búsqueda corta en inglés para cada una.
2. Se busca en Wikimedia Commons (mejor para hechos y lugares reales) y, si no, en Openverse (Creative Commons).
3. Nunca se repite la misma imagen en dos escenas. Se guarda autor y licencia de cada una.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

import requests

from . import gemini, registro

logger = logging.getLogger("studio4.referencias")
CABECERAS = {"User-Agent": "STUDIO4-Vol3/1.0 (referencias visuales; uso personal)"}
ANCHO = 640
MAXIMO = 3   # referencias por producción: solo las primeras escenas, para dar imagen al estudio


def busquedas(escenas: list[dict[str, Any]], tema: str, produccion: str = "") -> list[str]:
    """Una búsqueda por escena, pensada para encontrar una foto real de ese momento."""
    lista = "\n".join(f"{e['orden']}. Voz: {e['texto_voz']} | Plano: {e.get('accion_en', '')}" for e in escenas)
    crudo = gemini.generar(
        f"Tema del vídeo: {tema}\n\nEscenas en orden:\n{lista}\n\n"
        "Para cada escena escribe una búsqueda de 2 a 5 palabras en inglés para encontrar una FOTO REAL en "
        "Wikimedia Commons que muestre lo que se ve en ese momento (lugar, objeto, persona, época). Concreta y "
        "fotografiable: nada abstracto. Responde solo JSON: {\"busquedas\": [\"...\", ...]} con una por escena, en orden.",
        temperatura=0.3, detalle="búsquedas de referencias", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    salida = [str(b).strip() for b in json.loads(m.group(0) if m else crudo).get("busquedas", [])]
    while len(salida) < len(escenas):            # si faltan, se usa el plano de la escena
        e = escenas[len(salida)]
        salida.append(" ".join(re.findall(r"[A-Za-z]+", e.get("accion_en", tema))[:5]) or tema)
    return salida[:len(escenas)]


def _commons(q: str) -> list[dict[str, str]]:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=CABECERAS, timeout=20, params={
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 6,
        "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": ANCHO, "format": "json"})
    r.raise_for_status()
    paginas = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    salida = []
    for p in paginas:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        if not info.get("thumburl"):
            continue
        autor = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
        salida.append({"id": "commons:" + p["title"], "url": info["thumburl"], "pagina": info.get("descriptionurl", ""),
                       "autor": autor[:80], "licencia": meta.get("LicenseShortName", {}).get("value", ""), "fuente": "Wikimedia Commons"})
    return salida


def _openverse(q: str) -> list[dict[str, str]]:
    r = requests.get("https://api.openverse.org/v1/images/", headers=CABECERAS, timeout=20,
                     params={"q": q, "page_size": 6, "mature": "false"})
    r.raise_for_status()
    return [{"id": "openverse:" + x["id"], "url": x["thumbnail"], "pagina": x.get("foreign_landing_url", ""),
             "autor": (x.get("creator") or "")[:80], "licencia": (x.get("license") or "").upper(), "fuente": "Openverse"}
            for x in r.json().get("results", [])]


def _descargar(url: str, destino: Path) -> bool:
    try:
        r = requests.get(url, headers=CABECERAS, timeout=30)
        if r.ok and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 3000:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(r.content)) as im:
                im = im.convert("RGB")
                im.thumbnail((ANCHO, ANCHO))
                im.save(destino, "JPEG", quality=84)
            return True
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo bajar %s: %s", url, e)
    return False


def generar(escenas: list[dict[str, Any]], tema: str, carpeta: Path, produccion: str = "",
            avisar: Callable[[str, int], None] = lambda *_: None, excluir: set[str] | None = None,
            consultas: list[str] | None = None) -> dict[int, dict[str, str]]:
    """Devuelve {orden: {archivo, fuente, autor, licencia, pagina, busqueda}} para las escenas que encontraron imagen."""
    destino = carpeta / "ref_escenas"
    destino.mkdir(parents=True, exist_ok=True)
    consultas = consultas or busquedas(escenas, tema, produccion)
    usadas: set[str] = set(excluir or ())
    salida: dict[int, dict[str, str]] = {}
    for i, (e, q) in enumerate(zip(escenas, consultas)):
        avisar(f"Buscando referencia para la escena {e['orden']}: «{q}»", 10 + int(85 * i / max(1, len(escenas))))
        candidatas: list[dict[str, str]] = []
        # Si la búsqueda exacta no da nada, se prueba más amplia (menos palabras) y, al final, con el tema.
        palabras = q.split()
        intentos = list(dict.fromkeys([q, " ".join(palabras[:2]), tema]))
        for intento in intentos:
            for buscar in (_commons, _openverse):
                try:
                    candidatas += buscar(intento)
                except requests.RequestException as err:
                    logger.warning("%s «%s»: %s", buscar.__name__, intento, err)
                if any(c["id"] not in usadas for c in candidatas):
                    break
            if any(c["id"] not in usadas for c in candidatas):
                break
        for c in candidatas:
            if c["id"] in usadas:
                continue
            archivo = destino / f"escena_{e['orden']:02d}.jpg"
            if _descargar(c["url"], archivo):
                usadas.add(c["id"])
                salida[e["orden"]] = {"id": c["id"], "archivo": archivo.relative_to(carpeta).as_posix(), "fuente": c["fuente"],
                                      "autor": c["autor"], "licencia": c["licencia"], "pagina": c["pagina"], "busqueda": q}
                break
    registro.apuntar("Referencias (Commons / Openverse)", f"{len(salida)} de {len(escenas)} escenas", cantidad=len(salida),
                     unidad="imágenes", produccion=produccion)
    return salida
