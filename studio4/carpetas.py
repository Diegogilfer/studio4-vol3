"""La carpeta de cada producción, a la vista en tu PC (Vídeos\\STUDIO 4\\«fecha · título»):

  1 Clips de Flow     → dejas aquí cada clip que bajes de Flow, con el número de su escena en el nombre
                        («escena 3.mp4», «07.png»…): STUDIO lo coloca solo en su escena.
  2 Guion y escenas   → el guion y la lista de escenas (qué generar, vídeo o imagen, y su prompt).
  3 Entregas          → vídeo completo, Reels, Shorts, miniaturas y las descripciones para publicar.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger("studio4.carpetas")

RAIZ_USUARIO = Path(os.getenv("STUDIO4_CARPETA", str(Path.home() / "Videos" / "STUDIO 4")))
CLIPS, GUION, ENTREGAS = "1 Clips de Flow", "2 Guion y escenas", "3 Entregas"
EXTENSIONES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
               ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
VERSION = {"corto": "Corto", "largo": "Largo", "propio": "Guion propio"}

LEEME = """Guarda aquí cada clip que descargues de Google Flow con el NÚMERO DE SU ESCENA en el nombre:

    escena 1.mp4      escena 02.png      3.mp4      Escena 14 - toma buena.mp4

STUDIO 4 lo detecta en unos segundos y lo coloca en su escena (vídeo o imagen, como te recomendó).
Si dejas varios para la misma escena, se guardan todos como tomas y eliges la mejor en el panel.
"""


def _limpio(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)).strip().rstrip(".")


def nombre(p: dict[str, Any]) -> str:
    titulo = _limpio(p.get("titulo") or p.get("tema") or "Producción")[:80]
    version = VERSION.get(p.get("version", ""), "")
    return f"{p['creado'][:10]} · {titulo}" + (f" ({version})" if version else "")


def ruta(p: dict[str, Any]) -> Path:
    return Path(p["carpeta"]) if p.get("carpeta") else RAIZ_USUARIO / nombre(p)


def preparar(p: dict[str, Any]) -> Path:
    """Crea (o completa) la carpeta y escribe el guion y la lista de escenas. Devuelve su ruta."""
    base = ruta(p)
    for sub in (CLIPS, GUION, ENTREGAS):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / CLIPS / "LEEME.txt").write_text(LEEME, encoding="utf-8")
    if p.get("guion"):
        (base / GUION / "Guion.txt").write_text(p["guion"] + "\n", encoding="utf-8")
    if p.get("escenas"):
        lineas = []
        for e in p["escenas"]:
            tipo = "IMAGEN" if e.get("tipo_clip") == "imagen" else "VÍDEO"
            lineas += [f"ESCENA {e['orden']} · hazla como {tipo}" + (f" — {e['motivo_tipo']}" if e.get("motivo_tipo") else ""),
                       f"Voz: {e['texto_voz']}", f"Prompt para Flow: {e['prompt_flow']}", ""]
        (base / GUION / "Escenas para Flow.txt").write_text("\n".join(lineas), encoding="utf-8")
    return base


def importar(p: dict[str, Any], recibir) -> list[str]:
    """Mira «1 Clips de Flow» y entrega a su escena lo que aún no se había importado. Devuelve las claves nuevas."""
    carpeta = ruta(p) / CLIPS
    if not carpeta.is_dir():
        return []
    ya = set(p.get("importados", []))
    nuevas = []
    for f in sorted(carpeta.iterdir()):
        mime = EXTENSIONES.get(f.suffix.lower())
        if not mime or not f.is_file():
            continue
        clave = f"{f.name}|{f.stat().st_size}|{int(f.stat().st_mtime)}"
        if clave in ya:
            continue
        m = re.search(r"(\d+)", f.stem)
        n = int(m.group(1)) if m else 0
        if not 1 <= n <= len(p.get("escenas", [])):
            logger.warning("«%s»: no sé a qué escena va (pon el número de escena en el nombre).", f.name)
            nuevas.append(clave)   # no se vuelve a intentar hasta que cambie el archivo
            continue
        fd, tmp = tempfile.mkstemp(prefix="studio4_", suffix=f.suffix, dir=config.PRODUCCIONES)
        os.close(fd)
        shutil.copy(f, tmp)
        try:
            recibir(Path(tmp), mime, n)
            nuevas.append(clave)
        except Exception as e:  # noqa: BLE001 - un archivo malo no frena a los demás
            logger.warning("No pude importar «%s»: %s", f.name, e)
            nuevas.append(clave)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return nuevas


def exportar(p: dict[str, Any], archivos: list[tuple[Path, str]], textos: str) -> Path:
    """Copia las entregas con nombres claros a «3 Entregas» y deja las descripciones listas para publicar."""
    destino = ruta(p) / ENTREGAS
    destino.mkdir(parents=True, exist_ok=True)
    for origen, nombre_final in archivos:
        if origen.exists():
            shutil.copy(origen, destino / _limpio(nombre_final))
    (destino / "Descripciones para publicar.txt").write_text(textos, encoding="utf-8")
    return destino
