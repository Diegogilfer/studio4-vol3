"""
subtitles.py - Generador de Subtítulos Virales en formato ASS y SRT
Parte de STUDIO 4 Vol. 3 (Basado en la tecnología de producción de STUDIO #4)

Produce subtítulos con:
- Estilo viral (tipo TikTok / YouTube Shorts) con resaltado de la palabra activa en tiempo real.
- Banner de gancho (Hook) superior en los primeros segundos.
- Paletas de color personalizables (Amarillo Viral, Cyan Neón, Rosa Eléctrico, etc.).
- Ajustes de tamaño, tipografía y posición vertical en pantalla.
- Sincronización milimétrica con la voz de la escena.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("studio4.subtitles")

# Paletas de color para karaoke (formato BGR de ASS: &H00BBGGRR&)
PALETAS_SUBTITULOS = {
    "viral_yellow": {
        "name": "Amarillo Viral (Predeterminado)",
        "highlight": "&H0000FFFF&",  # Amarillo fluorescente
        "primary": "&H00FFFFFF&",    # Blanco puro
        "outline": "&H00000000&",    # Negro
    },
    "cyan_neon": {
        "name": "Cyan Neón Futurista",
        "highlight": "&H00FFFF00&",  # Cyan brillante
        "primary": "&H00FFFFFF&",
        "outline": "&H00000000&",
    },
    "pink_hot": {
        "name": "Rosa Eléctrico / TikTok",
        "highlight": "&H00B020FF&",  # Rosa intenso
        "primary": "&H00FFFFFF&",
        "outline": "&H00000000&",
    },
    "green_matrix": {
        "name": "Verde Matrix / Hacker",
        "highlight": "&H0000FF00&",  # Verde lima
        "primary": "&H00FFFFFF&",
        "outline": "&H00000000&",
    },
    "white_minimal": {
        "name": "Blanco Minimalista",
        "highlight": "&H00FFFFFF&",
        "primary": "&H00D0D0D0&",
        "outline": "&H00000000&",
    },
}


def _clean(word: str) -> str:
    """Limpia caracteres que interfieran con la sintaxis de ASS."""
    return word.strip().replace("{", "(").replace("}", ")").replace("\n", " ").replace("\\", "/")


def _fmt_ass_ts(seconds: float) -> str:
    """Formatea segundos a formato de timestamp ASS (H:MM:SS.CS)."""
    if seconds < 0:
        seconds = 0.0
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _balance(text: str, cpl: int, max_lines: int = 2) -> str:
    """Reparte un texto en líneas equilibradas con saltos duros de ASS (\\N)."""
    text = " ".join((text or "").split())
    if not text or len(text) <= cpl:
        return text
    palabras = text.split(" ")
    tope = cpl * max_lines
    if len(text) > tope:
        acumulado = ""
        for p in palabras:
            if len(acumulado) + len(p) + 1 > tope - 1:
                break
            acumulado = f"{acumulado} {p}".strip()
        text = (acumulado or text[:tope - 1]).rstrip(" ,;:.") + "…"
        palabras = text.split(" ")

    mejor, mejor_dif = len(palabras) // 2, None
    for i in range(1, len(palabras)):
        a = len(" ".join(palabras[:i]))
        b = len(" ".join(palabras[i:]))
        if a > cpl or b > cpl:
            continue
        if mejor_dif is None or abs(a - b) < mejor_dif:
            mejor, mejor_dif = i, abs(a - b)
    return "\\N".join([" ".join(palabras[:mejor]), " ".join(palabras[mejor:])])


def generar_palabras_desde_escenas(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Desglosa el texto de cada escena en palabras estimadas cronológicamente
    según la duración asignada a cada fragmento.
    """
    words_timeline: list[dict[str, Any]] = []
    t_acumulado = 0.0

    for sc in scenes:
        segment = sc.get("voice_segment", "").strip()
        dur = float(sc.get("duration_sec", 4.0))
        if not segment:
            t_acumulado += dur
            continue

        raw_words = segment.split()
        if not raw_words:
            t_acumulado += dur
            continue

        dur_por_palabra = dur / len(raw_words)

        for idx, w in enumerate(raw_words):
            w_start = t_acumulado + (idx * dur_por_palabra)
            w_end = w_start + dur_por_palabra
            words_timeline.append({
                "start": w_start,
                "end": w_end,
                "word": _clean(w),
            })

        t_acumulado += dur

    return words_timeline


def construir_archivo_ass(
    scenes: list[dict[str, Any]],
    output_ass_path: str,
    resolution: str = "1920x1080",
    hook_text: str = "",
    hook_seconds: float = 4.0,
    font_name: str = "Arial",
    palette_key: str = "viral_yellow",
    highlight_color: Optional[str] = None,
    primary_color: Optional[str] = None,
    outline_color: Optional[str] = None,
    position: str = "bottom",       # bottom, middle, top
    size_scale: str = "normal",     # small, normal, large
    show_hook: bool = True,
) -> str:
    """
    Construye un archivo de subtítulos ASS completo y configurable con estilo viral.
    """
    try:
        play_x, play_y = (int(v) for v in resolution.lower().split("x"))
    except Exception:
        play_x, play_y = 1920, 1080

    pal = PALETAS_SUBTITULOS.get(palette_key, PALETAS_SUBTITULOS["viral_yellow"])
    c_highlight = highlight_color or pal["highlight"]
    c_primary = primary_color or pal["primary"]
    c_outline = outline_color or pal["outline"]

    is_vertical = play_y > play_x
    base_font_size = 68 if is_vertical else 52

    # Escala de tamaño
    multiplicador_tamano = {"small": 0.8, "normal": 1.0, "large": 1.25}.get(size_scale, 1.0)
    font_size = int(base_font_size * multiplicador_tamano)
    hook_size = max(32, int(font_size * 0.7))

    # Posición vertical (margen inferior en px)
    if position == "middle":
        margin_v = int(play_y * 0.44)
    elif position == "top":
        margin_v = int(play_y * 0.78)
    else:  # bottom
        margin_v = int(play_y * (0.16 if is_vertical else 0.10))

    hook_margin_v = int(play_y * 0.06)
    hook_margin_h = int(play_x * 0.08)
    max_words = 3 if is_vertical else 5

    # Encabezado ASS con estilos V4+
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font_name},{font_size},{c_primary},{c_primary},{c_outline},&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,40,40,{margin_v},1
Style: Hook,{font_name},{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,12,0,8,{hook_margin_h},{hook_margin_h},{hook_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    # 1. Banner superior de gancho (Hook) si está activado
    if show_hook:
        if not hook_text and scenes:
            hook_text = scenes[0].get("overlay_text", "")

        if hook_text and hook_seconds > 0:
            clean_hook = _balance(_clean(hook_text).upper(), cpl=26)
            events.append(
                f"Dialogue: 1,0:00:00.00,{_fmt_ass_ts(hook_seconds)},Hook,,0,0,0,,{clean_hook}"
            )

    # 2. Generar subtítulos sincronizados con resaltado de palabra activa
    words = generar_palabras_desde_escenas(scenes)
    lines: list[list[dict[str, Any]]] = [
        words[i:i + max_words] for i in range(0, len(words), max_words)
    ]

    for line in lines:
        for i, w in enumerate(line):
            start = w["start"]
            end = line[i + 1]["start"] if i + 1 < len(line) else w["end"]
            if end <= start:
                end = start + 0.35

            parts = []
            for j, ww in enumerate(line):
                if j == i:
                    parts.append(f"{{\\c{c_highlight}\\b1}}{ww['word']}{{\\c{c_primary}\\b0}}")
                else:
                    parts.append(ww["word"])

            rendered_text = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_fmt_ass_ts(start)},{_fmt_ass_ts(end)},Main,,0,0,0,,{rendered_text}"
            )

    out_file = Path(output_ass_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

    logger.info("Subtítulos ASS generados: paleta='%s', posición='%s'", palette_key, position)
    return str(out_file)
