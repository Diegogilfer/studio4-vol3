"""Fase 1 · Guion: Gemini escribe la narración completa (solo lo que dice la voz)."""

from __future__ import annotations

from . import gemini

PALABRAS_POR_SEGUNDO = 2.4  # locución en español a ritmo de vídeo corto

SISTEMA = """Eres guionista de vídeos cortos de máxima retención en español neutro.
Escribes SOLO el texto que leerá la voz en off, de corrido.

1. Gancho en la primera frase (sin saludos ni "en este vídeo"): una afirmación que choque, una pregunta
   imposible de ignorar o una imagen mental potente.
2. Tensión creciente: cada frase abre una pregunta que la siguiente responde a medias.
3. Frases cortas y visuales: todo lo que se dice tiene que poder MOSTRARSE en un plano de vídeo.
4. Cierre con un giro o una idea que se quede, y una llamada a la acción breve y natural.
5. Nada de acotaciones, corchetes, emojis, títulos, viñetas ni Markdown. Solo la narración."""


def escribir(tema: str, segundos: int, produccion: str = "") -> str:
    palabras = int(segundos * PALABRAS_POR_SEGUNDO)
    prompt = (
        f"Tema: {tema}\n\n"
        f"Duración: {segundos} segundos, unas {palabras} palabras (no te pases: la voz debe caber en ese tiempo)."
    )
    texto = gemini.generar(prompt, sistema=SISTEMA, temperatura=0.8, detalle="guion", produccion=produccion)
    return " ".join(texto.split())
