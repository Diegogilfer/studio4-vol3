"""Registro de lo que gasta cada producción: llamadas a Gemini, tomas de Flow y créditos de ElevenLabs.

Todo lo de Google va por la API gratuita o por tu suscripción, así que aquí no se apuntan dólares:
se apuntan usos, para ver cuándo te acercas a un límite (sobre todo los 10.000 créditos/mes de ElevenLabs).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from . import config

_lock = threading.Lock()
_MOVIMIENTOS = config.PRODUCCIONES / "movimientos.jsonl"
_CONSUMO = config.PRODUCCIONES / "consumo.json"


def _mes() -> str:
    return time.strftime("%Y-%m")


def _leer_consumo() -> dict[str, Any]:
    try:
        return json.loads(_CONSUMO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apuntar(servicio: str, detalle: str, cantidad: int = 1, unidad: str = "llamadas", produccion: str = "",
            usd: float = 0.0) -> None:
    """Suma un uso al mes en curso y deja la línea en el historial."""
    with _lock:
        config.PRODUCCIONES.mkdir(parents=True, exist_ok=True)
        consumo = _leer_consumo()
        mes = consumo.setdefault(_mes(), {})
        fila = mes.setdefault(servicio, {"unidad": unidad, "total": 0})
        fila["total"] += int(cantidad)
        if usd:
            fila["usd"] = round(fila.get("usd", 0.0) + usd, 4)
        tmp = _CONSUMO.with_suffix(".tmp")
        tmp.write_text(json.dumps(consumo, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CONSUMO)
        linea = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "servicio": servicio, "detalle": detalle,
                 "cantidad": int(cantidad), "unidad": unidad, "produccion": produccion, "usd": round(usd, 4)}
        with _MOVIMIENTOS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")


def consumo_del_mes() -> dict[str, Any]:
    with _lock:
        return _leer_consumo().get(_mes(), {})


def creditos_elevenlabs_restantes() -> int:
    usados = consumo_del_mes().get("ElevenLabs", {}).get("total", 0)
    return max(0, config.ELEVENLABS_CREDITOS_MES - usados)


def ultimos(n: int = 40) -> list[dict[str, Any]]:
    try:
        lineas = _MOVIMIENTOS.read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in reversed(lineas) if l.strip()]
