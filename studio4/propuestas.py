"""Conversar primero, lanzar después: los chats responden y proponen; lo que lleva trabajo (crear un vídeo, renders,
buscar material, analizar nichos…) solo arranca cuando el autor lo confirma («lánzalo», «dale», «actualiza») o
pulsa «Lanzar». Así una pregunta nunca dispara 15 o 20 minutos de trabajo sin querer.
"""

from __future__ import annotations

import re

# respuestas cortas que significan «sí, hazlo»
CONFIRMAR = re.compile(r"^\s*(?:s[ií]\s*,?\s*)?(?:l[aá]nza(?:lo|la|r)?|dale|hazlo|hazla|h[aá]gale|adelante|actual[ií]za(?:lo|la)?|"
                       r"empieza|arranca|ejec[uú]ta(?:lo)?|venga|vamos|confirmo|ok(?:ay)?|vale|perfecto|de acuerdo|s[ií]|go)\b",
                       re.IGNORECASE)


def es_confirmacion(mensaje: str) -> bool:
    """¿El mensaje es un «sí, lánzalo» (y no una petición nueva)? Solo mensajes cortos."""
    return len(mensaje.split()) <= 6 and bool(CONFIRMAR.match(mensaje))
