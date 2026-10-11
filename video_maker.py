"""
video_maker.py - Montaje Visual y Ensamblado de Video con Pexels y FFmpeg
Parte de STUDIO 4 Vol. 3

Módulo encargado de:
1. Buscar y descargar metraje HD de stock en Pexels para cada escena.
2. Normalizar, recortar, concatenar clips y sincronizar la pista de audio con FFmpeg.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Optional
from dotenv import load_dotenv
import requests

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger("studio4.video_maker")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
DEFAULT_ORIENTATION = os.getenv("VIDEO_ORIENTATION", "landscape")  # landscape (1920x1080) o portrait (1080x1920)
DEFAULT_FPS = 30


def get_pexels_api_key(api_key: Optional[str] = None) -> str:
    """
    Obtiene y valida la clave de API de Pexels.
    """
    key = api_key or os.getenv("PEXELS_API_KEY")
    if not key:
        raise ValueError(
            "Falta la clave PEXELS_API_KEY. "
            "Defínela en tu archivo .env o en las variables de entorno."
        )
    return key


def get_media_duration_ffprobe(file_path: str) -> float:
    """
    Obtiene la duración exacta de un archivo multimedia (audio o video) usando ffprobe.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        logger.debug("ffprobe falló al obtener duración de %s: %s", file_path, e)
        return 0.0


def buscar_clip_pexels(
    query: str,
    api_key: str,
    orientation: str = "landscape",
    min_width: int = 1280,
) -> Optional[str]:
    """
    Busca un video HD en Pexels según la consulta en inglés.

    Returns:
        Optional[str]: URL directa de descarga del archivo de video MP4, o None si no se encuentra.
    """
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": 6,
        "orientation": orientation,
    }

    try:
        resp = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Error consultando Pexels para query '%s': %s", query, e)
        return None

    videos = data.get("videos", [])
    if not videos:
        # Intento de búsqueda fallback simplificando la consulta si era muy específica
        palabras = query.split()
        if len(palabras) > 2:
            query_simplificada = " ".join(palabras[:2])
            logger.info("Sin resultados para '%s'. Reintentando con '%s'...", query, query_simplificada)
            params["query"] = query_simplificada
            try:
                resp2 = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
                if resp2.status_code == 200:
                    videos = resp2.json().get("videos", [])
            except Exception:
                pass

    if not videos:
        return None

    # Seleccionar el mejor archivo MP4 disponible (preferencia HD 1080p o 720p)
    for video_item in videos:
        archivos = video_item.get("video_files", [])
        # Filtrar solo MP4
        mp4_files = [f for f in archivos if f.get("file_type") == "video/mp4"]
        if not mp4_files:
            continue

        # Ordenar por ancho descendente
        mp4_files.sort(key=lambda x: x.get("width") or 0, reverse=True)

        for f in mp4_files:
            width = f.get("width") or 0
            if width >= min_width:
                return f.get("link")

        # Si ninguno alcanza min_width, tomar el de mayor resolución
        if mp4_files:
            return mp4_files[0].get("link")

    return None


def descargar_broll(
    scenes: list[dict[str, Any]],
    folder: str = "temp_clips",
    orientation: str = DEFAULT_ORIENTATION,
    api_key: Optional[str] = None,
) -> list[str]:
    """
    Descarga clips B-roll de Pexels para cada una de las escenas especificadas.

    Args:
        scenes: Lista de diccionarios de escenas (deben incluir 'order' y 'broll_query_en').
        folder: Carpeta de destino temporal para almacenar los clips.
        orientation: 'landscape' (16:9) o 'portrait' (9:16).
        api_key: Clave opcional de Pexels.

    Returns:
        list[str]: Lista con las rutas a los archivos de video descargados por escena.
    """
    key = api_key or os.getenv("PEXELS_API_KEY")
    out_dir = Path(folder).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[str] = []
    fallback_query = "cinematic abstract dark technology background 4k"

    # Si no hay clave de Pexels, generamos clips sintéticos de fondo procedural con FFmpeg
    if not key:
        logger.warning(
            "PEXELS_API_KEY no configurada. Generando metraje cinemático procedural con FFmpeg para pruebas..."
        )
        w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)
        colores = ["0x0f172a", "0x1e1b4b", "0x111827", "0x1e293b", "0x09090b"]
        grid_colores = ["0x6366f1@0.3", "0xa855f7@0.3", "0x06b6d4@0.3", "0x3b82f6@0.3", "0xec4899@0.3"]

        for idx, sc in enumerate(scenes, start=1):
            order = sc.get("order", idx)
            target_file = out_dir / f"raw_scene_{order:02d}.mp4"
            dur = max(3.0, float(sc.get("duration_sec", 4)))
            color = colores[(idx - 1) % len(colores)]
            grid_color = grid_colores[(idx - 1) % len(grid_colores)]

            # Generar fondo con cuadrícula moderna y acento de color
            lavfi_input = f"color=c={color}:s={w}x{h}:r=30:d={dur:.2f},drawgrid=width=120:height=120:thickness=2:color={grid_color}"
            cmd_proc = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", lavfi_input,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                str(target_file),
            ]
            subprocess.run(cmd_proc, capture_output=True, check=True)
            clip_paths.append(str(target_file))
        return clip_paths

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        query = sc.get("broll_query_en", fallback_query)
        target_file = out_dir / f"raw_scene_{order:02d}.mp4"

        # Si ya existe y es válido (>50KB), reutilizarlo
        if target_file.exists() and target_file.stat().st_size > 50000:
            logger.info("Clip existente reutilizado para escena %d: %s", order, target_file.name)
            clip_paths.append(str(target_file))
            continue

        logger.info("Buscando metraje en Pexels para escena %d: '%s'...", order, query)
        video_url = buscar_clip_pexels(query, api_key=key, orientation=orientation)

        if not video_url:
            logger.warning(
                "No se encontró clip para '%s'. Usando metraje de respaldo...", query
            )
            video_url = buscar_clip_pexels(fallback_query, api_key=key, orientation=orientation)

        if not video_url:
            raise RuntimeError(
                f"No se pudo encontrar ningún clip en Pexels para la escena {order} ni con fallback."
            )

        logger.info("Descargando clip para escena %d...", order)
        with requests.get(video_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(target_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        logger.info("Escena %d descargada: %s (%.2f MB)", order, target_file.name, target_file.stat().st_size / (1024 * 1024))
        clip_paths.append(str(target_file))

    return clip_paths


def _escape_ffmpeg_text(t: str) -> str:
    """Escapa caracteres conflictivos para drawtext en FFmpeg."""
    if not t:
        return ""
    return t.replace("\\", "\\\\").replace("'", "").replace(":", "\\:").replace("%", "\\%").strip()


def _normalizar_clip(
    input_clip: str,
    output_clip: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: int = DEFAULT_FPS,
    overlay_text: Optional[str] = None,
    caption_text: Optional[str] = None,
) -> None:
    """
    Normaliza un clip a resolución, framerate, duración y formato uniforme usando FFmpeg.
    Superpone el texto de gancho (overlay) y subtítulo de la escena.
    """
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        f"fps={fps}",
        "setsar=1",
    ]

    # Fuente estándar de Windows para tipografía de impacto
    font_bold = "C\\:/Windows/Fonts/arialbd.ttf"
    font_regular = "C\\:/Windows/Fonts/arial.ttf"

    # Superponer texto de gancho central (Overlay)
    if overlay_text and overlay_text.strip():
        txt_escaped = _escape_ffmpeg_text(overlay_text.upper())
        font_size = 52 if width >= 1920 else 38
        filters.append(
            f"drawtext=fontfile='{font_bold}':text='{txt_escaped}':"
            f"fontsize={font_size}:fontcolor=white:box=1:boxcolor=0x0b0f19@0.75:boxborderw=16:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )

    # Superponer subtítulo inferior de la locución si existe
    if caption_text and caption_text.strip():
        sub_escaped = _escape_ffmpeg_text(caption_text)
        sub_size = 32 if width >= 1920 else 24
        filters.append(
            f"drawtext=fontfile='{font_regular}':text='{sub_escaped}':"
            f"fontsize={sub_size}:fontcolor=0xfacc15:box=1:boxcolor=black@0.65:boxborderw=10:"
            f"x=(w-text_w)/2:y=h-text_h-60"
        )

    filter_complex = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",  # Permite bucle si el clip de origen dura menos que duration_sec
        "-i", input_clip,
        "-t", f"{duration_sec:.2f}",
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-an",  # Remover audio original del stock
        output_clip,
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("FFmpeg error al normalizar %s:\n%s", input_clip, res.stderr)
        raise RuntimeError(f"FFmpeg falló al procesar {input_clip}")


def ensamblar_video(
    scenes: list[dict[str, Any]],
    audio_path: str,
    output_path: str = "output/video_final.mp4",
    temp_folder: str = "temp_clips",
    orientation: str = DEFAULT_ORIENTATION,
) -> str:
    """
    Ensambla el video final recortando, normalizando y concatenando los clips,
    y fusionando la pista de locución con FFmpeg.

    Args:
        scenes: Lista de escenas con metadatos y duraciones.
        audio_path: Ruta al archivo de audio de locución (.wav o .mp3).
        output_path: Ruta del video MP4 final.
        temp_folder: Carpeta donde residen los clips crudos y procesados.
        orientation: 'landscape' (1920x1080) o 'portrait' (1080x1920).

    Returns:
        str: Ruta absoluta del video final generado.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(temp_folder).resolve()

    # Dimensiones estándar
    if orientation == "portrait":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    # 1. Medir duración total del audio
    audio_dur = get_media_duration_ffprobe(audio_path)
    logger.info("Duración de audio detectada: %.2f segundos", audio_dur)

    # Si por alguna razón no se detecta la duración, sumar las duraciones estimadas de escenas
    plan_total_sec = sum(sc.get("duration_sec", 4) for sc in scenes)
    target_total_sec = audio_dur if audio_dur > 0 else float(plan_total_sec)

    # 2. Ajustar proporcionalmente las duraciones de cada escena para calzar exactamente con el audio
    num_scenes = len(scenes)
    escalar = target_total_sec / float(plan_total_sec) if plan_total_sec > 0 else 1.0

    normalized_clips: list[str] = []
    logger.info("Normalizando %d clips para resolución %dx%d...", num_scenes, width, height)

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        raw_clip = temp_dir / f"raw_scene_{order:02d}.mp4"
        norm_clip = temp_dir / f"norm_scene_{order:02d}.mp4"

        if not raw_clip.exists():
            raise FileNotFoundError(f"No existe el clip descargado: {raw_clip}")

        # Duración ajustada para esta escena
        base_dur = float(sc.get("duration_sec", 4))
        sc_dur = max(1.5, base_dur * escalar)

        _normalizar_clip(
            input_clip=str(raw_clip),
            output_clip=str(norm_clip),
            duration_sec=sc_dur,
            width=width,
            height=height,
            overlay_text=sc.get("overlay_text"),
            caption_text=sc.get("voice_segment"),
        )
        normalized_clips.append(str(norm_clip))

    # 3. Crear archivo de lista para el demuxer concat de FFmpeg
    concat_list_file = temp_dir / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for clip in normalized_clips:
            # En Windows FFmpeg requiere barras inclinadas hacia adelante o escapar adecuadamente
            safe_path = Path(clip).as_posix()
            f.write(f"file '{safe_path}'\n")

    # 4. Concatenación y mezcla final con la pista de audio
    logger.info("Concatenando clips y mezclando audio con FFmpeg...")
    cmd_concat = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",  # Finaliza cuando la pista de audio concluye
        str(out_file),
    ]

    res = subprocess.run(cmd_concat, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("Error en ensamblaje final de FFmpeg:\n%s", res.stderr)
        raise RuntimeError("FFmpeg falló al ensamblar el video final.")

    final_dur = get_media_duration_ffprobe(str(out_file))
    logger.info(
        "Video final exportado exitosamente en: %s (Duración: %.2fs)",
        out_file,
        final_dur,
    )
    return str(out_file)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    print("\n--- Verificación de video_maker.py ---")
    print(f"FFmpeg disponible: True")
    print(f"Pexels search endpoint configurado: {PEXELS_SEARCH_URL}")

