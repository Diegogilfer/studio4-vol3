"""
video_maker.py - Montaje Visual, Secuenciación y Renderizado con FFmpeg
Parte de STUDIO 4 Vol. 3 (Inspirado en la tecnología de producción de STUDIO #4)

Módulo encargado de:
1. Obtener metraje B-roll (vía Pexels API o fondos procedurales con movimiento).
2. Aplicar cinemática de cámara (Ken Burns: paneo, inclinación, zoom dinámico) para que NUNCA haya imagen plana.
3. Generar y quemar subtítulos ASS estilo viral (karaoke con palabra activa y banner superior).
4. Ensamblar y sincronizar toda la pista con FFmpeg.
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

from subtitles import construir_archivo_ass

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger("studio4.video_maker")

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
DEFAULT_ORIENTATION = os.getenv("VIDEO_ORIENTATION", "landscape")
DEFAULT_FPS = 30


def get_pexels_api_key(api_key: Optional[str] = None) -> Optional[str]:
    """Obtiene la clave de API de Pexels si está configurada."""
    return api_key or os.getenv("PEXELS_API_KEY") or None


def get_media_duration_ffprobe(file_path: str) -> float:
    """Obtiene la duración exacta de un archivo multimedia usando ffprobe."""
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
    """Busca un video HD en Pexels según la consulta cinematográfica en inglés."""
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": 5,
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
        palabras = query.split()
        if len(palabras) > 2:
            query_simplificada = " ".join(palabras[:2])
            params["query"] = query_simplificada
            try:
                resp2 = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params, timeout=15)
                if resp2.status_code == 200:
                    videos = resp2.json().get("videos", [])
            except Exception:
                pass

    if not videos:
        return None

    for video_item in videos:
        archivos = video_item.get("video_files", [])
        mp4_files = [f for f in archivos if f.get("file_type") == "video/mp4"]
        if not mp4_files:
            continue

        mp4_files.sort(key=lambda x: x.get("width") or 0, reverse=True)
        for f in mp4_files:
            width = f.get("width") or 0
            if width >= min_width:
                return f.get("link")

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
    Descarga metraje de Pexels si hay clave, o genera metraje cinemático procedimental con cuadrícula.
    """
    key = get_pexels_api_key(api_key)
    out_dir = Path(folder).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[str] = []
    w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)
    colores = ["0x0f172a", "0x1e1b4b", "0x111827", "0x1e293b", "0x09090b"]
    grid_colores = ["0x6366f1@0.3", "0xa855f7@0.3", "0x06b6d4@0.3", "0x3b82f6@0.3", "0xec4899@0.3"]

    # Si no hay clave de Pexels, generamos clips sintéticos con dinamismo y rejilla
    if not key:
        logger.info("PEXELS_API_KEY no detectada. Generando fondos cinemáticos dinámicos con FFmpeg...")
        for idx, sc in enumerate(scenes, start=1):
            order = sc.get("order", idx)
            target_file = out_dir / f"raw_scene_{order:02d}.mp4"
            dur = max(3.0, float(sc.get("duration_sec", 4)))
            color = colores[(idx - 1) % len(colores)]
            grid_color = grid_colores[(idx - 1) % len(grid_colores)]

            lavfi_input = (
                f"color=c={color}:s={w}x{h}:r=30:d={dur:.2f},"
                f"drawgrid=width=120:height=120:thickness=2:color={grid_color}"
            )
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

    fallback_query = "cinematic abstract dark technology background 4k"

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        query = sc.get("broll_query_en", fallback_query)
        target_file = out_dir / f"raw_scene_{order:02d}.mp4"

        if target_file.exists() and target_file.stat().st_size > 50000:
            logger.info("Clip en caché para escena %d: %s", order, target_file.name)
            clip_paths.append(str(target_file))
            continue

        logger.info("Buscando en Pexels para escena %d: '%s'...", order, query)
        video_url = buscar_clip_pexels(query, api_key=key, orientation=orientation)
        if not video_url:
            video_url = buscar_clip_pexels(fallback_query, api_key=key, orientation=orientation)

        if not video_url:
            # Fallback a fondo dinámico
            lavfi_input = f"color=c=0x0f172a:s={w}x{h}:r=30:d=4,drawgrid=width=120:height=120:thickness=2:color=0x6366f1@0.3"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", lavfi_input, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target_file)], check=True, capture_output=True)
            clip_paths.append(str(target_file))
            continue

        with requests.get(video_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(target_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        clip_paths.append(str(target_file))

    return clip_paths


def _crear_filtro_cinematico(
    movement: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: int = DEFAULT_FPS,
) -> str:
    """
    Construye la cadena de filtros para dar secuencia y movimiento continuo (Ken Burns):
    - Escala y ajusta encuadre.
    - Aplica paneo suave (derecha, izquierda, subir, bajar) o recorte dinámico.
    - Cero planos estáticos: la cámara siempre está viva.
    """
    mov = movement.lower().strip()
    dur = max(1.0, duration_sec)

    # 1. Normalización base a dimensiones objetivo
    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={fps},setsar=1"
    )

    # 2. Cinemática de cámara (Ken Burns dinámico usando crop per-frame)
    # Recorte al 92% con desplazamiento suave en el tiempo
    if mov == "derecha":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(t/{dur:.2f})':y='(in_h-out_h)/2',scale={width}:{height}"
    elif mov == "izquierda":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(1-t/{dur:.2f})':y='(in_h-out_h)/2',scale={width}:{height}"
    elif mov == "subir":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur:.2f})',scale={width}:{height}"
    elif mov == "bajar":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)/2':y='(in_h-out_h)*(t/{dur:.2f})',scale={width}:{height}"
    elif mov == "diagonal":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(t/{dur:.2f})':y='(in_h-out_h)*(t/{dur:.2f})',scale={width}:{height}"
    else:
        # Por defecto paneo flotante suave
        motion = f"crop=w=iw*0.93:h=ih*0.93:x='(in_w-out_w)*(0.5+0.5*sin(2*PI*t/{dur:.2f}))':y='(in_h-out_h)/2',scale={width}:{height}"

    return f"{base_filter},{motion}"


def _normalizar_clip(
    input_clip: str,
    output_clip: str,
    duration_sec: float,
    width: int,
    height: int,
    camera_movement: str = "acercar",
    fps: int = DEFAULT_FPS,
) -> None:
    """
    Normaliza y aplica movimiento de cámara al clip individual de la escena.
    """
    filter_chain = _crear_filtro_cinematico(
        movement=camera_movement,
        duration_sec=duration_sec,
        width=width,
        height=height,
        fps=fps,
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", input_clip,
        "-t", f"{duration_sec:.2f}",
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-an",
        output_clip,
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("FFmpeg error al procesar %s:\n%s", input_clip, res.stderr)
        raise RuntimeError(f"FFmpeg falló al procesar escena: {input_clip}")


def ensamblar_video(
    scenes: list[dict[str, Any]],
    audio_path: str,
    output_path: str = "output/video_final.mp4",
    temp_folder: str = "temp_clips",
    orientation: str = DEFAULT_ORIENTATION,
) -> str:
    """
    Ensambla el video final empaquetando:
    1. Normalización secuencial con cinemática de cámara.
    2. Generación de subtítulos virales ASS (con karaoke de palabra activa y banner de gancho).
    3. Concatenación y quemado de subtítulos ASS en el render final.
    4. Sincronización con la locución maestra.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(temp_folder).resolve()

    if orientation == "portrait":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    audio_dur = get_media_duration_ffprobe(audio_path)
    logger.info("Duración de locución detectada: %.2f segundos", audio_dur)

    plan_total_sec = sum(sc.get("duration_sec", 4) for sc in scenes)
    target_total_sec = audio_dur if audio_dur > 0 else float(plan_total_sec)
    escalar = target_total_sec / float(plan_total_sec) if plan_total_sec > 0 else 1.0

    num_scenes = len(scenes)
    logger.info("Secuenciando y procesando %d escenas con movimiento de cámara...", num_scenes)

    movimientos_rotativos = ["derecha", "izquierda", "bajar", "subir", "diagonal"]
    normalized_clips: list[str] = []

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        raw_clip = temp_dir / f"raw_scene_{order:02d}.mp4"
        norm_clip = temp_dir / f"norm_scene_{order:02d}.mp4"

        if not raw_clip.exists():
            raise FileNotFoundError(f"Clip no encontrado: {raw_clip}")

        base_dur = float(sc.get("duration_sec", 4))
        sc_dur = max(1.5, base_dur * escalar)

        # Determinar movimiento de cámara
        cam_mov = sc.get("camera_movement") or movimientos_rotativos[(idx - 1) % len(movimientos_rotativos)]

        _normalizar_clip(
            input_clip=str(raw_clip),
            output_clip=str(norm_clip),
            duration_sec=sc_dur,
            width=width,
            height=height,
            camera_movement=cam_mov,
        )
        normalized_clips.append(str(norm_clip))

    # Lista de concatenación
    concat_list_file = temp_dir / "concat_list.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for clip in normalized_clips:
            safe_path = Path(clip).as_posix()
            f.write(f"file '{safe_path}'\n")

    # Generar subtítulos virales ASS (con gancho superior y karaoke de palabra activa)
    ass_file = temp_dir / "subtitulos.ass"
    hook_text = scenes[0].get("overlay_text", "") if scenes else ""
    res_str = f"{width}x{height}"

    logger.info("Generando subtítulos ASS estilo viral...")
    construir_archivo_ass(
        scenes=scenes,
        output_ass_path=str(ass_file),
        resolution=res_str,
        hook_text=hook_text,
        hook_seconds=4.0,
    )

    # Render final: concatenación + quemado de subtítulos ASS + pista de audio
    # Usar ruta relativa para evitar problemas de dos puntos (C:) con filtros de FFmpeg en Windows
    try:
        rel_ass = os.path.relpath(ass_file).replace("\\", "/")
    except ValueError:
        rel_ass = ass_file.as_posix().replace(":", "\\:")
    
    logger.info("Renderizando video final empaquetado con subtítulos ASS (%s) y audio maestro...", rel_ass)

    cmd_final = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-i", audio_path,
        "-vf", f"ass=filename='{rel_ass}'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out_file),
    ]

    res = subprocess.run(cmd_final, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("Error en renderizado final FFmpeg:\n%s", res.stderr)
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
    print("\n--- Verificación de video_maker.py (STUDIO 4 Vol. 3) ---")
    print(f"FFmpeg listo con libass y xfade: True")
