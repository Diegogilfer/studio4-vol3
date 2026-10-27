"""¿Está saturado un nicho? Datos reales de YouTube (últimos 6 meses, vídeos en español): demanda (vistas medianas),
saturación (canales de más de 1M y cuánto se lleva el top 3) y hueco (canales pequeños que aun así explotan).
Cada tema gasta unas 102 unidades de las 10.000 gratis diarias de la API de YouTube.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from . import youtube

MAX_TEMAS = 5


def _lotes(xs: list[str], n: int = 50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def veredicto(f: dict[str, Any]) -> str:
    if f["mediana_vistas"] < 20_000:
        return "Poca demanda"
    if f["pequenos_que_explotan"] >= 10 and f["top3_cuota"] <= 0.55:
        return "Hueco: canales nuevos rompen"
    if f["pequenos_que_explotan"] <= 3 and f["grandes_1M"] >= 10:
        return "Saturado: lo dominan los grandes"
    if f["top3_cuota"] >= 0.8:
        return "Lo acapara un solo canal"
    return "Disputado: se puede, con un ángulo propio"


def analizar_tema(tema: str, meses: int = 6) -> dict[str, Any]:
    desde = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() - meses * 30 * 86400))
    d = youtube._get("search", part="snippet", q=tema, type="video", order="viewCount", maxResults=50,
                     relevanceLanguage="es", publishedAfter=desde, safeSearch="none")
    ids = [i["id"]["videoId"] for i in d.get("items", [])]
    vids: list[dict[str, Any]] = []
    for lote in _lotes(ids):
        vids += youtube._get("videos", part="statistics,snippet", id=",".join(lote)).get("items", [])
    subs: dict[str, int] = {}
    for lote in _lotes(list({v["snippet"]["channelId"] for v in vids})):
        for c in youtube._get("channels", part="statistics", id=",".join(lote)).get("items", []):
            subs[c["id"]] = int(c["statistics"].get("subscriberCount", 0) or 0)
    filas = [{"vistas": int(v["statistics"].get("viewCount", 0) or 0), "subs": subs.get(v["snippet"]["channelId"], 0),
              "canal": v["snippet"]["channelTitle"], "titulo": v["snippet"]["title"][:90]} for v in vids]
    if not filas:
        return {"tema": tema, "videos": 0, "veredicto": "Sin datos"}
    por_canal: dict[str, int] = {}
    for f in filas:
        por_canal[f["canal"]] = por_canal.get(f["canal"], 0) + f["vistas"]
    total = max(1, sum(f["vistas"] for f in filas))
    pequenos = sorted((f for f in filas if f["subs"] < 100_000 and f["vistas"] >= 100_000),
                      key=lambda f: -f["vistas"] / max(f["subs"], 1000))
    r = {"tema": tema, "videos": len(filas), "mediana_vistas": int(statistics.median(f["vistas"] for f in filas)),
         "canales": len(por_canal), "grandes_1M": len({f["canal"] for f in filas if f["subs"] >= 1_000_000}),
         "top3_cuota": round(sum(sorted(por_canal.values(), reverse=True)[:3]) / total, 2),
         "pequenos_que_explotan": len(pequenos),
         "ejemplo": (f"«{pequenos[0]['titulo']}» · {pequenos[0]['canal']} ({pequenos[0]['subs']:,} subs) · "
                     f"{pequenos[0]['vistas']:,} vistas") if pequenos else ""}
    r["veredicto"] = veredicto(r)
    return r


def analizar(temas: list[str]) -> list[dict[str, Any]]:
    """Varios temas a la vez, del que tiene más hueco al más saturado."""
    salida = [analizar_tema(t.strip()[:80]) for t in temas[:MAX_TEMAS] if t.strip()]
    orden = {"Hueco: canales nuevos rompen": 0, "Disputado: se puede, con un ángulo propio": 1,
             "Lo acapara un solo canal": 2, "Saturado: lo dominan los grandes": 3, "Poca demanda": 4, "Sin datos": 5}
    return sorted(salida, key=lambda r: (orden.get(r["veredicto"], 9), -r.get("mediana_vistas", 0)))
