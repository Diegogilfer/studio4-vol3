"""Imágenes reales de tus fuentes de confianza (p. ej. las capturas oficiales que publica gtabase.com).

Para un vídeo de un juego, una captura real vale más que una imagen inventada. Se buscan en las páginas de las fuentes
del canal (respetando su robots.txt y a una petición por segundo, como la investigación), se descartan logos e iconos,
y de cada imagen se queda la versión más grande. Cada toma guarda la página de donde salió.

Las capturas siguen siendo de sus autores: úsalas con comentario propio y edición (voz, datos, montaje), sin la música
ni trozos largos de los tráileres oficiales.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any

from PIL import Image

from . import archivo, canales, fuentes

logger = logging.getLogger("studio4.galeria")

_IMAGEN = re.compile(r'(?:href|src|data-src|content)="([^"]+?\.(?:jpe?g|png|webp))(?:\?[^"]*)?"', re.IGNORECASE)
DESCARTE = ("logo", "icon", "avatar", "menu", "banner", "sprite", "favicon", "emoji", "badge", "jch-optimize", "flag", "button")
PAGINAS = 4   # páginas por fuente y búsqueda (un vídeo largo pide más: ver «paginas» en buscar)


def _clave(url: str) -> tuple[str, int]:
    """«lucia-caminos-01-1080.jpg» → («lucia-caminos-01», 1080): la misma imagen en varios tamaños se agrupa."""
    nombre = Path(urllib.parse.urlparse(url).path).stem
    m = re.search(r"[-_](\d{3,4})$", nombre)
    return (nombre[:m.start()] if m else nombre).lower(), int(m.group(1)) if m else 0


def descripcion(url: str) -> str:
    return re.sub(r"[-_]+", " ", re.sub(r"\d+", " ", _clave(url)[0])).strip()


def imagenes_de(pagina: str) -> list[dict[str, Any]]:
    """Las imágenes de contenido de una página (sin logos ni iconos), cada una en su versión más grande."""
    texto = fuentes._get(pagina).text
    mejores: dict[str, tuple[int, str]] = {}
    for m in _IMAGEN.finditer(texto):
        url = urllib.parse.urljoin(pagina, html_unescape(m.group(1)))
        if any(d in url.lower() for d in DESCARTE):
            continue
        clave, tam = _clave(url)
        if clave not in mejores or tam > mejores[clave][0]:
            mejores[clave] = (tam, url)
    return [{"url": u, "descripcion": descripcion(u), "pagina": pagina} for _, u in mejores.values()]


def html_unescape(s: str) -> str:
    return s.replace("&amp;", "&")


def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", fuentes._normal(texto))}


def buscar(cid: str, consulta: str, n: int = 24, produccion: str = "", paginas_por_fuente: int = PAGINAS,
           minimo: int = 0, sitio_entero: bool = False) -> list[dict[str, Any]]:
    """Imágenes reales de las fuentes del canal que encajan con la consulta (en español o en inglés).
    Con «minimo», solo las que comparten al menos esas palabras con la consulta (para no mostrar una cualquiera).
    Con «sitio_entero», busca en toda la web de cada fuente y no solo en su sección (p. ej. todo gtabase.com y no
    solo /gta-6/: así un tema de San Andreas o de Red Dead también encuentra sus imágenes)."""
    canal = canales.obtener(cid)
    if not canal.get("fuentes"):
        raise ValueError("Añade las fuentes de confianza del canal (Canales) para buscar sus imágenes reales.")
    try:
        palabras = fuentes.claves(consulta, produccion)   # la consulta en inglés y sus nombres propios
    except Exception as e:  # noqa: BLE001 - sin IA se busca con las palabras tal cual
        logger.info("Claves de búsqueda: %s", e)
        palabras = sorted(_palabras(consulta))
    paginas: list[str] = []
    sitios = canal["fuentes"]
    if sitio_entero:
        sitios = list(dict.fromkeys(f"{urllib.parse.urlparse(f).scheme}://{urllib.parse.urlparse(f).netloc}/" for f in sitios))
    for f in sitios:
        try:
            paginas += fuentes.elegir(fuentes.indice(f), palabras, n=paginas_por_fuente)
        except Exception as e:  # noqa: BLE001 - una fuente caída no frena la búsqueda
            logger.warning("Fuente %s: %s", f, e)
    vistas: dict[str, dict[str, Any]] = {}
    for p in paginas[:paginas_por_fuente * 2]:
        try:
            for img in imagenes_de(p):
                vistas.setdefault(_clave(img["url"])[0], img)
        except Exception as e:  # noqa: BLE001
            logger.info("No pude leer %s: %s", p, e)
    buscadas = {w for k in palabras for w in _palabras(k)}
    orden = sorted(vistas.values(), key=lambda i: -len(_palabras(i["descripcion"]) & buscadas))
    return [{**i, "aciertos": sorted(_palabras(i["descripcion"]) & buscadas)} for i in orden
            if len(_palabras(i["descripcion"]) & buscadas) >= minimo][:n]


def encajar(foto: Image.Image, ancho: int, alto: int) -> Image.Image:
    """Si la imagen tiene casi la misma forma que el vídeo, lo llena; si no (captura 16:9 en un vertical), va entera
    sobre ella misma desenfocada, sin cortar a nadie."""
    r_img, r_vid = foto.width / foto.height, ancho / alto
    if abs(r_img - r_vid) / r_vid < 0.25:
        escala = max(ancho / foto.width, alto / foto.height)
        grande = foto.convert("RGB").resize((int(foto.width * escala) + 1, int(foto.height * escala) + 1), Image.LANCZOS)
        x, y = (grande.width - ancho) // 2, (grande.height - alto) // 2
        return grande.crop((x, y, x + ancho, y + alto))
    return archivo.componer(foto, ancho, alto)


def toma(url: str, pagina: str, carpeta: Path, orden: int, ancho: int, alto: int) -> dict[str, Any]:
    """Descarga la imagen real y la deja como toma de la escena (compuesta al formato del vídeo)."""
    datos = fuentes._get(url).content
    foto = Image.open(io.BytesIO(datos))
    destino = carpeta / "tomas" / f"escena_{orden:02d}_real_{hashlib.sha1(url.encode()).hexdigest()[:6]}.png"
    destino.parent.mkdir(exist_ok=True)
    encajar(foto, ancho, alto).save(destino)
    original = destino.with_name(destino.stem + "_original.jpg")   # a sangre, para la carátula y las portadas
    foto.convert("RGB").save(original, quality=92)
    return {"archivo": f"tomas/{destino.name}", "tipo": "imagen", "origen": "real", "fuente": pagina, "url": url,
            "original": f"tomas/{original.name}", "sha": hashlib.sha256(destino.read_bytes()).hexdigest()}


def repartir(escenas: list[dict[str, Any]], imagenes: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """A cada escena sin clip, la imagen que más encaja con lo que se dice y lo que se ve, sin repetir."""
    libres = list(imagenes)
    salida: dict[int, dict[str, Any]] = {}
    for e in escenas:
        if e.get("elegida") is not None or not imagenes:
            continue
        if not libres:   # más escenas que imágenes: se vuelven a usar, empezando por las de hace más tiempo
            libres = list(imagenes)
        mias = _palabras(" ".join([e.get("texto_voz", ""), e.get("accion_en", ""), " ".join(e.get("personajes") or [])]))
        mejor = max(libres, key=lambda i: len(_palabras(i["descripcion"]) & mias))
        salida[e["orden"]] = mejor
        libres.remove(mejor)
    return salida
