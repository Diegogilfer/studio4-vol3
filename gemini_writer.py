"""
gemini_writer.py - Guionista Creativo con Google Gemini 2.5
Parte de STUDIO 4 Vol. 3

Módulo de generación de guiones virales y de alta retención utilizando
el ecosistema de Google (Gemini 2.5 Flash / Pro).
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger("studio4.gemini_writer")

DEFAULT_MODEL = os.getenv("GEMINI_WRITER_MODEL", "gemini-2.5-flash")

SYSTEM_INSTRUCTION = """Eres un guionista audiovisual de élite especializado en redacción magnética, storytelling viral y máxima retención para videos de YouTube y formatos modernos.

Tu objetivo es redactar el guion de locución continua (voz en off) para un video impactante.

REGLAS DE ORO:
1. GANCHO INMEDIATO (0-3 segundos): La primera frase debe cortar el aire, despertar curiosidad extrema o desafiar una creencia popular sin rodeos ni saludos ("Hola a todos", "Bienvenidos al canal").
2. ESTRUCTURA NARRATIVA:
   - Gancho instantáneo (primeros 3-5s).
   - Desarrollo con tensión creciente y revelación de datos fascinantes (5-45s).
   - Clímax / Conclusión poderosa (45-55s).
   - Llamado a la acción breve, orgánico e intrigante (55-60s).
3. RITMO Y LOCUCIÓN: Español neutro, fluido, cinematográfico y conversacional, con cadencia natural para que el oyente no despegue la atención.
4. TEXTO PURO PARA TEXT-TO-SPEECH (TTS):
   - NO escribas acotaciones de sonido o dirección de cámara (NADA de "[Música de fondo]", "(Pausa dramática)", "[Corte a B-roll]").
   - NO incluyas asteriscos, títulos de sección, viñetas ni formato Markdown.
   - Entrega ÚNICAMENTE el texto que la voz del locutor leerá de corrido de inicio a fin.
"""


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """Inicializa el cliente oficial de Google GenAI."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Falta la clave GEMINI_API_KEY. "
            "Defínela en tu archivo .env o en las variables de entorno."
        )
    return genai.Client(api_key=key)


def escribir_guion_gemini(
    tema: str,
    target_seconds: int = 60,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> str:
    """
    Genera un guion de alta retención usando Google Gemini 2.5.

    Args:
        tema: Tema o premisa del video.
        target_seconds: Duración objetivo en segundos.
        model: Modelo de Gemini (por defecto 'gemini-2.5-flash').
        api_key: Clave opcional de API de Gemini.

    Returns:
        str: Texto limpio de locución continua.
    """
    client = get_gemini_client(api_key)

    # Estimación de palabras según cadencia media española (~145 palabras/min)
    palabras_objetivo = int((target_seconds / 60.0) * 145)

    prompt = (
        f"Redacta un guion magnético para video de aproximadamente {target_seconds} segundos "
        f"(alrededor de {palabras_objetivo} palabras) sobre el siguiente tema:\n\n"
        f"\"{tema}\"\n\n"
        f"Recuerda: Escribe solo la narración directa para el locutor, sin saludos ni acotaciones técnicas."
    )

    logger.info("Solicitando guion a Gemini (%s) para tema: '%s'", model, tema)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
            ),
        )
    except Exception as e:
        logger.error("Error al generar guion con Gemini: %s", e)
        raise

    guion = (response.text or "").strip()
    if not guion:
        raise RuntimeError("Gemini devolvió un texto de guion vacío.")

    logger.info("Guion redactado exitosamente con Gemini (%d palabras).", len(guion.split()))
    return guion


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    tema_test = sys.argv[1] if len(sys.argv) > 1 else "Por qué el cerebro humano olvida dónde dejó las llaves"
    print(f"\n--- Probando gemini_writer.py con tema: {tema_test} ---\n")
    try:
        resultado = escribir_guion_gemini(tema_test)
        print("=== GUION GEMINI ===")
        print(resultado)
    except Exception as err:
        print(f"Error: {err}")

