"""Escenas de los tráilers oficiales, segundo a segundo, desde GTA Wiki (gta.wiki).

La wiki transcribe cada tráiler de Rockstar escena por escena: el segundo exacto, qué se ve (con el nombre real de
cada coche, lugar, marca o personaje), quién habla y qué dice. Studio lo usa como ÍNDICE:
- al escribir un guion sobre los tráilers, el guionista recibe esos datos verificados (y los cuenta con sus
  palabras: la wiki es CC BY-NC-SA, «no comercial», así que su texto no se copia en un canal monetizado);
- en el montaje, cada frase recibe el plano del tráiler donde ocurre exactamente lo que dice.

Las páginas se guardan en producciones/_wiki (se vuelven a leer cada día: la wiki se actualiza con cada tráiler).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from . import config

logger = logging.getLogger("studio4.escenas")

API = "https://gta.wiki/api.php"
PAGINAS = ["Grand_Theft_Auto_VI/Trailers"]   # cada página: varios tráileres con su vídeo de YouTube y su transcripción
CREDITO = "Índice de escenas de los tráileres: GTA Wiki (gta.wiki), CC BY-NC-SA 3.0 · datos, no texto"
CABECERAS = {"User-Agent": "STUDIO4-Vol3/1.0 (indice de escenas para montaje; uso personal)"}   # sin tildes: la wiki da 403
UN_DIA = 24 * 3600


def _carpeta():
    c = config.PRODUCCIONES / "_wiki"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _texto(w: str) -> str:
    """Wikitexto → texto plano: [[a|b]] → b, {{nd}} → –, ''x'' → x, <br> → espacio."""
    w = re.sub(r"\[\[(?:File|Archivo):[^\]]*\]\]", "", w)
    w = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", w)
    w = re.sub(r"\{\{nd\}\}", "–", w)
    w = re.sub(r"\{\{(?:WP|VI|V|IV|SA|VC)\|?([^}]*)\}\}", lambda m: m.group(1) or "GTA", w)
    w = re.sub(r"\{\{[^}]*\}\}", "", w)
    w = re.sub(r"<br\s*/?>", " ", w)
    w = re.sub(r"<[^>]+>", "", w)
    return re.sub(r"\s+", " ", w.replace("'''", "").replace("''", "")).strip()


def _segundos(t: str) -> float:
    try:
        partes = [float(x) for x in t.strip().split(":")]
    except ValueError:
        return -1.0
    s = 0.0
    for x in partes:
        s = s * 60 + x
    return s


def parsear(wikitexto: str) -> dict[str, dict[str, Any]]:
    """{youtube_id: {titulo, cancion, escenas: [{t, fin, que, quien, dice}]}} de una página de tráileres."""
    salida: dict[str, dict[str, Any]] = {}
    for seccion in re.split(r"\n==(?!=)", wikitexto)[1:]:
        titulo = seccion.split("==", 1)[0].strip()
        ids = re.findall(r"\{\{YouTube\|([\w-]{11})", seccion)
        lineas = re.findall(r"\{\{Line\s*\n(.*?)\n\}\}", seccion, re.DOTALL)
        if not ids or not lineas:
            continue
        cancion = re.search(r'song used in the trailer is "(.*?)"', _texto(seccion))
        escenas = []
        for cuerpo in lineas:
            campos = dict((k.strip(), v.strip()) for k, v in re.findall(r"^\|\s*(\w+)\s*=(.*)$", cuerpo, re.MULTILINE))
            t = _segundos(campos.get("time", ""))
            if t < 0:
                continue
            escenas.append({"t": t, "que": _texto(campos.get("background", "")), "quien": _texto(campos.get("name", "")),
                            "dice": _texto(campos.get("dialogue", ""))})
        escenas.sort(key=lambda e: e["t"])
        for a, b in zip(escenas, escenas[1:] + [None]):
            a["fin"] = b["t"] if b else a["t"] + 3.0
        # la última sección con transcripción gana el id (la página pone a veces el teaser del mismo tráiler antes)
        salida[ids[-1]] = {"titulo": titulo, "cancion": cancion.group(1) if cancion else "", "escenas": escenas}
    return salida


def _pagina(pagina: str, red: bool = True) -> dict[str, dict[str, Any]]:
    archivo = _carpeta() / f"{re.sub(r'[^\\w.-]', '_', pagina)}.json"
    if archivo.exists() and (not red or time.time() - archivo.stat().st_mtime < UN_DIA):
        return json.loads(archivo.read_text(encoding="utf-8"))
    if not red:
        return {}
    try:
        r = requests.get(API, params={"action": "parse", "page": pagina, "prop": "wikitext", "format": "json"},
                         headers=CABECERAS, timeout=30)
        r.raise_for_status()
        datos = parsear(r.json()["parse"]["wikitext"]["*"])
        archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        return datos
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.warning("GTA Wiki (%s): %s", pagina, e)
        return json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else {}


def indice(red: bool = True) -> dict[str, dict[str, Any]]:
    """Todas las transcripciones conocidas, por id de YouTube del tráiler oficial. `red=False`: solo lo guardado
    (el panel nunca espera a la wiki para pintar un vídeo)."""
    salida: dict[str, dict[str, Any]] = {}
    for pagina in PAGINAS:
        salida.update(_pagina(pagina, red))
    return salida


def id_youtube(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def de_fuente(meta: dict[str, Any], todas: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Las escenas que caen dentro de una fuente del banco, con el segundo ya en el tiempo de la fuente (un tramo
    bajado «desde» un minuto empieza en 0) y el plano que las enseña."""
    todas = indice() if todas is None else todas
    datos = todas.get(id_youtube(meta.get("url", "")))
    if not datos:
        return []
    desde, hasta = float(meta.get("desde") or 0), float(meta.get("hasta") or 1e9)
    salida = []
    for e in datos["escenas"]:
        if not desde <= e["t"] < hasta:
            continue
        t, fin = e["t"] - desde, min(e["fin"], hasta) - desde
        plano = plano_en(meta, t + 0.3, fin)
        salida.append({**e, "t": round(t, 2), "fin": round(fin, 2), "plano": plano})
    return salida


def plano_en(meta: dict[str, Any], t: float, fin: float) -> int:
    """El plano que se ve en el segundo t; si es pobre (negro, logo, liso), el siguiente bueno antes de `fin`."""
    planos = meta.get("planos") or []
    k = next((i for i, pl in enumerate(planos) if pl["ini"] <= t < pl["fin"]), None)
    if k is None:
        return 0
    for pl in planos[k:]:
        if pl["ini"] >= fin:
            break
        if not pl.get("pobre"):
            return pl["n"]
    return planos[k]["n"]


def para_guion(metas: list[dict[str, Any]]) -> str:
    """El índice como texto para el guionista: datos verificados de cada tráiler, con su segundo."""
    todas = indice()
    bloques = []
    for meta in metas:
        datos = todas.get(id_youtube(meta.get("url", "")))
        if not datos:
            continue
        lineas = [f"[{int(e['t']) // 60}:{int(e['t']) % 60:02d}] {e['que']}" + (f" | {e['quien']}: «{e['dice']}»" if e["dice"] else "")
                  for e in datos["escenas"]]
        bloques.append(f"{meta.get('nombre') or datos['titulo']}" + (f" (canción: {datos['cancion']})" if datos["cancion"] else "")
                       + ":\n" + "\n".join(lineas))
    if not bloques:
        return ""
    return ("ESCENAS DE LOS TRÁILERES OFICIALES, SEGUNDO A SEGUNDO (índice de GTA Wiki: son DATOS verificados — nombres de "
            "coches, lugares, marcas y personajes —; cuéntalos con tus palabras, nunca copies sus frases; los diálogos son "
            "de Rockstar). Escribe solo sobre lo que aparece aquí, así cada frase tiene su plano:\n\n" + "\n\n".join(bloques))
