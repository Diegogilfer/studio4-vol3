"""Pegar un guion y trabajar desde ahí: Studio 4 lo recibe, quita marcadores de tiempo, números de subtítulo,
etiquetas de quien habla, acotaciones ([MÚSICA], (risas)) y muletillas, y lo deja partido en escenas, listo para
empezar. Si DeepSeek está conectado, además lo pule (puntuación, repeticiones, frases para locutar) SIN cambiar datos.
"""

from __future__ import annotations

import re
from typing import Any

# muletillas que en un texto para locutar sobran (solo como palabra suelta o al empezar la frase)
MULETILLAS = (r"e+h+", r"e+m+", r"m+h*m+", r"a+h+", r"o sea", r"bueno", r"pues", r"este", r"esto", r"vale", r"okey", r"ok",
              r"tipo", r"digamos", r"en plan", r"como que", r"sabes", r"¿sabes\?", r"¿no\?", r"¿vale\?", r"¿eh\?", r"verdad",
              r"la verdad es que", r"básicamente", r"literalmente", r"obviamente")
_RELLENO_SUELTO = re.compile(r"(?i)(?<![\wáéíóúñ])(?:e+h+|e+m+|m+h*m+|a+h+)(?![\wáéíóúñ])[,.]?\s*")
_INICIO = re.compile(r"(?i)(^|(?<=[.!?…]\s))(?:(?:" + "|".join(MULETILLAS) + r")(?:\.\.\.|…|[,.])?\s+)+")
_COLA = re.compile(r"(?i),?\s*(?:¿no\?|¿vale\?|¿sabes\?|¿eh\?|o sea)(?=\s*[.!?…]|\s*$)")

TIEMPO = re.compile(r"\[?\(?\b\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\b\)?\]?")
FLECHA_SRT = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}.*$", re.M)
ACOTACION = re.compile(r"\[[^\]]{1,40}\]|\((?:risas?|m[uú]sica|aplausos|inaudible|pausa|silencio|sonido[^)]*|efecto[^)]*|"
                       r"corte|transici[oó]n[^)]*|intro|outro)\)", re.I)
HABLANTE = re.compile(r"^\s*(?:narrador|narradora|voz|locutor|locutora|presentador|host|speaker\s*\d*|[A-ZÁÉÍÓÚÑ]{2,20})\s*:\s*", re.M)
NUMERO_SOLO = re.compile(r"^\s*\d{1,4}\s*$", re.M)
ESCENA = re.compile(r"^\s*(?:escena|bloque|parte|cap[ií]tulo|secci[oó]n)\s*\d+\s*[:.\-–]?\s*", re.I | re.M)


def limpiar(texto: str) -> dict[str, Any]:
    """Limpieza sin IA: siempre funciona. Devuelve {guion, quitado: {marcas, acotaciones, muletillas}}."""
    t = (texto or "").replace("\r\n", "\n").replace("\u00a0", " ")
    cuenta = {"marcas": 0, "acotaciones": 0, "muletillas": 0}

    def contar(patron, clave, s, por=""):
        nuevo, n = patron.subn(por, s)
        cuenta[clave] += n
        return nuevo
    t = contar(FLECHA_SRT, "marcas", t)
    t = contar(NUMERO_SOLO, "marcas", t)
    t = contar(TIEMPO, "marcas", t)
    t = re.sub(r"^\s*[-–—]\s*", "", t, flags=re.M)
    t = contar(ACOTACION, "acotaciones", t)
    t = contar(HABLANTE, "acotaciones", t)
    t = contar(ESCENA, "acotaciones", t)
    parrafos = []
    for p in re.split(r"\n\s*\n", t):
        linea = " ".join(p.split())
        linea = contar(_RELLENO_SUELTO, "muletillas", linea)
        linea = contar(_INICIO, "muletillas", linea, r"\1")
        linea = contar(_COLA, "muletillas", linea)
        linea = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", linea, flags=re.I)   # «que que» → «que»
        linea = re.sub(r"\s+([,.;:!?…])", r"\1", linea)
        linea = re.sub(r"([.!?…]\s+|^)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), linea).strip(" ,;")
        if len(linea.split()) >= 2:
            parrafos.append(linea if linea[-1] in ".!?…»\"" else linea + ".")   # cada escena acaba con su punto
    if len(parrafos) == 1 and len(parrafos[0].split()) > 120:   # un bloque enorme (transcripción): párrafos de ~4 oraciones
        oraciones = re.split(r"(?<=[.!?…])\s+", parrafos[0])
        parrafos = [" ".join(oraciones[k:k + 4]) for k in range(0, len(oraciones), 4)]
    return {"guion": "\n\n".join(parrafos), "quitado": cuenta}


SISTEMA_PULIR = """Te paso un guion que el autor pegó (puede venir de una transcripción o de sus notas), ya sin marcas de
tiempo. Déjalo LISTO PARA LOCUTAR en español: quita muletillas y repeticiones que queden, corrige la puntuación, une o
parte frases para que se lean bien en voz alta (8 a 25 palabras), y agrupa en párrafos: cada párrafo es una escena del
vídeo. NO cambies los datos, nombres, cifras ni el orden de lo que cuenta, NO añadas información y NO resumas: es el
guion del autor. Propón un título que se entienda solo: [quién u objeto] + [qué pasó, con gancho] + (lugar o época).
Devuelve JSON: {"titulo": "máx. 80 caracteres", "guion": "párrafos separados por una línea en blanco",
"cambios": ["lo que arreglaste, en 3-6 puntos muy cortos"]}"""


def preparar(texto: str, titulo: str = "") -> dict[str, Any]:
    """Limpieza + (si se puede) pulido con DeepSeek. Devuelve {titulo, guion, cambios, pulido}."""
    from . import deepseek
    base = limpiar(texto)
    if len(base["guion"].split()) < 8:
        raise ValueError("Pega el guion entero (lo que dirá la voz).")
    q = base["quitado"]
    cambios = [x for x in (f"{q['marcas']} marcas de tiempo quitadas" if q["marcas"] else "",
                           f"{q['acotaciones']} acotaciones y nombres de quien habla quitados" if q["acotaciones"] else "",
                           f"{q['muletillas']} muletillas quitadas" if q["muletillas"] else "") if x]
    final = {"titulo": titulo.strip(), "guion": base["guion"], "cambios": cambios, "pulido": False}
    if deepseek.disponible():
        try:
            r = deepseek.generar_json(SISTEMA_PULIR, base["guion"][:24000], temperatura=0.2, detalle="pegar guion: pulir")
            pulido = str(r.get("guion") or "").strip()
            # si el pulido se come media historia (o la alarga con cosas nuevas), se queda la limpieza
            if pulido and 0.75 <= len(pulido.split()) / max(1, len(base["guion"].split())) <= 1.15:
                final.update(guion=pulido, pulido=True, cambios=cambios + [str(c)[:120] for c in (r.get("cambios") or [])][:6])
                final["titulo"] = final["titulo"] or str(r.get("titulo") or "")[:100]
        except Exception:  # noqa: BLE001 - sin pulido, el guion limpio ya sirve
            pass
    if not final["titulo"]:
        final["titulo"] = " ".join(final["guion"].split()[:9]).rstrip(",.;:") + "…"
    return final
