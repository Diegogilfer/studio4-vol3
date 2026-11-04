"""Las miniaturas que el canal ya usó, para que Studio 4 aprenda su estilo y cada prompt nuevo salga más «suyo».

Cada vez que subes la imagen de Flow con «Gancho de continuidad», se guarda aquí (pequeña) con su título, el prompt que
la hizo y una descripción de su estilo que escribe Gemini mirándola (composición, colores, encuadre, dónde va el
texto). El prompt de la siguiente miniatura recibe las últimas referencias del canal: aprende de ellas sin copiarlas.
"""

from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger("studio4.miniaturas_ref")
CARPETA = config.PRODUCCIONES / "_miniaturas_ref"
MAXIMO = 30   # por canal: las más recientes mandan

SISTEMA = """Describe el ESTILO de esta miniatura de YouTube en una línea (máx. 45 palabras), para repetirlo en otras:
composición y encuadre, sujeto principal y su tamaño, colores dominantes, luz, dónde queda el hueco del texto y el
ambiente. Nada de nombres propios ni de lo que cuenta: solo el estilo visual."""


def _indice(canal: str) -> Path:
    return CARPETA / canal / "referencias.json"


def listar(canal: str) -> list[dict[str, Any]]:
    try:
        return json.loads(_indice(canal).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def describir(imagen: bytes) -> str:
    from . import gemini
    try:
        return gemini.generar("Describe el estilo visual de esta miniatura.", sistema=SISTEMA, temperatura=0.2,
                              detalle="estilo de una miniatura de referencia", imagenes=[imagen]).strip()[:400]
    except Exception as e:  # noqa: BLE001 - sin descripción también sirve (queda el prompt)
        logger.info("Describir miniatura: %s", e)
        return ""


def guardar(canal: str, imagen: Path, titulo: str, prompt: str = "", texto: str = "", video: str = "",
            describir_con=describir) -> dict[str, Any]:
    """Una miniatura que el canal usó → referencia (imagen pequeña + estilo + prompt). Devuelve la ficha."""
    from PIL import Image
    destino = CARPETA / canal
    destino.mkdir(parents=True, exist_ok=True)
    im = Image.open(imagen).convert("RGB")
    im.thumbnail((640, 640))
    nombre = f"{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    caja = io.BytesIO()
    im.save(caja, "JPEG", quality=88)
    (destino / nombre).write_bytes(caja.getvalue())
    ficha = {"archivo": nombre, "titulo": titulo[:120], "texto": texto[:40], "video": video,
             "prompt": prompt[:1200], "estilo": describir_con(caja.getvalue()), "fecha": time.strftime("%Y-%m-%d")}
    refs = [r for r in listar(canal) if not (video and r.get("video") == video)]   # un vídeo, una referencia (la última)
    refs.append(ficha)
    for vieja in refs[:-MAXIMO]:
        (destino / vieja["archivo"]).unlink(missing_ok=True)
    _indice(canal).write_text(json.dumps(refs[-MAXIMO:], ensure_ascii=False, indent=1), encoding="utf-8")
    return ficha


def para_prompt(canal: str, n: int = 5) -> str:
    """Las últimas referencias del canal, listas para el que escribe el prompt de la miniatura nueva."""
    refs = listar(canal)[-n:]
    if not refs:
        return ""
    lineas = [f"- «{r['titulo']}» · estilo: {r.get('estilo') or 'sin describir'}" + (f" · texto encima: {r['texto']}" if r.get("texto") else "")
              for r in refs]
    return ("MINIATURAS QUE EL CANAL YA USÓ (aprende su estilo: composición, colores, encuadre y hueco del texto; "
            "mantén la línea del canal pero NO copies ninguna):\n" + "\n".join(lineas))
