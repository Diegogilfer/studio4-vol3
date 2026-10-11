"""
writer.py - Fachada Unificada de Guionistas (Gemini / Claude)
Parte de STUDIO 4 Vol. 3

Permite alternar con total transparencia entre Google Gemini (predeterminado)
y Anthropic Claude según la configuración o el parámetro proporcionado.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional
from dotenv import load_dotenv

from gemini_writer import escribir_guion_gemini
from claude_writer import escribir_guion as escribir_guion_claude

load_dotenv()

logger = logging.getLogger("studio4.writer")

ProveedorGuion = Literal["gemini", "claude"]


def escribir_guion(
    tema: str,
    target_seconds: int = 60,
    provider: Optional[str] = None,
) -> str:
    """
    Orquesta la redacción del guion utilizando el proveedor seleccionado.

    Si no se especifica 'provider', se verifica:
    1. Variable de entorno WRITER_PROVIDER (si está definida).
    2. Por defecto: 'gemini' (ecosistema Google).
    """
    prov = (provider or os.getenv("WRITER_PROVIDER", "gemini")).lower().strip()

    if prov == "claude":
        logger.info("Ejecutando Guionista Creativo con Anthropic Claude...")
        return escribir_guion_claude(tema=tema, target_seconds=target_seconds)
    elif prov == "gemini":
        logger.info("Ejecutando Guionista Creativo con Google Gemini 2.5...")
        return escribir_guion_gemini(tema=tema, target_seconds=target_seconds)
    else:
        raise ValueError(
            f"Proveedor de guion desconocido: '{prov}'. Usa 'gemini' o 'claude'."
        )

