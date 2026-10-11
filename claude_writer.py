"""
claude_writer.py - Guionista Creativo con Anthropic Claude
Parte de STUDIO 4 Vol. 3

Módulo encargado de generar guiones magnéticos, con ganchos virales en los primeros
3 segundos, estructura de tensión-resolución y redacción diseñada para locución continua.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
import anthropic
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

logger = logging.getLogger("studio4.claude_writer")

# Modelos recomendados en orden de prioridad
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-7-sonnet-latest")
FALLBACK_MODEL = "claude-3-5-sonnet-latest"

SYSTEM_PROMPT = """Eres un guionista audiovisual de élite especializado en contenido viral y de alta retención para YouTube, TikTok y formatos audiovisuales modernos.

Tu misión es escribir el guion completo de locución (voz en off) para un video magnético.

REGLAS CRÍTICAS DE REDACCIÓN:
1. GANCHO (Primeros 3 segundos): La primera frase debe atrapar instantáneamente la curiosidad, romper un mito o plantear una pregunta irresistible sin rodeos ni saludos ("Hola a todos", "Bienvenidos").
2. ESTRUCTURA:
   - Gancho inicial inmediato (0-5s).
   - Desarrollo con escalada de tensión y ritmo constante (5-45s).
   - Clímax / Revelación de valor (45-55s).
   - Cierre contundente y llamado a la acción sutil y orgánico (55-60s).
3. TONO DE LOCUCIÓN: Español neutro, fluido, cercano y dinámico, con frases directas y pausas naturales para respiración.
4. TEXTO PURO PARA TEXT-TO-SPEECH (TTS):
   - NO incluyas acotaciones de dirección de arte ni sonido (NADA de "[Música]", "(Voz misteriosa)", "[Corte a cámara]").
   - NO uses títulos, encabezados, asteriscos de formato Markdown (*, **), ni viñetas.
   - Escribe EXCLUSIVAMENTE el texto continuo que el locutor leerá palabra por palabra de principio a fin.
"""


def get_anthropic_client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    """
    Inicializa y retorna el cliente de Anthropic.
    Verifica que la clave de API esté configurada.
    """
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "Falta la clave ANTHROPIC_API_KEY. "
            "Defínela en tu archivo .env o en las variables de entorno."
        )
    return anthropic.Anthropic(api_key=key)


def escribir_guion(
    tema: str,
    target_seconds: int = 60,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> str:
    """
    Genera un guion magnético para video continuo usando Claude.

    Args:
        tema: Tema, premisa o idea central del video.
        target_seconds: Duración estimada objetivo del video en segundos (por defecto ~60s).
        model: Nombre del modelo de Claude a utilizar.
        api_key: Clave opcional de API (si no se toma del entorno).

    Returns:
        str: Texto limpio del guion listo para narración continua.
    """
    client = get_anthropic_client(api_key)

    # Estimación de palabras según velocidad de habla media (~140-150 palabras/minuto)
    palabras_estimadas = int((target_seconds / 60.0) * 145)

    prompt = (
        f"Escribe un guion para un video de aproximadamente {target_seconds} segundos "
        f"({palabras_estimadas} palabras) sobre el siguiente tema:\n\n"
        f"\"{tema}\"\n\n"
        f"Recuerda: Solo texto corrido para el locutor, sin saludos genéricos ni acotaciones."
    )

    logger.info("Enviando solicitud a Claude (%s) para tema: '%s'", model, tema)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.NotFoundError:
        # Fallback a claude-3-5-sonnet si el modelo latest específico no estuviese disponible
        if model != FALLBACK_MODEL:
            logger.warning(
                "Modelo '%s' no disponible. Reintentando con '%s'...",
                model,
                FALLBACK_MODEL,
            )
            response = client.messages.create(
                model=FALLBACK_MODEL,
                max_tokens=1500,
                temperature=0.7,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            raise
    except anthropic.APIError as e:
        logger.error("Error al comunicarse con la API de Anthropic: %s", e)
        raise

    # Extraer el texto de la respuesta
    texto_partes: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            texto_partes.append(block.text)

    guion = "\n\n".join(texto_partes).strip()
    logger.info("Guion generado exitosamente con Claude (%d caracteres).", len(guion))
    return guion


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    tema_prueba = sys.argv[1] if len(sys.argv) > 1 else "La paradoja de Fermi y por qué no vemos extraterrestres"
    print(f"\n--- Probando claude_writer.py con tema: {tema_prueba} ---\n")
    try:
        resultado = escribir_guion(tema_prueba)
        print("=== GUION GENERADO ===")
        print(resultado)
    except Exception as err:
        print(f"Error durante la prueba: {err}")

