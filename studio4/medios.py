"""Utilidades de FFmpeg/FFprobe compartidas por voz, Flow y render."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("studio4.medios")


def _limite(args: tuple[str, ...], cwd: str | Path | None) -> int:
    """Tiempo máximo para un ffmpeg: 10 min de base y 40 s más por cada segundo del medio más largo que entra.
    Así nunca se corta un montaje largo en un PC lento, pero un FFmpeg colgado no bloquea la producción para siempre."""
    largo = 0.0
    for i, a in enumerate(args[:-1]):
        if a == "-i":
            ruta = Path(args[i + 1])
            ruta = ruta if ruta.is_absolute() or cwd is None else Path(cwd) / ruta
            if ruta.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".txt") and ruta.exists():
                try:
                    largo = max(largo, duracion(ruta) if ruta.suffix.lower() != ".txt" else 0.0)
                except (ValueError, RuntimeError):
                    pass
        if a == "-t":
            try:
                largo = max(largo, float(args[i + 1]))
            except ValueError:
                pass
    return int(600 + 40 * largo)


def ffmpeg(*args: str, cwd: str | Path | None = None, timeout: int | None = None) -> str:
    """Ejecuta ffmpeg y devuelve stderr (ahí escribe ffmpeg sus análisis). Lanza error con el final del log."""
    cmd = ["ffmpeg", "-hide_banner", "-y", *args]
    timeout = timeout or _limite(args, cwd)
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"FFmpeg tardó más de {timeout // 60} min y se detuvo para no bloquear la producción.") from e
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
