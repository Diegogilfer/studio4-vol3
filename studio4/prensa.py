"""Prensa reciente para la investigación: lo que las wikis y Wikipedia aún no cuentan (lanzamientos, noticias de la
semana, «lo que harán los jugadores el primer día»).

Fuentes con permiso de uso: los RSS públicos de la prensa de videojuegos (cada medio los publica para eso) y GDELT
(buscador abierto de noticias). Se leen las noticias que encajan con el tema y se descarga el texto del artículo;
el dossier las cita como cualquier otra fuente [Fn]. Sin claves y sin gasto.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("studio4.prensa")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Studio4/1.0 (investigacion de guiones)"}
FEEDS_JUEGOS = {"Vandal": "https://vandal.elespanol.com/xml.cgi", "Eurogamer": "https://www.eurogamer.es/feed",
                "IGN España": "https://es.ign.com/feed.xml", "HobbyConsolas": "https://www.hobbyconsolas.com/rss"}
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_TEXTO = 7000
_VACIAS = {"de", "del", "la", "las", "el", "los", "lo", "que", "en", "y", "a", "un", "una", "unos", "unas", "por", "para",
           "con", "sin", "su", "sus", "se", "es", "son", "al", "como", "más", "mas", "muy", "este", "esta", "estos", "esto",
           "harán", "haran", "hará", "hara", "hacer", "dia", "día", "primer", "primero", "todo", "todos", "cosas", "así",
           "the", "of", "and", "to", "in", "on", "for", "what", "will"}
_ALIAS = {"gta": ["gta", "grand theft auto"], "rdr": ["red dead"], "cod": ["call of duty"]}


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def claves(tema: str) -> list[str]:
    """Las palabras que tiene que tener una noticia para servir: el juego (con sus alias) y lo demás del tema."""
    t = _plano(tema)
    salida = [w for w in re.findall(r"[a-z0-9]+", t) if w not in {_plano(x) for x in _VACIAS} and (len(w) > 2 or w.isdigit())]
    for corto, largos in _ALIAS.items():
        if corto in salida or any(x in t for x in largos):
            salida = [w for w in salida if w != corto] + largos
    return list(dict.fromkeys(salida))


def _puntos(texto: str, cl: list[str]) -> int:
    t = _plano(texto)
    return sum(1 for c in cl if re.search(rf"\b{re.escape(c)}\b", t))


def _rss(nombre: str, url: str) -> list[dict[str, Any]]:
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    salida = []
    for it in BeautifulSoup(r.content, "xml").find_all("item"):
        fecha = ""
        if it.pubDate:
            try:
                fecha = parsedate_to_datetime(it.pubDate.text.strip()).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass
        resumen = BeautifulSoup(it.description.text, "lxml").get_text(" ", strip=True) if it.description else ""
        salida.append({"titulo": it.title.text.strip() if it.title else "", "url": (it.link.text or "").strip() if it.link else "",
                       "resumen": resumen[:600], "medio": nombre, "fecha": fecha})
    return salida


def _gdelt(cl: list[str]) -> list[dict[str, Any]]:
    consulta = " ".join(f'"{c}"' if " " in c else c for c in cl[:4]) + " sourcelang:spanish"
    for intento in range(2):   # GDELT pide una consulta cada 5 s
        r = requests.get(GDELT, params={"query": consulta, "mode": "artlist", "format": "json", "maxrecords": 15,
                                        "timespan": "30d", "sort": "datedesc"}, headers=UA, timeout=30)
        if r.status_code == 429 and not intento:
            time.sleep(6)
            continue
        r.raise_for_status()
        return [{"titulo": a.get("title", ""), "url": a.get("url", ""), "resumen": "", "medio": a.get("domain", ""),
                 "fecha": (a.get("seendate") or "")[:8]} for a in (r.json().get("articles") or [])]
    return []


def texto_articulo(url: str) -> str:
    """El cuerpo de la noticia (los párrafos del artículo, sin menús ni comentarios)."""
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    sopa = BeautifulSoup(r.content, "lxml")
    for basura in sopa(["script", "style", "nav", "footer", "aside", "form", "header"]):
        basura.decompose()
    zona = sopa.find("article") or sopa.find("main") or sopa
    parrafos = [p.get_text(" ", strip=True) for p in zona.find_all("p")]
    return "\n".join(p for p in parrafos if len(p) > 60)[:MAX_TEXTO]


def buscar(tema: str, n: int = 4, juegos: bool = True) -> list[dict[str, str]]:
    """Las n noticias más pertinentes y recientes del tema, con su texto. Lo que falle se salta."""
    cl = claves(tema)
    if not cl:
        return []
    candidatas: list[dict[str, Any]] = []
    for nombre, url in (FEEDS_JUEGOS.items() if juegos else []):
        try:
            candidatas += _rss(nombre, url)
        except Exception as e:  # noqa: BLE001 - un medio caído no para la investigación
            logger.info("RSS %s: %s", nombre, e)
    try:
        candidatas += _gdelt(cl)
    except Exception as e:  # noqa: BLE001
        logger.info("GDELT: %s", e)
    juego = [c for c in cl if c in sum(_ALIAS.values(), [])] or cl[:1]   # el juego tiene que salir sí o sí
    vistas, puntuadas = set(), []
    for c in candidatas:
        texto = f"{c['titulo']} {c['resumen']}"
        if not c["url"] or c["url"] in vistas or not _puntos(texto, juego):
            continue
        vistas.add(c["url"])
        puntuadas.append((_puntos(texto, cl), c["fecha"], c))
    puntuadas.sort(key=lambda x: (x[0], x[1]), reverse=True)   # más claves primero; a igualdad, la más reciente
    salida = []
    for _, _, c in puntuadas:
        try:
            texto = texto_articulo(c["url"])
        except Exception as e:  # noqa: BLE001
            logger.info("Artículo %s: %s", c["url"], e)
            continue
        if len(texto) < 400:
            continue
        salida.append({"titulo": f"{c['titulo']} ({c['medio']}, {c['fecha']})", "url": c["url"], "texto": texto})
        if len(salida) >= n:
            break
    return salida
