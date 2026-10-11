"""
voice.py - Generador de Voz en Off (Google Ecosystem)
Parte de STUDIO 4 Vol. 3

Módulo de locución que soporta:
1. Gemini Native Voice / TTS (mediante GEMINI_API_KEY, 24kHz Studio PCM WAV).
2. Google Cloud Text-to-Speech (mediante Service Account JSON o REST API).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
import wave
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger("studio4.voice")

DEFAULT_VOICE = os.getenv("TTS_VOICE_NAME", "es-US-Neural2-F")
DEFAULT_SPEAKING_RATE = float(os.getenv("TTS_SPEAKING_RATE", "1.02"))


def get_audio_duration_wave(audio_path: str) -> float:
    """Calcula la duración exacta en segundos de un archivo WAV."""
    try:
        with wave.open(audio_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception as e:
        logger.debug("No se pudo leer duración WAV con módulo estándar (%s)", e)
    return 0.0


def _sintetizar_con_gemini_native_tts(
    texto: str,
    out_path_obj: Path,
    api_key: Optional[str] = None,
) -> str:
    """
    Sintetiza voz de alta fidelidad directamente con los modelos de audio/TTS de Google Gemini.
    Genera un archivo WAV a 24000 Hz, 16-bit PCM mono.
    """
    from google import genai
    from google.genai import types

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("Falta GEMINI_API_KEY para síntesis vocal con Gemini.")

    client = genai.Client(api_key=key)

    # Modelos TTS disponibles en Gemini
    modelos_tts = [
        "gemini-2.5-flash-preview-tts",
        "gemini-3.1-flash-tts-preview",
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts",
    ]

    ultimo_error = None
    for modelo in modelos_tts:
        try:
            logger.info("Sintetizando locución con modelo nativo de audio '%s'...", modelo)
            resp = client.models.generate_content(
                model=modelo,
                contents=texto.strip(),
                config=types.GenerateContentConfig(response_modalities=["AUDIO"]),
            )
            if not resp.candidates or not resp.candidates[0].content or not resp.candidates[0].content.parts:
                continue

            for part in resp.candidates[0].content.parts:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    pcm_data = inline.data
                    with wave.open(str(out_path_obj), "wb") as wav_file:
                        wav_file.setnchannels(1)       # Mono
                        wav_file.setsampwidth(2)      # 16-bit
                        wav_file.setframerate(24000)   # 24 kHz
                        wav_file.writeframes(pcm_data)

                    duration = get_audio_duration_wave(str(out_path_obj))
                    logger.info(
                        "Audio masterizado con Gemini TTS: %s (Duración: %.2fs)",
                        out_path_obj,
                        duration,
                    )
                    return str(out_path_obj)
        except Exception as e:
            ultimo_error = e
            logger.warning("Fallo al sintetizar con %s: %s", modelo, e)

    raise RuntimeError(f"No se pudo generar audio con ningún modelo de Gemini TTS. Último error: {ultimo_error}")


def generar_locucion(
    texto_completo: str,
    output_path: str = "output/audio.wav",
    voice_name: str = DEFAULT_VOICE,
    speaking_rate: float = DEFAULT_SPEAKING_RATE,
    credentials_path: Optional[str] = None,
) -> str:
    """
    Sintetiza el texto del guion en un archivo de audio WAV.
    Utiliza Google Cloud TTS si cuenta con credenciales de cuenta de servicio,
    o Gemini Native TTS con la GEMINI_API_KEY.
    """
    if not texto_completo or not texto_completo.strip():
        raise ValueError("El texto para la locución no puede estar vacío.")

    out_path_obj = Path(output_path).resolve()
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # 1. Intentar con Service Account JSON de Google Cloud TTS si existe
    creds = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds and os.path.exists(creds):
        try:
            from google.cloud import texttospeech
            client = texttospeech.TextToSpeechClient()
            logger.info("Usando Google Cloud TTS con cuenta de servicio (%s)...", creds)

            partes = voice_name.split("-")
            language_code = f"{partes[0]}-{partes[1]}" if len(partes) >= 2 else "es-US"

            synthesis_input = texttospeech.SynthesisInput(text=texto_completo.strip())
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                speaking_rate=speaking_rate,
            )
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
            )
            with open(out_path_obj, "wb") as f:
                f.write(response.audio_content)

            duration = get_audio_duration_wave(str(out_path_obj))
            logger.info("Locución Google Cloud TTS guardada en %s (%.2fs)", out_path_obj, duration)
            return str(out_path_obj)
        except Exception as e:
            logger.warning("Fallo al usar TextToSpeechClient oficial: %s. Probando Gemini Native TTS...", e)

    # 2. Síntesis nativa con Google Gemini TTS (usando GEMINI_API_KEY)
    if os.getenv("GEMINI_API_KEY"):
        return _sintetizar_con_gemini_native_tts(
            texto=texto_completo,
            out_path_obj=out_path_obj,
        )

    raise RuntimeError(
        "No se pudo generar locución. Configura GEMINI_API_KEY en tu .env "
        "o proporciona un archivo de credenciales de Google Cloud."
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    test_text = sys.argv[1] if len(sys.argv) > 1 else (
        "El silencio del cosmos no es una casualidad. Podría ser la advertencia más aterradora jamás descubierta."
    )
    test_out = "output/test_voice.wav"
    print(f"\n--- Probando voice.py ---")
    print(f"Texto: {test_text}")
    try:
        archivo = generar_locucion(test_text, output_path=test_out)
        print(f"Voz generada exitosamente en: {archivo}")
    except Exception as err:
        print(f"Error durante la prueba de voz: {err}")
