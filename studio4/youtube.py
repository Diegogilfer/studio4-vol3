"""YouTube en solo lectura (tu misma cuenta de Google): datos de tu canal y lo que ya existe sobre un tema.
STUDIO no publica nada: pide únicamente los permisos youtube.readonly y yt-analytics.readonly.

Sirve a la investigación del guion: qué títulos funcionan en tu canal (tono) y qué vídeos hay ya sobre la
idea (para buscar un ángulo distinto en vez de repetir lo mismo).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
import urllib.parse
from typing import Any

import requests

from . import config, registro

logger = logging.getLogger("studio4.youtube")

CLIENTE = config.RAIZ / "secrets" / "youtube_client.json"
TOKEN = config.RAIZ / "secrets" / "youtube_token.json"
PERMISOS = ["https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly"]
API = "https://www.googleapis.com/youtube/v3"
VOLVER = f"http://localhost:{config.PUERTO}/youtube/volver"

_lock = threading.Lock()
_pendiente: dict[str, str] = {}               # state → verificador PKCE de la autorización en curso
_cache: dict[str, tuple[float, Any]] = {}


def _cliente() -> dict[str, str]:
    if not CLIENTE.exists():
        raise RuntimeError("Falta secrets/youtube_client.json (credencial OAuth de tu proyecto de Google Cloud).")
    d = json.loads(CLIENTE.read_text(encoding="utf-8"))
    return d.get("installed") or d.get("web") or {}


def conectado() -> bool:
    try:
        return bool(json.loads(TOKEN.read_text(encoding="utf-8")).get("refresh_token"))
    except (OSError, ValueError):
        return False


# --- Autorización (una vez; solo lectura) --------------------------------------------------------
def url_autorizacion() -> str:
    c = _cliente()
    estado = secrets.token_urlsafe(16)
    verificador = secrets.token_urlsafe(48)
    _pendiente[estado] = verificador
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": VOLVER, "response_type": "code", "scope": " ".join(PERMISOS),
        "access_type": "offline", "prompt": "consent", "state": estado,
        "code_challenge": reto, "code_challenge_method": "S256",
    })


def completar(codigo: str, estado: str) -> None:
    verificador = _pendiente.pop(estado, None)
    if not verificador:
        raise ValueError("La autorización caducó o no la pidió STUDIO: vuelve a pulsar «Conectar YouTube».")
    c = _cliente()
    r = requests.post(c.get("token_uri", "https://oauth2.googleapis.com/token"), timeout=20, data={
        "client_id": c["client_id"], "client_secret": c["client_secret"], "code": codigo, "code_verifier": verificador,
        "grant_type": "authorization_code", "redirect_uri": VOLVER})
    if not r.ok:
        raise RuntimeError(f"Google no aceptó la autorización: {r.text[:200]}")
    d = r.json()
    _guardar({"client_id": c["client_id"], "client_secret": c["client_secret"], "token_uri": c.get("token_uri"),
              "refresh_token": d["refresh_token"], "token": d["access_token"],
              "caduca": time.time() + int(d.get("expires_in", 3600)) - 60, "scopes": d.get("scope", "").split()})
    _cache.clear()


def _guardar(t: dict[str, Any]) -> None:
    TOKEN.parent.mkdir(exist_ok=True)
    TOKEN.write_text(json.dumps(t, indent=2), encoding="utf-8")


def desconectar() -> None:
    TOKEN.unlink(missing_ok=True)
    _cache.clear()


def _acceso() -> str:
    with _lock:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t.get("token") and time.time() < float(t.get("caduca", 0)):
            return t["token"]
        r = requests.post(t.get("token_uri") or "https://oauth2.googleapis.com/token", timeout=20, data={
            "client_id": t["client_id"], "client_secret": t["client_secret"],
            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code == 400 and "invalid_grant" in r.text:
            desconectar()  # Google retiró el permiso (p. ej. app en modo «Prueba»: dura 7 días)
            raise RuntimeError("El acceso a YouTube caducó: vuelve a pulsar «Conectar YouTube».")
        r.raise_for_status()
        d = r.json()
        t.update(token=d["access_token"], caduca=time.time() + int(d.get("expires_in", 3600)) - 60)
        _guardar(t)
        return t["token"]


def _get(ruta: str, **params: Any) -> dict[str, Any]:
    r = requests.get(f"{API}/{ruta}", params=params, timeout=20, headers={"Authorization": f"Bearer {_acceso()}"})
    if not r.ok:
        raise RuntimeError(f"YouTube {ruta}: {r.status_code} {r.text[:200]}")
    return r.json()


def _guardado(clave: str, segundos: int, fn):
    hit = _cache.get(clave)
    if hit and time.time() - hit[0] < segundos:
        return hit[1]
    valor = fn()
    _cache[clave] = (time.time(), valor)
    return valor


def _estadisticas(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    d = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[:50]))
    return [{"titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
             "vistas": int(v["statistics"].get("viewCount", 0)), "publicado": v["snippet"]["publishedAt"][:10],
             "duracion": v["contentDetails"].get("duration", ""), "url": f"https://youtu.be/{v['id']}"}
            for v in d.get("items", [])]


# --- Lo que usa STUDIO ---------------------------------------------------------------------------
def canal() -> dict[str, Any]:
    """Tu canal y tus vídeos más vistos (se guarda 15 min para no gastar cupo)."""
    def leer():
        d = _get("channels", part="snippet,statistics,contentDetails", mine="true")
        if not d.get("items"):
            raise RuntimeError("Esta cuenta de Google no tiene canal de YouTube.")
        ch = d["items"][0]
        subidas = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        lista = _get("playlistItems", part="contentDetails", playlistId=subidas, maxResults=50)
        videos = _estadisticas([i["contentDetails"]["videoId"] for i in lista.get("items", [])])
        registro.apuntar("YouTube (lectura)", "datos del canal", unidad="consultas")
        return {"nombre": ch["snippet"]["title"], "suscriptores": int(ch["statistics"].get("subscriberCount", 0)),
                "vistas": int(ch["statistics"].get("viewCount", 0)), "videos": int(ch["statistics"].get("videoCount", 0)),
                "foto": ch["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                "mas_vistos": sorted(videos, key=lambda v: -v["vistas"])[:10], "recientes": videos[:10]}
    return _guardado("canal", 900, leer)


def sobre_el_tema(tema: str, n: int = 8) -> list[dict[str, Any]]:
    """Los vídeos con más vistas sobre la idea, en español (cuesta 100 unidades de las 10.000 diarias)."""
    def buscar():
        d = _get("search", part="snippet", q=tema, type="video", order="relevance", maxResults=n,
                 relevanceLanguage="es", safeSearch="none")
        registro.apuntar("YouTube (lectura)", f"búsqueda «{tema[:40]}»", unidad="consultas")
        return sorted(_estadisticas([i["id"]["videoId"] for i in d.get("items", [])]), key=lambda v: -v["vistas"])
    return _guardado(f"tema:{tema.lower()}", 3600, buscar)


def contexto_para_guion(tema: str) -> dict[str, Any]:
    """Lo que la investigación pasa a DeepSeek. Si YouTube no está conectado o falla, vacío (no bloquea)."""
    if not conectado():
        return {}
    salida: dict[str, Any] = {}
    try:
        salida["competencia"] = sobre_el_tema(tema)
    except Exception as e:  # noqa: BLE001
        logger.warning("YouTube (búsqueda): %s", e)
    try:
        c = canal()
        salida["tu_canal"] = {"nombre": c["nombre"], "mas_vistos": c["mas_vistos"][:8]}
    except Exception as e:  # noqa: BLE001
        logger.warning("YouTube (canal): %s", e)
    return salida
