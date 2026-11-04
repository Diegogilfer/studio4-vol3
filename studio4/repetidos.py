"""Que no salga dos veces el mismo vídeo: un guion nuevo se compara con los del mismo canal de los últimos DIAS días.

Medido con los guiones reales: un vídeo repetido de verdad («Lo que GTA 6 hereda de The Warriors», hecho dos veces)
se parece un 49 %; vídeos distintos del mismo juego no pasan del 15 %. Por eso el umbral va en el 30 %. También cuenta
el título: el mismo tema con otras palabras se parece poco en el guion, pero mucho en el título.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import datetime
from typing import Any

DIAS = 20
UMBRAL_GUION = 0.30
UMBRAL_TITULO = 0.60
_VACIAS = set("""que de la el en y a los las del se un una por con para su es lo al como mas pero sus le ya o fue este esta
son entre cuando muy sin sobre tambien me hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso
ante ellos e esto mi antes algunos unos yo otro otras otra tanto esa estos mucho quienes nada muchos cual poco ella estar
estas algunas algo nosotros tu te ti si porque cada asi solo puede video juego""".split())


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def bolsa(texto: str) -> set[str]:
    """Las palabras con contenido, recortadas a su raíz (6 letras): «armas» y «armamento» cuentan como parecidas."""
    return {w[:6] for w in re.findall(r"[a-z0-9]+", _plano(texto)) if (len(w) > 3 or w.isdigit()) and w not in _VACIAS}


def parecido(a: str, b: str) -> float:
    x, y = bolsa(a), bolsa(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _fecha(mid: str) -> datetime | None:
    try:
        return datetime.strptime(mid[:8], "%Y%m%d")
    except ValueError:
        return None


def buscar(guion: str, titulo: str, canal: str, excluir: str = "", dias: int = DIAS) -> dict[str, Any] | None:
    """El vídeo reciente del canal que más se parece, si pasa el umbral; si no, None."""
    from . import montaje
    if not montaje.raiz().exists():
        return None
    ahora, mejor = datetime.now(), None
    for f in montaje.raiz().glob("*/proyecto.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fecha = _fecha(p.get("id", ""))
        if p.get("id") == excluir or (p.get("canal") or "") != canal or not fecha or (ahora - fecha).days > dias:
            continue
        g = parecido(guion, p.get("guion") or "")
        t = parecido(titulo, p.get("titulo") or "")
        if g >= UMBRAL_GUION or t >= UMBRAL_TITULO:
            nota = max(g, t)
            if not mejor or nota > mejor["parecido"]:
                mejor = {"id": p["id"], "titulo": p.get("titulo", ""), "guion": p.get("guion", ""), "parecido": round(nota, 2),
                         "dias": max(0, (ahora - fecha).days)}
    return mejor


def evitar(rep: dict[str, Any]) -> str:
    """La instrucción para el guionista cuando el guion se parece a uno reciente."""
    return (f"OJO: el canal ya hizo hace {rep['dias']} días el vídeo «{rep['titulo']}». NO lo repitas: cuenta OTRO ángulo del "
            f"tema, con otros datos, otro gancho y otro orden. Esto es lo que ya se contó (no lo repitas): "
            f"{re.sub(r'\\s+', ' ', rep['guion'])[:700]}")


def marca() -> str:
    return time.strftime("%Y-%m-%d %H:%M")
