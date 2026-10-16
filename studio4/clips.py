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


def palabras_por_clip(velocidad: float = 1.0) -> int:
    """Una voz más rápida dice más palabras en los mismos 8 s (a 1,1× caben ~20)."""
    return round(PALABRAS * float(velocidad or 1.0))


def plan(segundos: float, velocidad: float = 1.0) -> dict[str, int]:
    """48 s → 6 clips de 8 s, 108 palabras (a velocidad normal)."""
    n = max(2, round(float(segundos) / SEGUNDOS))
    return {"clips": n, "segundos": n * SEGUNDOS, "palabras": n * palabras_por_clip(velocidad)}


def _piezas(frase: str, por_clip: int, tope: int) -> list[str]:
    """Una frase que no cabe en un clip se parte por comas; si aún no cabe, por palabras."""
    if len(frase.split()) <= tope:
        return [frase]
    salida: list[str] = []
    for trozo in re.split(r"(?<=[,;:])\s+", frase):
        palabras = trozo.split()
        while len(palabras) > tope:
            salida.append(" ".join(palabras[:por_clip]))
            palabras = palabras[por_clip:]
        if palabras:
            salida.append(" ".join(palabras))
    return salida


def trocear(texto: str, velocidad: float = 1.0) -> list[str]:
    """El guion en bloques de un clip, respetando las frases: nunca se corta una frase si cabe entera."""
    por_clip = palabras_por_clip(velocidad)
    tope = por_clip + 4
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", " ".join(str(texto).split())) if f]
    bloques: list[list[str]] = []
    actual: list[str] = []
    for pieza in (p for f in frases for p in _piezas(f, por_clip, tope)):
        n = len(pieza.split())
        if actual and len(" ".join(actual).split()) + n > tope:
            bloques.append(actual)
            actual = []
        actual.append(pieza)
    if actual:
        bloques.append(actual)
    textos = [" ".join(b) for b in bloques]
    # Un último bloque diminuto se une al anterior si cabe (un clip de 2 s no compensa).
    if len(textos) > 1 and len(textos[-1].split()) < por_clip // 2 and len((textos[-2] + " " + textos[-1]).split()) <= tope + 6:
        textos[-2:] = [textos[-2] + " " + textos[-1]]
    return textos
