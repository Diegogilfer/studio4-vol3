"""Studio 4 en la nube (Supabase): copia los DATOS de lo que genera el estudio (canales, vídeos con sus textos, ideas
guardadas y tendencias) para no perderlos y tenerlos en cualquier sitio. Los vídeos y archivos pesados no van aquí.

El estudio entra con TU cuenta (SUPABASE_EMAIL + SUPABASE_CLAVE en .env) y la clave publicable: la base solo deja ver
y escribir a su dueño (seguridad por fila), así que el día que Studio 4 se venda cada cliente verá solo lo suyo.
Sin cuenta configurada no hace nada. Si no hay internet, lo intenta en la siguiente vuelta: el PC sigue mandando.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests

from . import canales, montaje, radar

logger = logging.getLogger("studio4.nube")
CADA_SEGUNDOS = 30 * 60
_sesion: dict[str, Any] = {}
_cerrojo = threading.Lock()
estado: dict[str, Any] = {"ultima": "", "error": "", "subidos": {}}


def _cfg() -> dict[str, str]:
    return {k: os.getenv(k, "").strip() for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_EMAIL", "SUPABASE_CLAVE")}


def disponible() -> bool:
    return all(_cfg().values())


def _token() -> str:
    """Inicia sesión con la cuenta del dueño (y la renueva antes de que caduque)."""
    c = _cfg()
    if _sesion.get("token") and _sesion.get("caduca", 0) > time.time() + 60:
        return _sesion["token"]
    r = requests.post(f"{c['SUPABASE_URL']}/auth/v1/token", params={"grant_type": "password"}, timeout=20,
                      headers={"apikey": c["SUPABASE_PUBLISHABLE_KEY"]},
                      json={"email": c["SUPABASE_EMAIL"], "password": c["SUPABASE_CLAVE"]})
    if r.status_code != 200:
        raise RuntimeError("La nube no acepta la cuenta: revisa SUPABASE_EMAIL y SUPABASE_CLAVE en .env.")
    d = r.json()
    _sesion.update(token=d["access_token"], caduca=time.time() + int(d.get("expires_in", 3600)))
    return _sesion["token"]


def _subir(tabla: str, filas: list[dict[str, Any]], conflicto: str = "") -> int:
    if not filas:
        return 0
    c = _cfg()
    r = requests.post(f"{c['SUPABASE_URL']}/rest/v1/{tabla}", timeout=60, json=filas,
                      params={"on_conflict": conflicto} if conflicto else None,
                      headers={"apikey": c["SUPABASE_PUBLISHABLE_KEY"], "Authorization": f"Bearer {_token()}",
                               "Prefer": "resolution=merge-duplicates,return=minimal"})
    if r.status_code >= 300:
        raise RuntimeError(f"La nube rechazó {tabla}: {r.status_code} {r.text[:200]}")
    return len(filas)


def _filas() -> dict[str, list[dict[str, Any]]]:
    from . import buscador
    ids_canales = {c["id"] for c in canales.listar()}
    filas: dict[str, list[dict[str, Any]]] = {"canales": [], "videos": [], "ideas": [], "tendencias": []}
    for c in canales.listar():
        filas["canales"].append({"id": c["id"], "nombre": c["nombre"], "nicho": c.get("nicho", ""), "tono": c.get("tono", ""),
                                 "publico": c.get("publico", ""), "voz": c.get("voz_nombre", ""), "redes": c.get("redes") or {},
                                 "fuentes": c.get("fuentes") or []})
        for i in buscador.leer(c["id"])["guardadas"]:
            filas["ideas"].append({"id": f"{c['id']}-{i['id']}", "canal": c["id"], "titulo": i["titulo"], "gancho": i.get("gancho", ""),
                                   "angulo": i.get("angulo", ""), "formato": i.get("formato", ""), "fuentes": i.get("fuentes") or [],
                                   "estado": "guardada"})
        for s in radar.guardadas(20, c["id"]):
            filas["tendencias"].append({"canal": c["id"], "dia": s.get("dia"), "tema": s["tema"], "fuerza": s.get("fuerza"),
                                        "titulares": s.get("titulares") or []})
    for v in montaje.listar():
        try:
            p = montaje.cargar(v["id"])
        except ValueError:
            continue
        canal = p.get("canal") or "fourlevel"
        filas["videos"].append({"id": p["id"], "canal": canal if canal in ids_canales else None, "titulo": p["titulo"],
                                "guion": p.get("guion", ""), "paso": v["paso"], "terminado": bool(p.get("final")),
                                "textos": p.get("textos")})
    filas["tendencias"] = [t for t in filas["tendencias"] if t["dia"]]
    return filas


def sincronizar() -> dict[str, int]:
    """Sube todo lo de ahora (si ya estaba, lo actualiza). Devuelve cuántas filas de cada cosa."""
    if not disponible():
        raise ValueError("La nube aún no tiene cuenta: pon SUPABASE_EMAIL y SUPABASE_CLAVE en .env.")
    with _cerrojo:
        f = _filas()
        subidos = {"canales": _subir("canales", f["canales"]), "videos": _subir("videos", f["videos"]),
                   "ideas": _subir("ideas", f["ideas"]),
                   "tendencias": _subir("tendencias", f["tendencias"], "dueno,canal,dia,tema")}
        estado.update(ultima=time.strftime("%Y-%m-%d %H:%M"), error="", subidos=subidos)
        return subidos


def vigilar() -> None:
    """Cada 30 minutos, en segundo plano, mientras el estudio está abierto."""
    while True:
        if disponible():
            try:
                sincronizar()
            except Exception as e:  # noqa: BLE001 - sin internet o la nube caída: se reintenta en la siguiente vuelta
                estado["error"] = str(e)[:200]
                logger.warning("Nube: %s", e)
        time.sleep(CADA_SEGUNDOS)
