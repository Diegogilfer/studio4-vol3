"""Control de calidad de un vídeo de Studio 4 antes de entregarlo: lo que el autor nota al verlo, medido.

Uso:
    python .claude/skills/revisar-video/revisar.py RUTA/final_16x9.mp4 [--proyecto RUTA/proyecto.json]

Mide: formato y volumen (LUFS), imagen quieta (congelados), saltos bruscos, huecos de sonido, silencio al final
y, con --proyecto, subtítulos que salen sin voz debajo. Termina con un veredicto: OK o la lista de fallos con su
segundo exacto. Sale con código 1 si hay fallos (para usarlo en pruebas).
"""

from __future__ import annotations

import argparse
import array
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ENTRADA_VOZ = 0.25          # la voz entra con este retraso en la línea (montaje.ENTRADA)
QUIETO_MIN = 0.4            # segundos de imagen sin cambios que ya se notan como «parado»
SALTO = 20.0                # cambio medio entre cuadros (0-255) que es un corte; sirve para listar los cortes
HUECO_DB = 12.0             # caída de volumen respecto a lo que suena alrededor que se oye como un corte
LUFS_OBJETIVO = (-12.5, -9.5)


def _ff(*args: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-nostats", *args], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


def _niveles(video: Path, paso: float = 0.05) -> list[float]:
    """Volumen (dB) cada `paso` segundos."""
    hz = 8000
    crudo = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(hz),
                            "-f", "s16le", "-"], stdin=subprocess.DEVNULL, capture_output=True).stdout
    a = array.array("h")
    a.frombytes(crudo[:len(crudo) // 2 * 2])
    w = int(hz * paso)
    return [20 * math.log10(max(1.0, math.sqrt(sum(x * x for x in a[k * w:(k + 1) * w]) / w)) / 32768)
            for k in range(len(a) // w)]


def revisar(video: Path, proyecto: Path | None = None) -> dict:
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                      "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json",
                                      str(video)], capture_output=True, text=True).stdout)
    dur = float(info["format"]["duration"])
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    fallos, avisos = [], []

    # volumen de YouTube
    lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", _ff("-i", str(video), "-vn", "-af", "ebur128", "-f", "null", "-"))[-1])
    if not LUFS_OBJETIVO[0] <= lufs <= LUFS_OBJETIVO[1]:
        fallos.append(f"Volumen {lufs:.1f} LUFS (debe estar entre {LUFS_OBJETIVO[0]} y {LUFS_OBJETIVO[1]})")
    if v["height"] < 1080 and "previa" not in video.name:
        fallos.append(f"Resolución {v['width']}x{v['height']}: el final va en 1920x1080")

    # imagen quieta
    log = _ff("-i", str(video), "-an", "-vf", f"freezedetect=n=0.001:d={QUIETO_MIN},metadata=mode=print:file=-",
              "-f", "null", "-")
    quietos = list(zip(map(float, re.findall(r"freeze_start=([\d.]+)", log)),
                       map(float, re.findall(r"freeze_duration=([\d.]+)", log))))
    for ini, d in quietos:
        (fallos if d >= 0.8 else avisos).append(f"Imagen quieta {d:.1f} s en el segundo {ini:.1f}")

    # cortes (para revisarlos a ojo: ¿son cambios de plano buscados?)
    log = _ff("-i", str(video), "-an", "-vf", "scale=480:-2,tblend=all_mode=difference,signalstats,"
              "metadata=mode=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-")
    tiempos = [float(x) for x in re.findall(r"pts_time:([\d.]+)", log)]
    cambios = [float(x) for x in re.findall(r"YAVG=([\d.]+)", log)]
    cortes = [round(t, 2) for t, c in zip(tiempos, cambios) if c > SALTO]

    # huecos de sonido: el fondo (lo más bajo que suena en general) se cae por debajo de sí mismo. Las pausas
    # entre palabras no cuentan: ahí sigue sonando el fondo; un hueco es cuando ni el fondo suena.
    db = _niveles(video)
    huecos = []
    cuerpo = sorted(db[int(1 / 0.05):max(int(1 / 0.05) + 1, len(db) - int(1.5 / 0.05))])
    fondo = cuerpo[len(cuerpo) // 10] if cuerpo else -40   # el nivel del fondo: el 10 % más bajo
    for k in range(int(0.5 / 0.05), len(db) - int(1.5 / 0.05)):
        if db[k] < fondo - HUECO_DB:
            if not huecos or k * 0.05 - huecos[-1] > 0.5:
                huecos.append(round(k * 0.05, 2))
    for t in huecos:
        fallos.append(f"Hueco de sonido en el segundo {t:.2f} (cae >{HUECO_DB:.0f} dB y vuelve: suena a corte)")
    final = db[-int(1.5 / 0.05):] if len(db) > 30 else db
    if final and min(final[:10]) < -60:
        fallos.append("El sonido muere de golpe antes de acabar el vídeo")

    # subtítulos sin voz debajo
    sin_voz = []
    if proyecto and proyecto.exists():
        p = json.loads(proyecto.read_text(encoding="utf-8"))
        voz = (p.get("voz") or {})
        palabras = (voz.get("pausas") or voz).get("palabras") or []
        wav = proyecto.parent / "render" / "voz_pausas.wav"
        if palabras and wav.exists():
            dv = _niveles(wav, 0.02)
            for w in palabras:
                pasos = [w["ini"] + i * 0.02 for i in range(max(1, int((w["fin"] - w["ini"]) / 0.02)))]
                con = sum(1 for t in pasos if 0 <= int((t - ENTRADA_VOZ) / 0.02) < len(dv)
                          and dv[int((t - ENTRADA_VOZ) / 0.02)] > -40) / len(pasos)
                if con < 0.3 and len(w["palabra"]) > 3:
                    sin_voz.append(f"«{w['palabra']}» en el segundo {w['ini']:.2f}")
        for s in sin_voz:
            fallos.append(f"Subtítulo sin voz debajo: {s}")

    return {"video": str(video), "duracion": round(dur, 2), "resolucion": f"{v['width']}x{v['height']}",
            "lufs": lufs, "cortes": cortes, "quietos": quietos, "huecos": huecos, "fallos": fallos, "avisos": avisos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--proyecto", type=Path, default=None, help="proyecto.json del vídeo (para los subtítulos)")
    a = ap.parse_args()
    r = revisar(a.video, a.proyecto)
    print(f"{Path(r['video']).name} · {r['duracion']} s · {r['resolucion']} · {r['lufs']:.1f} LUFS · {len(r['cortes'])} cortes")
    for t in r["avisos"]:
        print("  aviso:", t)
    if r["fallos"]:
        print("NO SE ENTREGA. Fallos:")
        for t in r["fallos"]:
            print("  ✗", t)
        return 1
    print("OK: sin congelados, huecos ni subtítulos sueltos")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
