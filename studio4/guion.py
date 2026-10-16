"""Fase 1 · Guion: DeepSeek escribe a partir de la investigación. Corto (Shorts y Reels) y largo (YouTube)
salen de la misma investigación pero son guiones distintos: otro ritmo, otra estructura, otro cierre.

Sin DEEPSEEK_API_KEY escribe Gemini con las mismas reglas, para que STUDIO nunca se quede parado."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import deepseek, gemini

logger = logging.getLogger("studio4.guion")

PALABRAS_POR_SEGUNDO = 2.25  # medido con Gemini TTS dirigida (372 palabras → 166 s; sin dirección, 2,3)
DESVIO_MAXIMO = 0.15         # si el guion se aparta más que esto de lo pedido, se ajusta con otra pasada

PROHIBIDO = [
    "Imagina", "¿Sabías que", "En un mundo", "sumérgete", "adentrémonos", "fascinante", "increíble", "asombroso",
    "descubre", "el secreto", "no creerás", "en este vídeo", "hoy te cuento", "acompáñame", "pero eso no es todo",
    "al final del día", "y aquí viene lo interesante", "y es que", "cabe destacar", "sin lugar a dudas",
    "en conclusión", "¿y tú qué opinas?", "prepárate", "este viaje", "un viaje a través", "misterio sin resolver",
]

SISTEMA = f"""Eres guionista de documentales y de vídeos de divulgación en español neutro, con voz propia.
Escribes SOLO lo que dirá la voz en off: sin acotaciones, corchetes, títulos, emojis ni Markdown.

VERDAD Y DETALLE
- Todo sale del dossier de investigación. Usa cifras, nombres, lugares y fechas concretas.
- Lo que el dossier marca como dudoso no se afirma. No inventes nada.

QUE NO SUENE A IA
- Prohibido: {", ".join(f"«{p}»" for p in PROHIBIDO)}.
- Nada de tríos de adjetivos, nada de moralejas, nada de preguntas retóricas de relleno.
- Habla como alguien que se lo cuenta a un amigo listo: frases de largo variado, muchas cortas
  (5-12 palabras), alguna larga; verbos concretos; una idea por frase.
- Antes de entregar, relee y reescribe cualquier frase genérica, de folleto o que podría estar en cualquier vídeo.

EL ESPECTADOR NO SABE NADA
- No des por conocido a nadie ni nada. La primera vez que aparece una persona, un lugar, un juego o un hecho,
  di en pocas palabras quién o qué es y por qué importa (p. ej. «Bonnie Parker, la mitad de Bonnie y Clyde, la
  pareja de atracadores más buscada de Estados Unidos en 1933»). El gancho puede abrir con el hecho fuerte, pero
  la frase siguiente presenta a quien sale en él.
- Escribe para alguien de 16 años que nunca ha oído hablar del tema: si sin contexto no entendería una frase,
  añade el contexto o cámbiala.

HECHO PARA VÍDEO
- La primera frase (máx. 14 palabras) engancha con un hecho concreto o una escena, nunca con una pregunta genérica.
- Cada frase tiene que poder MOSTRARSE en un plano de 8 segundos: personas, objetos, lugares, acciones.
- Abre preguntas y ciérralas más tarde para que nadie se vaya.

CORTO (Shorts y Reels): UNA historia verdadera y COMPLETA, aunque dure un minuto. En orden:
  1. quién y dónde (una frase de contexto con nombre, lugar y fecha),
  2. qué pasó: los hechos clave en secuencia, cada uno consecuencia del anterior,
  3. el giro o la revelación,
  4. qué significa ahora: un cierre que reencuadra la primera frase.
  Cada frase se engancha a la anterior por causa o por tiempo (entonces, por eso, pero, años después):
  nunca una lista de datos sueltos. Quien lo vea sin saber nada del tema tiene que entender la historia entera.
  Si el tema une dos mundos (un hecho real y un juego, una película o una marca), cuenta primero la historia
  real completa y después la conexión, explicando qué se tomó y qué cambió. Sin introducción; tensión
  constante; como mucho UNA frase final de llamada a la acción, natural.
REPARTO (no se narra): para cada persona o personaje que aparece en la historia, escribe su ficha visual para
que el vídeo la dibuje SIEMPRE igual: edad aproximada, origen, rostro, pelo (color, largo, peinado), ojos,
complexión, ropa exacta con colores y materiales, y un detalle distintivo. 40 a 70 palabras cada una, sin
adjetivos vagos («normal», «guapo»). Si es una persona real, su aspecto real en la época de la historia.

LARGO (YouTube): 4-6 bloques con un mini-gancho al empezar cada bloque, una historia o caso real como hilo,
contexto, giro y cierre que conecte con el principio; termina invitando a un tema relacionado. Sin títulos.

Devuelve JSON: {{"titulo_provisional": "...", "reparto": [{{"nombre": "...", "ficha": "..."}}],
"<versión>": {{"guion": "...", "ganchos": ["...", "...", "..."]}}}}
donde "ganchos" son 3 primeras frases alternativas (distintas de la que usaste)."""


def _peticion(idea: str, dossier: str, versiones: dict[str, int], tono: str = "", publico: str = "",
              youtube: dict[str, Any] | None = None, referencias: str = "", manual: str = "") -> str:
    partes = [f"Tema: {idea}"]
    if manual:   # cómo cuentan los vídeos que funcionan en el nicho: manda sobre el estilo genérico
        partes += ["", manual, ""]
    if tono:
        partes.append(f"Tono: {tono}")
    if publico:
        partes.append(f"Público: {publico}")
    yt = youtube or {}
    if yt.get("competencia"):
        partes += ["", "LO QUE YA HAY EN YOUTUBE SOBRE ESTO (no lo repitas: busca un ángulo, un dato o una historia que ellos no cuenten):"]
        partes += [f"- «{v['titulo']}» ({v['canal']}, {v['vistas']:,} vistas)".replace(",", ".") for v in yt["competencia"][:8]]
    if (yt.get("tu_canal") or {}).get("mas_vistos"):
        partes += ["", f"LOS VÍDEOS QUE MEJOR FUNCIONAN EN EL CANAL «{yt['tu_canal']['nombre']}» (su público responde a este tono y estos temas):"]
        partes += [f"- «{v['titulo']}» ({v['vistas']:,} vistas)".replace(",", ".") for v in yt["tu_canal"]["mas_vistos"][:8]]
    if yt.get("tendencias"):
        t = yt["tendencias"]
        partes += ["", f"LO QUE FUNCIONA HOY EN YOUTUBE, SHORTS Y REELS (tendencias del {t['fecha']}; úsalo para el ritmo y el gancho, no para cambiar el tema):",
                   f"- Corto: {t['duracion_corto']}", f"- Largo: {t['duracion_largo']}", f"- Títulos: {t['titulos']}"]
        partes += [f"- {c}" for c in t["consejos"]] + [f"- Evita: {e}" for e in t["evitar"]]
    if referencias:
        partes += ["", "--- MATERIAL QUE APORTA EL AUTOR (prioritario: úsalo; si choca con la investigación, manda esto) ---",
                   referencias, "--- FIN DEL MATERIAL ---"]
    partes += ["", "--- DOSSIER DE INVESTIGACIÓN ---", dossier or "(sin investigación: usa solo hechos muy conocidos)",
              "--- FIN DEL DOSSIER ---", "", "Escribe estas versiones:"]
    for v, seg in versiones.items():
        nombre = "CORTO (Shorts y Reels, vertical)" if v == "corto" else "LARGO (YouTube, horizontal)"
        partes.append(f"- \"{v}\": {nombre}, {seg} segundos: {int(seg * PALABRAS_POR_SEGUNDO)} palabras (±10 %; "
                      f"si te quedas corto, la voz no llena el vídeo).")
    return "\n".join(partes)


def completar(borrador: str, idea: str, dossier: str, segundos: int, produccion: str = "", tono: str = "",
              referencias: str = "", manual: str = "") -> dict[str, Any]:
    """Un guion del autor que se queda corto: con la investigación se convierte en la historia verdadera y completa,
    conservando su ángulo, su tono y sus mejores frases. Devuelve {"titulo_provisional", "reparto", "guion", "autor"}."""
    objetivo = int(segundos * PALABRAS_POR_SEGUNDO)
    prompt = "\n".join([
        f"Tema: {idea}", f"Tono: {tono}" if tono else "", manual,
        "", "--- GUION DEL AUTOR (punto de partida: respeta su ángulo, su tono y sus frases buenas) ---", borrador,
        "--- FIN DEL GUION DEL AUTOR ---",
        "", f"Es demasiado corto o le faltan pasos de la historia. Con el dossier, conviértelo en la historia verdadera y "
            f"completa (contexto, hechos en orden, giro, cierre), de {objetivo} palabras (±10 %). Añade solo hechos del "
            "dossier; donde el autor afirme algo que el dossier contradice, manda el dossier.",
        "" if not referencias else f"\n--- MATERIAL QUE APORTA EL AUTOR ---\n{referencias}\n--- FIN DEL MATERIAL ---",
        "", "--- DOSSIER DE INVESTIGACIÓN ---", dossier or "(sin investigación: usa solo hechos muy conocidos)",
        "--- FIN DEL DOSSIER ---",
        "", 'Devuelve JSON: {"titulo_provisional": "...", "reparto": [{"nombre": "...", "ficha": "..."}], "guion": "..."}'])
    datos = None
    if deepseek.disponible():
        try:
            datos, autor = deepseek.generar_json(SISTEMA, prompt, detalle="guion completado", produccion=produccion), "DeepSeek"
        except RuntimeError as e:
            logger.warning("%s: el guion lo completa Gemini.", e)
    if datos is None:
        crudo = gemini.generar(prompt + "\n\nResponde solo con el JSON.", sistema=SISTEMA, temperatura=0.8,
                               detalle="guion completado (reserva)", produccion=produccion)
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        datos, autor = json.loads(m.group(0) if m else crudo), "Gemini"
    texto = _limpiar(str(datos.get("guion", "")))
    if len(texto.split()) < len(borrador.split()):
        raise RuntimeError(f"{autor} no devolvió el guion completado. Vuelve a intentarlo.")
    return {"titulo_provisional": str(datos.get("titulo_provisional", "")).strip(), "autor": autor,
            "guion": _ajustar_largo(texto, objetivo, produccion),
            "reparto": [{"nombre": str(r.get("nombre", "")).strip()[:40], "ficha": str(r.get("ficha", "")).strip()[:600]}
                        for r in datos.get("reparto") or [] if isinstance(r, dict) and r.get("nombre")][:4]}


def corto_de_mas(texto: str, segundos: int) -> bool:
    """¿El guion pegado no llega a contar la historia? (menos del 70 % de las palabras que pide su duración)."""
    return len(texto.split()) < 0.7 * segundos * PALABRAS_POR_SEGUNDO


def _limpiar(texto: str) -> str:
    texto = re.sub(r"\[[^\]]*\]|\([^)]*(?:pausa|música|sonido)[^)]*\)", "", texto, flags=re.I)  # acotaciones
    texto = texto.replace("*", "").replace("#", "")
    return " ".join(texto.split())


def escribir(idea: str, dossier: str, versiones: dict[str, int], produccion: str = "", tono: str = "",
             publico: str = "", youtube: dict[str, Any] | None = None, referencias: str = "", manual: str = "") -> dict[str, Any]:
    """Devuelve {"titulo_provisional", "autor", "<versión>": {"guion", "ganchos"}} para cada versión pedida."""
    prompt = _peticion(idea, dossier, versiones, tono, publico, youtube, referencias, manual)
    datos = None
    if deepseek.disponible():
        try:
            datos, autor = deepseek.generar_json(SISTEMA, prompt, detalle="guion", produccion=produccion), "DeepSeek"
        except RuntimeError as e:   # DeepSeek caído o sin espacio: Gemini (gratis) escribe para no dejarte sin guion
            logger.warning("%s: el guion lo escribe Gemini.", e)
    else:
        logger.warning("Sin DEEPSEEK_API_KEY: el guion lo escribe Gemini.")
    if datos is None:
        crudo = gemini.generar(prompt + "\n\nResponde solo con el JSON.", sistema=SISTEMA, temperatura=0.9,
                               detalle="guion (reserva)", produccion=produccion)
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        datos, autor = json.loads(m.group(0) if m else crudo), "Gemini"

    salida: dict[str, Any] = {"titulo_provisional": str(datos.get("titulo_provisional", "")).strip(), "autor": autor,
                              "reparto": [{"nombre": str(r.get("nombre", "")).strip()[:40], "ficha": str(r.get("ficha", "")).strip()[:600]}
                                          for r in datos.get("reparto") or [] if isinstance(r, dict) and r.get("nombre")][:4]}
    for v, seg in versiones.items():
        bloque = datos.get(v) or {}
        texto = _limpiar(str(bloque.get("guion", "")))
        if len(texto.split()) < 15:
            raise RuntimeError(f"{autor} no devolvió el guion {v}. Vuelve a intentarlo.")
        texto = _ajustar_largo(texto, int(seg * PALABRAS_POR_SEGUNDO), produccion)
        salida[v] = {"guion": texto, "ganchos": [_limpiar(str(g)) for g in bloque.get("ganchos", [])][:3]}
    return salida


def _ajustar_largo(texto: str, objetivo: int, produccion: str) -> str:
    """Si el guion se pasa o se queda corto (más de un 15 %), una pasada lo lleva a la longitud pedida
    sin perder datos ni estilo. Así la voz dura lo que elegiste en el asistente."""
    n = len(texto.split())
    if abs(n - objetivo) <= objetivo * DESVIO_MAXIMO:
        return texto
    accion = "Acórtalo" if n > objetivo else "Alárgalo con datos del mismo tema (sin inventar)"
    sistema = "Eres editor de guiones de vídeo. Devuelve JSON: {\"guion\": \"...\"}. Mismo estilo, mismas reglas, sin acotaciones."
    prompt = (f"{accion} a {objetivo} palabras (ahora tiene {n}). Conserva el gancho, los datos concretos y el cierre.\n\n{texto}")
    try:
        if deepseek.disponible():
            nuevo = deepseek.generar_json(sistema, prompt, temperatura=0.4, detalle="ajuste de largo", produccion=produccion)
        else:
            crudo = gemini.generar(prompt + "\n\nResponde solo con el JSON.", sistema=sistema, temperatura=0.4,
                                   detalle="ajuste de largo", produccion=produccion)
            m = re.search(r"\{.*\}", crudo, re.DOTALL)
            nuevo = json.loads(m.group(0) if m else crudo)
        ajustado = _limpiar(str(nuevo.get("guion", "")))
    except Exception as e:  # noqa: BLE001 - si el ajuste falla, el guion original sigue valiendo
        logger.warning("No se pudo ajustar el largo del guion: %s", e)
        return texto
    # Solo se acepta si de verdad se acerca a lo pedido.
    return ajustado if abs(len(ajustado.split()) - objetivo) < abs(n - objetivo) else texto


def frases_prohibidas(texto: str) -> list[str]:
    """Lo que aún suena a IA en un guion (se muestra en el panel para que lo corrijas si quieres)."""
    bajo = texto.lower()
    return [p for p in PROHIBIDO if p.lower() in bajo]
