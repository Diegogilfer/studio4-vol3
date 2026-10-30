"""Leer el JSON que devuelve una IA sin caerse: viene dentro de ```json, con texto alrededor, con comas de más o
cortado a mitad (se quedó sin tokens). Se repara lo reparable; si no hay JSON, ValueError con un motivo claro.
"""

from __future__ import annotations

import json
import re
from typing import Any

_VALLA = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_COMA_SOBRANTE = re.compile(r",(\s*[}\]])")


def _cerrar(texto: str) -> str:
    """Cierra lo que quedó abierto (cadenas, listas, objetos) en un JSON cortado, quitando el último trozo a medias."""
    pila, en_cadena, escape, ultima_coma = [], False, False, -1
    for i, c in enumerate(texto):
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c in "{[":
            pila.append("}" if c == "{" else "]")
        elif c in "}]" and pila:
            pila.pop()
        elif c == ",":
            ultima_coma = i
    if not pila:
        return texto
    if en_cadena or texto.rstrip()[-1:] in (":", ","):   # cortado a mitad de un valor: se tira ese último elemento
        texto = texto[:ultima_coma] if ultima_coma > 0 else texto
        return _cerrar(texto) if texto.count("{") + texto.count("[") else texto
    return texto + "".join(reversed(pila))


def leer(crudo: str) -> Any:
    """El JSON de la respuesta de una IA (objeto o lista), reparado si hace falta."""
    texto = (crudo or "").strip()
    valla = _VALLA.search(texto)
    if valla:
        texto = valla.group(1).strip()
    try:
        return json.loads(texto)
    except ValueError:
        pass
    inicio = min((i for i in (texto.find("{"), texto.find("[")) if i >= 0), default=-1)
    if inicio < 0:
        raise ValueError("La IA no devolvió JSON.")
    texto = texto[inicio:]
    try:   # JSON bueno seguido de texto: se lee hasta donde acaba
        return json.JSONDecoder().raw_decode(texto)[0]
    except ValueError:
        pass
    reparado = _cerrar(_COMA_SOBRANTE.sub(r"\1", texto))
    try:
        return json.loads(_COMA_SOBRANTE.sub(r"\1", reparado))
    except ValueError as e:
        raise ValueError(f"La IA devolvió un JSON que no se puede leer ({e.msg}, posición {e.pos}).") from None
