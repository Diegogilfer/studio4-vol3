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


def _en_streaming(cuerpo: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """La respuesta llega a trozos mientras el modelo piensa y escribe: la conexión nunca se queda minutos callada
    (sin streaming, un router o un micro-corte la tiraba en mitad de un guion largo). Devuelve (texto, fin, uso)."""
    r = requests.post(f"{config.DEEPSEEK_URL}/chat/completions", timeout=(20, 120), stream=True,
                      json={**cuerpo, "stream": True, "stream_options": {"include_usage": True}},
                      headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"})
    if r.status_code in (429, 500, 502, 503, 504):
        raise RuntimeError(f"DeepSeek ocupado ({r.status_code})")
    if r.status_code != 200:
        raise ValueError(f"DeepSeek respondió {r.status_code}: {r.text[:300]}")
    trozos, fin, uso = [], "", {}
    for linea in r.iter_lines(decode_unicode=True):   # 120 s sin ningún dato = conexión muerta
        if not linea or not linea.startswith("data:"):
            continue
        dato = linea[5:].strip()
        if dato == "[DONE]":
            break
        d = json.loads(dato)
        uso = d.get("usage") or uso
        for c in d.get("choices") or []:
            trozos.append((c.get("delta") or {}).get("content") or "")
            fin = c.get("finish_reason") or fin
    return "".join(trozos).strip(), fin, uso


def generar_texto(sistema: str, prompt: str, *, temperatura: float = 0.7, detalle: str = "", produccion: str = "") -> str:
    """Texto libre (sin JSON). Lo usa la reserva cuando Gemini no responde. Reintenta saturación y red."""
    if not disponible():
        raise RuntimeError("Falta DEEPSEEK_API_KEY en .env.")
    cuerpo = {"model": config.DEEPSEEK_MODEL, "temperature": temperatura, "max_tokens": 16000,
              "messages": [{"role": "system", "content": sistema or "Responde en español."}, {"role": "user", "content": prompt}]}
    ultimo: Exception | None = None
    for intento in range(3):
        try:
            texto, _fin, uso = _en_streaming(cuerpo)
            registro.apuntar("DeepSeek", f"{detalle} · {config.DEEPSEEK_MODEL} · {uso.get('total_tokens', 0)} tokens",
                             cantidad=int(uso.get("total_tokens", 0)), unidad="tokens", produccion=produccion)
            if texto:
                return texto
            ultimo = RuntimeError("respuesta vacía")
        except ValueError as e:
            ultimo = e
            if "respondió 4" in str(e):
                break
        except (RuntimeError, requests.RequestException) as e:
            ultimo = e
        time.sleep(3 * (intento + 1))
    raise RuntimeError(f"DeepSeek no respondió: {ultimo}")


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
            texto, fin, uso = _en_streaming(cuerpo)
            registro.apuntar("DeepSeek", f"{detalle} · {config.DEEPSEEK_MODEL} · {uso.get('prompt_tokens', 0)}+"
                             f"{uso.get('completion_tokens', 0)} tokens",
                             cantidad=int(uso.get("total_tokens", 0)), unidad="tokens", produccion=produccion)
            if fin == "length" or not texto:
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
