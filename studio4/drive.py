"""Google Drive: cada vídeo terminado sube su carpeta de entrega entera (los 3 formatos, miniaturas, subtítulos,
textos y proyecto) a «Studio 4/<canal>/<fecha · título>» en el Drive del autor.

Permiso mínimo (drive.file): Studio 4 solo ve y toca los archivos que él mismo sube, nunca el resto del Drive.
Conexión propia («Conectar Google Drive»): Google no deja pedir los permisos de YouTube y de Drive juntos. Usa la
misma credencial de Google Cloud (secrets/youtube_client.json, tipo escritorio) y guarda su permiso aparte
(secrets/drive_token.json). Solo hace falta tener la Google Drive API activada en ese proyecto.
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
from pathlib import Path
from typing import Any

import requests

from . import config


logger = logging.getLogger("studio4.drive")
PERMISO = "https://www.googleapis.com/auth/drive.file"
TOKEN = config.RAIZ / "secrets" / "drive_token.json"
VOLVER = f"http://localhost:{config.PUERTO}/drive/volver"
TROZO = 8 * 1024 * 1024   # subida reanudable en trozos de 8 MB (múltiplo de 256 KB, como pide Google)
_pendiente: dict[str, str] = {}
_lock = threading.Lock()


def conectado() -> bool:
    try:
        return bool(json.loads(TOKEN.read_text(encoding="utf-8")).get("refresh_token"))
    except (OSError, ValueError):
        return False


def estado() -> dict[str, Any]:
    from . import youtube
    return {"configurado": youtube.CLIENTE.exists(), "conectado": conectado()}


def url_autorizacion() -> str:
    from . import youtube
    c = youtube._cliente()
    estado_ = secrets.token_urlsafe(16)
    verificador = secrets.token_urlsafe(48)
    _pendiente[estado_] = verificador
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": VOLVER, "response_type": "code", "scope": PERMISO,
        "access_type": "offline", "prompt": "consent", "state": estado_, "code_challenge": reto, "code_challenge_method": "S256"})


def completar(codigo: str, estado_: str) -> None:
    from . import youtube
    verificador = _pendiente.pop(estado_, None)
    if not verificador:
        raise ValueError("La autorización caducó o no la pidió Studio 4: vuelve a pulsar «Conectar Google Drive».")
    c = youtube._cliente()
    r = requests.post(c.get("token_uri", "https://oauth2.googleapis.com/token"), timeout=20, data={
        "client_id": c["client_id"], "client_secret": c["client_secret"], "code": codigo, "code_verifier": verificador,
        "grant_type": "authorization_code", "redirect_uri": VOLVER})
    if not r.ok:
        raise RuntimeError(f"Google no aceptó la autorización: {r.text[:200]}")
    t = r.json()
    TOKEN.parent.mkdir(exist_ok=True)
    TOKEN.write_text(json.dumps({"client_id": c["client_id"], "client_secret": c["client_secret"], "token_uri": c.get("token_uri"),
                                 "refresh_token": t["refresh_token"], "token": t["access_token"],
                                 "caduca": time.time() + int(t.get("expires_in", 3600)) - 60}, indent=2), encoding="utf-8")


def _acceso() -> str:
    if not conectado():
        raise ValueError("Google Drive no está conectado: pulsa «Conectar Google Drive» en Herramientas.")
    with _lock:
        t = json.loads(TOKEN.read_text(encoding="utf-8"))
        if t.get("token") and time.time() < float(t.get("caduca", 0)):
            return t["token"]
        r = requests.post(t.get("token_uri") or "https://oauth2.googleapis.com/token", timeout=20, data={
            "client_id": t["client_id"], "client_secret": t["client_secret"], "refresh_token": t["refresh_token"],
            "grant_type": "refresh_token"})
        if r.status_code == 400 and "invalid_grant" in r.text:
            TOKEN.unlink(missing_ok=True)   # Google retiró el permiso (app en modo «Prueba»: dura 7 días)
            raise ValueError("El acceso a Drive caducó: vuelve a pulsar «Conectar Google Drive».")
        r.raise_for_status()
        d = r.json()
        t.update(token=d["access_token"], caduca=time.time() + int(d.get("expires_in", 3600)) - 60)
        TOKEN.write_text(json.dumps(t, indent=2), encoding="utf-8")
        return t["token"]


def _carpeta(nombre: str, padre: str | None) -> str:
    """La carpeta (la crea si no existe) dentro de `padre` (o en la raíz del Drive)."""
    cab = {"Authorization": f"Bearer {_acceso()}"}
    nombre_q = nombre.replace("\\", "\\\\").replace("'", "\\'")
    q = f"name='{nombre_q}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if padre:
        q += f" and '{padre}' in parents"
    hallada = requests.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"}, headers=cab, timeout=30)
    hallada.raise_for_status()
    if hallada.json().get("files"):
        return hallada.json()["files"][0]["id"]
    meta = {"name": nombre, "mimeType": "application/vnd.google-apps.folder", **({"parents": [padre]} if padre else {})}
    r = requests.post("https://www.googleapis.com/drive/v3/files", headers=cab, json=meta, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _subir_archivo(archivo: Path, padre: str) -> None:
    """Subida reanudable por trozos: sirve para vídeos grandes y aguanta cortes de red."""
    cab = {"Authorization": f"Bearer {_acceso()}"}
    tam = archivo.stat().st_size
    inicio = requests.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable", timeout=30,
                           headers={**cab, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": str(tam)},
                           data=json.dumps({"name": archivo.name, "parents": [padre]}).encode("utf-8"))
    inicio.raise_for_status()
    sesion = inicio.headers["Location"]
    with archivo.open("rb") as f:
        enviado = 0
        while enviado < tam or tam == 0:
            trozo = f.read(TROZO)
            fin = enviado + len(trozo) - 1
            r = requests.put(sesion, data=trozo, timeout=300, headers={
                "Content-Length": str(len(trozo)), **({"Content-Range": f"bytes {enviado}-{fin}/{tam}"} if tam else {})})
            if r.status_code not in (200, 201, 308):
                r.raise_for_status()
            enviado += len(trozo)
            if tam == 0 or r.status_code in (200, 201):
                break


def subir_carpeta(carpeta: Path, canal: str, avisar=lambda _t: None) -> str:
    """Sube la carpeta de entrega a «Studio 4/<canal>/<carpeta>», con sus subcarpetas. Devuelve el enlace."""
    raiz = _carpeta("Studio 4", None)
    destino = _carpeta(carpeta.name, _carpeta(canal, raiz))
    ids = {carpeta: destino}
    archivos = sorted(f for f in carpeta.rglob("*") if f.is_file())
    for k, f in enumerate(archivos, 1):
        padre_local = f.parent
        if padre_local not in ids:
            ids[padre_local] = _carpeta(padre_local.name, ids[padre_local.parent])
        avisar(f"Subiendo a Drive ({k} de {len(archivos)}): {f.name}")
        _subir_archivo(f, ids[padre_local])
    return f"https://drive.google.com/drive/folders/{destino}"
