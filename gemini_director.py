"""
gemini_director.py - Director Técnico con Google Gemini 2.5 Flash
Parte de STUDIO 4 Vol. 3

Módulo que recibe el guion narrativo de Claude y lo desglosa técnicamente en un
plan de producción audiovisual en JSON estricto: título viral, descripción SEO
y lista de escenas sincronizadas con términos cinematográficos para Pexels.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger("studio4.gemini_director")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


# ==============================================================================
# Esquema Pydantic para Salida Estructurada JSON Estricta
# ==============================================================================
class ScenePlan(BaseModel):
    order: int = Field(
        description="Número correlativo de la escena empezando en 1."
    )
    duration_sec: int = Field(
        description="Duración de la escena en segundos (ritmo dinámico de 3 a 7 segundos)."
    )
    voice_segment: str = Field(
        description="Fragmento textual exacto del guion que se narra durante esta escena."
    )
    broll_query_en: str = Field(
        description=(
            "Términos cinematográficos precisos en INGLÉS para buscar metraje en Pexels "
            "(ej. 'macro human eye pupil dilating cinematic lighting', "
            "'aerial view futuristic city night neon lights 4k')."
        )
    )
    overlay_text: str = Field(
        description=(
            "Texto corto e impactante para superponer en pantalla (máximo 3 a 5 palabras, "
            "en mayúsculas o estilo subtítulo clave)."
        )
    )
    camera_movement: str = Field(
        default="acercar",
        description="Movimiento de cámara dinámico: 'acercar', 'alejar', 'subir', 'bajar', 'derecha', 'izquierda'."
    )
    transition: str = Field(
        default="crossfade",
        description="Transición cinematográfica con la siguiente escena: 'crossfade', 'fadeblack', 'wipeleft', 'none'."
    )
    flow_prompt_en: str = Field(
        default="",
        description=(
            "Dirección de IMAGEN en INGLÉS para Google Flow (un solo fotograma): tipo de plano + sujeto "
            "haciendo una acción VISIBLE y concreta + lugar + composición. Usa los nombres de personaje "
            "definidos en visual_bible. Sin estilo artístico (va aparte) y sin texto en la imagen. "
            "Ej: 'Medium close-up of LEO, looking up at a cracked observatory dome, night sky through the gap, "
            "subject on the left third'."
        )
    )
    characters: list[str] = Field(
        default_factory=list,
        description="Nombres (de visual_bible.characters) que aparecen en esta escena. Vacío si no sale ninguno."
    )


class CharacterSheet(BaseModel):
    name: str = Field(description="Nombre corto en MAYÚSCULAS para referenciarlo en las escenas (ej. 'LEO').")
    look_en: str = Field(
        description=(
            "Aspecto FIJO en inglés, idéntico en todas las escenas: edad, rasgos, pelo, ropa exacta y un "
            "detalle distintivo (ej. '30-year-old man, short black curly hair, round glasses, mustard wool coat')."
        )
    )


class VisualBible(BaseModel):
    """La biblia visual: lo que NO cambia entre escenas para que Flow mantenga la secuencia."""
    style_lock_en: str = Field(default="", description="Dirección de arte fija en inglés, una frase.")
    palette_en: str = Field(default="", description="Paleta de color dominante en inglés (3-4 colores).")
    lighting_en: str = Field(default="", description="Esquema de luz constante en inglés.")
    setting_en: str = Field(default="", description="Mundo/época/lugar común de la historia en inglés.")
    characters: list[CharacterSheet] = Field(
        default_factory=list,
        description="Personajes recurrentes (0 a 3). Vacío si el vídeo no tiene protagonistas humanos."
    )


class ProductionPlan(BaseModel):
    title: str = Field(
        description="Título de alto impacto (High-CTR) optimizado para YouTube / redes."
    )
    description: str = Field(
        description="Descripción estructurada para SEO incluyendo resumen, puntos clave y hashtags (#shorts #tecnologia etc.)."
    )
    visual_bible: VisualBible = Field(
        default_factory=VisualBible,
        description="Biblia visual común a todas las escenas (personajes, paleta, luz, escenario)."
    )
    scenes: list[ScenePlan] = Field(
        description="Lista ordenada y cronológica de todas las escenas que componen el video."
    )


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Inicializa el cliente oficial de Google GenAI.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Falta la clave GEMINI_API_KEY. "
            "Defínela en tu archivo .env o en las variables de entorno."
        )
    return genai.Client(api_key=key)


DIRECTOR_INSTRUCTIONS = """Actúas como el Director Técnico y Editor Audiovisual Jefe de un canal de video moderno de alto rendimiento.

Tu tarea es tomar el guion de voz en off redactado por Claude y estructurarlo milimétricamente en un PLAN DE PRODUCCIÓN en formato JSON.

CRITERIOS DIRECTORIALES:
1. DESGLOSE COMPLETO: Debes cubrir el 100% del texto del guion en las escenas de forma secuencial. No omitas frases.
2. RITMO VISUAL: Cada escena debe durar entre 3 y 7 segundos. Los cortes frecuentes mantienen la retención visual del espectador.
3. B-ROLL QUERIES (EN INGLÉS):
   - Pexels busca en inglés con palabras clave descriptivas y cinematográficas.
   - Describe tomas concretas: tipo de plano ('macro', 'aerial drone', 'close-up', 'slow motion', 'timelapse'), sujeto, ambiente e iluminación ('neon dark', 'golden hour', 'studio lighting').
   - Evita metáforas abstractas que el buscador no entienda; describe lo que la cámara realmente enfoca.
4. TEXTO OVERLAY: Textos breves en mayúsculas que refuercen la idea emocional o dato numérico de la escena.
5. METADATOS:
   - Título: Intrigante, que genere curiosidad sin ser engañoso (máx 70 caracteres).
   - Descripción: Con gancho, síntesis y entre 4 y 8 hashtags populares.
6. BIBLIA VISUAL (para Google Flow, que genera UNA imagen por escena):
   - Define una sola vez lo que no cambia: personajes con aspecto y ropa exactos, escenario/época, paleta y luz.
   - La dirección de arte debe respetar el ESTILO GRÁFICO indicado abajo.
7. FLOW_PROMPT_EN (una imagen fija por escena, en inglés):
   - Plano (wide / medium / close-up / macro / aerial) + sujeto + acción VISIBLE + lugar + composición.
   - Lo que se narra tiene que VERSE: si la voz dice "su radar falla", la imagen muestra el radar fallando.
   - Encuadra pensando en el FORMATO indicado (vertical = sujeto centrado y alto; horizontal = espacio lateral).
   - Varía el plano entre escenas consecutivas (no dos close-ups seguidos) pero mantén personajes y lugar.
   - Nunca pidas texto, letras, logos ni pantallas divididas.
"""

FORMATOS_ASPECTO = {"portrait": "9:16", "landscape": "16:9", "square": "1:1"}


def estructurar_produccion(
    guion_claude: str,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    style: str = "cinematic",
    orientation: str = "portrait",
) -> dict[str, Any]:
    """
    Transforma un guion en un plan de producción estructurado usando Gemini 2.5 Flash.

    Args:
        guion_claude: Texto completo del guion producido por Claude.
        model: Modelo de Gemini (por defecto 'gemini-2.5-flash').
        api_key: Clave opcional de API de Gemini.
        style: Clave del estilo gráfico elegido en el panel (visual_generator.ESTILOS_GRAFICOS).
        orientation: 'portrait' | 'landscape' | 'square' (formato final del vídeo).

    Returns:
        dict: Diccionario validado con 'title', 'description', 'visual_bible' y 'scenes'.
    """
    if not guion_claude or not guion_claude.strip():
        raise ValueError("El guion proporcionado está vacío.")

    client = get_gemini_client(api_key)

    try:
        from visual_generator import ESTILOS_GRAFICOS
        estilo_txt = ESTILOS_GRAFICOS.get(style, style)
    except Exception:  # noqa: BLE001
        estilo_txt = style
    aspecto = FORMATOS_ASPECTO.get(orientation, "9:16")

    prompt = (
        f"{DIRECTOR_INSTRUCTIONS}\n\n"
        f"ESTILO GRÁFICO: {estilo_txt}\n"
        f"FORMATO: {aspecto}\n\n"
        f"--- GUION A ESTRUCTURAR ---\n"
        f"{guion_claude.strip()}\n"
        f"--- FIN DEL GUION ---"
    )

    logger.info("Enviando guion a Gemini para estructuración de producción...")

    modelos_candidatos = [model, "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-pro-preview"]
    # Eliminar duplicados preservando orden
    modelos_candidatos = list(dict.fromkeys(modelos_candidatos))
    
    response = None
    ultimo_error = None

    import time
    for m in modelos_candidatos:
        for intento in range(2):
            try:
                logger.info("Intentando con modelo %s (intento %d)...", m, intento + 1)
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ProductionPlan,
                        temperature=0.2,
                    ),
                )
                if response and response.text:
                    break
            except Exception as e:
                ultimo_error = e
                logger.warning("Fallo con modelo %s en intento %d: %s", m, intento + 1, e)
                time.sleep(2)
        if response and response.text:
            break

    if not response or not response.text:
        logger.error("Todos los modelos de Gemini fallaron: %s", ultimo_error)
        raise ultimo_error

    raw_text = response.text or ""
    if not raw_text.strip():
        raise RuntimeError("Gemini devolvió una respuesta vacía.")

    # Parsear y validar contra el esquema Pydantic
    try:
        plan_obj = ProductionPlan.model_validate_json(raw_text)
        plan_dict = plan_obj.model_dump()
    except Exception as parse_err:
        logger.warning(
            "Fallo al validar directamente con Pydantic (%s). Intentando extracción regex...",
            parse_err,
        )
        # Limpieza de posibles bloques ```json ... ```
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            clean_json = match.group(0)
            plan_obj = ProductionPlan.model_validate_json(clean_json)
            plan_dict = plan_obj.model_dump()
        else:
            raise RuntimeError(f"No se pudo decodificar el JSON de Gemini: {raw_text[:200]}") from parse_err

    # Asegurar orden correlativo en las escenas
    for idx, scene in enumerate(plan_dict.get("scenes", []), start=1):
        scene["order"] = idx
        # Asegurar duración mínima para evitar clips de 0 segundos
        if scene.get("duration_sec", 0) <= 0:
            scene["duration_sec"] = 4

    logger.info(
        "Plan de producción estructurado exitosamente: '%s' con %d escenas.",
        plan_dict.get("title", "Sin título"),
        len(plan_dict.get("scenes", [])),
    )
    return plan_dict


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    guion_test = (
        "El universo tiene noventa y tres mil millones de años luz de diámetro y al menos "
        "dos billones de galaxias. Matemáticamente, la vida inteligente debería estar en todas partes. "
        "Sin embargo, nuestros radiotelescopios solo captan silencio absoluto. "
        "Esto se conoce como la Paradoja de Fermi. Una de las hipótesis más aterradoras "
        "es la teoría del Gran Filtro: una barrera evolutiva casi insuperable. "
        "¿Será que todas las civilizaciones colapsan antes de viajar a las estrellas, "
        "o la humanidad ya superó esa prueba? Suscríbete y déjanos tu opinión."
    )
    print("\n--- Probando gemini_director.py con guion de muestra ---\n")
    try:
        resultado = estructurar_produccion(guion_test)
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    except Exception as err:
        print(f"Error durante la prueba: {err}")

