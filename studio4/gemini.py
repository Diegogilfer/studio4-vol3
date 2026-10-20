"""Cliente de Gemini (API gratuita de AI Studio) con modelos de reserva y reintentos."""

from __future__ import annotations

import json
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


def cambiar_clave(clave: str) -> str:
    """Una clave nueva de AI Studio para volver a las voces gratis. Antes de guardarla se prueba diciendo «Hola»
    con una voz del panel: si Google la rechaza o es de un proyecto con facturación sin saldo (402), no se guarda
    y se explica por qué. Si sirve, queda en .env y se usa al momento (sin reiniciar). Devuelve el modelo que habló."""
    global _cliente
    import re as _re
    from dotenv import set_key
    clave = (clave or "").strip()
    # dos formatos: el clásico «AIza…» y el nuevo de AI Studio «AQ.…» (octubre de 2026)
    if not _re.fullmatch(r"(AIza[0-9A-Za-z_\-]{30,}|AQ\.[0-9A-Za-z_\-]{30,})", clave):
        raise ValueError("Eso no parece una clave de Google: empiezan por «AIza» o «AQ.» (cópiala de aistudio.google.com/apikey).")
    prueba = genai.Client(api_key=clave)
    cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOZ_GEMINI))))
    ultimo = ""
    for modelo in _modelos(config.MODELO_TTS, config.MODELOS_TTS_RESERVA):
        try:
            prueba.models.generate_content(model=modelo, contents="Di con calma: Hola.", config=cfg)
            break
        except Exception as e:  # noqa: BLE001
            ultimo = str(e)
            if "402" in ultimo or "prepayment" in ultimo:
                raise ValueError("Esa clave es de un proyecto CON facturación y sin saldo, como la anterior. Crea la clave "
                                 "en un proyecto NUEVO sin facturación («Create API key» → «Create API key in new project»).") from e
            if "API_KEY_INVALID" in ultimo or "API key not valid" in ultimo:
                raise ValueError("Google dice que esa clave no es válida: cópiala entera otra vez.") from e
            logger.warning("Probando la clave nueva con %s: %s", modelo, ultimo[:200])
    else:
        raise ValueError(f"La clave funciona, pero Google no deja hacer voz con ella ahora mismo: {ultimo[:200]}")
    config.ENV_FILE.touch(exist_ok=True)
    set_key(str(config.ENV_FILE), "GEMINI_API_KEY", clave, quote_mode="never")
    config.GEMINI_API_KEY = clave
    _cliente = None
    _bloqueo.update(hasta=0.0, motivo="")   # fuera la pausa por el 402 de la clave anterior
    registro.apuntar("Gemini TTS", "prueba de la clave nueva", produccion="")
    return modelo


def _modelos(preferido: str, reserva: list[str]) -> list[str]:
    return list(dict.fromkeys([preferido, *reserva]))


# Cortocircuito: si Google dice que el proyecto no tiene saldo (402) o que se acabó el cupo del día, no se le
# vuelve a preguntar en cada paso (cada intento perdía 30-40 s de esperas): durante un rato se va directo a la reserva.
_bloqueo = {"hasta": 0.0, "motivo": ""}
BLOQUEO_SIN_SALDO = 30 * 60
BLOQUEO_CUPO_DIA = 60 * 60


def bloqueado() -> str:
    """El motivo si Gemini está en pausa por el cortocircuito ("" si se le puede preguntar)."""
    return _bloqueo["motivo"] if time.time() < _bloqueo["hasta"] else ""


def _bloquear(segundos: int, motivo: str) -> None:
    _bloqueo.update(hasta=time.time() + segundos, motivo=motivo)
    logger.warning("Gemini en pausa %d min: %s", segundos // 60, motivo)


def _reserva(prompt: str, sistema: str, esquema: Any, temperatura: float, detalle: str, produccion: str, causa: str) -> str:
    """Plan B de texto: DeepSeek hace el mismo trabajo y devuelve lo mismo (JSON del esquema o texto)."""
    from . import deepseek   # aquí para no crear un ciclo al importar
    if not deepseek.disponible():
        raise RuntimeError(causa)
    logger.warning("Gemini no disponible (%s): «%s» lo hace la reserva.", causa[:120], detalle)
    if esquema is None:
        return deepseek.generar_texto(sistema, prompt, temperatura=temperatura, detalle=f"{detalle} (reserva)", produccion=produccion)
    forma = json.dumps(esquema.model_json_schema(), ensure_ascii=False)
    datos = deepseek.generar_json(sistema or "Responde en español.",
                                  f"{prompt}\n\nResponde SOLO con un objeto JSON que cumpla exactamente este esquema "
                                  f"(mismos nombres de campo):\n{forma}", temperatura=temperatura,
                                  detalle=f"{detalle} (reserva)", produccion=produccion)
    return esquema.model_validate(datos).model_dump_json()


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
    reserva: bool = True,
) -> str:
    """Devuelve el texto de la respuesta. Con `esquema` (Pydantic) la respuesta es JSON validable.
    `imagenes` (JPEG) van delante del texto, numeradas en el orden dado: Gemini las ve todas.
    `archivos` son otros adjuntos (bytes, tipo MIME), p. ej. un PDF: también van delante del texto.
    Si Gemini no responde (sin clave, sin saldo, cupo agotado o caído) y la petición es solo texto, la hace la
    reserva (DeepSeek) con el mismo formato. `reserva=False` cuando quien llama ya viene de DeepSeek."""
    sin_adjuntos = not imagenes and not archivos
    try:
        return _con_gemini(prompt, sistema, esquema, temperatura, detalle, produccion, imagenes, archivos)
    except RuntimeError as e:
        if reserva and sin_adjuntos:
            return _reserva(prompt, sistema, esquema, temperatura, detalle, produccion, str(e))
        raise


def _con_gemini(prompt: str, sistema: str, esquema: Any, temperatura: float, detalle: str, produccion: str,
                imagenes: Optional[list[bytes]], archivos: Optional[list[tuple[bytes, str]]]) -> str:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env.")
    if motivo := bloqueado():
        raise RuntimeError(motivo)
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
                if "402" in str(e) or "prepayment credits" in str(e):   # proyecto sin saldo: ningún reintento ni modelo lo arregla
                    motivo = ("Tu proyecto de Google se quedó sin saldo de prepago (402): crea una clave de API en un "
                              "proyecto SIN facturación para volver al nivel gratuito.")
                    _bloquear(BLOQUEO_SIN_SALDO, motivo)
                    raise RuntimeError(motivo) from e
                if "PerDay" in str(e) and "limit: 0" not in str(e):   # cupo del día agotado: esperar minutos no sirve
                    _bloquear(BLOQUEO_CUPO_DIA, "Se acabó el cupo gratis de Gemini de hoy.")
                    raise RuntimeError(f"Se acabó el cupo gratis de Gemini de hoy: {e}") from e
                limite = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                logger.warning("Gemini %s (intento %d): %s", modelo, intento + 1, e)
                if not limite and intento:
                    break
                time.sleep(4 * (intento + 1) if limite else 2)
    raise RuntimeError(f"Gemini no respondió con ningún modelo: {ultimo}")
