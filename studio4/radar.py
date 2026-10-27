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


# Canal de historia, misterios y mitos: webs de arqueología e historia (una noticia grande sale en varias a la vez)
HISTORIA: dict[str, Any] = {
    "rss": [
        {"id": "physorg", "nombre": "Phys.org Arqueología", "url": "https://phys.org/rss-feed/science-news/archaeology/"},
        {"id": "smithsonian", "nombre": "Smithsonian Historia", "url": "https://www.smithsonianmag.com/rss/history/"},
        {"id": "ancientorigins", "nombre": "Ancient Origins", "url": "https://www.ancient-origins.net/rss.xml"},
        {"id": "historyblog", "nombre": "The History Blog", "url": "https://www.thehistoryblog.com/feed"},
        {"id": "brujulaverde", "nombre": "La Brújula Verde", "url": "https://www.labrujulaverde.com/feed"},
        {"id": "worldhistory", "nombre": "World History Encyclopedia", "url": "https://www.worldhistory.org/rss/"},
    ],
    "wiki_api": "",
    "min_fuentes": 2,
    "max_titulares": 120,
    "ruido": POR_DEFECTO["ruido"] + [
        "archaeologists", "scientists", "researchers", "study", "ancient", "discovery", "discovered", "found", "rare",
        "oldest", "old", "world", "year", "years", "century", "mysterious", "mystery", "secret", "inside", "could",
        "may", "might", "experts", "museum", "new study", "un", "una", "el", "la", "descubren", "hallan", "arqueólogos",
        "investigadores", "nuevo", "nueva", "antiguo", "antigua", "encuentran", "estudio", "revela", "reveals",
        "where", "when", "who", "they", "these", "were", "was", "from", "after", "before", "near", "under"],
    "calientes": ["egipto", "egypt", "maya", "azteca", "aztec", "roma", "roman", "grecia", "greek", "vikingo", "viking",
                  "pirámide", "pyramid", "atlántida", "atlantis", "faraón", "pharaoh", "momia", "mummy", "templario",
                  "inca", "stonehenge", "pompeya", "pompeii", "babilonia", "babylon", "mitología", "mythology"],
    "descripcion": "De qué hablan hoy las webs de historia y arqueología (cuántos titulares tiene cada tema).",
    # en historia no se agrupa por nombres propios (los titulares en inglés van en Mayúsculas) sino por grandes temas
    "temas": {
        "Roma antigua": ["roman", "romano", "romana", "imperio romano", "pompeii", "pompeya", "legion", "legión"],
        "Antiguo Egipto": ["egypt", "egipto", "egipcio", "pharaoh", "faraón", "pyramid", "pirámide", "nile", "nilo"],
        "Mayas": ["maya", "mayan"],
        "Aztecas": ["aztec", "azteca", "mexica", "tenochtitlan"],
        "Incas": ["inca", "machu picchu", "andes"],
        "Vikingos y nórdicos": ["viking", "vikingo", "norse", "nórdico", "rune", "runa"],
        "Grecia antigua": ["greek", "grecia", "griego", "griega", "athens", "atenas", "sparta", "esparta"],
        "Mesopotamia": ["mesopotamia", "babylon", "babilonia", "sumer", "sumerio", "assyria", "asiria", "cuneiform", "cuneiforme"],
        "Celtas": ["celt", "celta", "druid", "druida"],
        "Edad Media": ["medieval", "middle ages", "edad media", "templar", "templario", "knight", "caballero", "crusade", "cruzada"],
        "Naufragios": ["shipwreck", "naufragio", "pecio", "sunken", "hundido"],
        "Tumbas y momias": ["tomb", "tumba", "burial", "entierro", "grave", "mummy", "momia", "skeleton", "esqueleto", "necrópolis", "necropolis"],
        "Prehistoria": ["neolithic", "neolítico", "paleolithic", "paleolítico", "stone age", "edad de piedra", "prehistoric", "prehistoria", "neanderthal", "neandertal"],
        "Mitos y dioses": ["myth", "mito", "mitología", "mythology", "god ", "dios", "goddess", "diosa", "legend", "leyenda"],
        "Manuscritos y textos perdidos": ["manuscript", "manuscrito", "codex", "códice", "inscription", "inscripción", "scroll", "papiro", "papyrus"],
        "Misterios sin resolver": ["mystery", "misterio", "enigma", "unexplained", "inexplicable", "cold case", "disappear", "desaparec"],
        "Tesoros": ["treasure", "tesoro", "hoard", "coins", "monedas", "gold", "oro"],
    },
    "min_titulares": 2,
}
POR_DEFECTO.setdefault("descripcion", "Juegos y temas que suenan en varias webs de videojuegos a la vez, antes de ser tendencia en vídeo.")
CANAL_ORIGINAL = "fourlevel"   # el radar de siempre (videojuegos) sigue en sus archivos de siempre


def _rutas(cid: str | None):
    """Cada canal con su radar: su configuración y sus señales aparte (nunca se mezclan)."""
    if not cid or cid == CANAL_ORIGINAL:
        return CONFIG, SENALES
    base = config.PRODUCCIONES / "_canales" / cid
    return base / "radar.json", base / "radar.jsonl"


def _plantilla(cid: str | None) -> dict[str, Any]:
    if not cid or cid == CANAL_ORIGINAL:
        return POR_DEFECTO
    from . import canales
    try:
        nicho = f"{canales.obtener(cid).get('nicho', '')}".lower()
    except ValueError:
        nicho = ""
    if re.search(r"misterio|mito|historia|leyenda|arqueolog|enigma", nicho):
        return HISTORIA
    if re.search(r"juego|gaming|gamer", nicho):
        return {**POR_DEFECTO, "wiki_api": ""}
    return {**POR_DEFECTO, "rss": [], "wiki_api": "", "descripcion": "Añade las webs RSS de tu nicho en el radar de este canal."}


def config_radar(cid: str | None = None) -> dict[str, Any]:
    archivo, _ = _rutas(cid)
    base = _plantilla(cid)
    if archivo.is_file():
        try:
            return {**base, **json.loads(archivo.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(base)


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


def escanear(cfg: dict[str, Any] | None = None, cid: str | None = None) -> list[dict[str, Any]]:
    """Señales de hoy: juegos/temas que salen en varias fuentes a la vez, ordenados por fuerza. No llama a ninguna IA."""
    cfg = cfg or config_radar(cid)
    ruido = {x.lower() for x in cfg["ruido"]}
    items: list[tuple[str, str, str]] = []   # (fuente, titular, enlace de la fuente)
    for f in cfg["rss"]:
        for t in _titulares_rss(f, cfg["max_titulares"]):
            items.append((f["id"], t, f["url"]))
    for t in (_titulos_wiki(cfg) if cfg.get("wiki_api") else []):
        items.append(("gtawiki", t, "https://gta.wiki/w/" + t.replace(" ", "_")))

    temas: dict[str, dict[str, Any]] = {}
    if cfg.get("temas"):   # por grandes temas (historia): un titular cuenta en cada tema cuyas palabras nombra
        for fuente, titular, _ in items:
            t = f" {titular.lower()} "
            for tema, palabras in cfg["temas"].items():
                if any(p in t for p in palabras):
                    d = temas.setdefault(tema.lower(), {"tema": tema, "fuentes": set(), "titulares": [], "caliente": True})
                    d["fuentes"].add(fuente)
                    if titular not in d["titulares"]:
                        d["titulares"].append(titular)
        senales = [{"tema": d["tema"], "fuerza": len(d["fuentes"]) * 4 + min(len(d["titulares"]), 12), "fuentes": sorted(d["fuentes"]),
                    "n_fuentes": len(d["titulares"]), "caliente": len(d["fuentes"]) >= 2, "titulares": d["titulares"][:4]}
                   for d in temas.values() if len(d["titulares"]) >= cfg.get("min_titulares", 2)]
        return sorted(senales, key=lambda s: -s["fuerza"])
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


def _guardar(senales: list[dict[str, Any]], cid: str | None = None) -> None:
    _, archivo = _rutas(cid)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    dia = time.strftime("%Y-%m-%d")
    with archivo.open("a", encoding="utf-8") as f:
        for s in senales:
            f.write(json.dumps({**s, "dia": dia}, ensure_ascii=False) + "\n")


def señales(n: int = 10, guardar: bool = False, cid: str | None = None) -> list[dict[str, Any]]:
    """Las n señales más fuertes de ahora. `guardar`: deja constancia en _radar.jsonl (para la tarea diaria).
    Hace 6 descargas en vivo: lento. El panel usa `guardadas()`, no esto."""
    s = escanear(cid=cid)[:n]
    if guardar and s:
        _guardar(s, cid)
    return s


def guardadas(n: int = 12, cid: str | None = None) -> list[dict[str, Any]]:
    """Las señales del último escaneo guardado (rápido, sin red). Para el panel: no espera a 6 webs en cada carga."""
    _, archivo = _rutas(cid)
    if not archivo.is_file():
        return []
    try:
        lineas = [json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines() if l.strip()]
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
    for s in escanear(cid=cid):
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


_actualizando: set[str] = set()


def para_panel(cid: str, n: int = 12) -> dict[str, Any]:
    """Lo que enseña el panel del canal activo: sus señales guardadas; si no son de hoy, se buscan en segundo plano
    (el panel no espera) y salen en la siguiente carga."""
    import threading
    s = guardadas(n, cid)
    if (not s or s[0].get("dia") != time.strftime("%Y-%m-%d")) and cid not in _actualizando and config_radar(cid)["rss"]:
        _actualizando.add(cid)

        def fondo() -> None:
            try:
                señales(10, guardar=True, cid=cid)
            except Exception as e:  # noqa: BLE001 - sin red no hay radar; el panel sigue
                logger.warning("Radar de %s: %s", cid, e)
            finally:
                _actualizando.discard(cid)
        threading.Thread(target=fondo, daemon=True).start()
    return {"senales": s, "descripcion": config_radar(cid).get("descripcion", ""), "actualizando": cid in _actualizando}
