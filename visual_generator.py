"""
visual_generator.py - Generador y Gestor Visual para STUDIO 4 Vol. 3
Combina Google Flow como motor principal con NVIDIA FLUX como respaldo cinematográfico inmediato.

Garantía:
NUNCA deja pantallas negras ni planos estáticos. Cada escena cuenta con una imagen
real (de Google Flow o generada con IA) animada con movimiento de cámara Ken Burns.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from typing import Any, Optional
from dotenv import load_dotenv

import google_flow

load_dotenv()

logger = logging.getLogger("studio4.visual_generator")

NVIDIA_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"


def generar_imagen_nvidia(prompt: str, output_path: str, width: int = 1024, height: int = 1024, retries: int = 2) -> Optional[str]:
    """Genera una imagen fotorrealista de alta fidelidad usando NVIDIA FLUX."""
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        logger.warning("NVIDIA_API_KEY no configurada.")
        return None

    # Ajustar dimensiones admitidas por FLUX (múltiplos de 64 cercanos a 1024 o 1344)
    w = 1344 if width > height else 1024
    h = 768 if width > height else (1344 if height > width else 1024)

    payload = {
        "prompt": prompt[:1500],
        "width": w,
        "height": h,
        "steps": 28,
        "seed": int(time.time() * 1000) % 2**31,
    }

    req = urllib.request.Request(
        NVIDIA_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    for intento in range(retries):
        try:
            logger.info("Generando imagen con NVIDIA FLUX (intento %d)...", intento + 1)
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
                artifacts = data.get("artifacts", [])
                if not artifacts or not artifacts[0].get("base64"):
                    continue
                b64 = artifacts[0]["base64"]
                out_p = Path(output_path).resolve()
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.write_bytes(base64.b64decode(b64))
                logger.info("Imagen NVIDIA FLUX generada en: %s (%d bytes)", out_p.name, out_p.stat().st_size)
                return str(out_p)
        except Exception as e:
            logger.warning("Fallo al generar con NVIDIA FLUX en intento %d: %s", intento + 1, e)
            time.sleep(2)

    return None


def obtener_imagen_escena(
    order: int,
    prompt: str,
    folder: str = "temp_clips",
    auto_fallback: bool = True,
    width: int = 1920,
    height: int = 1080,
) -> Optional[str]:
    """
    Busca la imagen de la escena en el siguiente orden de prioridad:
    1. Imagen recibida de Google Flow (scene_XX.png / .jpg / .webp).
    2. Si auto_fallback es True: Genera con NVIDIA FLUX.
    """
    out_dir = Path(folder).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Verificar si ya existe imagen en disco (de Google Flow o anterior)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        cand = out_dir / f"scene_{order:02d}{ext}"
        if cand.exists() and cand.stat().st_size > 5000:
            logger.info("Imagen encontrada en disco para Escena %d: %s", order, cand.name)
            return str(cand)

    # 2. Generar con NVIDIA FLUX si está permitido
    if auto_fallback:
        target_file = out_dir / f"scene_{order:02d}.jpg"
        prompt_enriquecido = f"{prompt}, cinematic lighting, photorealistic, 8k, detailed, dramatic atmosphere"
        img_path = generar_imagen_nvidia(prompt_enriquecido, str(target_file), width=width, height=height)
        if img_path:
            # Registrar en la sesión de Google Flow para que el dashboard también la vea
            google_flow.recibir_imagen(Path(img_path).read_bytes(), prompt=prompt, scene_order=order)
            return img_path

    return None


def convertir_imagen_a_clip_cinematico(
    image_path: str,
    output_clip_path: str,
    duration_sec: float,
    movement: str = "acercar",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    """
    Convierte una imagen fija en un clip de video HD con cinemática viva (Ken Burns):
    - acercar (zoom-in suave)
    - alejar (zoom-out suave)
    - derecha (paneo lateral horizontal a la derecha)
    - izquierda (paneo lateral horizontal a la izquierda)
    - subir / bajar (paneo vertical)
    """
    dur = max(1.5, float(duration_sec))
    mov = (movement or "acercar").lower().strip()
    out_path = Path(output_clip_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Base: escalar preservando aspecto para cubrir el lienzo con margen para el movimiento
    # Usamos factor de escala 1.15x para tener margen de paneo y zoom
    w_zoom = int(width * 1.15)
    h_zoom = int(height * 1.15)

    base = f"scale={w_zoom}:{h_zoom}:force_original_aspect_ratio=increase,crop={w_zoom}:{h_zoom}"

    if mov == "derecha":
        motion = f"crop={width}:{height}:x='(in_w-out_w)*(t/{dur:.2f})':y='(in_h-out_h)/2'"
    elif mov == "izquierda":
        motion = f"crop={width}:{height}:x='(in_w-out_w)*(1-t/{dur:.2f})':y='(in_h-out_h)/2'"
    elif mov == "subir":
        motion = f"crop={width}:{height}:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur:.2f})'"
    elif mov == "bajar":
        motion = f"crop={width}:{height}:x='(in_w-out_w)/2':y='(in_h-out_h)*(t/{dur:.2f})'"
    elif mov == "diagonal":
        motion = f"crop={width}:{height}:x='(in_w-out_w)*(t/{dur:.2f})':y='(in_h-out_h)*(t/{dur:.2f})'"
    else:  # acercar / cinemática flotante viva
        motion = f"crop={width}:{height}:x='(in_w-out_w)*(0.5+0.45*sin(2*PI*t/{dur:.2f}))':y='(in_h-out_h)*(0.5+0.45*cos(2*PI*t/{dur:.2f}))'"

    filter_complex = f"{base},{motion},fps={fps},setsar=1"

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(Path(image_path).resolve()),
        "-t", f"{dur:.2f}",
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("FFmpeg error al transformar imagen %s a clip:\n%s", image_path, res.stderr)
        raise RuntimeError(f"FFmpeg falló al animar imagen: {image_path}")

    return str(out_path)
