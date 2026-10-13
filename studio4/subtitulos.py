"""Subtítulos virales (ASS): 2-5 palabras en pantalla con la palabra que suena resaltada."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Colores ASS en formato &H00BBGGRR
PALETAS = {
    "amarillo": {"nombre": "Amarillo viral", "resalte": "&H0000E5FF", "texto": "&H00FFFFFF"},
    "cian": {"nombre": "Cian neón", "resalte": "&H00FFE100", "texto": "&H00FFFFFF"},
    "rosa": {"nombre": "Rosa eléctrico", "resalte": "&H00B020FF", "texto": "&H00FFFFFF"},
    "verde": {"nombre": "Verde lima", "resalte": "&H0000FF7F", "texto": "&H00FFFFFF"},
    "blanco": {"nombre": "Blanco minimal", "resalte": "&H00FFFFFF", "texto": "&H00C8C8C8"},
}
POR_DEFECTO = {"activos": True, "paleta": "amarillo", "posicion": "abajo", "tamano": "normal", "gancho": True}


def _ts(s: float) -> str:
    s = max(0.0, s)
    h, rem = divmod(s, 3600)
    m, seg = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{seg:05.2f}"


def _limpia(palabra: str) -> str:
    return re.sub(r"[{}\\]", "", palabra).strip()


def _lineas(palabras: list[dict], max_palabras: int) -> list[list[dict]]:
    """Agrupa palabras en líneas; corta antes si hay pausa larga o fin de frase."""
    lineas: list[list[dict]] = []
    actual: list[dict] = []
    for i, p in enumerate(palabras):
        actual.append(p)
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else None
        fin_frase = p["palabra"].endswith((".", "?", "!", "…", ":", ";"))
        pausa = siguiente is not None and siguiente["ini"] - p["fin"] > 0.35
        if len(actual) >= max_palabras or fin_frase or pausa or siguiente is None:
            lineas.append(actual)
            actual = []
    return lineas


def construir(palabras: list[dict[str, Any]], destino: Path, ancho: int, alto: int,
              ajustes: dict[str, Any] | None = None, gancho: str = "", segundos_gancho: float = 3.0) -> Path:
    a = {**POR_DEFECTO, **(ajustes or {})}
    pal = PALETAS.get(a["paleta"], PALETAS["amarillo"])
    vertical = alto > ancho
    tam = int((74 if vertical else 58) * {"pequeno": 0.8, "normal": 1.0, "grande": 1.25}.get(a["tamano"], 1.0))
    margen = {"arriba": int(alto * 0.72), "centro": int(alto * 0.42)}.get(a["posicion"], int(alto * (0.2 if vertical else 0.1)))
    tam_gancho = max(36, int(tam * 0.72))

    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ancho}
PlayResY: {alto}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Arial Black,{tam},{pal['texto']},{pal['texto']},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margen},1
Style: Gancho,Arial Black,{tam_gancho},&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,14,0,8,{int(ancho * 0.08)},{int(ancho * 0.08)},{int(alto * 0.07)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos: list[str] = []
    if a["gancho"] and gancho.strip():
        eventos.append(f"Dialogue: 1,{_ts(0)},{_ts(segundos_gancho)},Gancho,,0,0,0,,{_limpia(gancho).upper()}")

    if a["activos"]:
        lineas = _lineas(palabras, 3 if vertical else 5)
        for n, linea in enumerate(lineas):
            textos = [_limpia(p["palabra"]).upper() for p in linea]
            # La línea se quita justo cuando empieza la siguiente: nunca dos líneas encimadas.
            tope = lineas[n + 1][0]["ini"] if n + 1 < len(lineas) else float("inf")
            for i, p in enumerate(linea):
                ini = p["ini"]
                fin = linea[i + 1]["ini"] if i + 1 < len(linea) else min(p["fin"] + 0.15, tope)
                partes = [f"{{\\c{pal['resalte']}\\fscx108\\fscy108}}{t}{{\\c{pal['texto']}\\fscx100\\fscy100}}" if j == i else t
                          for j, t in enumerate(textos)]
                eventos.append(f"Dialogue: 0,{_ts(ini)},{_ts(max(fin, ini + 0.08))},Main,,0,0,0,,{' '.join(partes)}")

    destino.write_text(cab + "\n".join(eventos) + "\n", encoding="utf-8")
    return destino
