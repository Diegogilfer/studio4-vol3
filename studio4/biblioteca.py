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
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from . import config

_MARCA = re.compile(r"^\s*={3,}\s*([A-Za-z]{1,6}-?\d{1,4})\s*[|—–:-]\s*(LARGO|CORTO)\s*([^=]*?)\s*={3,}\s*$",
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


def limpiar(texto: str) -> str:
    """Quita el formato que añaden los chats (negritas, títulos «###», citas «>», bloques de código) sin tocar
    el texto: así el paquete se lee igual venga como venga pegado."""
    lineas = []
    for linea in (texto or "").replace("\r\n", "\n").split("\n"):
        if re.match(r"^\s*`{3,}", linea):   # las vallas de un bloque de código
            continue
        linea = re.sub(r"^\s*(?:#{1,6}|>)\s*", "", linea)        # «### …» y «> …»
        linea = re.sub(r"(\*\*|__)", "", linea)                   # **negrita**
        lineas.append(linea.strip().strip("*_").strip())
    return "\n".join(lineas)


def parsear(texto: str) -> list[dict[str, Any]]:
    """Los guiones de un paquete. Error claro si no trae las marcas o algún guion está vacío."""
    texto = limpiar(texto)
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
        partes = re.split(r"^\s*GUI[OÓ]N\s*:\s*$", bloque, maxsplit=1, flags=re.IGNORECASE | re.MULTILINE)
        guion = " ".join((partes[1] if len(partes) > 1 else _CAMPO.sub("", bloque)).split())
        tipo = m.group(2).lower()
        etiqueta = m.group(3).strip()
        if len(guion.split()) < 20:
            raise ValueError(f"El guion {m.group(1)} {tipo} {etiqueta} está vacío o es demasiado corto.")
        salida.append({"codigo": m.group(1).upper(), "tipo": tipo, "etiqueta": etiqueta,
                       "titulo": campos.get("TITULO", "")[:100], "descripcion": campos.get("DESCRIPCION", "")[:600],
                       "hashtags": [h for h in re.findall(r"#\w+", campos.get("HASHTAGS", ""))][:10],
                       "guion": guion, "palabras": len(guion.split()), "producido": ""})
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
