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


# Palabras que no pueden cerrar una línea: «VUELVE A VICE CITY CON» deja la idea colgada
DEBILES = {"a", "al", "con", "de", "del", "el", "en", "la", "las", "lo", "los", "un", "una", "y", "e", "o", "que",
           "no", "ha", "han", "se", "su", "sus", "por", "para", "sin", "mi", "tu", "le", "les", "me", "te", "es", "más"}


def _cierra(p: dict) -> bool:
    return p["palabra"].endswith((".", "?", "!", "…", ":", ";"))


def _mismo_nombre(a: dict, b: dict) -> bool:
    """«Vice City», «The Warriors»: dos palabras seguidas con mayúscula no se separan de línea."""
    x, y = _limpia(a["palabra"]), _limpia(b["palabra"])
    return bool(x[:1].isupper() and y[:1].isupper() and not x.endswith((",", ".")))


def _lineas(palabras: list[dict], max_palabras: int) -> list[list[dict]]:
    """Agrupa palabras en líneas; corta en el fin de frase, en una coma, en una pausa o al llenarse.
    Una línea llena nunca acaba en «con», «no ha»…: esas palabras pasan a la siguiente. Y si a la frase le quedan
    una o dos palabras, se quedan en esta línea en vez de salir solas."""
    lineas: list[list[dict]] = []
    i = 0
    while i < len(palabras):
        actual: list[dict] = []
        while i < len(palabras):
            p = palabras[i]
            actual.append(p)
            i += 1
            siguiente = palabras[i] if i < len(palabras) else None
            if siguiente is None or _cierra(p) or siguiente["ini"] - p["fin"] > 0.35:
                break
            if p["palabra"].endswith(",") and len(actual) >= 3:
                break
            if len(actual) >= max_palabras:
                resto = palabras[i:i + 3]
                cierre = next((k for k, w in enumerate(resto) if _cierra(w) or w["palabra"].endswith(",")), None)
                if cierre == 0:   # «… CONTADO | TODO.» → todo en una línea
                    actual += resto[:1]
                    i += 1
                    break
                while len(actual) > 2 and (_limpia(actual[-1]["palabra"]).lower().strip(",") in DEBILES
                                           or _mismo_nombre(actual[-1], palabras[i])):
                    actual.pop()
                    i -= 1
                break
        lineas.append(actual)
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


def srt(palabras: list[dict[str, Any]], destino: Path, max_linea: int = 42) -> Path:
    """Los subtítulos en .srt para subirlos a YouTube (subtítulos aparte, que YouTube indexa): frases de una o dos
    líneas, cortadas como en el cine (fin de frase, coma o pausa)."""
    def ts(s: float) -> str:
        ms = int(round(max(0.0, s) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    frases = _frases(palabras, max_linea * 2)
    bloques = []
    for n, frase in enumerate(frases):
        ini = frase[0]["ini"]
        tope = frases[n + 1][0]["ini"] - 0.05 if n + 1 < len(frases) else float("inf")
        fin = min(max(frase[-1]["fin"] + 0.3, ini + 0.9), tope)
        texto = _dos_lineas([_limpia(p["palabra"]) for p in frase], max_linea).replace("\\N", "\n")
        bloques.append(f"{n + 1}\n{ts(ini)} --> {ts(max(fin, ini + 0.2))}\n{texto}\n")
    destino.write_text("\n".join(bloques), encoding="utf-8")
    return destino


# --- Subtítulos en varios idiomas (pistas .srt para subir a YouTube) -----------------------------------------------
# Códigos de archivo → nombre del idioma para el traductor. El español es el original (no se traduce).
IDIOMAS = {"es": "español latino neutro", "en": "inglés", "zh": "chino mandarín simplificado", "ja": "japonés"}


def _leer_srt(texto: str) -> list[tuple[str, str]]:
    """Un .srt → [(cabecera «n\\ntiempos», texto)]: separa el tiempo (que no se toca) del texto (que se traduce)."""
    cues = []
    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = bloque.splitlines()
        if len(lineas) >= 2 and "-->" in lineas[1]:
            cues.append(("\n".join(lineas[:2]), "\n".join(lineas[2:])))
    return cues


def traducir_srt(texto: str, idioma: str, generar) -> str:
    """Traduce SOLO el texto de cada subtítulo a `idioma` y reconstruye el .srt con los mismos números y tiempos.
    `generar(prompt)` devuelve el texto del modelo (Gemini/DeepSeek). Si falla o descuadra, devuelve el original."""
    import json
    nombre = IDIOMAS.get(idioma, idioma)
    cues = _leer_srt(texto)
    if not cues:
        return texto
    originales = [c[1].replace("\n", " ") for c in cues]
    sistema = (f"Eres subtitulador profesional. Traduce al {nombre} cada línea de esta lista de subtítulos, "
               "una traducción por entrada, en el MISMO orden y la misma cantidad. Mantén el sentido, natural y "
               "breve para que quepa en pantalla. No numeres, no añadas comillas. Devuelve solo JSON: "
               '{"t": ["traducción 1", "traducción 2", ...]}')
    crudo = generar(sistema + "\n\nLÍNEAS:\n" + json.dumps(originales, ensure_ascii=False))
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    traducidas = json.loads(m.group(0) if m else crudo).get("t", []) if m or crudo.strip().startswith("{") else []
    if len(traducidas) != len(cues):   # el modelo descuadró: mejor el original que un .srt roto
        raise ValueError(f"El traductor devolvió {len(traducidas)} líneas de {len(cues)}")
    partes = [f"{cab}\n{str(t).strip()}" for (cab, _orig), t in zip(cues, traducidas)]
    return "\n\n".join(partes) + "\n"


def construir(palabras: list[dict[str, Any]], destino: Path, ancho: int, alto: int,
              ajustes: dict[str, Any] | None = None, gancho: str = "", segundos_gancho: float = 3.0,
              sonidos: list[dict[str, Any]] | None = None, inicio_gancho: float = 0.0) -> Path:
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
        eventos.append(f"Dialogue: 1,{_ts(inicio_gancho)},{_ts(inicio_gancho + segundos_gancho)},Gancho,,0,0,0,,"
                       f"{_limpia(gancho).upper()}")

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
