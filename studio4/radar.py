"""Radar de tendencias: qué juegos se mueven AHORA en el mundo de los videojuegos, antes de que sean tendencia en vídeo.

Idea tomada del radar de SKAY (fuente pública → señal con sentido → sugerencia, nunca ejecuta). Aquí, para un canal de
videojuegos y entretenimiento (no solo GTA):

  varias webs de noticias de juegos (RSS) + GTA Wiki  →  qué juego/tema sale en varias a la vez  →  señal {tema, fuerza}
                                                                                                   →  idea con material ya buscado

La tendencia en vivo de YouTube ya la da `tendencias`/`ideas` (lo que crece en vistas). El radar es complementario: coge
lo que las webs de juegos publican a la vez (una noticia grande sale en todas) y lo que los editores de GTA Wiki tocan al
minuto, la señal más temprana que hay, y lo pasa a ideas con su material real. No publica ni escribe a nadie. Coste 0 €.

Config editable: producciones/_radar.json (fuentes y qué ignorar). Señales en producciones/_radar.jsonl.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any

import requests

from . import config

logger = logging.getLogger("studio4.radar")

CONFIG = config.PRODUCCIONES / "_radar.json"
SENALES = config.PRODUCCIONES / "_radar.jsonl"
CABECERAS = {"User-Agent": "STUDIO4-Vol3/1.0 (radar de tendencias de videojuegos; uso personal)"}

POR_DEFECTO: dict[str, Any] = {
    # webs de noticias de juegos (RSS): una noticia grande sale en varias a la vez
    "rss": [
        {"id": "ign", "nombre": "IGN", "url": "https://feeds.feedburner.com/ign/games-all"},
        {"id": "gamespot", "nombre": "GameSpot", "url": "https://www.gamespot.com/feeds/game-news/"},
        {"id": "eurogamer", "nombre": "Eurogamer", "url": "https://www.eurogamer.net/feed/news"},
        {"id": "pcgamer", "nombre": "PC Gamer", "url": "https://www.pcgamer.com/rss/"},
        {"id": "polygon", "nombre": "Polygon", "url": "https://www.polygon.com/rss/index.xml"},
        {"id": "kotaku", "nombre": "Kotaku", "url": "https://kotaku.com/rss"},
    ],
    "wiki_api": "https://gta.wiki/api.php",   # GTA Wiki: cambios recientes (señal temprana específica de GTA)
    "min_fuentes": 2,                         # un tema cuenta si sale en ≥ 2 sitios (no una sola web)
    "max_titulares": 120,                     # por fuente
    # palabras que no nombran un juego (se ignoran al detectar el tema)
    "ruido": ["the", "new", "all", "best", "how", "why", "what", "your", "you", "with", "this", "that", "for", "and",
              "game", "games", "gaming", "update", "review", "trailer", "release", "date", "out", "now", "get", "guide",
              "here", "every", "will", "has", "its", "are", "can", "gets", "coming", "first", "next", "más", "los", "las",
              "una", "con", "del", "por", "ign", "gamespot", "report", "says", "video", "nintendo", "xbox", "playstation"],
    "calientes": ["gta", "grand theft auto", "vice city", "call of duty", "fortnite", "minecraft", "zelda", "mario",
                  "pokemon", "pokémon", "fifa", "ea sports fc", "elden ring", "red dead", "cyberpunk", "hollow knight"],
}


def config_radar() -> dict[str, Any]:
    if CONFIG.is_file():
        try:
            return {**POR_DEFECTO, **json.loads(CONFIG.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(POR_DEFECTO, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(POR_DEFECTO)


def _titulares_rss(fuente: dict[str, str], maximo: int) -> list[str]:
    try:
        r = requests.get(fuente["url"], headers=CABECERAS, timeout=20)
        r.raise_for_status()
        titulos = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", r.text, re.DOTALL)
        return [html.unescape(re.sub(r"<[^>]+>", "", t)).strip() for t in titulos[1 : maximo + 1]]   # [0] es el del feed
    except (requests.RequestException, ValueError) as e:
        logger.warning("RSS %s: %s", fuente.get("id"), e)
        return []


def _titulos_wiki(cfg: dict[str, Any]) -> list[str]:
    try:
        r = requests.get(cfg["wiki_api"], headers={"User-Agent": "STUDIO4-Vol3/1.0 (radar; uso personal)"}, timeout=20,
                         params={"action": "query", "list": "recentchanges", "rcnamespace": "0", "rclimit": "100",
                                 "rcprop": "title", "rctype": "edit|new", "format": "json"})
        r.raise_for_status()
        vistos, salida = set(), []
        for c in r.json().get("query", {}).get("recentchanges", []):
            t = c.get("title", "")
            if t and t not in vistos and not re.search(r"/|:", t):
                vistos.add(t)
                salida.append(t)
        return salida
    except (requests.RequestException, ValueError) as e:
        logger.warning("GTA Wiki (cambios recientes): %s", e)
        return []


def _temas(titulo: str, ruido: set[str]) -> list[str]:
    """Nombres propios del titular, uniendo «of/the/&» para no partir juegos: «Call of Duty», «World of Warcraft»,
    «Mass Effect 5», «GTA 6»."""
    palabras = re.findall(r"\b([A-Z][\w']+(?:\s+(?:of|the|and|&|[A-Z][\w']+|\d+|VI|IV|VII))*)\b", titulo)
    salida = []
    for p in palabras:
        p = re.sub(r"^(?:of|the|and)\s+|\s+(?:of|the|and)$", "", p.strip(), flags=re.I).strip()
        if len(p) < 3 or p.lower() in ruido or re.fullmatch(r"[\d\s]+", p):
            continue
        salida.append(p)
    return salida


def escanear(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Señales de hoy: juegos/temas que salen en varias fuentes a la vez, ordenados por fuerza. No llama a ninguna IA."""
    cfg = cfg or config_radar()
    ruido = {x.lower() for x in cfg["ruido"]}
    items: list[tuple[str, str, str]] = []   # (fuente, titular, enlace de la fuente)
    for f in cfg["rss"]:
        for t in _titulares_rss(f, cfg["max_titulares"]):
            items.append((f["id"], t, f["url"]))
    for t in _titulos_wiki(cfg):
        items.append(("gtawiki", t, "https://gta.wiki/w/" + t.replace(" ", "_")))

    temas: dict[str, dict[str, Any]] = {}
    for fuente, titular, _ in items:
        for tema in _temas(titular, ruido):
            clave = tema.lower()
            d = temas.setdefault(clave, {"tema": tema, "fuentes": set(), "titulares": [], "caliente": False})
            d["fuentes"].add(fuente)
            if titular not in d["titulares"]:
                d["titulares"].append(titular)
            if any(c in clave for c in cfg["calientes"]):
                d["caliente"] = True

    senales = []
    for d in temas.values():
        if len(d["fuentes"]) < cfg["min_fuentes"]:
            continue
        fuerza = len(d["fuentes"]) * 4 + min(len(d["titulares"]), 8) + (8 if d["caliente"] else 0)
        senales.append({"tema": d["tema"], "fuerza": fuerza, "fuentes": sorted(d["fuentes"]),
                        "n_fuentes": len(d["fuentes"]), "caliente": d["caliente"], "titulares": d["titulares"][:4]})
    senales.sort(key=lambda s: -s["fuerza"])
    return senales


def _guardar(senales: list[dict[str, Any]]) -> None:
    SENALES.parent.mkdir(parents=True, exist_ok=True)
    dia = time.strftime("%Y-%m-%d")
    with SENALES.open("a", encoding="utf-8") as f:
        for s in senales:
            f.write(json.dumps({**s, "dia": dia}, ensure_ascii=False) + "\n")


def señales(n: int = 10, guardar: bool = False) -> list[dict[str, Any]]:
    """Las n señales más fuertes de ahora. `guardar`: deja constancia en _radar.jsonl (para la tarea diaria).
    Hace 6 descargas en vivo: lento. El panel usa `guardadas()`, no esto."""
    s = escanear()[:n]
    if guardar and s:
        _guardar(s)
    return s


def guardadas(n: int = 12) -> list[dict[str, Any]]:
    """Las señales del último escaneo guardado (rápido, sin red). Para el panel: no espera a 6 webs en cada carga."""
    if not SENALES.is_file():
        return []
    try:
        lineas = [json.loads(l) for l in SENALES.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    if not lineas:
        return []
    ultimo = lineas[-1].get("dia")
    return [s for s in lineas if s.get("dia") == ultimo][:n]


def para_ideas(cid: str, n: int = 3, avisar=lambda _f: None) -> list[dict[str, Any]]:
    """Las señales más fuertes como semillas de idea, cada una CON su material real ya buscado (material.py): una idea
    del radar llega lista para escribir solo sobre lo que se puede enseñar."""
    from . import material
    salida = []
    for s in escanear():
        if len(salida) >= n:
            break
        avisar(f"Buscando material para «{s['tema']}» ({len(salida) + 1} de {n})")
        try:
            inv = material.inventario(s["tema"], por_escena=2)
        except Exception as e:  # noqa: BLE001 - una señal sin material no bloquea las demás
            logger.warning("Material para «%s»: %s", s["tema"], e)
            inv = []
        if not any(e.get("videos") for e in inv):
            continue
        salida.append({"tema": s["tema"], "fuerza": s["fuerza"], "fuentes": s["fuentes"], "caliente": s["caliente"],
                       "titulares": s["titulares"], "material_sugerido": inv,
                       "por_que": f"«{s['tema']}» sale en {s['n_fuentes']} webs de juegos a la vez ahora mismo: señal "
                                  f"temprana antes de que sea tendencia en vídeo."})
    return salida
