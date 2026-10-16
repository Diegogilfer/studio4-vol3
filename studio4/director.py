"""Fase 2 · Director: Gemini parte el guion en escenas de vídeo y escribe el prompt de Flow (Veo) de cada una.

La biblia visual (personajes, escenario, luz, paleta, estilo) se define una vez y se copia literal en
cada prompt: así Veo ve la misma descripción en todas las escenas y la secuencia no salta.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from pydantic import BaseModel, Field

from . import config, gemini
from .guion import PALABRAS_POR_SEGUNDO

logger = logging.getLogger("studio4.director")

SEGUNDOS_CLIP = 8          # lo que dura un clip de Veo en Flow
PALABRAS_MAX_ESCENA = 18   # ~7,5 s de voz: cabe en un clip sin cámara lenta


class Personaje(BaseModel):
    nombre: str = Field(description="Nombre corto en MAYÚSCULAS para referirse a él (ej. 'LEO').")
    aspecto_en: str = Field(description="Ficha visual fija en inglés, 40-70 palabras: edad, origen, rostro, pelo, ojos, "
                                        "complexión, ropa exacta con colores y materiales y un detalle distintivo. Sin pose ni encuadre.")


class Biblia(BaseModel):
    escenario_en: str = Field(description="Mundo, época y lugar común de la historia, en inglés.")
    luz_en: str = Field(description="Esquema de luz constante, en inglés.")
    paleta_en: str = Field(description="Paleta dominante (3-4 colores), en inglés.")
    personajes: list[Personaje] = Field(default_factory=list, description="Todos los personajes que se ven (máx. 8). "
                                                                         "Si hay REPARTO, todos los del reparto, con su ficha.")


class Escena(BaseModel):
    texto_voz: str = Field(description="Fragmento EXACTO y consecutivo del guion que se narra en esta escena.")
    plano_en: str = Field(description="Tipo de plano en inglés: extreme wide, wide, medium, medium close-up, close-up, macro, aerial, POV...")
    camara_en: str = Field(description="Movimiento de cámara en inglés: slow dolly-in, tracking shot, crane up, orbit, static, handheld push...")
    accion_en: str = Field(description="Qué se VE en inglés: sujeto (nombres de la biblia) + acción visible y concreta + lugar + composición.")
    personajes: list[str] = Field(default_factory=list, description="TODOS los nombres de la biblia que se ven en esta escena, "
                                                                     "aunque sea de espaldas, lejos o solo sus manos.")
    continua: bool = Field(default=False, description="true SOLO si este plano sigue al anterior sin corte: mismo sitio, mismo "
                                                      "personaje y la acción continúa. Casi siempre false.")
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
   Usa los nombres de la biblia para los personajes; no repitas su aspecto (se añade solo). Cada escena con un
   personaje muestra una postura y una acción distintas a la anterior: nunca «de pie mirando» dos veces seguidas.
5. Alterna planos (no dos close-ups seguidos) y elige un movimiento de cámara que sume emoción.
6. Nunca pidas texto, letras, logotipos, subtítulos ni pantallas divididas dentro de la imagen.
7. La biblia visual define lo que NO cambia entre escenas: escenario, luz, paleta y personajes con ficha exacta
   (identidad y ropa; nunca pose, gesto ni encuadre). Si te dan un REPARTO, cada ficha se traduce al inglés tal cual.
8. DIRECCIÓN DE VOZ: eres también director de locución. Para cada escena elige tono_voz y ritmo_voz según el
   arco (presentación → tensión → giro → clímax → cierre) y lo que se ve en el plano: misterio = intrigante o
   tenso y lento; revelación o acción = emocionante y rápido; plano épico o clímax = cinematografico; dato
   humano = intimo; cierre = solemne o triunfal. Varía: no repitas el mismo tono más de dos escenas seguidas.
9. VÍDEO O IMAGEN en Flow (tipo_clip): vídeo cuando hay acción, movimiento o emoción que se mueve (y siempre el
   gancho y el clímax); imagen en momentos descriptivos, datos, retratos o pausas (el montaje la anima con un
   movimiento de cámara suave). Intercala: nunca más de 2 imágenes seguidas, y que ninguno de los dos domine.
10. Si una frase es abstracta o difícil de ver, NO la cambies: búscale la mejor imagen posible y añádela a «avisos»
   con una sugerencia de reescritura. El guion lo ha aprobado una persona."""


def duracion_clip(segundos: float) -> int:
    """Segundos de clip a pedir en Flow para un trozo de voz: lo que dura, redondeado arriba, entre 4 y 8."""
    return min(config.SEGUNDOS_CLIP, max(4, math.ceil(segundos or 0)))


def _prompt_flow(esc: dict[str, Any], biblia: dict[str, Any], estilo: str, aspecto: str) -> str:
    """Prompt autosuficiente para pegar en Flow: plano + acción + biblia completa + estilo.
    Para imagen pide una foto fija (sin movimiento de cámara); para vídeo, un plano de los segundos que dura su voz
    (máximo 8), con la acción repartida en ese tiempo."""
    imagen = esc.get("tipo_clip") == "imagen"
    looks = {p["nombre"].upper(): _aspecto(p) for p in biblia.get("personajes", [])}
    salen = [n.upper() for n in esc.get("personajes", []) if n.upper() in looks]
    if not salen:   # Gemini olvidó apuntarlo: si la acción nombra o señala a alguien, va su ficha igualmente
        accion = f" {esc.get('accion_en', '')} ".lower()
        salen = [n for n in looks if n.lower() in accion]
        if not salen and len(looks) == 1 and re.search(r"\b(he|she|him|her|his|man|woman|boy|girl|guy|person|protagonist)\b", accion):
            salen = list(looks)
    if imagen:
        partes = [f"{esc['plano_en'].strip().capitalize()}. {esc['accion_en'].strip().rstrip('.')}."]
    else:
        partes = [f"{esc['plano_en'].strip().capitalize()}, {esc['camara_en'].strip()}. {esc['accion_en'].strip().rstrip('.')}."]
    if salen:
        partes.append("Characters (keep exactly the same face, hair and clothes in every shot): "
                      + "; ".join(f"{n} is {looks[n]}" for n in salen) + ".")
    partes.append(f"Setting: {biblia.get('escenario_en', '').strip().rstrip('.')}.")
    partes.append(f"Lighting: {biblia.get('luz_en', '').strip().rstrip('.')}. Palette: {biblia.get('paleta_en', '').strip().rstrip('.')}.")
    partes.append(f"Style: {estilo}.")
    if imagen:
        partes.append(f"Single still photograph, frozen moment, aspect ratio {aspecto}. No text, no letters.")
    else:
        n = duracion_clip(esc.get("segundos") or config.SEGUNDOS_CLIP)
        partes.append(f"Duration: one continuous {n}-second shot; the action fills the whole {n} seconds.")
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


def _aspecto(p: dict[str, Any]) -> str:
    """La ficha sin el nombre repetido delante («GUY: A man…» → «A man…»)."""
    return re.sub(rf"^\s*{re.escape(p['nombre'])}\s*[:\-–]\s*", "", p["aspecto_en"].strip(), flags=re.I).rstrip(".")


class Fichas(BaseModel):
    personajes: list[Personaje]


def afinar_personajes(guion: str, biblia: dict[str, Any], reparto: list[dict[str, str]] | None = None,
                      produccion: str = "") -> list[dict[str, Any]]:
    """Rehace solo las fichas de los personajes (más precisas, sin poses ni objetos en la mano) sin tocar las
    escenas: sirve para producciones que ya están en Flow."""
    actuales = "\n".join(f"- {p['nombre']}: {p['aspecto_en']}" for p in biblia.get("personajes", []))
    extra = ("\n\nREPARTO DEL GUIONISTA:\n" + "\n".join(f"- {r['nombre']}: {r['ficha']}" for r in reparto)) if reparto else ""
    crudo = gemini.generar(
        f"Personajes actuales (mismos nombres, en mayúsculas):\n{actuales}{extra}\n\n--- GUION ---\n{guion}\n--- FIN ---\n\n"
        "Reescribe la ficha visual de CADA personaje para que un generador de vídeo lo dibuje idéntico en todas las escenas, "
        f"{FICHA_VISUAL} No cambies a nadie: precisa lo que ya es.",
        esquema=Fichas, temperatura=0.3, detalle="afinar personajes", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    nuevas = {p.nombre.upper(): p.aspecto_en for p in Fichas.model_validate_json(m.group(0) if m else crudo).personajes}
    return [{**p, "aspecto_en": nuevas.get(p["nombre"].upper(), p["aspecto_en"])} for p in biblia.get("personajes", [])]


FICHA_VISUAL = ("en inglés, 40-70 palabras, SOLO aspecto: edad, origen, forma del rostro, pelo (color, largo, peinado), ojos, "
                "complexión, ropa exacta con colores y materiales, calzado y un detalle distintivo. Si el texto no da un rasgo, "
                "decídelo tú de forma concreta y coherente con el personaje. Prohibido: carácter o personalidad, pose, gesto, "
                "lugar u objetos en la mano.")


def personajes_de_reparto(reparto: list[dict[str, str]], guion: str = "", produccion: str = "") -> list[dict[str, Any]]:
    """La biblia de personajes sale del reparto del guion, completa (todos, no solo los del principio), con una
    ficha visual concreta por personaje. Así el vídeo entero usa las mismas caras."""
    lista = "\n".join(f"- {r['nombre']}: {r['ficha']}" for r in reparto)
    crudo = gemini.generar(
        f"REPARTO:\n{lista}\n\n--- GUION (contexto) ---\n{guion[:12000]}\n--- FIN ---\n\n"
        f"Escribe la ficha visual de CADA personaje del reparto, uno por uno y con su nombre corto en MAYÚSCULAS "
        f"(una palabra si se puede, p. ej. «MILLIE»): {FICHA_VISUAL}",
        esquema=Fichas, temperatura=0.3, detalle="fichas del reparto", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    return [{"nombre": p.nombre.strip().upper(), "aspecto_en": p.aspecto_en.strip()}
            for p in Fichas.model_validate_json(m.group(0) if m else crudo).personajes if p.nombre.strip()][:8]


def fichas(biblia: dict[str, Any], estilo: str) -> list[dict[str, str]]:
    """Un prompt por personaje para generar UNA vez su retrato de referencia en Flow y usarlo como ingrediente
    en cada escena: Flow mantiene la cara y la ropa sin copiar el plano (a diferencia de la imagen inicial)."""
    return [{"nombre": p["nombre"].upper(),
             "prompt": (f"Character reference portrait of {p['nombre'].upper()}: {_aspecto(p)}. "
                        f"Full body, front view, relaxed neutral stance, plain light grey studio background, soft even light. "
                        f"Style: {estilo}. Single still photograph. No text, no letters.")}
            for p in biblia.get("personajes", []) if p.get("nombre") and p.get("aspecto_en")]


def poner_duraciones(escenas: list[dict[str, Any]], tiempos: list[dict[str, Any]], biblia: dict[str, Any],
                     estilo_en: str, aspecto: str) -> None:
    """Con la voz ya grabada, cada escena sabe lo que dura de verdad: se apunta y su prompt pide ese tiempo
    (salvo que lo hayas editado a mano)."""
    for e, t in zip(escenas, tiempos):
        e["segundos"] = round(t["fin"] - t["ini"], 1)
        if not e.get("prompt_editado") and e.get("plano_en") and e.get("accion_en"):
            e["prompt_flow"] = _prompt_flow(e, biblia, estilo_en, aspecto)


def _palabras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


TRAMO_PALABRAS = 200   # guiones más largos se planifican por tramos: Gemini no se salta escenas


class PlanTramo(BaseModel):
    escenas: list[Escena]
    avisos: list[Aviso] = Field(default_factory=list)


def tramos(guion: str, n: int = TRAMO_PALABRAS) -> list[str]:
    """Trozos de unas `n` palabras que acaban en final de frase."""
    frases = re.split(r"(?<=[.!?…])\s+", guion.strip())
    salida, actual = [], []
    for f in frases:
        actual.append(f)
        if sum(len(x.split()) for x in actual) >= n:
            salida.append(" ".join(actual))
            actual = []
    if actual:
        if salida and sum(len(x.split()) for x in actual) < n // 3:
            salida[-1] += " " + " ".join(actual)   # un resto corto se une al último tramo
        else:
            salida.append(" ".join(actual))
    return salida


def _plan_tramo(base: str, guion: str, tramo: str, k: int, total: int, biblia: dict[str, Any], previa: dict[str, Any] | None,
                produccion: str) -> dict[str, Any]:
    """Escenas de un tramo con la biblia ya fijada (mismos personajes y mundo en todo el vídeo)."""
    prompt = (f"{base}\n\nBIBLIA FIJA (no la cambies; usa estos nombres de personaje):\n{json.dumps(biblia, ensure_ascii=False)}\n\n"
              f"--- GUION COMPLETO (solo contexto) ---\n{guion}\n--- FIN ---\n\n"
              f"Ahora reparte en escenas SOLO el TRAMO {k} de {total}, palabra por palabra (aquí «el guion» es este tramo):\n"
              f"--- TRAMO ---\n{tramo}\n--- FIN DEL TRAMO ---")
    if previa:
        prompt += f"\n\nLa escena anterior era: «{previa['texto_voz']}» ({previa.get('plano_en', '')}): no repitas su plano."
    for intento in range(2):
        crudo = gemini.generar(prompt, sistema=SISTEMA, esquema=PlanTramo, temperatura=0.4,
                               detalle=f"plan de escenas · tramo {k}/{total}", produccion=produccion)
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        parte = PlanTramo.model_validate_json(m.group(0) if m else crudo).model_dump()
        cubiertas = len(_palabras(" ".join(e["texto_voz"] for e in parte["escenas"])))
        if parte["escenas"] and cubiertas >= 0.9 * len(_palabras(tramo)):
            return parte
        logger.warning("Tramo %d: las escenas cubren %d de %d palabras; lo pido otra vez.", k, cubiertas, len(_palabras(tramo)))
    return parte


def _etiquetar(bloques: list[str], desde: int = 1) -> str:
    return "\n".join(f"[Clip {i}] {b}" for i, b in enumerate(bloques, desde))


def _tramos_de_bloques(bloques: list[str], n: int = TRAMO_PALABRAS) -> list[str]:
    """Guion largo por clips: tramos de ~n palabras que nunca parten un clip (la numeración sigue entre tramos)."""
    partes, actual, desde = [], [], 1
    for i, b in enumerate(bloques, 1):
        actual.append(b)
        if sum(len(x.split()) for x in actual) >= n:
            partes.append(_etiquetar(actual, desde))
            actual, desde = [], i + 1
    if actual:
        partes.append(_etiquetar(actual, desde))
    return partes


def _sin_etiqueta(texto: str) -> str:
    return re.sub(r"\[Clip \d+\]\s*", "", texto).strip()


def _ajustar_a_bloques(escenas: list[dict[str, Any]], bloques: list[str]) -> list[dict[str, Any]]:
    """Una escena por clip, pase lo que pase: si Gemini juntó o partió clips, cada bloque toma lo que se ve en la
    escena que cubre su mitad (y si repite escena, continúa el mismo plano)."""
    if len(escenas) == len(bloques):
        return [{**e, "texto_voz": b} for e, b in zip(escenas, bloques)]
    total_e = sum(len(_sin_etiqueta(e["texto_voz"]).split()) for e in escenas) or 1
    total_b = sum(len(b.split()) for b in bloques) or 1
    limites, acum = [], 0
    for e in escenas:
        acum += len(_sin_etiqueta(e["texto_voz"]).split())
        limites.append(acum)
    salida, previa, pos = [], -1, 0
    for b in bloques:
        mitad = (pos + len(b.split()) / 2) * total_e / total_b
        k = next((i for i, lim in enumerate(limites) if mitad <= lim), len(escenas) - 1)
        salida.append({**escenas[k], "texto_voz": b, "continua": k == previa})
        previa, pos = k, pos + len(b.split())
    return salida


def planificar(guion: str, estilo: str, formato: str, produccion: str = "",
               titulos_existentes: list[str] | None = None, referencias_visuales: list[str] | None = None,
               reparto: list[dict[str, str]] | None = None, bloques: list[str] | None = None,
               publico: str = "") -> dict[str, Any]:
    """Con `bloques` (guion por clips de Flow), una escena exacta por bloque: Gemini decide lo que se ve."""
    estilo_en = config.ESTILOS.get(estilo, estilo)
    aspecto = config.FORMATOS[formato]["aspecto"]
    texto = _etiquetar(bloques) if bloques else guion
    prompt = (
        f"ESTILO VISUAL: {estilo_en}\nFORMATO: {aspecto} "
        f"({'sujeto centrado y alto' if aspecto == '9:16' else 'deja aire a los lados'})\n\n"
        f"--- GUION ---\n{texto}\n--- FIN ---"
    )
    if bloques:
        prompt += (f"\n\nEL GUION VIENE EN {len(bloques)} CLIPS DE {config.SEGUNDOS_CLIP} s ([Clip n]). Devuelve EXACTAMENTE una "
                   "escena por clip, en orden, sin juntar ni partir clips; texto_voz = el texto del clip tal cual, sin la etiqueta.")
    fijos = personajes_de_reparto(reparto, guion, produccion) if reparto else []
    if fijos:
        prompt += ("\n\nPERSONAJES FIJOS (copia esta lista tal cual en biblia.personajes y usa estos nombres en las escenas):\n"
                   + "\n".join(f"- {p['nombre']}: {p['aspecto_en']}" for p in fijos))
    if referencias_visuales:
        prompt += ("\n\nFOTOS DE REFERENCIA DEL AUTOR: copia en la biblia la IDENTIDAD (rostro, pelo, edad, complexión, ropa) "
                   "de las personas y el aspecto de lugares y objetos. NUNCA copies su pose, gesto ni encuadre: cada escena "
                   "tiene su propio plano.\n" + "\n".join(f"- Foto {i}: {d}" for i, d in enumerate(referencias_visuales, 1)))
    if publico and publico != "todos":   # el título, la descripción y los hashtags, pensados para ese público
        prompt += f"\n\nPÚBLICO: {publico}. Escribe el título, la descripción y los hashtags para él."
    if titulos_existentes:
        prompt += ("\n\nTÍTULOS QUE YA EXISTEN EN YOUTUBE SOBRE ESTO (el tuyo tiene que ser claramente distinto, "
                   "con otro ángulo o un detalle concreto del guion):\n" + "\n".join(f"- {t}" for t in titulos_existentes[:8]))
    partes = _tramos_de_bloques(bloques) if bloques else tramos(guion)
    if len(partes) > 1:   # guion largo: el primer tramo fija título y biblia; los demás la respetan
        prompt = prompt.replace(f"--- GUION ---\n{texto}\n--- FIN ---",
                                f"--- GUION COMPLETO (contexto para título y biblia) ---\n{guion}\n--- FIN ---\n\n"
                                f"Reparte en escenas SOLO el TRAMO 1 de {len(partes)} (aquí «el guion» es este tramo):\n"
                                f"--- TRAMO ---\n{partes[0]}\n--- FIN DEL TRAMO ---")
    crudo = gemini.generar(prompt, sistema=SISTEMA, esquema=Plan, temperatura=0.4,
                           detalle="plan de escenas" + (f" · tramo 1/{len(partes)}" if len(partes) > 1 else ""),
                           produccion=produccion)
    match = re.search(r"\{.*\}", crudo, re.DOTALL)
    plan = Plan.model_validate_json(match.group(0) if match else crudo).model_dump()
    if fijos:   # el reparto manda: todos los personajes, con su ficha exacta, aunque Gemini haya omitido alguno
        plan["biblia"]["personajes"] = fijos
    base = (f"ESTILO VISUAL: {estilo_en}\nFORMATO: {aspecto} "
            f"({'sujeto centrado y alto' if aspecto == '9:16' else 'deja aire a los lados'})")
    for k, tramo in enumerate(partes[1:], start=2):
        parte = _plan_tramo(base, guion, tramo, k, len(partes), plan["biblia"],
                            plan["escenas"][-1] if plan["escenas"] else None, produccion)
        plan["escenas"] += parte["escenas"]
        plan["avisos"] += parte.get("avisos", [])

    if not plan["escenas"]:
        raise RuntimeError("Gemini no devolvió escenas.")
    for e in plan["escenas"]:
        e["texto_voz"] = _sin_etiqueta(e["texto_voz"])
    if bloques:
        plan["escenas"] = _ajustar_a_bloques(plan["escenas"], bloques)
    if _palabras(" ".join(e["texto_voz"] for e in plan["escenas"])) != _palabras(guion):
        # La voz lee las escenas, no el guion original: así la sincronía con los clips siempre cuadra.
        logger.warning("Las escenas no reproducen el guion palabra por palabra; la narración será la de las escenas.")

    _intercalar(plan["escenas"])
    for i, esc in enumerate(plan["escenas"], start=1):
        esc["orden"] = i
        esc["segundos"] = round(len(esc["texto_voz"].split()) / PALABRAS_POR_SEGUNDO, 1)   # se afina al grabar la voz
        esc["prompt_flow"] = _prompt_flow(esc, plan["biblia"], estilo_en, aspecto)
        n = len(esc["texto_voz"].split())
        if n > PALABRAS_MAX_ESCENA + 4:
            logger.warning("Escena %d tiene %d palabras: el clip irá a cámara lenta.", i, n)
    plan["estilo_en"] = estilo_en
    return plan
