"""Utilidades de FFmpeg/FFprobe compartidas por voz, Flow y render."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("studio4.medios")


def ffmpeg(*args: str, cwd: str | Path | None = None, timeout: int = 600) -> str:
    """Ejecuta ffmpeg y devuelve stderr (ahí escribe ffmpeg sus análisis). Lanza error con el final del log."""
    cmd = ["ffmpeg", "-hide_banner", "-y", *args]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"FFmpeg tardó más de {timeout} s y se detuvo para no bloquear la producción.") from e
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falló: {r.stderr.strip()[-800:]}")
    return r.stderr


def info(ruta: str | Path, timeout: int = 30) -> dict:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", str(ruta)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ValueError(f"FFprobe tardó demasiado al leer: {Path(ruta).name}") from e
    if r.returncode != 0:
        raise ValueError(f"No es un archivo de vídeo/imagen/audio válido: {Path(ruta).name}")
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duracion": float(d.get("format", {}).get("duration") or 0),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "ancho": int(video.get("width") or 0),
        "alto": int(video.get("height") or 0),
    }


def duracion(ruta: str | Path) -> float:
    return info(ruta)["duracion"]


def silencios(wav: str | Path, umbral_db: int = -35, minimo: float = 0.15) -> list[tuple[float, float]]:
    """Tramos de silencio (inicio, fin) de una locución: ahí se cortan las escenas."""
    log = ffmpeg("-i", str(wav), "-af", f"silencedetect=noise={umbral_db}dB:d={minimo}", "-f", "null", "-")
    inicios = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    fines = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(inicios, fines))


def ultimo_fotograma(video: str | Path, salida: str | Path) -> Path:
    """Saca el último fotograma de un clip: sirve de referencia en Flow para que la escena siguiente encaje."""
    ffmpeg("-sseof", "-0.2", "-i", str(video), "-frames:v", "1", "-q:v", "2", "-update", "1", str(salida))
    return Path(salida)
