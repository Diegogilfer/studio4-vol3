"""El empaque de un vídeo antes de subirlo: título + miniatura como UNA pareja, capítulos que YouTube acepte y el
gancho de la primera frase. Reglas fijas y gratis (sin IA): avisan de lo que suele costar clics.

Ideas tomadas de youtube-agent-skill (Jake Schincariol, MIT), reescritas para español y para Studio 4.
"""

from __future__ import annotations

import re
from typing import Any

ESCRITORIO, MOVIL, MAXIMO = 60, 40, 100      # YouTube corta el título hacia los 60 (búsqueda) y los 40 (móvil)
VACIAS = {"increíble", "increible", "brutal", "épico", "epico", "loco", "locura", "mejor", "definitivo", "definitiva",
          "secreto", "todo", "impresionante", "alucinante", "perfecto", "nunca", "visto", "insano", "tremendo"}
RELLENO = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y", "o", "que", "es",
           "por", "para", "con", "su", "sus", "lo", "se", "este", "esta", "esto", "mi", "tu", "como", "qué", "sin", "no", "más",
           "ya", "le", "les", "me", "te", "nos"}


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü0-9]+", texto.lower())


def revisar_titulo(titulo: str, miniatura: str = "") -> dict[str, Any]:
    """Nota de 0 a 100, lo que falla y lo que está bien de un título junto al texto de su miniatura."""
    t = " ".join((titulo or "").split())
    sin_emoji = re.sub(r"[^\w\s¿?¡!:,.$%#|()-]", "", t).strip()
    n = len(t)
    mal: list[str] = []
    bien: list[str] = []
    info: list[str] = []   # para saberlo, sin restar nota
    if n > MAXIMO:
        mal.append(f"{n} caracteres: YouTube no deja más de {MAXIMO}")
    elif n > ESCRITORIO:
        mal.append(f"{n} caracteres: en la búsqueda se corta hacia el {ESCRITORIO}")
    else:
        bien.append(f"{n} caracteres, se ve entero en la búsqueda")
    if n > MOVIL:
        corte = t[:MOVIL].rsplit(" ", 1)[0]
        info.append(f"en el móvil se lee «{corte}…»: que el tema quede ahí")
    gritos = [w for w in sin_emoji.split() if len(w) > 2 and w.isupper() and not w.isdigit()]
    if len(gritos) > 2:
        mal.append(f"{len(gritos)} palabras en MAYÚSCULAS: más de dos parece spam")
    vacias = sorted({w for w in _palabras(t) if w in VACIAS})
    if vacias:
        mal.append(f"«{', '.join(vacias)}» no dice nada: cámbialo por un número, un nombre o una fecha")
    if re.search(r"\d", t):
        bien.append("lleva un dato concreto (número o fecha)")
    else:
        mal.append("sin número ni fecha: es el arreglo que más suele subir los clics")
    if not [w for w in _palabras(t)[:3] if w not in RELLENO]:
        mal.append("las tres primeras palabras son relleno: adelanta el tema")
    if miniatura:
        comunes = sorted((set(_palabras(t)) - RELLENO) & (set(_palabras(miniatura)) - RELLENO))
        if comunes:
            mal.append(f"la miniatura repite «{', '.join(comunes)}» del título: que diga lo que el título no dice")
        else:
            bien.append("título y miniatura dicen cosas distintas (se suman)")
        if len(_palabras(miniatura)) > 4:
            mal.append(f"{len(_palabras(miniatura))} palabras en la miniatura: en pequeño no se leen más de 3 o 4")
    nota = max(0, min(100, 100 - 14 * len(mal) + 4 * len(bien)))
    return {"titulo": t, "nota": nota, "mal": mal, "bien": bien, "info": info}


def _segundos(marca: str) -> int:
    partes = [int(x) for x in marca.split(":")]
    s = 0
    for x in partes:
        s = s * 60 + x
    return s


def capitulos_validos(capitulos: list[str], duracion: float) -> tuple[list[str], str]:
    """Los capítulos solo aparecen en YouTube si hay 3 o más, el primero empieza en 0:00 y cada uno dura 10 s o
    más. Junta los que se quedan cortos; si aun así no cumplen, no se ponen (y se dice por qué)."""
    filas = []
    for c in capitulos:
        m = re.match(r"^\s*(\d{1,2}(?::\d{2}){1,2})\s+(.+)$", c)
        if m:
            filas.append((_segundos(m.group(1)), m.group(2).strip()))
    filas.sort()
    if filas and filas[0][0] != 0:
        filas.insert(0, (0, filas[0][1]))
    limpios: list[tuple[int, str]] = []
    for s, txt in filas:
        if limpios and s - limpios[-1][0] < 10:
            continue   # demasiado cerca del anterior: se queda dentro de él
        limpios.append((s, txt))
    if limpios and duracion - limpios[-1][0] < 10:
        limpios.pop()
    if len(limpios) < 3:
        return [], "Vídeo demasiado corto para capítulos (YouTube pide 3 o más de 10 s)."
    return [f"{s // 60}:{s % 60:02d} {txt}" for s, txt in limpios], ""


def revisar_gancho(frase: str, titulo: str) -> dict[str, Any]:
    """La primera frase decide si se quedan: corta, con un dato concreto y sobre lo que promete el título."""
    p = _palabras(frase)
    mal, bien = [], []
    if len(p) > 18:
        mal.append(f"{len(p)} palabras: el gancho se dice en 3-4 segundos (unas 12)")
    else:
        bien.append("corto, se dice en pocos segundos")
    if re.search(r"\d", frase) or re.search(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", frase[1:]):
        bien.append("lleva un dato o un nombre concreto")
    else:
        mal.append("sin dato ni nombre concreto")
    clave = (set(_palabras(titulo)) - RELLENO) & (set(p) - RELLENO)
    if clave:
        bien.append("confirma lo que promete el título")
    else:
        mal.append("no repite nada del título: quien hizo clic no ve confirmado lo que buscaba")
    return {"nota": max(0, min(100, 100 - 20 * len(mal) + 5 * len(bien))), "mal": mal, "bien": bien}


def revisar(textos: dict[str, Any], primera_frase: str, duracion: float) -> dict[str, Any]:
    """Todo el empaque de un vídeo, para enseñarlo junto a los textos de publicar."""
    mini = textos.get("texto_miniatura", "")
    titulos = [revisar_titulo(t, mini) for t in textos.get("titulos") or []]
    capitulos, aviso = capitulos_validos(textos.get("capitulos") or [], duracion)
    return {"titulos": titulos, "mejor": max(range(len(titulos)), key=lambda k: titulos[k]["nota"]) if titulos else -1,
            "gancho": revisar_gancho(primera_frase, (textos.get("titulos") or [""])[0]),
            "capitulos": capitulos, "aviso_capitulos": aviso}
