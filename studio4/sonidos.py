"""Subtítulos de sonido (como en el cine para personas sordas): [Explosión lejana], [Música tensa], [Pasos]…

Gemini (gratis) escucha UNA vez la pista de sonido ambiente ya montada —los clips de Flow en su sitio, sin la voz del
narrador— y devuelve cada sonido importante con su segundo. Como esa pista ya está alineada con el vídeo, los tiempos
valen tal cual para el vídeo completo y, desplazados, para Reels y Shorts. Si algo falla, el vídeo sale sin ellos.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import gemini, medios

logger = logging.getLogger("studio4.sonidos")


class Sonido(BaseModel):
    inicio: float = Field(description="Segundo en que empieza el sonido.")
    fin: float = Field(description="Segundo en que termina (o deja de ser relevante).")
    sonido: str = Field(description="Descripción breve en español, estilo subtítulo de cine: «Explosión lejana», «Música tensa».")


class Sonidos(BaseModel):
    sonidos: list[Sonido]


INSTRUCCION = """Esta es la pista de sonido ambiente de un vídeo (no lleva la voz del narrador). Escribe los subtítulos de
sonido que necesitaría una persona sorda, como en el cine: efectos que importan (explosiones, disparos, golpes, puertas,
pasos, motores, lluvia, multitudes, risas, gritos, alarmas, animales) y la música cuando empieza o cambia de carácter.
Reglas: ignora el ruido de fondo constante y los silencios; como mucho un sonido cada 4 segundos; descripciones de 1 a 4
palabras, en español, empezando en mayúscula y sin corchetes; los segundos, medidos desde el principio de la pista.
Si no hay nada relevante, devuelve la lista vacía."""


def detectar(video: Path, duracion: float, produccion: str = "") -> list[dict[str, Any]]:
    """[{ini, fin, texto}] en segundos del vídeo. Vacío si no hay audio, no hay sonidos o Gemini no responde."""
    if not medios.info(video).get("audio"):
        return []
    with tempfile.TemporaryDirectory() as d:
        pista = Path(d) / "ambiente.mp3"
        medios.ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(pista))
        datos = pista.read_bytes()
        tramos = _tramos_con_sonido(medios.silencios(pista, umbral_db=-38, minimo=0.25), duracion)
    try:
        crudo = gemini.generar(INSTRUCCION, archivos=[(datos, "audio/mp3")], esquema=Sonidos, temperatura=0.2,
                               detalle="subtítulos de sonido", produccion=produccion)
        bloque = re.search(r"\{.*\}", crudo, re.DOTALL)
        lista = Sonidos.model_validate_json(bloque.group(0) if bloque else crudo).sonidos
    except Exception as e:  # noqa: BLE001 - sin sonidos el vídeo sale igual
        logger.warning("No pude escuchar el sonido ambiente: %s", e)
        return []
    return limpiar(ajustar([{"ini": s.inicio, "fin": s.fin, "texto": s.sonido} for s in lista], tramos), duracion)


def _tramos_con_sonido(silencios: list[tuple[float, float]], duracion: float) -> list[tuple[float, float]]:
    """Lo contrario de los silencios: dónde suena algo, medido por FFmpeg al milisegundo."""
    tramos, cursor = [], 0.0
    for ini, fin in silencios:
        if ini - cursor > 0.15:
            tramos.append((cursor, ini))
        cursor = fin
    if duracion - cursor > 0.15:
        tramos.append((cursor, duracion))
    return tramos


def ajustar(sonidos: list[dict[str, Any]], tramos: list[tuple[float, float]], margen: float = 3.5) -> list[dict[str, Any]]:
    """Gemini acierta qué suena, pero sus segundos pueden bailar: cada sonido se coloca en el arranque real más
    cercano que mide FFmpeg (si hay uno a menos de `margen` segundos)."""
    salida = []
    for s in sonidos:
        cerca = min(tramos, key=lambda t: abs(t[0] - s["ini"]), default=None)
        if cerca and abs(cerca[0] - s["ini"]) <= margen:
            s = {**s, "ini": cerca[0], "fin": cerca[1]}
        salida.append(s)
    return salida


def limpiar(sonidos: list[dict[str, Any]], duracion: float) -> list[dict[str, Any]]:
    """Ordena, recorta al vídeo, da a cada uno entre 1,2 y 4 s en pantalla y evita que dos se pisen."""
    salida: list[dict[str, Any]] = []
    for s in sorted(sonidos, key=lambda x: x["ini"]):
        texto = re.sub(r"[\[\]{}\\]", "", str(s.get("texto", ""))).strip().rstrip(".")
        ini = max(0.0, float(s["ini"]))
        if not texto or ini >= duracion - 0.3:
            continue
        if salida and ini < salida[-1]["fin"]:
            if ini - salida[-1]["ini"] < 1.2:
                continue                       # casi a la vez que el anterior: sobra
            salida[-1]["fin"] = ini
        fin = min(max(float(s.get("fin", ini)), ini + 1.2), ini + 4.0, duracion)
        salida.append({"ini": round(ini, 2), "fin": round(fin, 2), "texto": texto[:1].upper() + texto[1:]})
    return salida


def guardar(ruta: Path, sonidos: list[dict[str, Any]]) -> None:
    ruta.write_text(json.dumps(sonidos, ensure_ascii=False, indent=1), encoding="utf-8")


def leer(ruta: Path) -> list[dict[str, Any]]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
