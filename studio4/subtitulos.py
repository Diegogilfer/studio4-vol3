"""Subtítulos (ASS), en dos estilos:
- viral: 2-5 palabras en mayúsculas con la palabra que suena resaltada;
- cine: la frase entera en una o dos líneas, blanca y limpia, como en las películas.
En los dos se pueden añadir los sonidos entre corchetes y en cursiva ([Explosión lejana]), encima del diálogo."""

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
POR_DEFECTO = {"activos": True, "paleta": "amarillo", "posicion": "abajo", "tamano": "normal", "gancho": True,
               "estilo": "viral", "sonidos": True}
ESTILOS = {"viral": "Viral", "cine": "Cine"}


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


def _frases(palabras: list[dict], max_letras: int) -> list[list[dict]]:
    """Agrupa palabras en frases de cine: corta al acabar la frase, en una pausa o al llenar dos líneas."""
    frases: list[list[dict]] = []
    actual: list[dict] = []
    for i, p in enumerate(palabras):
        actual.append(p)
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else None
        letras = sum(len(w["palabra"]) + 1 for w in actual)
        fin_frase = p["palabra"].endswith((".", "?", "!", "…"))
        pausa = siguiente is not None and siguiente["ini"] - p["fin"] > 0.6
        coma = p["palabra"].endswith((",", ";", ":")) and letras > max_letras * 0.55   # mejor cortar en una coma
        llena = siguiente is not None and letras + len(siguiente["palabra"]) > max_letras
        if llena:   # no dejar 1 o 2 palabras sueltas: si la frase acaba enseguida, se estira un poco
            resto = [w for w in palabras[i + 1:i + 3]]
            cierre = next((k for k, w in enumerate(resto) if w["palabra"].endswith((".", "?", "!", "…"))), None)
            if cierre is not None and letras + sum(len(w["palabra"]) + 1 for w in resto[:cierre + 1]) <= max_letras + 16:
                llena = False
        if fin_frase or pausa or coma or llena or siguiente is None:
            frases.append(actual)
            actual = []
    return frases


def _dos_lineas(textos: list[str], max_linea: int) -> str:
    """Una línea si cabe; si no, dos lo más parejas posible (como los subtítulos de cine)."""
    frase = " ".join(textos)
    if len(frase) <= max_linea:
        return frase
    mejor = min(range(1, len(textos)), key=lambda k: abs(len(" ".join(textos[:k])) - len(" ".join(textos[k:]))))
    return " ".join(textos[:mejor]) + "\\N" + " ".join(textos[mejor:])


def construir(palabras: list[dict[str, Any]], destino: Path, ancho: int, alto: int,
              ajustes: dict[str, Any] | None = None, gancho: str = "", segundos_gancho: float = 3.0,
              sonidos: list[dict[str, Any]] | None = None) -> Path:
    a = {**POR_DEFECTO, **(ajustes or {})}
    cine = a["estilo"] == "cine"
    pal = PALETAS.get(a["paleta"], PALETAS["amarillo"])
    vertical = alto > ancho
    tam = int((74 if vertical else 80) * {"pequeno": 0.8, "normal": 1.0, "grande": 1.25}.get(a["tamano"], 1.0))
    margen = {"arriba": int(alto * 0.72), "centro": int(alto * 0.42)}.get(a["posicion"], int(alto * (0.2 if vertical else 0.1)))
    tam_gancho = max(44, int(tam * (0.72 if vertical else 0.95)))
    factor = {"pequeno": 0.85, "normal": 1.0, "grande": 1.2}.get(a["tamano"], 1.0)
    tam_cine = int((60 if vertical else 54) * factor)
    margen_cine = {"arriba": int(alto * 0.78), "centro": int(alto * 0.45)}.get(a["posicion"], int(alto * (0.14 if vertical else 0.07)))
    tam_sonido = int(tam_cine * 0.86)
    # Los sonidos van justo encima del diálogo en cine; con el viral (letras grandes), arriba del todo.
    if cine:
        estilo_sonido = f"Sonido,Arial,{tam_sonido},&H00E8E8E8,&H00E8E8E8,&H00000000,&H80000000,0,-1,0,0,100,100,0,0,1,2.2,1,2,60,60,{margen_cine + int(tam_cine * 2.5)},1"
    else:
        estilo_sonido = f"Sonido,Arial,{tam_sonido},&H00E8E8E8,&H00E8E8E8,&H00000000,&H80000000,0,-1,0,0,100,100,0,0,1,2.2,1,8,60,60,{int(alto * 0.13)},1"

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
Style: Cine,Arial,{tam_cine},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.6,1.2,2,{int(ancho * 0.08)},{int(ancho * 0.08)},{margen_cine},1
Style: {estilo_sonido}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos: list[str] = []
    if a["gancho"] and gancho.strip():
        eventos.append(f"Dialogue: 1,{_ts(0)},{_ts(segundos_gancho)},Gancho,,0,0,0,,{_limpia(gancho).upper()}")

    if a["activos"] and cine:
        max_linea = 30 if vertical else 42
        frases = _frases(palabras, max_linea * 2)
        for n, frase in enumerate(frases):
            ini = frase[0]["ini"]
            tope = frases[n + 1][0]["ini"] - 0.05 if n + 1 < len(frases) else float("inf")
            fin = min(max(frase[-1]["fin"] + 0.3, ini + 0.9), tope)
            texto = _dos_lineas([_limpia(p["palabra"]) for p in frase], max_linea)
            eventos.append(f"Dialogue: 0,{_ts(ini)},{_ts(max(fin, ini + 0.2))},Cine,,0,0,0,,{texto}")
    elif a["activos"]:
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

    if a["sonidos"]:
        for s in sonidos or []:
            eventos.append(f"Dialogue: 2,{_ts(s['ini'])},{_ts(s['fin'])},Sonido,,0,0,0,,[{_limpia(s['texto'])}]")

    destino.write_text(cab + "\n".join(eventos) + "\n", encoding="utf-8")
    return destino
