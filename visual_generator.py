"""
visual_generator.py - Generador y Gestor Visual para STUDIO 4 Vol. 3
Permite seleccionar modelos de imagen (Google Flow, NVIDIA FLUX, Nano Banana)
y estilos gráficos cinematográficos (Anime, Cyberpunk, Sci-Fi, Documental).
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

# Catálogo de estilos visuales predefinidos para dirección de arte
ESTILOS_GRAFICOS = {
    "cinematic": "cinematic photorealistic, 35mm lens, anamorphic lighting, 8k, hyperdetailed, dramatic atmosphere",
    "anime": "Studio Ghibli and Makoto Shinkai anime aesthetic, vibrant atmospheric sky, soft painterly background, cel shaded, highly detailed anime artwork",
    "cyberpunk": "cyberpunk neon aesthetic, rainy asphalt reflections, volumetric smog, futuristic city night, dark moody atmosphere, holographic glows",
    "documentary": "National Geographic documentary photography, natural golden hour lighting, authentic real-world textures, 50mm lens, sharp crisp focus",
    "scifi": "hard science fiction, deep space cosmos, nebula glow, quantum physics, interstellar scale, high-tech holographic elements",
    "vintage": "retro vintage 1970s film stock, warm Kodak Kodachrome color grading, authentic film grain, nostalgic composition",
    "dark_fantasy": "dark fantasy oil painting, ethereal lighting, mysterious shadows, baroque art style, dramatic contrast",
}

# Catálogo de motores de imagen admitidos
MODELOS_IMAGEN = {
    "google_flow": "Google Flow (labs.google - Gratuito, estilo consistente vía extensión)",
    "nvidia_flux": "NVIDIA FLUX.1 Dev (Fotorrealismo ultrarrápido ~5s)",
    "nano_banana": "Nano Banana / fal.ai (Generación ultra premium por API)",
    "pexels_video": "Pexels Stock Video HD (Metraje de archivo real)",
}


def generar_imagen_nvidia(
    prompt: str,
    output_path: str,
    style: str = "cinematic",
    width: int = 1024,
    height: int = 1024,
    retries: int = 2,
) -> Optional[str]:
    """Genera una imagen de alta fidelidad usando NVIDIA FLUX."""
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        logger.warning("NVIDIA_API_KEY no configurada.")
        return None

    # Enriquecer prompt con el estilo gráfico seleccionado
    modificador_estilo = ESTILOS_GRAFICOS.get(style, ESTILOS_GRAFICOS["cinematic"])
    prompt_completo = f"{prompt}, {modificador_estilo}"

    # Ajustar dimensiones admitidas por FLUX (múltiplos de 64)
    if width > height:
        w, h = 1344, 768
    elif height > width:
        w, h = 768, 1344
    else:
        w, h = 1024, 1024

    payload = {
        "prompt": prompt_completo[:1500],
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
            logger.info("Generando imagen con NVIDIA FLUX (estilo '%s', intento %d)...", style, intento + 1)
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
                artifacts = data.get("artifacts", [])
                if not artifacts or not artifacts[0].get("base64"):
                    continue
                b64 = artifacts[0]["base64"]
                out_p = Path(output_path).resolve()
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.write_bytes(base64.b64decode(b64))
                dur = time.time() - t0
                logger.info("Imagen NVIDIA FLUX generada en %.2fs: %s (%d bytes)", dur, out_p.name, out_p.stat().st_size)
                return str(out_p)
        except Exception as e:
            logger.warning("Fallo al generar con NVIDIA FLUX en intento %d: %s", intento + 1, e)
            time.sleep(2)

    return None


def obtener_imagen_escena(
    order: int,
    prompt: str,
    folder: str = "temp_clips",
    style: str = "cinematic",
    model_provider: str = "google_flow",
    auto_fallback: bool = True,
    width: int = 1920,
    height: int = 1080,
) -> Optional[str]:
    """
    Busca o genera la imagen de la escena según el modelo y estilo seleccionados.
    """
    out_dir = Path(folder).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Si ya existe imagen recibida en disco (de Google Flow o subida manual)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        cand = out_dir / f"scene_{order:02d}{ext}"
        if cand.exists() and cand.stat().st_size > 5000:
            logger.info("Imagen lista en disco para Escena %d: %s", order, cand.name)
            return str(cand)

    # 2. Si el motor seleccionado es NVIDIA FLUX directo o fallback
    if model_provider in ("nvidia_flux", "auto") or auto_fallback:
        target_file = out_dir / f"scene_{order:02d}.jpg"
        img_path = generar_imagen_nvidia(
            prompt=prompt,
            output_path=str(target_file),
            style=style,
            width=width,
            height=height,
        )
        if img_path:
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
    Convierte una imagen fija en un clip de video HD con movimiento cinemático vivo (Ken Burns).
    Soporta formato 16:9 (1920x1080), 9:16 (1080x1920) y 1:1 (1080x1080).
    """
    dur = max(1.5, float(duration_sec))
    mov = (movement or "acercar").lower().strip()
    out_path = Path(output_clip_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

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
    else:  # acercar o cinemática flotante viva
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
