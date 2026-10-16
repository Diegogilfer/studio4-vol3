"""Guion por clips de Flow: cada escena es UN clip de 8 s (lo más largo que genera Veo).

El guion se escribe a la medida de los clips (unas 18 palabras por cada 8 s de voz) y, al aprobarlo, se trocea en
bloques de un clip: el director decide qué se VE en cada bloque, pero no junta ni parte bloques. Así cada vídeo que
generas en Flow cubre exactamente su trozo de voz: sin cámara lenta ni planos congelados.
"""

from __future__ import annotations

import re

from . import config
from .guion import PALABRAS_POR_SEGUNDO

SEGUNDOS = config.SEGUNDOS_CLIP                     # 8 s
PALABRAS = int(SEGUNDOS * PALABRAS_POR_SEGUNDO)     # ~18 palabras por clip
TOPE = PALABRAS + 4                                 # un bloque puede estirarse un poco antes de partir una frase


def plan(segundos: float) -> dict[str, int]:
    """48 s → 6 clips de 8 s, 108 palabras."""
    n = max(2, round(float(segundos) / SEGUNDOS))
    return {"clips": n, "segundos": n * SEGUNDOS, "palabras": n * PALABRAS}


def _piezas(frase: str) -> list[str]:
    """Una frase que no cabe en un clip se parte por comas; si aún no cabe, por palabras."""
    if len(frase.split()) <= TOPE:
        return [frase]
    salida: list[str] = []
    for trozo in re.split(r"(?<=[,;:])\s+", frase):
        palabras = trozo.split()
        while len(palabras) > TOPE:
            salida.append(" ".join(palabras[:PALABRAS]))
            palabras = palabras[PALABRAS:]
        if palabras:
            salida.append(" ".join(palabras))
    return salida


def trocear(texto: str) -> list[str]:
    """El guion en bloques de un clip, respetando las frases: nunca se corta una frase si cabe entera."""
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", " ".join(str(texto).split())) if f]
    bloques: list[list[str]] = []
    actual: list[str] = []
    for pieza in (p for f in frases for p in _piezas(f)):
        n = len(pieza.split())
        if actual and len(" ".join(actual).split()) + n > TOPE:
            bloques.append(actual)
            actual = []
        actual.append(pieza)
    if actual:
        bloques.append(actual)
    textos = [" ".join(b) for b in bloques]
    # Un último bloque diminuto se une al anterior si cabe (un clip de 2 s no compensa).
    if len(textos) > 1 and len(textos[-1].split()) < PALABRAS // 2 and len((textos[-2] + " " + textos[-1]).split()) <= TOPE + 6:
        textos[-2:] = [textos[-2] + " " + textos[-1]]
    return textos
