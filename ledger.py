"""
ledger.py - Libro Mayor de Gastos, Entradas y Estadísticas de Movimientos
Parte de STUDIO 4 Vol. 3 (Basado en la arquitectura financiera de STUDIO #4)

Módulo encargado de:
1. Control de Costes y Presupuesto (Gastos en USD por proveedor, día y sesión).
2. Métricas de Entradas (Tokens de entrada/salida, llamadas API, imágenes y audio).
3. Registro de Movimientos (Log auditable cronológico de cada fase del pipeline).
4. Cálculo de Ahorro Real (imágenes gratuitas de Google Flow vs proveedores de pago).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("studio4.ledger")

BASE_DIR = Path(__file__).resolve().parent
COSTS_FILE = BASE_DIR / "costs.json"
MOVIMIENTOS_FILE = BASE_DIR / "movimientos.jsonl"

_lock = threading.Lock()
PRESUPUESTO_DIARIO_DEFECTO = 10.0  # USD


def _migrar_movimientos_historicos() -> None:
    if MOVIMIENTOS_FILE.exists() and MOVIMIENTOS_FILE.stat().st_size > 0:
        return
    previo = Path(r"C:\Users\Lenovo\Desktop\STUDIO #4\costs_log.jsonl")
    if not previo.exists():
        return
    try:
        lineas_out: list[str] = []
        for line in previo.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            ts = item.get("ts", time.time())
            fecha = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            mov = {
                "fecha": fecha,
                "fase": f"Generación ({item.get('tipo', 'ia')})",
                "proveedor": item.get("proveedor", "ia"),
                "modelo": item.get("modelo", ""),
                "tipo": item.get("tipo", "texto"),
                "detalle": f"{item.get('modelo', '')} • {item.get('tokens_in', 0)} in / {item.get('tokens_out', 0)} out",
                "tokens_in": int(item.get("tokens_in", 0)),
                "tokens_out": int(item.get("tokens_out", 0)),
                "duracion_segundos": round(float(item.get("segundos", 0.0)), 1),
                "coste_usd": round(float(item.get("usd", 0.0)), 6),
                "ahorro_usd": 0.0,
            }
            lineas_out.append(json.dumps(mov, ensure_ascii=False))
        if lineas_out:
            MOVIMIENTOS_FILE.write_text("\n".join(lineas_out) + "\n", encoding="utf-8")
            logger.info("Migrados %d movimientos históricos a %s", len(lineas_out), MOVIMIENTOS_FILE.name)
    except Exception as exc:
        logger.warning("No se pudo migrar costs_log.jsonl histórico: %s", exc)

_migrar_movimientos_historicos()


def _cargar_costs() -> dict[str, Any]:
    if COSTS_FILE.exists():
        try:
            return json.loads(COSTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Si no existe en el proyecto, intentar migrar el histórico de STUDIO #4
    historico_previo = Path(r"C:\Users\Lenovo\Desktop\STUDIO #4\costs.json")
    if historico_previo.exists():
        try:
            data = json.loads(historico_previo.read_text(encoding="utf-8"))
            COSTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception:
            pass

    return {
        "total_usd": 0.0,
        "count": 0,
        "presupuesto_diario_usd": PRESUPUESTO_DIARIO_DEFECTO,
        "by_provider": {},
        "ahorro_acumulado_usd": 0.0,
    }


def _guardar_costs(data: dict[str, Any]) -> None:
    try:
        COSTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("Error guardando costs.json: %s", e)


def registrar_movimiento(
    fase: str,
    proveedor: str,
    modelo: str,
    detalle: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    coste_usd: float = 0.0,
    duracion_segundos: float = 0.0,
    estado: str = "ok",
    tipo: str = "texto",  # texto, audio, imagen, video, montaje
    ahorro_usd: float = 0.0,
) -> dict[str, Any]:
    """
    Registra un movimiento en el libro mayor y actualiza los acumulados de gastos y entradas.
    """
    ahora = time.time()
    hora_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ahora))

    movimiento = {
        "id": f"mov_{int(ahora * 1000)}",
        "timestamp": ahora,
        "fecha": hora_str,
        "fase": fase,
        "proveedor": proveedor,
        "modelo": modelo,
        "detalle": detalle,
        "tipo": tipo,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "coste_usd": round(float(coste_usd or 0.0), 6),
        "ahorro_usd": round(float(ahorro_usd or 0.0), 4),
        "duracion_segundos": round(float(duracion_segundos or 0.0), 2),
        "estado": estado,
    }

    with _lock:
        # 1. Guardar línea en movimientos.jsonl
        try:
            with open(MOVIMIENTOS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(movimiento, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Error escribiendo en movimientos.jsonl: %s", e)

        # 2. Actualizar balance en costs.json
        d = _cargar_costs()
        d["total_usd"] = round(float(d.get("total_usd", 0.0)) + movimiento["coste_usd"], 6)
        d["count"] = int(d.get("count", 0)) + 1
        d["ahorro_acumulado_usd"] = round(float(d.get("ahorro_acumulado_usd", 0.0)) + movimiento["ahorro_usd"], 4)

        bp = d.setdefault("by_provider", {})
        prov_data = bp.setdefault(proveedor, {
            "usd": 0.0,
            "calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
        })
        prov_data["usd"] = round(float(prov_data["usd"]) + movimiento["coste_usd"], 6)
        prov_data["calls"] = int(prov_data.get("calls", 0)) + 1
        prov_data["tokens_in"] = int(prov_data.get("tokens_in", 0)) + movimiento["tokens_in"]
        prov_data["tokens_out"] = int(prov_data.get("tokens_out", 0)) + movimiento["tokens_out"]

        _guardar_costs(d)

    return movimiento


def obtener_estadisticas_completas(max_movimientos: int = 50) -> dict[str, Any]:
    """
    Retorna el informe consolidado de Gastos, Entradas y Movimientos para el panel.
    """
    with _lock:
        costs_data = _cargar_costs()

    # Leer movimientos del log jsonl
    movimientos: list[dict[str, Any]] = []
    if MOVIMIENTOS_FILE.exists():
        try:
            lineas = MOVIMIENTOS_FILE.read_text(encoding="utf-8").splitlines()
            for ln in reversed(lineas):
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    movimientos.append(json.loads(ln))
                    if len(movimientos) >= max_movimientos:
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Error leyendo movimientos: %s", e)

    total_usd = float(costs_data.get("total_usd", 0.0))
    presupuesto = float(costs_data.get("presupuesto_diario_usd", PRESUPUESTO_DIARIO_DEFECTO))
    disponible = max(0.0, round(presupuesto - total_usd, 4))

    # Calcular estadísticas de entradas agregadas
    total_tokens_in = sum(p.get("tokens_in", 0) for p in costs_data.get("by_provider", {}).values())
    total_tokens_out = sum(p.get("tokens_out", 0) for p in costs_data.get("by_provider", {}).values())
    total_llamadas = int(costs_data.get("count", 0))
    ahorro_total = float(costs_data.get("ahorro_acumulado_usd", 0.0))

    # Resumen por tipo de movimiento
    por_tipo: dict[str, int] = {"texto": 0, "audio": 0, "imagen": 0, "video": 0, "montaje": 0}
    for m in movimientos:
        t = m.get("tipo", "texto")
        por_tipo[t] = por_tipo.get(t, 0) + 1

    return {
        "gastos": {
            "total_usd": total_usd,
            "presupuesto_diario_usd": presupuesto,
            "disponible_usd": disponible,
            "porcentaje_usado": round((total_usd / presupuesto) * 100, 1) if presupuesto > 0 else 0.0,
            "por_proveedor": costs_data.get("by_provider", {}),
            "ahorro_flow_usd": ahorro_total,
        },
        "entradas": {
            "total_llamadas": total_llamadas,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "por_tipo": por_tipo,
        },
        "movimientos": movimientos,
    }
