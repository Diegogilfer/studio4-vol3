"""Fase 2 · Director: Gemini parte el guion en escenas de vídeo y escribe el prompt de Flow (Veo) de cada una.

La biblia visual (personajes, escenario, luz, paleta, estilo) se define una vez y se copia literal en
cada prompt: así Veo ve la misma descripción en todas las escenas y la secuencia no salta.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from . import config, gemini

logger = logging.getLogger("studio4.director")

SEGUNDOS_CLIP = 8          # lo que dura un clip de Veo en Flow
PALABRAS_MAX_ESCENA = 18   # ~7,5 s de voz: cabe en un clip sin cámara lenta


class Personaje(BaseModel):
    nombre: str = Field(description="Nombre corto en MAYÚSCULAS para referirse a él (ej. 'LEO').")
    aspecto_en: str = Field(description="Aspecto fijo en inglés: edad, rasgos, pelo, ropa exacta y un detalle distintivo.")


class Biblia(BaseModel):
    escenario_en: str = Field(description="Mundo, época y lugar común de la historia, en inglés.")
    luz_en: str = Field(description="Esquema de luz constante, en inglés.")
    paleta_en: str = Field(description="Paleta dominante (3-4 colores), en inglés.")
    personajes: list[Personaje] = Field(default_factory=list, description="0 a 3 personajes recurrentes.")


class Escena(BaseModel):
    texto_voz: str = Field(description="Fragmento EXACTO y consecutivo del guion que se narra en esta escena.")
    plano_en: str = Field(description="Tipo de plano en inglés: extreme wide, wide, medium, medium close-up, close-up, macro, aerial, POV...")
    camara_en: str = Field(description="Movimiento de cámara en inglés: slow dolly-in, tracking shot, crane up, orbit, static, handheld push...")
    accion_en: str = Field(description="Qué se VE en inglés: sujeto (nombres de la biblia) + acción visible y concreta + lugar + composición.")
    personajes: list[str] = Field(default_factory=list, description="Nombres de la biblia que salen en esta escena.")
    texto_pantalla: str = Field(default="", description="2 a 5 palabras impactantes para rotular (puede quedar vacío).")
    tono_voz: str = Field(default="narrativo", description="Cómo se DICE esta escena, según la historia y lo que se ve: "
                                                          "narrativo, intrigante, tenso, emocionante, cinematografico, intimo, "
                                                          "solemne, asombro o triunfal.")
    ritmo_voz: str = Field(default="normal", description="lento, normal o rapido.")
    tipo_clip: str = Field(default="video", description="Qué generar en Flow: 'video' (acción, movimiento, gancho, clímax) "
                                                         "o 'imagen' (momento descriptivo o de pausa; se anima en el montaje).")
    motivo_tipo: str = Field(default="", description="Por qué vídeo o imagen, en una frase corta en español.")


class Aviso(BaseModel):
    frase: str = Field(description="Frase literal del guion que es difícil de mostrar en vídeo.")
    problema: str = Field(description="Por qué no se puede filmar bien (abstracta, sin sujeto visible, cifra sin imagen...).")
    sugerencia: str = Field(description="Cómo reescribirla para que se pueda ver, manteniendo el sentido.")


class Plan(BaseModel):
    titulo: str = Field(description="Título con curiosidad, sin clickbait engañoso, máx. 70 caracteres.")
    descripcion: str = Field(description="Descripción para redes: gancho + resumen en 2-3 frases.")
    hashtags: list[str] = Field(description="Entre 4 y 8 hashtags, con #.")
    biblia: Biblia
    escenas: list[Escena]
    avisos: list[Aviso] = Field(default_factory=list, description="Frases del guion difíciles de filmar (0 a 5). "
                                                                  "No cambies el guion: solo avisa.")


SISTEMA = f"""Eres director de fotografía y de montaje de vídeos cortos generados con Google Veo (Flow).
Cada escena se rodará como UN clip de Veo de {SEGUNDOS_CLIP} segundos.

REGLAS:
1. Reparte el guion COMPLETO en escenas consecutivas. Concatenando todos los texto_voz debe salir el guion
   palabra por palabra: no reescribas, no resumas, no saltes nada.
2. Cada escena: entre 8 y {PALABRAS_MAX_ESCENA} palabras de voz (corta siempre en final de frase o de coma).
3. Lo que se narra tiene que VERSE: si la voz dice "su radar falla", el plano muestra el radar fallando.
4. accion_en describe UNA acción continua que se pueda rodar en {SEGUNDOS_CLIP} s, con sujeto, lugar y composición.
   Usa los nombres de la biblia para los personajes; no repitas su aspecto (se añade solo).
5. Alterna planos (no dos close-ups seguidos) y elige un movimiento de cámara que sume emoción.
6. Nunca pidas texto, letras, logotipos, subtítulos ni pantallas divididas dentro de la imagen.
7. La biblia visual define lo que NO cambia entre escenas: escenario, luz, paleta y personajes con ropa exacta.
8. DIRECCIÓN DE VOZ: eres también director de locución. Para cada escena elige tono_voz y ritmo_voz según el
   arco (presentación → tensión → giro → clímax → cierre) y lo que se ve en el plano: misterio = intrigante o
   tenso y lento; revelación o acción = emocionante y rápido; plano épico o clímax = cinematografico; dato
   humano = intimo; cierre = solemne o triunfal. Varía: no repitas el mismo tono más de dos escenas seguidas.
9. VÍDEO O IMAGEN en Flow (tipo_clip): vídeo cuando hay acción, movimiento o emoción que se mueve (y siempre el
   gancho y el clímax); imagen en momentos descriptivos, datos, retratos o pausas (el montaje la anima con un
   movimiento de cámara suave). Intercala: nunca más de 2 imágenes seguidas, y que ninguno de los dos domine.
10. Si una frase es abstracta o difícil de ver, NO la cambies: búscale la mejor imagen posible y añádela a «avisos»
   con una sugerencia de reescritura. El guion lo ha aprobado una persona."""


def _prompt_flow(esc: dict[str, Any], biblia: dict[str, Any], estilo: str, aspecto: str) -> str:
    """Prompt autosuficiente para pegar en Flow: plano + acción + biblia completa + estilo.
    Para imagen pide una foto fija (sin movimiento de cámara); para vídeo, un plano de 8 s con su movimiento."""
    imagen = esc.get("tipo_clip") == "imagen"
    looks = {p["nombre"].upper(): p["aspecto_en"] for p in biblia.get("personajes", [])}
    salen = [n.upper() for n in esc.get("personajes", []) if n.upper() in looks]
    if imagen:
        partes = [f"{esc['plano_en'].strip().capitalize()}. {esc['accion_en'].strip().rstrip('.')}."]
    else:
        partes = [f"{esc['plano_en'].strip().capitalize()}, {esc['camara_en'].strip()}. {esc['accion_en'].strip().rstrip('.')}."]
    if salen:
        partes.append("Characters: " + "; ".join(f"{n} is {looks[n]}" for n in salen) + ".")
    partes.append(f"Setting: {biblia.get('escenario_en', '').strip().rstrip('.')}.")
    partes.append(f"Lighting: {biblia.get('luz_en', '').strip().rstrip('.')}. Palette: {biblia.get('paleta_en', '').strip().rstrip('.')}.")
    partes.append(f"Style: {estilo}.")
    if imagen:
        partes.append(f"Single still photograph, frozen moment, aspect ratio {aspecto}. No text, no letters.")
    else:
        partes.append(f"Aspect ratio {aspecto}. Ambient sound effects only: no dialogue, no voice-over, no music. No on-screen text.")
    return " ".join(partes)


def _intercalar(escenas: list[dict[str, Any]]) -> None:
    """Reglas fijas sobre la recomendación: el gancho en vídeo y nunca 3 imágenes seguidas."""
    seguidas = 0
    for i, e in enumerate(escenas):
        e["tipo_clip"] = "imagen" if e.get("tipo_clip") == "imagen" else "video"
        if i == 0 and e["tipo_clip"] == "imagen":
            e.update(tipo_clip="video", motivo_tipo="Es el gancho: el vídeo retiene en los primeros segundos.")
        seguidas = seguidas + 1 if e["tipo_clip"] == "imagen" else 0
        if seguidas > 2:
            e.update(tipo_clip="video", motivo_tipo="Para no encadenar tres imágenes seguidas.")
            seguidas = 0


class Recomendacion(BaseModel):
    tipo_clip: str
    motivo_tipo: str


class Recomendaciones(BaseModel):
    escenas: list[Recomendacion]


def recomendar_tipos(escenas: list[dict[str, Any]], biblia: dict[str, Any], estilo_en: str, aspecto: str,
                     produccion: str = "") -> None:
    """Para producciones hechas antes de esta función: decide vídeo o imagen por escena y rehace sus prompts."""
    lista = "\n".join(f"{e['orden']}. {e['texto_voz']} | Plano: {e.get('plano_en', '')}, {e.get('accion_en', '')}" for e in escenas)
    crudo = gemini.generar(
        f"Escenas de un vídeo, en orden:\n{lista}\n\nPara cada escena decide si en Google Flow conviene generar 'video' "
        "(acción, movimiento, gancho, clímax) o 'imagen' (momento descriptivo, dato, retrato o pausa; el montaje la anima). "
        "Intercala: nunca más de 2 imágenes seguidas. Da el motivo en una frase corta en español. Una entrada por escena, en orden.",
        esquema=Recomendaciones, temperatura=0.3, detalle="vídeo o imagen por escena", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    recs = Recomendaciones.model_validate_json(m.group(0) if m else crudo).escenas
    for e, r in zip(escenas, recs):
        e["tipo_clip"], e["motivo_tipo"] = r.tipo_clip.strip().lower(), r.motivo_tipo.strip()
    _intercalar(escenas)
    for e in escenas:
        if e.get("plano_en") and e.get("accion_en"):
            e["prompt_flow"] = _prompt_flow(e, biblia, estilo_en, aspecto)


def _palabras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def planificar(guion: str, estilo: str, formato: str, produccion: str = "",
               titulos_existentes: list[str] | None = None) -> dict[str, Any]:
    estilo_en = config.ESTILOS.get(estilo, estilo)
    aspecto = config.FORMATOS[formato]["aspecto"]
    prompt = (
        f"ESTILO VISUAL: {estilo_en}\nFORMATO: {aspecto} "
        f"({'sujeto centrado y alto' if aspecto == '9:16' else 'deja aire a los lados'})\n\n"
        f"--- GUION ---\n{guion}\n--- FIN ---"
    )
    if titulos_existentes:
        prompt += ("\n\nTÍTULOS QUE YA EXISTEN EN YOUTUBE SOBRE ESTO (el tuyo tiene que ser claramente distinto, "
                   "con otro ángulo o un detalle concreto del guion):\n" + "\n".join(f"- {t}" for t in titulos_existentes[:8]))
    crudo = gemini.generar(prompt, sistema=SISTEMA, esquema=Plan, temperatura=0.4, detalle="plan de escenas",
                           produccion=produccion)
    match = re.search(r"\{.*\}", crudo, re.DOTALL)
    plan = Plan.model_validate_json(match.group(0) if match else crudo).model_dump()

    if not plan["escenas"]:
        raise RuntimeError("Gemini no devolvió escenas.")
    if _palabras(" ".join(e["texto_voz"] for e in plan["escenas"])) != _palabras(guion):
        # La voz lee las escenas, no el guion original: así la sincronía con los clips siempre cuadra.
        logger.warning("Las escenas no reproducen el guion palabra por palabra; la narración será la de las escenas.")

    _intercalar(plan["escenas"])
    for i, esc in enumerate(plan["escenas"], start=1):
        esc["orden"] = i
        esc["prompt_flow"] = _prompt_flow(esc, plan["biblia"], estilo_en, aspecto)
        n = len(esc["texto_voz"].split())
        if n > PALABRAS_MAX_ESCENA + 4:
            logger.warning("Escena %d tiene %d palabras: el clip irá a cámara lenta.", i, n)
    plan["estilo_en"] = estilo_en
    return plan
