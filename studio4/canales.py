"""Canales: cada uno con su YouTube, sus redes, sus producciones y su carpeta. Nada se mezcla entre canales.

Se guardan en producciones/canales.json. El canal activo decide qué producciones ve el panel, a qué canal de
YouTube mira la investigación del guion y en qué carpeta de Vídeos\\STUDIO 4\\<canal> se guarda todo.
Las redes (Instagram, TikTok, Facebook…) se apuntan aquí por canal; conectarlas es aparte y en solo lectura.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from typing import Any

from . import config

REDES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook"}
POR_DEFECTO = [
    {"id": "fourlevel", "nombre": "FourLevel", "redes": {"youtube": "@Four4Level"}},
    {"id": "arigab", "nombre": "ARIGAB", "redes": {"youtube": "@ARIGAB2.0"}},
]
_lock = threading.RLock()


def _archivo():
    return config.PRODUCCIONES / "canales.json"


def _leer() -> dict[str, Any]:
    with _lock:
        try:
            d = json.loads(_archivo().read_text(encoding="utf-8"))
            if d.get("canales"):
                return d
        except (OSError, ValueError):
            pass
        d = {"activo": POR_DEFECTO[0]["id"], "canales": [_limpio(c) for c in POR_DEFECTO]}
        _escribir(d)
        return d


def _escribir(d: dict[str, Any]) -> None:
    with _lock:
        config.PRODUCCIONES.mkdir(parents=True, exist_ok=True)
        tmp = _archivo().with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_archivo())


def _id(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:30] or "canal"


def _usuario(valor: str) -> str:
    """«https://www.tiktok.com/@ari», «ari» o «@ari» → «@ari». Los enlaces de Facebook se guardan tal cual."""
    v = (valor or "").strip()
    if not v:
        return ""
    if "facebook.com/profile.php" in v:      # perfiles sin @usuario: se guarda el enlace
        return v
    if v.startswith("UC") and re.fullmatch(r"UC[\w-]{22}", v):
        return v
    m = re.search(r"@([\w.-]+)", v) or re.search(r"(?:instagram|facebook|tiktok)\.com/([\w.-]+)", v)
    return f"@{m.group(1)}" if m else (v if v.startswith("@") else f"@{v}")


def _limpio(c: dict[str, Any]) -> dict[str, Any]:
    nombre = str(c.get("nombre", "")).strip()[:40]
    if not nombre:
        raise ValueError("Ponle un nombre al canal.")
    redes = {k: _usuario(str((c.get("redes") or {}).get(k, ""))) for k in REDES}
    return {"id": c.get("id") or _id(nombre), "nombre": nombre, "redes": {k: v for k, v in redes.items() if v},
            "voz_nombre": str(c.get("voz_nombre", ""))[:30], "estilo": str(c.get("estilo", ""))[:30],
            "nicho": str(c.get("nicho", "")).strip()[:80], "tono": str(c.get("tono", ""))[:80],
            "fuentes": [u.strip() for u in (c.get("fuentes") or []) if re.match(r"https?://\S+$", str(u).strip())][:6], "publico": str(c.get("publico", ""))[:80]}


def listar() -> list[dict[str, Any]]:
    return _leer()["canales"]


def obtener(cid: str) -> dict[str, Any]:
    for c in listar():
        if c["id"] == cid:
            return c
    raise ValueError(f"No existe el canal «{cid}».")


def activo() -> dict[str, Any]:
    d = _leer()
    return next((c for c in d["canales"] if c["id"] == d.get("activo")), d["canales"][0])


def activar(cid: str) -> dict[str, Any]:
    with _lock:
        d = _leer()
        c = obtener(cid)
        d["activo"] = cid
        _escribir(d)
        return c


def guardar(datos: dict[str, Any]) -> dict[str, Any]:
    """Crea un canal nuevo o actualiza uno existente (si trae su id)."""
    with _lock:
        d = _leer()
        c = _limpio(datos)
        existentes = {x["id"]: i for i, x in enumerate(d["canales"])}
        if datos.get("id") in existentes:
            d["canales"][existentes[datos["id"]]] = c
        else:
            base, n = c["id"], 2
            while c["id"] in existentes:
                c["id"] = f"{base}-{n}"
                n += 1
            d["canales"].append(c)
        _escribir(d)
        return c


def resumen(cid: str, youtube_de, producciones: list[dict[str, Any]]) -> dict[str, Any]:
    """Lo que enseña el panel de control de un canal: sus redes, su YouTube (si se puede leer) y lo hecho en STUDIO.
    `youtube_de(usuario)` devuelve los datos públicos del canal de YouTube; si falla, el panel muestra el error."""
    c = obtener(cid)
    yt, error = None, ""
    if c["redes"].get("youtube"):
        try:
            yt = youtube_de(c["redes"]["youtube"])
        except Exception as e:  # noqa: BLE001 - un canal sin datos no tumba el panel
            error = str(e)
    return {"canal": c, "youtube": yt, "error": error,
            "producciones": {"total": len(producciones), "terminadas": sum(p["estado"] == "terminado" for p in producciones),
                             "en_flow": sum(p["estado"] == "rodando" for p in producciones)}}


def de_produccion(p: dict[str, Any]) -> dict[str, Any]:
    """El canal de una producción (las de antes de los canales son del primero)."""
    try:
        return obtener(p.get("canal") or listar()[0]["id"])
    except ValueError:
        return listar()[0]
