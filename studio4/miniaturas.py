"""Miniaturas para las entregas finales: YouTube (largos), portadas de Shorts y Reels, y feed cuadrado.

1. Se sacan fotogramas de la toma elegida de cada escena (y se suman las imágenes que subas o
   generes en Flow para la miniatura).
2. Gemini (gratis, ve imágenes) elige el más potente, dónde está el sujeto, y escribe 2-4 palabras.
3. Pillow compone cada plataforma en local: encuadre sobre el sujeto, contraste, degradado y texto
   grande con una palabra resaltada, siempre dentro de la zona que cada red no tapa ni recorta.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from pydantic import BaseModel, Field

from . import config, gemini, medios

logger = logging.getLogger("studio4.miniaturas")

# zona = caja del texto (x0, y0, x1, y1) en fracciones; degradado = de dónde sale la sombra que lo hace legible.
PLATAFORMAS = {
    "youtube": {"nombre": "Miniatura YouTube (largos)", "ancho": 1280, "alto": 720,
                "zona": (0.05, 0.10, 0.60, 0.90), "alinear": "izquierda", "degradado": "izquierda"},
    # Shorts: arriba-centro; abajo lo tapan el título y los botones.
    "shorts": {"nombre": "Portada Shorts", "ancho": 1080, "alto": 1920,
               "zona": (0.07, 0.13, 0.93, 0.44), "alinear": "centro", "degradado": "arriba"},
    # Reels: el perfil la recorta a 3:4 (franja central 1080x1440, y de 240 a 1680): el texto va dentro.
    "reels": {"nombre": "Portada Reels", "ancho": 1080, "alto": 1920,
              "zona": (0.07, 0.17, 0.93, 0.46), "alinear": "centro", "degradado": "arriba"},
    "feed": {"nombre": "Portada feed 1:1", "ancho": 1080, "alto": 1080,
             "zona": (0.07, 0.60, 0.93, 0.92), "alinear": "centro", "degradado": "abajo"},
}
POR_FORMATO = {"vertical": ["shorts", "reels"], "horizontal": ["youtube"], "cuadrado": ["feed"]}

FUENTES = [os.getenv("STUDIO4_FUENTE_MINIATURA", ""), r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\ariblk.ttf",
           r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/System/Library/Fonts/Supplemental/Impact.ttf"]
BLANCO, AMARILLO = (255, 255, 255), (255, 214, 10)
MAX_CANDIDATOS = 12


def plataformas(formato: str) -> list[str]:
    return POR_FORMATO.get(formato, ["youtube"])


def _fuente(tam: int) -> ImageFont.FreeTypeFont:
    for ruta in FUENTES:
        if ruta and Path(ruta).exists():
            return ImageFont.truetype(ruta, tam)
    return ImageFont.load_default(tam)


# --- 1. Candidatos ------------------------------------------------------------------------------
def extraer_candidatos(p: dict[str, Any], base: Path) -> list[dict[str, Any]]:
    destino = base / "miniaturas" / "candidatos"
    destino.mkdir(parents=True, exist_ok=True)
    for viejo in destino.glob("c*.jpg"):
        viejo.unlink()
    escenas = [e for e in p["escenas"] if e.get("elegida") is not None]
    if not escenas:
        raise RuntimeError("Aún no hay clips elegidos: las miniaturas salen de tus escenas de Flow.")
    por_escena = max(1, MAX_CANDIDATOS // len(escenas))
    salida: list[dict[str, Any]] = []
    for e in escenas:
        toma = e["tomas"][e["elegida"]]
        origen = base / toma["archivo"]
        if not origen.exists():
            continue
        if toma["tipo"] == "imagen":
            archivo = destino / f"c{len(salida) + 1:02d}.jpg"
            Image.open(origen).convert("RGB").save(archivo, quality=95)
            salida.append({"archivo": archivo.relative_to(base).as_posix(), "escena": e["orden"]})
            continue
        dur = medios.duracion(origen) or 1.0
        for k in range(min(por_escena, 3)):
            t = dur * (0.3 + 0.45 * k / max(1, min(por_escena, 3) - 1)) if por_escena > 1 else dur * 0.5
            archivo = destino / f"c{len(salida) + 1:02d}.jpg"
            medios.ffmpeg("-ss", f"{t:.2f}", "-i", str(origen), "-frames:v", "1", "-q:v", "2", str(archivo))
            salida.append({"archivo": archivo.relative_to(base).as_posix(), "escena": e["orden"]})
        if len(salida) >= MAX_CANDIDATOS:
            break
    return salida[:MAX_CANDIDATOS]


# --- 2. Gemini elige y escribe -------------------------------------------------------------------
class Eleccion(BaseModel):
    mejor: int = Field(description="Número (empezando en 1) de la imagen con más gancho para miniatura.")
    foco_x: float = Field(description="Posición horizontal del sujeto principal en esa imagen, de 0 (izq.) a 1 (der.).")
    foco_y: float = Field(description="Posición vertical del sujeto principal, de 0 (arriba) a 1 (abajo).")
    texto: str = Field(description="2 a 4 palabras en español, en MAYÚSCULAS, que provoquen curiosidad. Tiene que ser una "
                                   "frase natural y gramatical que se entienda sola (nada de palabras sueltas pegadas). "
                                   "No repitas el título.")
    resalte: str = Field(description="UNA palabra del texto que irá en amarillo (la más potente).")
    alternativas: list[str] = Field(description="3 textos alternativos con el mismo estilo.")
    prompt_flow_en: str = Field(description="Prompt en inglés para generar en Google Flow una imagen de miniatura: "
                                            "primer plano expresivo del sujeto, mucho contraste, fondo limpio, sin texto.")


SISTEMA = """Eres diseñador de miniaturas de YouTube, Shorts y Reels con millones de clics.
Una buena miniatura: un sujeto claro y grande, una emoción o un misterio visible, contraste alto y
poco ruido. Elige la imagen que mejor funciona en tamaño pequeño y escribe un texto corto que añada
curiosidad a lo que se ve (no lo describa)."""


def analizar(p: dict[str, Any], base: Path, candidatos: list[dict[str, Any]]) -> dict[str, Any]:
    imagenes = []
    for c in candidatos:
        im = Image.open(base / c["archivo"]).convert("RGB")
        im.thumbnail((512, 512))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
        imagenes.append(b.getvalue())
    biblia = p.get("biblia") or {}
    prompt = (f"Título del vídeo: {p.get('titulo') or p['tema']}\nGuion: {p.get('guion', '')[:800]}\n"
              f"Personajes: {'; '.join(x['nombre'] + ': ' + x['aspecto_en'] for x in biblia.get('personajes', []))}\n"
              f"Estilo: {p.get('estilo_en', '')}\n\nTienes {len(imagenes)} imágenes numeradas del 1 al {len(imagenes)} en orden.")
    crudo = gemini.generar(prompt, sistema=SISTEMA, esquema=Eleccion, temperatura=0.6, imagenes=imagenes,
                           detalle="miniatura", produccion=p["id"])
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    e = Eleccion.model_validate_json(m.group(0) if m else crudo).model_dump()
    e["mejor"] = min(max(1, e["mejor"]), len(candidatos)) - 1
    e["foco_x"] = min(max(e["foco_x"], 0.0), 1.0)
    e["foco_y"] = min(max(e["foco_y"], 0.0), 1.0)
    return e


# --- 3. Composición ------------------------------------------------------------------------------
def _encuadrar(im: Image.Image, ancho: int, alto: int, fx: float, fy: float) -> Image.Image:
    """Recorta a la proporción final manteniendo el sujeto (fx, fy) lo más centrado posible."""
    escala = max(ancho / im.width, alto / im.height)
    im = im.resize((max(ancho, round(im.width * escala)), max(alto, round(im.height * escala))), Image.LANCZOS)
    x = min(max(round(fx * im.width - ancho / 2), 0), im.width - ancho)
    y = min(max(round(fy * im.height - alto / 2), 0), im.height - alto)
    return im.crop((x, y, x + ancho, y + alto))


def _degradado(ancho: int, alto: int, desde: str) -> Image.Image:
    """Sombra negra que nace en un borde: hace legible el texto sin tapar al sujeto."""
    g = Image.linear_gradient("L")              # 256x256: negro arriba → blanco abajo
    if desde == "arriba":
        g = ImageOps.invert(g)
    elif desde == "izquierda":
        g = ImageOps.invert(g.rotate(90))       # el borde de arriba pasa a la izquierda
    g = g.point(lambda v: int(min(255, max(0, (v - 70) * 1.35)) * 0.82))  # se desvanece hacia el ~60 %
    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    capa.putalpha(g.resize((ancho, alto)))
    return capa


def _repartir(palabras: list[str], fuente: ImageFont.FreeTypeFont, max_ancho: int, max_lineas: int) -> list[list[str]] | None:
    lineas: list[list[str]] = [[]]
    for pal in palabras:
        prueba = " ".join(lineas[-1] + [pal])
        if lineas[-1] and fuente.getlength(prueba) > max_ancho:
            lineas.append([pal])
        else:
            lineas[-1].append(pal)
        if fuente.getlength(" ".join(lineas[-1])) > max_ancho:
            return None
    return lineas if len(lineas) <= max_lineas else None


def _texto(lienzo: Image.Image, texto: str, resalte: str, zona: tuple, alinear: str) -> None:
    ancho, alto = lienzo.size
    x0, y0, x1, y1 = zona[0] * ancho, zona[1] * alto, zona[2] * ancho, zona[3] * alto
    palabras = texto.upper().split()
    if not palabras:
        return
    clave = re.sub(r"\W", "", resalte.upper())

    def medidas(f: ImageFont.FreeTypeFont, trazo: int) -> tuple[float, float, float]:
        """Tinta real de una línea (con tildes y contorno): (arriba, alto, interlínea)."""
        arriba, abajo = f.getbbox("ÁÉÓQJ", stroke_width=trazo)[1::2]
        alto_linea = abajo - arriba
        return arriba, alto_linea, alto_linea * 0.9   # líneas apretadas, como en las miniaturas virales

    lineas = None
    for tam in range(int(y1 - y0), 20, -4):
        f = _fuente(tam)
        trazo = max(3, tam // 11)
        lineas = _repartir(palabras, f, x1 - x0 - 2 * trazo, 3)
        arriba, alto_linea, interlinea = medidas(f, trazo)
        if lineas and (len(lineas) - 1) * interlinea + alto_linea + 3 * trazo <= y1 - y0:  # + la sombra
            break
    if not lineas:  # ni con la letra más pequeña: una palabra por línea
        lineas = [[w] for w in palabras[:3]]
    capa = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(capa)
    sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    dsombra = ImageDraw.Draw(sombra)
    total = (len(lineas) - 1) * interlinea + alto_linea + 3 * trazo
    y = y0 + ((y1 - y0) - total) / 2 - arriba          # se dibuja desde la línea de ascenso de la letra
    espacio = f.getlength(" ")
    for linea in lineas:
        largo = f.getlength(" ".join(linea))
        x = x0 + trazo if alinear == "izquierda" else x0 + ((x1 - x0) - largo) / 2
        for pal in linea:
            color = AMARILLO if clave and re.sub(r"\W", "", pal) == clave else BLANCO
            dsombra.text((x + trazo, y + trazo * 1.4), pal, font=f, fill=(0, 0, 0, 170))
            dibujo.text((x, y), pal, font=f, fill=color, stroke_width=trazo, stroke_fill=(0, 0, 0))
            x += f.getlength(pal) + espacio
        y += interlinea
    lienzo.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(trazo)))
    lienzo.alpha_composite(capa)


def componer(fuente: Path, destino: Path, plataforma: str, texto: str, resalte: str, fx: float = 0.5, fy: float = 0.5) -> Path:
    pl = PLATAFORMAS[plataforma]
    im = ImageOps.exif_transpose(Image.open(fuente)).convert("RGB")
    im = _encuadrar(im, pl["ancho"], pl["alto"], fx, fy)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    im = ImageEnhance.Color(im).enhance(1.2)
    im = ImageEnhance.Sharpness(im).enhance(1.25)
    lienzo = im.convert("RGBA")
    lienzo.alpha_composite(_degradado(pl["ancho"], pl["alto"], pl["degradado"]))
    _texto(lienzo, texto, resalte, pl["zona"], pl["alinear"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    lienzo.convert("RGB").save(destino, "JPEG", quality=90, optimize=True)  # YouTube admite hasta 2 MB
    return destino


def componer_todas(p: dict[str, Any], base: Path) -> dict[str, str]:
    m = p["miniaturas"]
    fuente = base / m["candidatos"][m["elegido"]]["archivo"]
    salidas = {}
    for pl in plataformas(p["formato"]):
        componer(fuente, base / "miniaturas" / f"{pl}.jpg", pl, m["texto"], m.get("resalte", ""),
                 m.get("foco_x", 0.5), m.get("foco_y", 0.5))
        salidas[pl] = f"miniaturas/{pl}.jpg"
    m["salidas"] = salidas
    m["version"] = time.strftime("%H%M%S")
    return salidas
