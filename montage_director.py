"""
montage_director.py - Director de Montaje Cinematográfico con IA para FFmpeg
Permite que Claude (o Gemini bajo tu suscripción Google) actúe como el Montajista
Profesional que diseña los ritmos, movimientos de cámara Ken Burns, transiciones
y filtros cinematográficos que ejecuta FFmpeg.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("studio4.montage_director")

# Modos cinematográficos de cámara sugeridos por el Montajista
ESTILOS_MOVIMIENTO = {
    "zoom_in_dramatico": "crop=w=iw*(1-0.12*t/{dur}):h=ih*(1-0.12*t/{dur}):x='(in_w-out_w)/2':y='(in_h-out_h)/2',scale={w}:{h}",
    "zoom_out_revelacion": "crop=w=iw*(0.88+0.12*t/{dur}):h=ih*(0.88+0.12*t/{dur}):x='(in_w-out_w)/2':y='(in_h-out_h)/2',scale={w}:{h}",
    "paneo_derecha_suave": "crop=w=iw*0.90:h=ih*0.90:x='(in_w-out_w)*(t/{dur})':y='(in_h-out_h)/2',scale={w}:{h}",
    "paneo_izquierda_suave": "crop=w=iw*0.90:h=ih*0.90:x='(in_w-out_w)*(1-t/{dur})':y='(in_h-out_h)/2',scale={w}:{h}",
    "barrido_vertical_subir": "crop=w=iw*0.90:h=ih*0.90:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur})',scale={w}:{h}",
    "barrido_vertical_bajar": "crop=w=iw*0.90:h=ih*0.90:x='(in_w-out_w)/2':y='(in_h-out_h)*(t/{dur})',scale={w}:{h}",
    "pulso_cinematico": "crop=w=iw*0.92:h=ih*0.92:x='(in_w-out_w)*(0.5+0.5*sin(2*PI*t/{dur}))':y='(in_h-out_h)/2',scale={w}:{h}",
}

# Gradación de color y atmósfera cinematográfica FFmpeg
GRADOS_COLOR = {
    "hollywood": "eq=contrast=1.12:brightness=0.01:saturation=1.15,vignette=angle=PI/4:aspect=1",
    "cyberpunk": "eq=contrast=1.20:brightness=0.02:saturation=1.35,colorbalance=rs=0.1:gs=-0.05:bs=0.2",
    "documental": "eq=contrast=1.05:brightness=0.00:saturation=1.05,unsharp=5:5:0.8:5:5:0.4",
    "vintage": "eq=contrast=1.08:brightness=0.03:saturation=0.90,colorbalance=rs=0.15:gs=0.05:bs=-0.1",
    "natural": "eq=contrast=1.04:brightness=0.01:saturation=1.08",
}


def planificar_montaje_escenas(
    scenes: list[dict[str, Any]],
    orientation: str = "portrait",
    engine: str = "auto",  # 'claude', 'gemini' o 'auto'
) -> list[dict[str, Any]]:
    """
    Claude (o Gemini en fallback con tu suscripción Google) analiza las escenas
    y asigna a cada una el movimiento cinematográfico, grado de color y ritmo
    óptimo para captar y retener la atención del espectador.
    """
    plan_montaje: list[dict[str, Any]] = []
    num_escenas = len(scenes)

    # 1. Si hay clave de Claude configurada y engine lo solicita, usar Claude
    claude_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if (engine == "claude" or (engine == "auto" and claude_key)) and claude_key:
        try:
            logger.info("Claude como Director de Montaje para FFmpeg analizando %d escenas...", num_escenas)
            import anthropic
            client = anthropic.Anthropic(api_key=claude_key)
            prompt_editor = f"""Actúa como Director de Montaje Cinematográfico experto para FFmpeg.
Analiza este desglose de escenas para un video en formato {orientation.upper()}:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

Para cada escena, asigna:
1. "camera_movement": uno de ["zoom_in_dramatico", "zoom_out_revelacion", "paneo_derecha_suave", "paneo_izquierda_suave", "barrido_vertical_subir", "barrido_vertical_bajar", "pulso_cinematico"]
2. "color_grade": uno de ["hollywood", "cyberpunk", "documental", "vintage", "natural"]
3. "tension_level": número del 1 al 10.

Responde ÚNICAMENTE en JSON con la clave "scenes": [...]
"""
            msg = client.messages.create(
                model="claude-3-7-sonnet-latest",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt_editor}],
            )
            raw = msg.content[0].text.strip()
            # Limpiar posibles bloques markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())
            return data.get("scenes", scenes)
        except Exception as e:
            logger.warning("Claude no disponible para montaje (%s), delegando en motor de reglas cinematográficas...", e)

    # 2. Reglas cinematográficas maestras (ritmo de retención comprobado)
    for idx, sc in enumerate(scenes, start=1):
        sc_copy = dict(sc)
        if idx == 1:
            # Escena 1: Gancho viral inicial -> Zoom in rápido hacia el foco de atención
            sc_copy["camera_movement"] = "zoom_in_dramatico"
            sc_copy["color_grade"] = "hollywood"
            sc_copy["tension_level"] = 9
        elif idx == num_escenas:
            # Última escena: Cierre / Resolución -> Revelación panorámica
            sc_copy["camera_movement"] = "zoom_out_revelacion"
            sc_copy["color_grade"] = "hollywood"
            sc_copy["tension_level"] = 8
        elif idx % 2 == 0:
            # Escenas pares: Transición lateral fluida
            sc_copy["camera_movement"] = "paneo_derecha_suave" if idx % 4 == 0 else "paneo_izquierda_suave"
            sc_copy["color_grade"] = "natural"
            sc_copy["tension_level"] = 6
        else:
            # Escenas impares: Barrido vertical
            sc_copy["camera_movement"] = "barrido_vertical_subir" if idx % 3 == 0 else "pulso_cinematico"
            sc_copy["color_grade"] = "hollywood"
            sc_copy["tension_level"] = 7

        plan_montaje.append(sc_copy)

    return plan_montaje


def generar_cadena_filtros_ffmpeg(
    movement: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: int = 30,
    color_grade: str = "hollywood",
    blurred_background: bool = True,
) -> str:
    """
    Construye la cadena de filtros FFmpeg (filter_complex / -vf) diseñada
    por el Montajista, con Ken Burns cinematográfico, blur backdrop para 9:16 y color grading.
    """
    dur = max(1.0, duration_sec)
    mov_key = movement.lower().strip()
    motion_expr = ESTILOS_MOVIMIENTO.get(
        mov_key,
        ESTILOS_MOVIMIENTO["zoom_in_dramatico"]
    ).format(dur=f"{dur:.2f}", w=width, h=height)

    color_filter = GRADOS_COLOR.get(color_grade, GRADOS_COLOR["hollywood"])

    if blurred_background and height > width:
        # Modo Vertical (9:16 Reels/Shorts): Crea fondo con desenfoque gaussiano + imagen central nítida
        # Evita bandas negras feas en imágenes que no sean nativas 9:16
        filter_str = (
            f"split [fg][bg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=25:5[bgblur];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgfit];"
            f"[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2,"
            f"{motion_expr},"
            f"{color_filter},"
            f"fps={fps},setsar=1"
        )
        return filter_str
    else:
        # Modo Paisaje (16:9) o Cuadrado (1:1)
        base_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        return f"{base_filter},{motion_expr},{color_filter},fps={fps},setsar=1"
