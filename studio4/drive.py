"""Google Drive: cada vídeo terminado sube su carpeta de entrega entera (los 3 formatos, miniaturas, subtítulos,
textos y proyecto) a «Studio 4/<canal>/<fecha · título>» en el Drive del autor.

Permiso mínimo (drive.file): Studio 4 solo ve y toca los archivos que él mismo sube, nunca el resto del Drive.
Usa el MISMO acceso de Google que YouTube (secrets/youtube_client.json): un solo «Conectar con Google» sirve para las
dos cosas. Solo hay que tener la Google Drive API activada en el proyecto de Google Cloud.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests


logger = logging.getLogger("studio4.drive")
PERMISO = "https://www.googleapis.com/auth/drive.file"
TROZO = 8 * 1024 * 1024   # subida reanudable en trozos de 8 MB (múltiplo de 256 KB, como pide Google)


def conectado() -> bool:
    """Conectado a Google Y con el permiso de Drive (un acceso antiguo, solo de YouTube, no vale)."""
    from . import youtube
    if not youtube.conectado():
        return False
    try:
        return PERMISO in json.loads(youtube.TOKEN.read_text(encoding="utf-8")).get("scopes", [])
    except (OSError, ValueError):
        return False


def estado() -> dict[str, Any]:
    from . import youtube
    return {"configurado": youtube.CLIENTE.exists(), "conectado": conectado()}


def _acceso() -> str:
    from . import youtube
    if not conectado():
        raise ValueError("Google Drive no está conectado: pulsa «Conectar con Google» en el panel.")
    return youtube._acceso()


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
