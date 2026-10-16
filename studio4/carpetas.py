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

from . import canales, config

logger = logging.getLogger("studio4.carpetas")

RAIZ_USUARIO = Path(os.getenv("STUDIO4_CARPETA", str(Path.home() / "Videos" / "STUDIO 4")))
# Subcarpetas: llevan delante el nombre del vídeo (ver subcarpeta()).
CLIPS, GUION, ENTREGAS = "1 Clips de Flow", "2 Guion y escenas", "3 Entregas"
EXTENSIONES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
               ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
VERSION = {"corto": "Corto", "largo": "Largo", "propio": "Guion propio", "importado": "Importado"}

LEEME = """«{titulo}» · clips de Google Flow

Guarda aquí cada clip que descargues de Flow con el nombre del vídeo y el NÚMERO DE SU ESCENA:

    {corto} - escena 01.mp4
    {corto} - escena 02.png
    {corto} - escena 14 (toma 2).mp4

STUDIO 4 lo detecta en unos segundos y lo coloca en su escena (vídeo o imagen, como te recomendó).
Si dejas varios para la misma escena, se guardan todos como tomas y eliges la mejor en el panel.
"""


def _limpio(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)).strip().rstrip(".")


def _recortar(texto: str, n: int) -> str:
    """Como mucho `n` letras, cortando en una palabra entera (Windows no admite rutas de más de 260 letras y el
    nombre del vídeo se repite en la carpeta, la subcarpeta y cada archivo)."""
    if len(texto) <= n:
        return texto
    corte = texto[:n].rsplit(" ", 1)[0]
    palabras = (corte if len(corte) > n // 2 else texto[:n]).rstrip(" ,;:-·").split(" ")
    while len(palabras) > 2 and palabras[-1].lower() in SUELTAS:   # que no acabe en «y el», «de la»…
        palabras.pop()
    return " ".join(palabras).rstrip(" ,;:-·")


SUELTAS = {"y", "e", "o", "u", "el", "la", "los", "las", "lo", "de", "del", "al", "a", "en", "con", "por", "para", "un", "una",
           "su", "sus", "que", "the", "of", "and", "to", "in"}


def _titulo(p: dict[str, Any]) -> str:
    """El título para nombrar carpetas: si tiene dos partes («Bonnie nunca disparó: lo que…»), la primera."""
    t = (p.get("titulo") or p.get("tema") or "Producción").strip()
    antes = t.split(":")[0].strip()
    return _limpio(antes if len(antes) >= 12 else t)


def nombre(p: dict[str, Any]) -> str:
    titulo = _recortar(_titulo(p), 44)
    version = VERSION.get(p.get("version", ""), "")
    return f"{p['creado'][:10]} · {titulo}" + (f" ({version})" if version else "")


def corto(p: dict[str, Any]) -> str:
    """El nombre del vídeo para ponerlo delante de cada archivo y subcarpeta."""
    return _recortar(_titulo(p), 32)


def subcarpeta(p: dict[str, Any], cual: str) -> str:
    return f"{cual} · {corto(p)}"


def ruta(p: dict[str, Any]) -> Path:
    """Vídeos/STUDIO 4/<canal>/<fecha · título>. Las carpetas de antes de los canales (sin la del canal) se mueven."""
    if p.get("carpeta") and Path(p["carpeta"]).parent != RAIZ_USUARIO:
        return Path(p["carpeta"])
    return RAIZ_USUARIO / _limpio(canales.de_produccion(p)["nombre"]) / nombre(p)


def preparar(p: dict[str, Any]) -> Path:
    """Crea (o completa) la carpeta y escribe el guion y la lista de escenas, todo con el nombre del vídeo."""
    base = ruta(p)
    vieja_raiz = Path(p["carpeta"]) if p.get("carpeta") else None
    if vieja_raiz and vieja_raiz != base and vieja_raiz.is_dir() and not base.exists():
        base.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(vieja_raiz), str(base))   # a la carpeta de su canal
    c = corto(p)
    for cual in (CLIPS, GUION, ENTREGAS):
        nueva = base / subcarpeta(p, cual)
        viejas = [base / cual] + sorted(base.glob(f"{cual} · *"))   # sin el nombre del vídeo, o con uno más largo
        vieja = next((v for v in viejas if v.is_dir() and v != nueva), None)
        if vieja and not nueva.exists():
            vieja.rename(nueva)
        nueva.mkdir(parents=True, exist_ok=True)
    clips, guion = base / subcarpeta(p, CLIPS), base / subcarpeta(p, GUION)
    for viejo in (clips / "LEEME.txt", guion / "Guion.txt", guion / "Escenas para Flow.txt"):
        viejo.unlink(missing_ok=True)
    (clips / f"{c} - LEEME.txt").write_text(LEEME.format(titulo=p.get("titulo") or p.get("tema", ""), corto=c), encoding="utf-8")
    if p.get("guion"):
        (guion / f"{c} - Guion.txt").write_text(f"«{p.get('titulo') or p['tema']}» · Guion\n\n{p['guion']}\n", encoding="utf-8")
    if p.get("escenas"):
        lineas = [f"«{p.get('titulo') or p['tema']}» · Escenas para Google Flow",
                  f"Guarda cada clip en «{subcarpeta(p, CLIPS)}» como: {c} - escena 01.mp4", ""]
        for e in p["escenas"]:
            tipo = "IMAGEN" if e.get("tipo_clip") == "imagen" else "VÍDEO"
            lineas += [f"{c} · ESCENA {e['orden']:02d} · hazla como {tipo}" + (f" — {e['motivo_tipo']}" if e.get("motivo_tipo") else ""),
                       f"Guárdala como: {c} - escena {e['orden']:02d}{'.png' if tipo == 'IMAGEN' else '.mp4'}",
                       f"Voz: {e['texto_voz']}", f"Prompt para Flow: {e['prompt_flow']}", ""]
        (guion / f"{c} - Escenas para Flow.txt").write_text("\n".join(lineas), encoding="utf-8")
    return base


def numero_de_escena(p: dict[str, Any], nombre_archivo: str) -> int:
    """«Título 2 - escena 07.mp4» → 7. Primero busca «escena N»; si no, el primer número que no sea del título."""
    stem = Path(nombre_archivo).stem
    m = re.search(r"escena\s*0*(\d+)", stem, re.IGNORECASE)
    if m:
        return int(m.group(1))
    resto = stem.replace(corto(p), " ")
    m = re.search(r"(\d+)", resto)
    return int(m.group(1)) if m else 0


def estado(p: dict[str, Any]) -> dict[str, Any]:
    """Lo que hay en «1 Clips de Flow»: la ruta, cuántos clips hay y a cuántas escenas corresponden."""
    carpeta = ruta(p) / subcarpeta(p, CLIPS)
    total = len(p.get("escenas") or [])
    archivos = [f for f in carpeta.iterdir() if f.is_file() and f.suffix.lower() in EXTENSIONES] if carpeta.is_dir() else []
    con_escena = {numero_de_escena(p, f.name) for f in archivos} & set(range(1, total + 1))
    return {"ruta": str(carpeta), "archivos": len(archivos), "escenas_en_carpeta": len(con_escena),
            "escenas_con_clip": sum(1 for e in p.get("escenas") or [] if e.get("elegida") is not None), "total": total}


def importar(p: dict[str, Any], recibir) -> list[str]:
    """Mira «1 Clips de Flow» y entrega a su escena lo que aún no se había importado. Devuelve las claves nuevas."""
    carpeta = ruta(p) / subcarpeta(p, CLIPS)
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
        n = numero_de_escena(p, f.name)
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
    destino = ruta(p) / subcarpeta(p, ENTREGAS)
    destino.mkdir(parents=True, exist_ok=True)
    c = corto(p)
    for origen, nombre_final in archivos:
        if origen.exists():
            shutil.copy(origen, destino / f"{c} - {_limpio(nombre_final)}")
    (destino / f"{c} - Descripciones para publicar.txt").write_text(f"«{p.get('titulo') or p['tema']}»\n\n{textos}", encoding="utf-8")
    return destino
