"""Control de calidad de un vídeo antes de entregarlo: lo que el autor nota al verlo, medido.

Imagen quieta (congelados), cortes, huecos de sonido, sonido que muere antes del final, subtítulos que salen
sin voz debajo y volumen de YouTube (LUFS). Lo usa el montaje al terminar cada previa y cada final (el resultado
se ve en el panel) y la habilidad `revisar-video` desde la consola.
"""

from __future__ import annotations

import array
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

ENTRADA_VOZ = 0.25          # la voz entra con este retraso en la línea (montaje.ENTRADA)
QUIETO_MIN = 0.4            # segundos de imagen sin cambios que ya se notan como «parado»
QUIETO_FALLO = 0.8          # a partir de aquí no se entrega
SALTO = 20.0                # cambio medio entre cuadros (0-255) que es un corte
HUECO_DB = 12.0             # caída por debajo del fondo que se oye como un corte
LUFS_OBJETIVO = (-12.5, -9.5)


def _ff(*args: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-nostats", *args], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


def niveles(audio_o_video: Path, paso: float = 0.05) -> list[float]:
    """Volumen (dB) cada `paso` segundos."""
    hz = 8000
    crudo = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(audio_o_video), "-vn", "-ac", "1", "-ar", str(hz),
                            "-f", "s16le", "-"], stdin=subprocess.DEVNULL, capture_output=True).stdout
    a = array.array("h")
    a.frombytes(crudo[:len(crudo) // 2 * 2])
    w = int(hz * paso)
    return [20 * math.log10(max(1.0, math.sqrt(sum(x * x for x in a[k * w:(k + 1) * w]) / w)) / 32768)
            for k in range(len(a) // w)]


def revisar(video: Path, palabras: list[dict[str, Any]] | None = None, voz: Path | None = None) -> dict[str, Any]:
    """{ok, fallos, avisos, duracion, resolucion, lufs, cortes, quietos, huecos}. `palabras` y `voz` (la voz con
    pausas, sin retraso) añaden la comparación de subtítulos contra la voz."""
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                                      "-of", "json", str(video)], capture_output=True, text=True).stdout)
    dur = float(info["format"]["duration"])
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    fallos, avisos = [], []

    medida = re.findall(r"I:\s+(-?[\d.]+) LUFS", _ff("-i", str(video), "-vn", "-af", "ebur128", "-f", "null", "-"))
    lufs = float(medida[-1]) if medida else -70.0
    if not LUFS_OBJETIVO[0] <= lufs <= LUFS_OBJETIVO[1]:
        fallos.append(f"Volumen {lufs:.1f} LUFS (debe estar entre {LUFS_OBJETIVO[0]} y {LUFS_OBJETIVO[1]})")
    if v["height"] < 1080 and "previa" not in video.name:
        fallos.append(f"Resolución {v['width']}x{v['height']}: el final va en 1920x1080")

    log = _ff("-i", str(video), "-an", "-vf", f"freezedetect=n=0.001:d={QUIETO_MIN},metadata=mode=print:file=-",
              "-f", "null", "-")
    quietos = list(zip(map(float, re.findall(r"freeze_start=([\d.]+)", log)),
                       map(float, re.findall(r"freeze_duration=([\d.]+)", log))))
    for ini, d in quietos:
        (fallos if d >= QUIETO_FALLO else avisos).append(f"Imagen quieta {d:.1f} s en el segundo {ini:.1f}")

    log = _ff("-i", str(video), "-an", "-vf", "scale=480:-2,tblend=all_mode=difference,signalstats,"
              "metadata=mode=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-")
    tiempos = [float(x) for x in re.findall(r"pts_time:([\d.]+)", log)]
    cambios = [float(x) for x in re.findall(r"YAVG=([\d.]+)", log)]
    cortes = [round(t, 2) for t, c in zip(tiempos, cambios) if c > SALTO]

    # huecos: el fondo (lo más bajo que suena en general) se cae por debajo de sí mismo; las pausas entre
    # palabras no cuentan porque ahí sigue sonando el fondo
    db = niveles(video)
    huecos: list[float] = []
    cuerpo = sorted(db[int(1 / 0.05):max(int(1 / 0.05) + 1, len(db) - int(1.5 / 0.05))])
    fondo = cuerpo[len(cuerpo) // 10] if cuerpo else -40
    for k in range(int(0.5 / 0.05), len(db) - int(1.5 / 0.05)):
        if db[k] < fondo - HUECO_DB and (not huecos or k * 0.05 - huecos[-1] > 0.5):
            huecos.append(round(k * 0.05, 2))
    fallos += [f"Hueco de sonido en el segundo {t:.2f} (se oye como un corte)" for t in huecos]
    final = db[-int(1.5 / 0.05):] if len(db) > 30 else db
    if final and min(final[:10]) < -60:
        fallos.append("El sonido muere de golpe antes de acabar el vídeo")

    if palabras and voz and voz.exists():
        dv = niveles(voz, 0.02)
        for w in palabras:
            pasos = [w["ini"] + i * 0.02 for i in range(max(1, int((w["fin"] - w["ini"]) / 0.02)))]
            dentro = [int((t - ENTRADA_VOZ) / 0.02) for t in pasos]
            con = sum(1 for k in dentro if 0 <= k < len(dv) and dv[k] > -40) / len(pasos)
            if con < 0.3 and len(w["palabra"]) > 3:
                fallos.append(f"Subtítulo sin voz debajo: «{w['palabra']}» en el segundo {w['ini']:.2f}")

    return {"ok": not fallos, "fallos": fallos, "avisos": avisos, "duracion": round(dur, 2),
            "resolucion": f"{v['width']}x{v['height']}", "lufs": lufs, "cortes": cortes,
            "quietos": [[round(a, 2), round(b, 2)] for a, b in quietos], "huecos": huecos}
