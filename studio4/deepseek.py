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
    return bool(config.DEEPSEEK_API_KEY or config.XIAOMIMIMO_API_KEY)


def _proveedores() -> list[tuple[str, str, str, str]]:
    """Proveedores de texto compatibles con OpenAI en orden: DeepSeek y Xiaomi MiMo."""
    lista = []
    if config.DEEPSEEK_API_KEY:
        lista.append(("DeepSeek", config.DEEPSEEK_URL, config.DEEPSEEK_API_KEY, config.DEEPSEEK_MODEL))
    if config.XIAOMIMIMO_API_KEY:
        lista.append(("Xiaomi MiMo", config.XIAOMIMIMO_URL, config.XIAOMIMIMO_API_KEY, config.XIAOMIMIMO_MODEL))
    return lista


class SinEspacio(RuntimeError):
    """El modelo gastó todos los tokens (pensando) sin terminar la respuesta."""


def _en_streaming(cuerpo: dict[str, Any], *, url: str = "", clave: str = "", nombre: str = "DeepSeek") -> tuple[str, str, dict[str, Any]]:
    """La respuesta llega a trozos mientras el modelo piensa y escribe: la conexión nunca se queda minutos callada
    (sin streaming, un router o un micro-corte la tiraba en mitad de un guion largo). Devuelve (texto, fin, uso)."""
    url = url or config.DEEPSEEK_URL
    clave = clave or config.DEEPSEEK_API_KEY
    r = requests.post(f"{url}/chat/completions", timeout=(20, 120), stream=True,
                      json={**cuerpo, "stream": True, "stream_options": {"include_usage": True}},
                      headers={"Authorization": f"Bearer {clave}"})
    if r.status_code in (429, 500, 502, 503, 504):
        raise RuntimeError(f"{nombre} ocupado ({r.status_code})")
    if r.status_code == 402:
        raise ValueError(f"{nombre} respondió 402: sin saldo en la cuenta ({r.text[:200]})")
    if r.status_code != 200:
        raise ValueError(f"{nombre} respondió {r.status_code}: {r.text[:300]}")
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
    proveedores = _proveedores()
    if not proveedores:
        raise RuntimeError("Falta DEEPSEEK_API_KEY o XIAOMIMIMO_API_KEY en .env.")
    ultimo: Exception | None = None
    for nombre, url, clave, modelo in proveedores:
        cuerpo = {"model": modelo, "temperature": temperatura, "max_tokens": 16000,
                  "messages": [{"role": "system", "content": sistema or "Responde en español."}, {"role": "user", "content": prompt}]}
        for intento in range(3):
            try:
                texto, _fin, uso = _en_streaming(cuerpo, url=url, clave=clave, nombre=nombre)
                registro.apuntar(nombre, f"{detalle} · {modelo} · {uso.get('total_tokens', 0)} tokens",
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
    - Clave mala o petición rechazada: no reintenta (pero prueba el siguiente proveedor si lo hay)."""
    proveedores = _proveedores()
    if not proveedores:
        raise RuntimeError("Falta DEEPSEEK_API_KEY en .env (platform.deepseek.com › API keys).")
    ultimo: Exception | None = None
    for nombre, url, clave, modelo in proveedores:
        cuerpo = {
            "model": modelo,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": prompt}],
            "temperature": temperatura,
            "response_format": {"type": "json_object"},
            "max_tokens": 16000,
        }
        ampliado = False
        for intento in range(3):
            try:
                texto, fin, uso = _en_streaming(cuerpo, url=url, clave=clave, nombre=nombre)
                registro.apuntar(nombre, f"{detalle} · {modelo} · {uso.get('prompt_tokens', 0)}+"
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
                logger.warning("%s %s: reintento con %d tokens de margen.", nombre, e, cuerpo["max_tokens"])
                continue
            except ValueError as e:      # clave mala, petición mal formada o JSON roto
                ultimo = e
                if "respondió 4" in str(e):
                    break
            except (RuntimeError, requests.RequestException) as e:
                ultimo = e
            logger.warning("%s (intento %d): %s", nombre, intento + 1, ultimo)
            time.sleep(3 * (intento + 1))
    raise RuntimeError(f"DeepSeek no respondió: {ultimo}")
