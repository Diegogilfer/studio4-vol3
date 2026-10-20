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
# Lado largo mínimo para pantalla completa: por debajo se ve borrosa (las miniaturas de 192×108 y 320×180 de los
# listados de gtabase estiradas a 1080×1920 «casi no se podían ver»). Las capturas grandes de gtabase miden 832×468.
LADO_MINIMO = 800
_MINIATURA = re.compile(r"_(\d{2,4})x(\d{2,4})$")


def grande(url: str) -> str:
    """La versión grande de una miniatura: «…/resized/foto_320x180.jpg» → «…/foto.jpg» (gtabase y webs parecidas)."""
    partes = urllib.parse.urlparse(url)
    ruta = Path(partes.path)
    if "/resized/" not in partes.path and not _MINIATURA.search(ruta.stem):
        return url
    nueva = partes.path.replace("/resized/", "/")
    nueva = nueva[: -len(ruta.name)] + _MINIATURA.sub("", ruta.stem) + ruta.suffix
    return urllib.parse.urlunparse(partes._replace(path=nueva))


def _clave(url: str) -> tuple[str, int]:
    """«lucia-caminos-01-1080.jpg» → («lucia-caminos-01», 1080) y «foto_320x180.jpg» → («foto», 320): la misma
    imagen en varios tamaños se agrupa y gana la más grande."""
    nombre = Path(urllib.parse.urlparse(url).path).stem
    m = _MINIATURA.search(nombre)
    if m:
        return nombre[:m.start()].lower(), int(m.group(1))
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
        if _MINIATURA.search(Path(urllib.parse.urlparse(url).path).stem) or "/resized/" in url:
            url, tam = grande(url), 10_000   # su original sin recortar: por delante de cualquier miniatura
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
    """Descarga la imagen real y la deja como toma de la escena (compuesta al formato del vídeo).
    Una imagen demasiado pequeña para pantalla completa se rechaza (ValueError) para que se pruebe otra."""
    datos = fuentes._get(grande(url)).content
    foto = Image.open(io.BytesIO(datos))
    if max(foto.size) < LADO_MINIMO:
        raise ValueError(f"Imagen demasiado pequeña ({foto.width}×{foto.height}): se vería borrosa a pantalla completa.")
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
