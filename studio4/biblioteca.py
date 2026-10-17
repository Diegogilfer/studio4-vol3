"""Biblioteca de guiones: paquetes escritos fuera (p. ej. por chat con otro asistente) que se convierten en
producciones con un clic.

Formato del paquete (marcas fijas, para que nada dependa de cómo escriba cada asistente):

    === FL-001 | LARGO ===
    TÍTULO: …
    DESCRIPCIÓN: …
    HASHTAGS: #a #b #c
    GUION:
    (el texto de la voz)

    === FL-001 | CORTO a ===
    …

LARGO → 16:9 (YouTube); CORTO → 9:16 (Shorts y Reels). Se guarda por canal y recuerda qué ya se produjo.

El PLAN DEL MES (paso 1 del prompt) se pega en el mismo sitio: una tabla con una fila por tema,
    | FL-001 | Tema | Juego | Por qué ahora | Fuentes |
y el panel muestra en qué va cada tema (sin guiones, con guiones, creados).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from . import config

# «=== FL-001 | LARGO ===» y lo que los chats hacen con ella: sin los «===», «·» o «/» en vez de la barra,
# «FL 001», «Guion FL-001 — Corto a: lo más llamativo»…
_MARCA = re.compile(r"^\s*(?:={2,}\s*)?(?:GUI[OÓ]N\s+)?([A-Za-z]{1,6})[ -]?(\d{1,4})\s*[|—–:·•/-]\s*(LARGO|CORTO)\b\s*([^=|\n]*?)\s*(?:={2,})?\s*$",
                    re.IGNORECASE | re.MULTILINE)
_CAMPO = re.compile(r"^\s*(T[IÍ]TULO|DESCRIPCI[OÓ]N|HASHTAGS)\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def _archivo(cid: str):
    return config.PRODUCCIONES / f"biblioteca_{cid}.json"


def leer(cid: str) -> list[dict[str, Any]]:
    try:
        return json.loads(_archivo(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _escribir(cid: str, items: list[dict[str, Any]]) -> None:
    ruta = _archivo(cid)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)


_FILA = re.compile(r"^\s*\|?\s*([A-Za-z]{1,6}-\d{1,4})\s*\|(.*)$", re.MULTILINE)


def _archivo_plan(cid: str):
    return config.PRODUCCIONES / f"plan_{cid}.json"


def leer_plan(cid: str) -> list[dict[str, Any]]:
    try:
        return json.loads(_archivo_plan(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def parsear_plan(texto: str) -> list[dict[str, Any]]:
    """Las filas del plan del mes: código, tema, juego, por qué ahora y fuentes (las que falten quedan vacías)."""
    plan: dict[str, dict[str, Any]] = {}
    for m in _FILA.finditer(limpiar(texto)):
        celdas = [c.strip() for c in m.group(2).split("|")]
        celdas = (celdas + [""] * 4)[:max(4, len(celdas))]
        codigo = m.group(1).upper()
        plan[codigo] = {"codigo": codigo, "tema": celdas[0][:200], "juego": celdas[1][:80], "por_que": celdas[2][:400],
                        "fuentes": " ".join(celdas[3:]).strip(" |")[:600]}
    return [p for p in plan.values() if p["tema"]]


def guardar_plan(cid: str, filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade o actualiza los temas del plan (un código repetido reemplaza al anterior)."""
    plan = {p["codigo"]: p for p in leer_plan(cid)}
    for f in filas:
        plan[f["codigo"]] = {**plan.get(f["codigo"], {}), **f}
    filas = sorted(plan.values(), key=lambda p: p["codigo"])
    ruta = _archivo_plan(cid)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)
    return filas


def plan_con_estado(cid: str) -> list[dict[str, Any]]:
    """El plan con lo que lleva cada tema: cuántos guiones hay en la biblioteca y cuántos ya se crearon."""
    guiones = leer(cid)
    salida = []
    for p in leer_plan(cid):
        suyos = [g for g in guiones if g["codigo"] == p["codigo"]]
        salida.append({**p, "guiones": len(suyos), "creados": sum(1 for g in suyos if g.get("producido"))})
    return salida


def pegar(cid: str, texto: str) -> dict[str, Any]:
    """Lo que se pega en la biblioteca: paquetes de guiones, el plan del mes o las dos cosas a la vez."""
    hay_guiones = bool(_MARCA.search(limpiar(texto)))
    filas = [] if hay_guiones else parsear_plan(texto)
    if not hay_guiones and not filas:
        raise ValueError("No encuentro guiones ni plan: cada guion empieza con «=== FL-001 | LARGO ===» y cada tema "
                         "del plan es una fila «| FL-001 | Tema | Juego | Por qué ahora | Fuentes |».")
    if filas:
        guardar_plan(cid, filas)
    previos = leer(cid)
    nuevos = parsear(texto) if hay_guiones else []
    repetidos = sorted({f"{_nombre(n)} se parece a {_nombre(p)}" for n in nuevos for p in previos
                        if p["codigo"] != n["codigo"] and parecido(n, p)})
    guiones = anadir(cid, texto) if hay_guiones else previos
    return {"guiones": con_parecidos(guiones), "plan": plan_con_estado(cid), "temas_nuevos": len(filas),
            "repetidos": repetidos}


_MARCA_SUELTA = re.compile(r"[«\"“]?\s*(={2,}\s*[A-Za-z]{1,6}[ -]?\d{1,4}\s*[|—–:·•/-]\s*(?:LARGO|CORTO)\b[^=\n|]*?={2,})\s*[»\"”]?",
                           re.IGNORECASE)
_ETIQUETAS = re.compile(r"[ \t]+(T[IÍ]TULO|DESCRIPCI[OÓ]N|HASHTAGS|GUI[OÓ]N|FUENTES|CONTROL DE CALIDAD)\s*:")


def _separar(texto: str) -> str:
    """Un paquete que llega en una sola línea (al copiar de un chat se pierden los saltos) o con la marca entre
    comillas («=== FL-001 | LARGO ===»): cada marca y cada etiqueta vuelve a su propia línea."""
    texto = _MARCA_SUELTA.sub(lambda m: f"\n{m.group(1)}\n", texto)
    return _ETIQUETAS.sub(lambda m: f"\n{m.group(1)}:", texto)   # solo en MAYÚSCULAS: dentro del guion no se toca


def limpiar(texto: str) -> str:
    """Quita el formato que añaden los chats (negritas, títulos «###», citas «>», bloques de código) sin tocar
    el texto: así el paquete se lee igual venga como venga pegado."""
    lineas = []
    for linea in _separar((texto or "").replace("\r\n", "\n")).split("\n"):
        if re.match(r"^\s*`{3,}", linea):   # las vallas de un bloque de código
            continue
        linea = re.sub(r"^\s*(?:#{1,6}|>)\s*", "", linea)        # «### …» y «> …»
        linea = re.sub(r"(\*\*|__)", "", linea)                   # **negrita**
        lineas.append(linea.strip().strip("*_").strip())
    return "\n".join(lineas)


def fuentes_de(texto: str) -> list[dict[str, str]]:
    """Las páginas de la sección FUENTES del paquete (donde investigó el asistente), con su nota si la trae."""
    m = re.search(r"^\s*FUENTES\b(.*?)(?=^\s*CONTROL DE CALIDAD\b|^\s*={2,}|\Z)", texto or "",
                  re.IGNORECASE | re.MULTILINE | re.DOTALL)
    salida: list[dict[str, str]] = []
    for u, nota in re.findall(r"(https?://[^\s)\]>]+)\s*(?:\(([^)]*)\))?", m.group(1) if m else ""):
        u = u.rstrip(".,;")
        if u not in [f["url"] for f in salida]:
            salida.append({"url": u, "titulo": " ".join(nota.split())[:200]})
    return salida[:20]


def parsear(texto: str) -> list[dict[str, Any]]:
    """Los guiones de un paquete. Error claro si no trae las marcas o algún guion está vacío."""
    texto = limpiar(texto)
    fuentes = fuentes_de(texto)
    marcas = list(_MARCA.finditer(texto or ""))
    if not marcas:
        raise ValueError("No encuentro guiones: cada uno debe empezar con una línea como «=== FL-001 | LARGO ===».")
    salida = []
    for i, m in enumerate(marcas):
        bloque = texto[m.end(): marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)]
        # Lo que el asistente añade al final del paquete (fuentes, control de calidad) no es guion.
        bloque = re.split(r"^\s*(?:FUENTES|CONTROL DE CALIDAD|\[[ xX]?\])\b", bloque, maxsplit=1,
                          flags=re.IGNORECASE | re.MULTILINE)[0]
        campos = {k.upper().replace("Í", "I").replace("Ó", "O"): v.strip() for k, v in _CAMPO.findall(bloque)}
        partes = re.split(r"^\s*GUI[OÓ]N\s*:[ \t]*", bloque, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
        guion = " ".join((partes[1] if len(partes) > 1 else _CAMPO.sub("", bloque)).split())
        tipo = m.group(3).lower()
        etiqueta = m.group(4).strip(" :.-—–")
        codigo = f"{m.group(1).upper()}-{int(m.group(2)):03d}"
        if len(guion.split()) < 20:
            raise ValueError(f"El guion {codigo} {tipo} {etiqueta} está vacío o es demasiado corto.")
        salida.append({"codigo": codigo, "tipo": tipo, "etiqueta": etiqueta,
                       "titulo": campos.get("TITULO", "")[:100], "descripcion": campos.get("DESCRIPCION", "")[:600],
                       "hashtags": [h for h in re.findall(r"#\w+", campos.get("HASHTAGS", ""))][:10],
                       "guion": guion, "palabras": len(guion.split()), "producido": "", "fuentes": fuentes})
    return salida


# --- Repetidos: dos guiones de temas distintos que cuentan casi lo mismo ----------------------------
# Medido con los 72 guiones del primer mes: entre temas distintos el texto comparte como mucho un 20 % de
# palabras; el único caso repetido de verdad (Vice City vs GTA 6 en FL-001 y FL-006) compartía el 26 %.
PARECIDO_TEXTO = 0.25
PARECIDO_TITULO = 0.5


def _palabras(texto: str) -> set[str]:
    from .fuentes import _normal
    return set(re.findall(r"[a-z0-9]{4,}", _normal(texto or "")))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a | b))


def _nombre(x: dict[str, Any]) -> str:
    return f"{x['codigo']} {'largo' if x['tipo'] == 'largo' else ('corto ' + x['etiqueta'].split(':')[0]).strip()}"


def parecido(a: dict[str, Any], b: dict[str, Any]) -> bool:
    texto = _jaccard(_palabras(a["guion"]), _palabras(b["guion"]))
    titulo = _jaccard(_palabras(a.get("titulo", "")), _palabras(b.get("titulo", "")))
    return texto >= PARECIDO_TEXTO or (titulo >= PARECIDO_TITULO and texto >= 0.15)


def con_parecidos(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada guion con «parecido_a»: los de OTROS temas que cuentan casi lo mismo (para no grabarlo dos veces)."""
    salida = [{**x, "parecido_a": []} for x in items]
    for i, a in enumerate(salida):
        for b in salida[i + 1:]:
            if a["codigo"] != b["codigo"] and parecido(a, b):
                a["parecido_a"].append(_nombre(b))
                b["parecido_a"].append(_nombre(a))
    return salida


def anadir(cid: str, texto: str) -> list[dict[str, Any]]:
    """Guarda los guiones del paquete en la biblioteca del canal (uno igual que ya estaba se reemplaza)."""
    nuevos = parsear(texto)
    clave = lambda x: (x["codigo"], x["tipo"], x["etiqueta"].lower())  # noqa: E731
    previos = {clave(x): x for x in leer(cid)}
    for n in nuevos:
        n["id"] = f"{n['codigo']}-{n['tipo']}{('-' + re.sub(r'[^a-z0-9]+', '', n['etiqueta'].lower())) if n['etiqueta'] else ''}"
        n["anadido"] = time.strftime("%Y-%m-%d %H:%M")
        if clave(n) in previos:
            n["producido"] = previos[clave(n)].get("producido", "")
        previos[clave(n)] = n
    items = sorted(previos.values(), key=lambda x: (x["codigo"], x["tipo"] != "largo", x["etiqueta"]))
    _escribir(cid, items)
    return items


def marcar(cid: str, item_id: str, pid: str) -> None:
    items = leer(cid)
    for x in items:
        if x["id"] == item_id:
            x["producido"] = pid
    _escribir(cid, items)


def quitar(cid: str, item_id: str) -> None:
    _escribir(cid, [x for x in leer(cid) if x["id"] != item_id])
