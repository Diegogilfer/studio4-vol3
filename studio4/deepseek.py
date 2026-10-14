"""Cliente de DeepSeek (API oficial, formato OpenAI). Solo escribe guiones: no ve imágenes ni busca en internet."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from . import config, registro

logger = logging.getLogger("studio4.deepseek")


def disponible() -> bool:
    return bool(config.DEEPSEEK_API_KEY)


class SinEspacio(RuntimeError):
    """El modelo gastó todos los tokens (pensando) sin terminar la respuesta."""


def generar_json(sistema: str, prompt: str, *, temperatura: float = 0.9, detalle: str = "", produccion: str = "") -> dict[str, Any]:
    """Pide una respuesta en JSON y la devuelve ya decodificada.
    - Saturación o red: reintenta igual (hasta 3 veces).
    - Se queda sin tokens o devuelve vacío: un solo reintento con el doble de margen (repetir igual gastaría lo mismo).
    - Clave mala o petición rechazada: no reintenta."""
    if not disponible():
        raise RuntimeError("Falta DEEPSEEK_API_KEY en .env (platform.deepseek.com › API keys).")
    cuerpo = {
        "model": config.DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": prompt}],
        "temperature": temperatura,
        "response_format": {"type": "json_object"},
        "max_tokens": 16000,
    }
    ultimo: Exception | None = None
    ampliado = False
    for intento in range(3):
        try:
            r = requests.post(f"{config.DEEPSEEK_URL}/chat/completions", json=cuerpo, timeout=240,
                              headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"})
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"DeepSeek ocupado ({r.status_code})")
            if r.status_code != 200:
                raise ValueError(f"DeepSeek respondió {r.status_code}: {r.text[:300]}")
            d = r.json()
            eleccion = d["choices"][0]
            texto = (eleccion["message"].get("content") or "").strip()
            uso = d.get("usage", {})
            registro.apuntar("DeepSeek", f"{detalle} · {config.DEEPSEEK_MODEL} · {uso.get('prompt_tokens', 0)}+"
                             f"{uso.get('completion_tokens', 0)} tokens",
                             cantidad=int(uso.get("total_tokens", 0)), unidad="tokens", produccion=produccion)
            if eleccion.get("finish_reason") == "length" or not texto:
                raise SinEspacio(f"respuesta {'cortada' if texto else 'vacía'} ({uso.get('completion_tokens', 0)} tokens)")
            return json.loads(texto)
        except SinEspacio as e:
            ultimo = e
            if ampliado:
                break
            ampliado = True
            cuerpo["max_tokens"] *= 2
            logger.warning("DeepSeek %s: reintento con %d tokens de margen.", e, cuerpo["max_tokens"])
            continue
        except ValueError as e:      # clave mala, petición mal formada o JSON roto
            ultimo = e
            if "respondió 4" in str(e):
                break
        except (RuntimeError, requests.RequestException) as e:
            ultimo = e
        logger.warning("DeepSeek (intento %d): %s", intento + 1, ultimo)
        time.sleep(3 * (intento + 1))
    raise RuntimeError(f"DeepSeek no respondió: {ultimo}")
