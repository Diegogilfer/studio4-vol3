"""Ninguna imagen mala entra en un vídeo: Google (Gemini, gratis con la clave de Google) revisa cada foto antes de usarla
y lo que pasa se retoca en el PC, sin coste.

- revisar(): nitidez, resolución aparente, marcas de agua, texto encima, collage o captura de web, y si ENSEÑA lo que
  dice la frase. Devuelve {nota 1-5, encaja, motivo}. Solo se usan las de nota >= 3 que encajan.
- retocar(): ampliar a 1920 de ancho si viene pequeña (Lanczos), enfoque suave, contraste y color automáticos ligeros.
  No inventa nada: el retoque con IA generativa (Nano Banana) es de pago y solo con el sí del autor.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from . import gemini, jsonia

logger = logging.getLogger("studio4.calidad_imagen")
NOTA_MINIMA = 3

SISTEMA = """Eres el editor de fotografía de un canal de vídeo. Te doy UNA imagen y la frase que se dirá mientras se ve.
Puntúa la imagen de 1 a 5 para usarla A PANTALLA COMPLETA en un vídeo 1080p: 5 = nítida, bien expuesta, limpia;
3 = aceptable; 1 = borrosa, pixelada, diminuta, con marca de agua, con texto o logos encima, collage, captura de una
web o de un móvil, meme. Di si ENCAJA con la frase como imagen de referencia: true si enseña la misma CLASE de cosa
(un estadio de fútbol de noche, un dron, un árbitro, un barco antiguo) aunque no sea el sitio exacto; false si es otra
cosa (otro deporte, otra época, otro objeto) o si es un lugar FAMOSO y reconocible distinto del que nombra la frase
(no se hace pasar un sitio conocido por otro). Devuelve solo JSON: {"nota": 1, "encaja": true, "motivo": "muy corto"}"""


def revisar(imagen: bytes, frase: str) -> dict[str, Any]:
    """La revisión de Google de una imagen para una frase. Si Gemini no responde, se deja pasar (no frena el vídeo)."""
    try:
        crudo = gemini.generar(f"FRASE: {frase[:300]}\n\nResponde solo con el JSON.", sistema=SISTEMA, temperatura=0.1,
                               detalle="revisar imagen", imagenes=[_jpeg(imagen, 1024)])
        d = jsonia.leer(crudo)
        nota = int(d.get("nota") or 0)
        return {"nota": max(1, min(5, nota)), "encaja": d.get("encaja") is not False, "motivo": str(d.get("motivo", ""))[:120],
                "revisada": True}
    except Exception as e:  # noqa: BLE001 - sin revisión, la imagen sigue su camino (y el filtro de tamaño vale)
        logger.info("Revisión de imagen sin Gemini: %s", e)
        return {"nota": NOTA_MINIMA, "encaja": True, "motivo": "sin revisar", "revisada": False}


def aprobada(r: dict[str, Any]) -> bool:
    return r["nota"] >= NOTA_MINIMA and r["encaja"]


def _jpeg(datos: bytes, lado: int) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(datos)).convert("RGB")
    im.thumbnail((lado, lado))
    salida = io.BytesIO()
    im.save(salida, "JPEG", quality=88)
    return salida.getvalue()


def retocar(im):
    """Retoque local y sin IA generativa: tamaño de vídeo, enfoque y color. Recibe y devuelve una imagen de PIL (RGB)."""
    from PIL import ImageEnhance, ImageFilter, ImageOps
    if im.width < 1920:   # ampliar con buen filtro antes que dejar que el vídeo la estire a lo bruto
        alto = round(im.height * 1920 / im.width)
        im = im.resize((1920, alto), resample=1)   # 1 = LANCZOS: el filtro que menos emborrona al ampliar
    im = ImageOps.autocontrast(im, cutoff=0.5, preserve_tone=True)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=3))
    im = ImageEnhance.Color(im).enhance(1.06)
    return im
