"""
video_maker.py - Montaje Visual, Secuenciación y Renderizado con FFmpeg
Parte de STUDIO 4 Vol. 3 (Inspirado en la tecnología de producción de STUDIO #4)

Módulo encargado de:
1. Obtener imágenes/metraje B-roll (prioridad Google Flow > Pexels > IA NVIDIA FLUX).
2. Aplicar cinemática de cámara (Ken Burns: paneo, inclinación, zoom dinámico) para que NUNCA haya imagen plana ni pantalla negra.
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
import google_flow
from montage_director import generar_cadena_filtros_ffmpeg, planificar_montaje_escenas
from visual_generator import convertir_imagen_a_clip_cinematico, obtener_imagen_escena

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


def preparar_visuales_escenas(
    scenes: list[dict[str, Any]],
    folder: str = "temp_clips",
    orientation: str = DEFAULT_ORIENTATION,
    api_key: Optional[str] = None,
    auto_fallback_ai: bool = True,
) -> list[str]:
    """
    Garantiza que TODAS las escenas tengan material visual cinematográfico:
    1. Revisa si hay imagen entregada por Google Flow (scene_XX.png/.jpg/.webp).
    2. Si hay clave Pexels, busca clip de video HD.
    3. Si no, genera una imagen fotorrealista con IA (NVIDIA FLUX).
    4. Convierte cada imagen en un clip animado HD con movimiento de cámara Ken Burns.
    """
    pexels_key = get_pexels_api_key(api_key)
    out_dir = Path(folder).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    w, h = (1080, 1920) if orientation == "portrait" else (1920, 1080)
    clip_paths: list[str] = []
    movimientos_rotativos = ["acercar", "derecha", "alejar", "izquierda", "bajar", "subir"]

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        dur = max(2.0, float(sc.get("duration_sec", 4)))
        query = sc.get("broll_query_en") or sc.get("voice_segment") or f"Cinematic scene {order}"
        cam_mov = sc.get("camera_movement") or movimientos_rotativos[(idx - 1) % len(movimientos_rotativos)]

        target_clip = out_dir / f"raw_scene_{order:02d}.mp4"

        # 1. ¿Existe imagen de Google Flow o generada previamente?
        img_flow = None
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            cand = out_dir / f"scene_{order:02d}{ext}"
            if cand.exists() and cand.stat().st_size > 5000:
                img_flow = str(cand)
                break

        if img_flow:
            logger.info("Usando imagen visual para Escena %d: %s (Ken Burns: %s)", order, Path(img_flow).name, cam_mov)
            convertir_imagen_a_clip_cinematico(
                image_path=img_flow,
                output_clip_path=str(target_clip),
                duration_sec=dur,
                movement=cam_mov,
                width=w,
                height=h,
            )
            clip_paths.append(str(target_clip))
            continue

        # 2. Si hay Pexels configurado, buscar video
        video_url = None
        if pexels_key:
            logger.info("Buscando clip en Pexels para Escena %d: '%s'...", order, query)
            video_url = buscar_clip_pexels(query, api_key=pexels_key, orientation=orientation)

        if video_url:
            raw_video = out_dir / f"pexels_{order:02d}.mp4"
            with requests.get(video_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(raw_video, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            _normalizar_clip(str(raw_video), str(target_clip), dur, w, h, cam_mov)
            clip_paths.append(str(target_clip))
            continue

        # 3. Fallback inteligente a IA (NVIDIA FLUX) para generar la imagen de la escena
        logger.info("Generando imagen cinematográfica IA para Escena %d: '%s'...", order, query)
        img_ai = obtener_imagen_escena(
            order=order,
            prompt=query,
            folder=folder,
            auto_fallback=auto_fallback_ai,
            width=w,
            height=h,
        )

        if img_ai and Path(img_ai).exists():
            convertir_imagen_a_clip_cinematico(
                image_path=img_ai,
                output_clip_path=str(target_clip),
                duration_sec=dur,
                movement=cam_mov,
                width=w,
                height=h,
            )
            clip_paths.append(str(target_clip))
            continue

        # 4. Respaldo estilizado de emergencia si no hay red (gradiente dinámico con viñeta, nunca pantalla negra)
        logger.warning("Generando fondo de respaldo de emergencia para Escena %d", order)
        colores = ["0x1e1b4b", "0x0f172a", "0x111827", "0x1e293b", "0x022c22"]
        col = colores[(idx - 1) % len(colores)]
        lavfi = f"color=c={col}:s={w}x{h}:r=30:d={dur:.2f},noise=alls=10:allf=t+u"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", lavfi, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target_clip)], check=True, capture_output=True)
        clip_paths.append(str(target_clip))

    return clip_paths


# Mantener retrocompatibilidad
descargar_broll = preparar_visuales_escenas


def _crear_filtro_cinematico(
    movement: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: int = DEFAULT_FPS,
) -> str:
    mov = movement.lower().strip()
    dur = max(1.0, duration_sec)

    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={fps},setsar=1"
    )

    if mov == "derecha":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(t/{dur:.2f})':y='(in_h-out_h)/2',scale={width}:{height}"
    elif mov == "izquierda":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(1-t/{dur:.2f})':y='(in_h-out_h)/2',scale={width}:{height}"
    elif mov == "subir":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur:.2f})',scale={width}:{height}"
    elif mov == "bajar":
        motion = f"crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)/2':y='(in_h-out_h)*(t/{dur:.2f})',scale={width}:{height}"
    else:
        motion = f"crop=w=iw*0.93:h=ih*0.93:x='(in_w-out_w)*(0.5+0.5*sin(2*PI*t/{dur:.2f}))':y='(in_h-out_h)/2',scale={width}:{height}"

    return f"{base_filter},{motion}"


def _normalizar_clip(
    input_clip: str,
    output_clip: str,
    duration_sec: float,
    width: int,
    height: int,
    camera_movement: str = "zoom_in_dramatico",
    color_grade: str = "hollywood",
    fps: int = DEFAULT_FPS,
) -> None:
    filter_chain = generar_cadena_filtros_ffmpeg(
        movement=camera_movement,
        duration_sec=duration_sec,
        width=width,
        height=height,
        fps=fps,
        color_grade=color_grade,
        blurred_background=False,
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
    subtitle_config: Optional[dict[str, Any]] = None,
) -> str:
    """
    Ensambla el video final empaquetando:
    1. Preparación visual (Google Flow / IA) con cinemática de cámara continua.
    2. Subtítulos virales ASS configurables (paletas de color, posición, tamaño).
    3. Concatenación y quemado de subtítulos ASS en el render final.
    4. Sincronización exacta con la locución maestra.
    Soporta formatos para redes: 'reels' (9:16), 'feed' (1:1), 'completo' (16:9).
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(temp_folder).resolve()

    ori = str(orientation).lower().strip()
    if ori in ("portrait", "reels", "shorts", "tiktok", "9:16"):
        width, height = 1080, 1920
    elif ori in ("square", "feed", "1:1", "instagram"):
        width, height = 1080, 1080
    else:  # landscape / youtube / completo / 16:9
        width, height = 1920, 1080

    audio_dur = get_media_duration_ffprobe(audio_path)
    logger.info("Duración de locución detectada: %.2f segundos (%dx%d)", audio_dur, width, height)

    plan_total_sec = sum(sc.get("duration_sec", 4) for sc in scenes)
    target_total_sec = audio_dur if audio_dur > 0 else float(plan_total_sec)
    escalar = target_total_sec / float(plan_total_sec) if plan_total_sec > 0 else 1.0

    num_scenes = len(scenes)
    logger.info("Secuenciando y procesando %d escenas con movimiento de cámara...", num_scenes)

    # 1. Asegurar que cada escena tenga su clip visual animado
    preparar_visuales_escenas(scenes, folder=temp_folder, orientation=orientation, auto_fallback_ai=True)

    # 2. Dirección de Montaje Cinematográfico inteligente (Claude / Reglas de retención)
    scenes = planificar_montaje_escenas(scenes, orientation=orientation)

    normalized_clips: list[str] = []

    for idx, sc in enumerate(scenes, start=1):
        order = sc.get("order", idx)
        raw_clip = temp_dir / f"raw_scene_{order:02d}.mp4"
        norm_clip = temp_dir / f"norm_scene_{order:02d}.mp4"

        if not raw_clip.exists():
            raise FileNotFoundError(f"Clip no encontrado: {raw_clip}")

        base_dur = float(sc.get("duration_sec", 4))
        sc_dur = max(1.5, base_dur * escalar)

        cam_mov = sc.get("camera_movement", "zoom_in_dramatico")
        color_gr = sc.get("color_grade", "hollywood")

        _normalizar_clip(
            input_clip=str(raw_clip),
            output_clip=str(norm_clip),
            duration_sec=sc_dur,
            width=width,
            height=height,
            camera_movement=cam_mov,
            color_grade=color_gr,
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
    sub_cfg = subtitle_config or {}

    logger.info("Generando subtítulos ASS estilo viral...")
    construir_archivo_ass(
        scenes=scenes,
        output_ass_path=str(ass_file),
        resolution=res_str,
        hook_text=sub_cfg.get("hook_text") or hook_text,
        hook_seconds=float(sub_cfg.get("hook_seconds", 4.0)),
        palette_key=sub_cfg.get("palette_key", "viral_yellow"),
        position=sub_cfg.get("position", "bottom"),
        size_scale=sub_cfg.get("size_scale", "normal"),
        show_hook=sub_cfg.get("show_hook", True),
    )

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
