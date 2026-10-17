"""La metodología de guion del estudio, en un solo sitio.

La usan todos los que escriben: DeepSeek, Gemini, la reserva y cualquier modelo de lenguaje que se conecte
después (dentro de Studio 4 entra en el sistema del guionista), y el asistente por chat (PROMPTS_AGRON.md
copia estas mismas reglas; una prueba comprueba que no se separen). Si cambias una regla, cámbiala aquí."""

from __future__ import annotations

IDIOMA = 'Español latino neutro: "ustedes", nunca "vosotros". Narrador en primera persona, cercano, con datos.'

VERDAD = [
    "Solo datos verificables (gtabase.com para GTA, Wikipedia, webs oficiales de cada juego o estudio). "
    "Lo no confirmado se dice como rumor.",
    "Que la investigación no traiga un dato no significa que no exista: cuenta lo que sí está confirmado y nunca "
    "concluyas que «no hay nada».",
    "Primera persona sí, experiencias inventadas no: nada de «llevo semanas buscando» ni «lo probé» si no es verdad.",
    "Nunca menciones a otros youtubers ni canales, ni copies frases de otros vídeos.",
    "Nada de emojis dentro de los guiones.",
]

FORMA = [
    "Primera frase con un dato fuerte; cada nombre que el público no conozca se presenta.",
    "Frases cortas (cada ~18 palabras se muestra con una captura de 8 segundos).",
]

LARGO = ('LARGO: bloques anunciados, conectores ("además", "según Rockstar"), cierre con balance y una pregunta '
         "concreta para comentar.")

CORTO = ("CORTO: trata una sola cosa, con su propio gancho, contada completa para quien no sabe nada; si hay un "
         "vídeo largo del tema, termina invitando a verlo.")

CONTROL = [
    "Datos verificables; lo no confirmado, marcado como rumor.",
    "Primera frase con un dato fuerte; nadie se pierde.",
    'Español latino ("ustedes"), primera persona, frases cortas.',
    "Cada ~18 palabras se puede mostrar con una captura del juego.",
    "Ninguna mención a youtubers o canales ni frases copiadas.",
]


def reglas() -> list[str]:
    """Todas las reglas, una por línea (las mismas que lleva el prompt del asistente por chat)."""
    return [IDIOMA, *VERDAD, *FORMA, LARGO, CORTO]


def para_sistema() -> str:
    """El bloque que va en el sistema de cualquier modelo que escriba guiones."""
    return "\n".join(["METODOLOGÍA DEL ESTUDIO (manda sobre cualquier otra indicación de estilo)",
                      *(f"- {r}" for r in reglas()),
                      "Antes de entregar, comprueba cada punto y reescribe lo que falle:",
                      *(f"[ ] {c}" for c in CONTROL)])
