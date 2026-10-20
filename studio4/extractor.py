"""Extractor: fragmentos cortos de vídeos REALES (tráilers oficiales, gameplay sin comentario) para ilustrar un guion.

1. `descargar`: baja el vídeo (hasta 1080p) una sola vez y lo guarda en la caché de fuentes.
2. `planos`: detecta cada cambio de plano con FFmpeg (sin dependencias nuevas).
3. `hoja`: una imagen con un fotograma de cada plano, numerado, para que el autor elija.
4. `cortar`: el trozo elegido, SIN su audio (fuera su música y su voz) y reencodificado para cortar exacto.

Reglas del canal: fuentes seguras; fragmentos de pocos segundos, transformados (en tarjetas, con nuestra voz y
rótulos); nunca la voz, la cara, el logo ni la música de otro creador. Cada fuente queda en `fuentes.json`.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import config, medios

CACHE = config.PRODUCCIONES / "_fuentes_video"
MAX_ALTO = 1080


def opciones_ytdlp(**extra: Any) -> dict[str, Any]:
    """Opciones comunes de yt-dlp: YouTube ya exige un motor de JavaScript (Node está instalado)."""
    return {"quiet": True, "no_warnings": True, "noplaylist": True, "js_runtimes": {"node": {}}, **extra}


def descargar(url: str) -> dict[str, Any]:
    """Baja el vídeo una vez (se reutiliza). Devuelve {archivo, titulo, canal, url, duracion}."""
    import yt_dlp
    CACHE.mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL(opciones_ytdlp(skip_download=True)) as y:
        info = y.extract_info(url, download=False)
    destino = CACHE / f"{info['id']}.mp4"
    if not destino.exists():
        with yt_dlp.YoutubeDL(opciones_ytdlp(
                format=f"bv*[height<={MAX_ALTO}]+ba/b[height<={MAX_ALTO}]/b",   # sin forzar mp4: algunos dan 403
                merge_output_format="mp4", outtmpl=str(CACHE / "%(id)s.%(ext)s"))) as y:
            y.download([url])
    datos = {"archivo": str(destino), "titulo": info.get("title", ""), "canal": info.get("channel") or info.get("uploader", ""),
             "url": info.get("webpage_url", url), "duracion": float(info.get("duration") or 0)}
    (CACHE / f"{info['id']}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


def descargar_tramo(url: str, ini: float, fin: float, alto: int = MAX_ALTO, nombre: str = "") -> Path:
    """Solo el tramo [ini, fin] de un vídeo largo (p. ej. una misión de un gameplay de 4 h), a la altura pedida:
    en baja para buscar escenas sin descargar horas, en alta solo los segundos elegidos."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    CACHE.mkdir(parents=True, exist_ok=True)
    vid = re.search(r"(?:v=|youtu\.be/)([\w-]{6,})", url)
    base = nombre or f"{vid.group(1) if vid else 'video'}_{int(ini)}-{int(fin)}_{alto}p"
    destino = CACHE / f"{base}.mp4"
    if not destino.exists():
        with yt_dlp.YoutubeDL(opciones_ytdlp(
                format=f"bv*[height<={alto}]+ba/b[height<={alto}]/b", merge_output_format="mp4",
                download_ranges=download_range_func(None, [(ini, fin)]), force_keyframes_at_cuts=alto >= 720,
                outtmpl=str(CACHE / f"{base}.%(ext)s"))) as y:
            y.download([url])
    return destino


def planos(video: Path, umbral: float = 0.32, minimo: float = 0.8) -> list[tuple[float, float]]:
    """Los planos del vídeo [(ini, fin)] según los cambios de imagen (los de menos de `minimo` s se juntan)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-an", "-vf",
                        f"scale=320:-2,select='gt(scene,{umbral})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    cortes = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    total = medios.duracion(video)
    bordes = [0.0]
    for c in cortes:
        if c - bordes[-1] >= minimo:
            bordes.append(c)
    if total - bordes[-1] < minimo and len(bordes) > 1:
        bordes.pop()
    bordes.append(total)
    return [(round(a, 2), round(b, 2)) for a, b in zip(bordes, bordes[1:])]


def hoja(video: Path, lista: list[tuple[float, float]], destino: Path, prefijo: str = "P", columnas: int = 6) -> Path:
    """Un fotograma (el del medio) de cada plano, numerado y con su duración, para elegir."""
    tiles = []
    fuente = ImageFont.truetype("arialbd.ttf", 18)
    for k, (a, b) in enumerate(lista):
        tmp = destino.with_name(f"_t{k}.jpg")
        medios.ffmpeg("-ss", f"{(a + b) / 2:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=320:180", str(tmp))
        t = Image.open(tmp).convert("RGB")
        tmp.unlink(missing_ok=True)
        d = ImageDraw.Draw(t)
        d.rectangle([0, 0, 118, 24], fill="black")
        d.text((4, 2), f"{prefijo}{k + 1:02d} · {b - a:.1f}s", fill="yellow", font=fuente)
        tiles.append(t)
    filas = max(1, (len(tiles) + columnas - 1) // columnas)
    out = Image.new("RGB", (columnas * 320, filas * 180), "black")
    for k, t in enumerate(tiles):
        out.paste(t, ((k % columnas) * 320, (k // columnas) * 180))
    destino.parent.mkdir(parents=True, exist_ok=True)
    out.save(destino, quality=85)
    return destino


def cortar(video: Path, ini: float, fin: float, destino: Path, alto: int = MAX_ALTO) -> Path:
    """El fragmento [ini, fin] sin audio, cortado exacto (reencodificado)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    medios.ffmpeg("-ss", f"{ini:.3f}", "-i", str(video), "-t", f"{max(0.2, fin - ini):.3f}", "-an",
                  "-vf", f"scale=-2:'min({alto},ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destino))
    return destino


def apuntar_fuente(carpeta: Path, datos: dict[str, Any], ini: float, fin: float, uso: str) -> None:
    """Deja constancia de cada fragmento usado (para «Fuentes y créditos» de la descripción)."""
    ruta = carpeta / "fuentes.json"
    lista = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    lista.append({"titulo": datos.get("titulo", ""), "canal": datos.get("canal", ""), "url": datos.get("url", ""),
                  "ini": ini, "fin": fin, "uso": uso, "fecha": time.strftime("%Y-%m-%d")})
    ruta.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
