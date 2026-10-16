"""Fotos de archivo reales y gratis: Wikimedia Commons, solo dominio público (sin licencias que obliguen a nada).

Para escenas históricas (personas reales, épocas, lugares): una foto auténtica vale más que una imagen inventada.
Se compone al formato del vídeo sin recortar a nadie: la foto entera en el centro, sobre ella misma desenfocada.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

API = "https://commons.wikimedia.org/w/api.php"
CABECERAS = {"User-Agent": "Studio4/1.0 (local video studio)"}
LIBRES = ("public domain", "pd", "cc0")


def buscar(consulta: str, cuantas: int = 10, min_lado: int = 400) -> list[dict[str, Any]]:
    """Fotos de dominio público que encajan con la consulta: [{titulo, url, ancho, alto, fecha}]."""
    r = requests.get(API, headers=CABECERAS, timeout=30, params=dict(
        action="query", format="json", generator="search", gsrsearch=f"{consulta} filetype:bitmap", gsrnamespace=6,
        gsrlimit=cuantas * 2, prop="imageinfo", iiprop="url|size|extmetadata", iiurlwidth=1920)).json()
    salida = []
    for p in ((r.get("query") or {}).get("pages") or {}).values():
        ii = p["imageinfo"][0]
        m = ii.get("extmetadata") or {}
        licencia = (m.get("LicenseShortName") or {}).get("value", "").lower()
        if not licencia.startswith(LIBRES) or min(ii["width"], ii["height"]) < min_lado:
            continue
        salida.append({"titulo": p["title"], "url": ii.get("thumburl") or ii["url"], "ancho": ii["width"], "alto": ii["height"],
                       "fecha": ((m.get("DateTimeOriginal") or {}).get("value") or "")[:10]})
    return salida[:cuantas]


def url_de(titulo: str) -> str:
    """URL descargable (máx. 1920 px, un tamaño estándar de Commons) de un archivo de Commons, comprobando que es de dominio público."""
    r = requests.get(API, headers=CABECERAS, timeout=30, params=dict(
        action="query", format="json", titles=titulo, prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=1920)).json()
    ii = next(iter(r["query"]["pages"].values()))["imageinfo"][0]
    licencia = ((ii.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "").lower()
    if not licencia.startswith(LIBRES):
        raise ValueError(f"{titulo} no es de dominio público ({licencia}).")
    return ii.get("thumburl") or ii["url"]


def componer(foto: Image.Image, ancho: int, alto: int) -> Image.Image:
    """La foto entera, centrada y con esquinas suaves, sobre su versión desenfocada y oscurecida."""
    foto = foto.convert("RGB")
    escala = max(ancho / foto.width, alto / foto.height)
    fondo = foto.resize((int(foto.width * escala) + 1, int(foto.height * escala) + 1), Image.LANCZOS)
    x, y = (fondo.width - ancho) // 2, (fondo.height - alto) // 2
    fondo = fondo.crop((x, y, x + ancho, y + alto)).filter(ImageFilter.GaussianBlur(min(ancho, alto) // 18))
    fondo = ImageEnhance.Brightness(fondo).enhance(0.45)
    # Cabe dentro del 86 % del ancho y el 62 % del alto: el acercamiento del montaje (12 %) nunca la corta.
    caber = min(ancho * 0.86 / foto.width, alto * 0.62 / foto.height)
    frente = foto.resize((int(foto.width * caber), int(foto.height * caber)), Image.LANCZOS)
    radio = max(8, min(ancho, alto) // 40)
    mascara = Image.new("L", frente.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *frente.size), radio, fill=255)
    px, py = (ancho - frente.width) // 2, (alto - frente.height) // 2
    sombra = Image.new("L", (ancho, alto), 0)
    ImageDraw.Draw(sombra).rounded_rectangle((px, py + radio, px + frente.width, py + frente.height + radio), radio, fill=150)
    fondo.paste((0, 0, 0), (0, 0), sombra.filter(ImageFilter.GaussianBlur(radio * 2)))
    fondo.paste(frente, (px, py), mascara)
    return fondo


def toma(titulo: str, carpeta: Path, orden: int, ancho: int, alto: int) -> dict[str, Any]:
    """Descarga la foto de Commons y la deja como toma de la escena (imagen ya compuesta al formato)."""
    r = requests.get(url_de(titulo), headers=CABECERAS, timeout=60)
    r.raise_for_status()
    datos = r.content
    destino = carpeta / "tomas" / f"escena_{orden:02d}_archivo.png"
    destino.parent.mkdir(exist_ok=True)
    componer(Image.open(io.BytesIO(datos)), ancho, alto).save(destino)
    original = destino.with_name(destino.stem + "_original.jpg")   # a sangre, para la carátula y las portadas
    Image.open(io.BytesIO(datos)).convert("RGB").save(original, quality=92)
    return {"archivo": f"tomas/{destino.name}", "tipo": "imagen", "origen": "archivo", "fuente": titulo,
            "original": f"tomas/{original.name}",
            "sha": hashlib.sha256(destino.read_bytes()).hexdigest()}
