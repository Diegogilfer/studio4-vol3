"""Estilos de producción: la ficha que la IA sigue en TODO el vídeo, no solo en las imágenes. Cada estilo dice cómo
se escribe el guion, qué prompt visual llevan las imágenes y vídeos generados, cómo se monta (ritmo, transición,
música, subtítulos), cuántas escenas se animan como mucho y qué modelo conviene para crear (con su coste).

Los modelos recomendados son los que mejor suelen rendir en cada estética (octubre de 2026); cambian rápido, así que
se revisan aquí. «Mundo abierto» es una estética propia inspirada en portadas de juegos de acción: nunca logos,
personajes ni arte de ningún juego real.
"""

from __future__ import annotations

from typing import Any

ESTILOS: dict[str, dict[str, Any]] = {
    "gameplay": {
        "nombre": "Gameplay real", "para": "Noticias y curiosidades de juegos con material oficial (FourLevel)",
        "visual": "", "genera": False,
        "guion": "narración informativa y emocionante sobre lo que se ve en pantalla; cada frase con su plano real",
        "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "acción", "subtitulos": "viral"},
        "imagen": "No genera: tráilers oficiales y gameplay sin comentario", "video": "No genera",
        "coste": "gratis", "animar": 0},
    "cinematografico": {
        "nombre": "Cinematográfico", "para": "Historias épicas y dramáticas con imagen de película",
        "visual": "cinematic live-action, anamorphic 35mm lens, shallow depth of field, film grain, natural color grading",
        "guion": "narración pausada con tensión creciente; frases cortas en los momentos clave",
        "montaje": {"ritmo": "medio", "transicion": "fundido", "musica": "épica", "subtitulos": "cine"},
        "imagen": "Imagen 4 (Google) o Nano Banana Pro", "video": "Veo 3.1 (Standard para clímax, Fast para el resto)",
        "coste": "alto", "animar": 3},
    "documental": {
        "nombre": "Documental", "para": "Misterios, historia y divulgación (ARIGAB)",
        "visual": "documentary realism, archival photograph feel, natural light, authentic textures, muted earthy palette",
        "guion": "tono sereno y riguroso; separa lo comprobado de la leyenda; dato concreto en cada frase",
        "montaje": {"ritmo": "lento", "transicion": "fundido", "musica": "misterio", "subtitulos": "cine"},
        "imagen": "Nano Banana (barato y fiel al prompt) o Imagen 4 para fotorrealismo",
        "video": "Veo 3.1 Lite/Fast solo en 1-2 escenas clímax; el resto, imagen con movimiento lento",
        "coste": "bajo", "animar": 2},
    "hiperrealista": {
        "nombre": "Hiperrealista", "para": "Productos, lugares y recreaciones que deben parecer fotos",
        "visual": "hyperrealistic, photorealistic 8K detail, true-to-life skin and materials, natural lighting, no stylization",
        "guion": "descriptivo y concreto; enseña detalles", "montaje": {"ritmo": "medio", "transicion": "corte", "musica": "inspiradora", "subtitulos": "viral"},
        "imagen": "Imagen 4 (Google)", "video": "Veo 3.1 Standard", "coste": "alto", "animar": 2},
    "mundo_abierto": {
        "nombre": "Mundo abierto", "para": "Historias de acción y crimen con estética de portada de videojuego",
        "visual": ("open-world action video game cover art style, painted illustration, bold saturated colors, sunset "
                   "palm-lined city, neon signs, dramatic character poses, loading-screen artwork look, original "
                   "characters, no logos, no text"),
        "guion": "ritmo rápido, frases con gancho, tono de acción y algo de humor",
        "montaje": {"ritmo": "rapido", "transicion": "rejilla", "musica": "acción", "subtitulos": "viral"},
        "imagen": "Nano Banana Pro (mantiene a los personajes entre escenas) o Flux para el acabado pintado",
        "video": "Kling (movimiento de acción) o Veo 3.1 Fast", "coste": "medio", "animar": 3},
    "animacion3d": {
        "nombre": "Animación 3D", "para": "Cuentos, novelas y personajes entrañables",
        "visual": "high-end 3D animated film, soft global illumination, expressive characters, rich materials",
        "guion": "historia con personajes fijos, emoción y giro final; diálogos breves",
        "montaje": {"ritmo": "medio", "transicion": "fundido", "musica": "emotiva", "subtitulos": "viral"},
        "imagen": "Nano Banana Pro con ficha de personaje (misma cara en todas las escenas)",
        "video": "Kling (el mejor en personajes animados) o Veo 3.1 Fast", "coste": "medio", "animar": 4},
    "anime": {
        "nombre": "Anime", "para": "Historias juveniles, acción y fantasía",
        "visual": "high-quality anime, cel shading, vibrant colors, detailed backgrounds, Studio-style lighting",
        "guion": "intensidad emocional, monólogo interior, momentos épicos", "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "épica", "subtitulos": "viral"},
        "imagen": "Flux o Nano Banana con estilo anime", "video": "Kling o Seedance", "coste": "medio", "animar": 3},
    "cartoon": {
        "nombre": "Dibujo animado 2D", "para": "Humor, explicaciones sencillas, público familiar",
        "visual": "2D cartoon animation, bold clean outlines, flat vibrant colors, exaggerated expressive characters",
        "guion": "humor ligero, frases cortas, exageración", "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "alegre", "subtitulos": "viral"},
        "imagen": "Nano Banana", "video": "Kling", "coste": "medio", "animar": 3},
    "stickman": {
        "nombre": "Stickman", "para": "Explicaciones, listas y psicología: barato y muy claro",
        "visual": "minimalist stick figure animation, simple black line characters on a plain white background, clean doodle style",
        "guion": "explicativo, un concepto por frase, ejemplos cotidianos",
        "montaje": {"ritmo": "medio", "transicion": "corte", "musica": "tranquila", "subtitulos": "viral"},
        "imagen": "Nano Banana (barato) — o sin IA: animación propia del estudio, gratis",
        "video": "No hace falta: el movimiento lo pone el montaje", "coste": "bajo", "animar": 0},
    "comic": {
        "nombre": "Cómic", "para": "Leyendas, héroes y relatos por viñetas",
        "visual": "comic book style, bold ink lines, halftone dots, dramatic panels, saturated colors",
        "guion": "narrador de viñeta, frases rotundas, onomatopeyas con moderación", "montaje": {"ritmo": "medio", "transicion": "rejilla", "musica": "épica", "subtitulos": "viral"},
        "imagen": "Ideogram (si hay texto dentro de la imagen) o Flux", "video": "Kling", "coste": "medio", "animar": 2},
    "noir": {
        "nombre": "Noir", "para": "Crímenes, casos reales y suspense",
        "visual": "neo-noir, high-contrast low-key lighting, deep shadows, wet streets, teal and amber palette",
        "guion": "voz grave en primera persona de investigador, pistas, giro", "montaje": {"ritmo": "lento", "transicion": "fundido", "musica": "tensión", "subtitulos": "cine"},
        "imagen": "Imagen 4 o Nano Banana Pro", "video": "Veo 3.1 Fast", "coste": "medio", "animar": 2},
    "pixelart": {
        "nombre": "Pixel art", "para": "Retro gaming y curiosidades de juegos antiguos",
        "visual": "retro pixel art, 16-bit video game style, limited color palette, crisp pixels",
        "guion": "nostálgico y divertido", "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "alegre", "subtitulos": "viral"},
        "imagen": "Flux o Nano Banana", "video": "No hace falta (movimiento en montaje)", "coste": "bajo", "animar": 0},
    "stopmotion": {
        "nombre": "Plastilina", "para": "Historias tiernas o absurdas con aire artesanal",
        "visual": "claymation stop-motion, handmade plasticine characters, miniature sets, tactile textures",
        "guion": "ritmo de cuento, humor tierno", "montaje": {"ritmo": "medio", "transicion": "corte", "musica": "alegre", "subtitulos": "viral"},
        "imagen": "Nano Banana Pro", "video": "Kling", "coste": "medio", "animar": 3},
    "scifi": {
        "nombre": "Ciencia ficción", "para": "Futuro, espacio y tecnología",
        "visual": "epic science fiction, volumetric light, atmospheric haze, futuristic production design",
        "guion": "asombro y escala, datos científicos reales cuando los haya", "montaje": {"ritmo": "medio", "transicion": "fundido", "musica": "épica", "subtitulos": "cine"},
        "imagen": "Imagen 4", "video": "Veo 3.1", "coste": "alto", "animar": 3},
}
# estilos que Claude hace con CÓDIGO (SVG/HTML animado que renderiza el estudio, o edición de material real): gratis
ESTILOS.update({
    "motion": {
        "nombre": "Motion graphics", "para": "Datos, listas, comparativas, rankings y explicaciones con cifras",
        "visual": "", "genera": False,
        "guion": "un dato o idea por frase, con cifras concretas que se puedan enseñar en pantalla",
        "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "inspiradora", "subtitulos": "viral"},
        "imagen": "Lo hace Claude con código (gráficos, iconos, mapas, líneas de tiempo)", "video": "No hace falta",
        "coste": "gratis", "animar": 0},
    "tipografia": {
        "nombre": "Tipografía cinética", "para": "Frases potentes, motivación, citas y Shorts de impacto",
        "visual": "", "genera": False,
        "guion": "frases cortas y rotundas, pensadas para leerse grandes en pantalla",
        "montaje": {"ritmo": "rapido", "transicion": "corte", "musica": "épica", "subtitulos": "viral"},
        "imagen": "Lo hace Claude con código (texto animado al ritmo de la voz)", "video": "No hace falta",
        "coste": "gratis", "animar": 0},
    "vectorial": {
        "nombre": "Dibujo vectorial", "para": "Personajes y escenas sencillas de formas limpias (explicativos, cuentos)",
        "visual": "", "genera": False,
        "guion": "narración clara, escenas simples, un personaje protagonista",
        "montaje": {"ritmo": "medio", "transicion": "corte", "musica": "alegre", "subtitulos": "viral"},
        "imagen": "Lo hace Claude con código (ilustración plana original)", "video": "No hace falta",
        "coste": "gratis", "animar": 0},
    "collage": {
        "nombre": "Collage documental", "para": "Historia y misterios con fotos de archivo, mapas y documentos reales",
        "visual": "", "genera": False,
        "guion": "tono de expediente; cada frase enseña una prueba (foto, mapa, documento)",
        "montaje": {"ritmo": "lento", "transicion": "fundido", "musica": "misterio", "subtitulos": "cine"},
        "imagen": "Lo hace Claude: material real de archivo con movimiento lento y rótulos", "video": "No hace falta",
        "coste": "gratis", "animar": 0},
})
HECHO_POR_CLAUDE = {"gameplay", "stickman", "pixelart", "motion", "tipografia", "vectorial", "collage"}
for _k, _e in ESTILOS.items():
    _e["hecho_por"] = "claude" if _k in HECHO_POR_CLAUDE else "modelo"
POR_DEFECTO = "documental"


def valido(estilo: str | None, canal: dict[str, Any] | None = None) -> str:
    """El estilo pedido; si no vale, el del canal; si tampoco, el de por defecto."""
    if estilo in ESTILOS:
        return str(estilo)
    if canal and canal.get("estilo") in ESTILOS:
        return str(canal["estilo"])
    return POR_DEFECTO


def para_guion(estilo: str) -> str:
    e = ESTILOS[valido(estilo)]
    return f"Estilo de producción «{e['nombre']}»: {e['guion']}."


def catalogo() -> list[dict[str, Any]]:
    """Para el panel: nombre, para qué sirve, modelos recomendados, coste y cuántas escenas se animan."""
    return [{"id": k, "nombre": e["nombre"], "para": e["para"], "imagen": e["imagen"], "video": e["video"],
             "coste": e["coste"], "animar": e["animar"], "hecho_por": e["hecho_por"]}
            for k, e in sorted(ESTILOS.items(), key=lambda kv: kv[1]["hecho_por"] != "claude")]
