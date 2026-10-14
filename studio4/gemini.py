"""Cliente de Gemini (API gratuita de AI Studio) con modelos de reserva y reintentos."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from google import genai
from google.genai import types

from . import config, registro

logger = logging.getLogger("studio4.gemini")
_cliente: Optional[genai.Client] = None


def cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("Falta GEMINI_API_KEY en .env (gratis en https://aistudio.google.com/apikey).")
        _cliente = genai.Client(api_key=config.GEMINI_API_KEY)
    return _cliente


def _modelos(preferido: str, reserva: list[str]) -> list[str]:
    return list(dict.fromkeys([preferido, *reserva]))


def generar(
    prompt: str,
    *,
    sistema: str = "",
    esquema: Any = None,
    temperatura: float = 0.7,
    detalle: str = "",
    produccion: str = "",
    imagenes: Optional[list[bytes]] = None,
    archivos: Optional[list[tuple[bytes, str]]] = None,
) -> str:
    """Devuelve el texto de la respuesta. Con `esquema` (Pydantic) la respuesta es JSON validable.
    `imagenes` (JPEG) van delante del texto, numeradas en el orden dado: Gemini las ve todas.
    `archivos` son otros adjuntos (bytes, tipo MIME), p. ej. un PDF: también van delante del texto."""
    cfg = types.GenerateContentConfig(temperature=temperatura, system_instruction=sistema or None)
    if esquema is not None:
        cfg.response_mime_type = "application/json"
        cfg.response_schema = esquema
    contenido: Any = prompt
    adjuntos = [(b, "image/jpeg") for b in imagenes or []] + list(archivos or [])
    if adjuntos:
        contenido = [types.Part.from_bytes(data=b, mime_type=m) for b, m in adjuntos] + [prompt]

    ultimo: Exception | None = None
    for modelo in _modelos(config.MODELO_TEXTO, config.MODELOS_TEXTO_RESERVA):
        for intento in range(3):
            try:
                r = cliente().models.generate_content(model=modelo, contents=contenido, config=cfg)
                texto = (r.text or "").strip()
                if texto:
                    registro.apuntar("Gemini (texto)", f"{detalle} · {modelo}", produccion=produccion)
                    return texto
                ultimo = RuntimeError(f"{modelo} devolvió una respuesta vacía")
            except Exception as e:  # noqa: BLE001 - la API mezcla tipos de error; se reintenta igual
                ultimo = e
                limite = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                logger.warning("Gemini %s (intento %d): %s", modelo, intento + 1, e)
                if not limite and intento:
                    break
                time.sleep(4 * (intento + 1) if limite else 2)
    raise RuntimeError(f"Gemini no respondió con ningún modelo: {ultimo}")
