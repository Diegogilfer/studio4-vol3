"""Higgsfield por API: anima la imagen de una frase (la que haces gratis en Google Flow) en un clip corto de vídeo.

Solo para lo importante: el gancho del inicio (plan «mínima») o el gancho y unos pocos apoyos (plan «media»). Se paga
por segundo desde el saldo de tu cuenta de la API (cloud.higgsfield.ai), aparte del plan de la web. Cada vídeo tiene
un tope: si un clip lo pasaría, no se pide.

Clave: en el almacén de Windows, «Studio4» → HIGGSFIELD_KEY con el formato «clave:secreto» (o HIGGSFIELD_API_KEY y
HIGGSFIELD_API_SECRET por separado).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from . import config, registro, secretos

logger = logging.getLogger("studio4.higgsfield")
BASE = "https://api.higgsfield.ai"
# El modelo de imagen → vídeo (configurable: el catálogo cambia). Precio por segundo reservado por lo alto.
MODELO = "kling-video/v2.1/pro/image-to-video"
PRECIO_SEGUNDO = 0.07
SEGUNDOS = 5
PLANES = {"minima": {"nombre": "Mínima", "clips": 1, "detalle": "solo el gancho del inicio"},
          "media": {"nombre": "Media", "clips": 4, "detalle": "el gancho y hasta 3 apoyos"}}
AJUSTES = config.PRODUCCIONES / "higgsfield.json"
FINALES = {"completed", "failed", "nsfw", "canceled"}


def ajustes() -> dict[str, Any]:
    try:
        a = json.loads(AJUSTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        a = {}
    plan = a.get("plan") if a.get("plan") in PLANES else "minima"
    return {"plan": plan, "tope": float(a.get("tope", 1.0)), "modelo": a.get("modelo") or MODELO,
            "precio_segundo": float(a.get("precio_segundo", PRECIO_SEGUNDO))}


def guardar_ajustes(plan: str | None = None, tope: float | None = None) -> dict[str, Any]:
    a = ajustes()
    if plan is not None:
        if plan not in PLANES:
            raise ValueError("Elige el plan «minima» o «media».")
        a["plan"] = plan
    if tope is not None:
        if not 0 < float(tope) <= 5:
            raise ValueError("El tope por vídeo va de 0,01 a 5 $.")
        a["tope"] = round(float(tope), 2)
    AJUSTES.parent.mkdir(parents=True, exist_ok=True)
    AJUSTES.write_text(json.dumps(a, indent=2), encoding="utf-8")
    return a


def _credencial() -> str:
    clave = secretos.leer("HIGGSFIELD_KEY")
    if clave:
        return clave
    k, s = secretos.leer("HIGGSFIELD_API_KEY"), secretos.leer("HIGGSFIELD_API_SECRET")
    return f"{k}:{s}" if k and s else ""


def disponible() -> bool:
    return bool(_credencial()) and not config.SIN_PAGO


def coste_clip() -> float:
    a = ajustes()
    return round(SEGUNDOS * a["precio_segundo"], 3)


def estado(p: dict[str, Any] | None = None) -> dict[str, Any]:
    """Para el panel: si hay clave, el plan, el tope y (con un vídeo) lo que lleva gastado y los clips que quedan."""
    a = ajustes()
    e = {"disponible": disponible(), "plan": a["plan"], "planes": PLANES, "tope": a["tope"], "coste_clip": coste_clip()}
    if p is not None:
        h = p.get("higgsfield") or {}
        e.update(gastado=round(h.get("gastado", 0.0), 3), clips=h.get("clips", 0))
    return e


def _cabeceras() -> dict[str, str]:
    return {"Authorization": f"Key {_credencial()}", "Content-Type": "application/json", "User-Agent": "Studio4"}


def _subir(imagen: Path) -> str:
    """La imagen a Higgsfield (URL firmada) → su dirección pública para pedir el vídeo."""
    tipo = "image/png" if imagen.suffix.lower() == ".png" else "image/jpeg"
    r = requests.post(f"{BASE}/files/generate-upload-url", headers=_cabeceras(), json={"content_type": tipo}, timeout=30)
    r.raise_for_status()
    d = r.json()
    s = requests.put(d["upload_url"], data=imagen.read_bytes(), headers=d.get("upload_headers") or {"Content-Type": tipo}, timeout=120)
    s.raise_for_status()
    return d["public_url"]


def _url_video(res: Any) -> str:
    """Busca el .mp4 en la respuesta (la forma cambia de un modelo a otro: video.url, videos[0].url…)."""
    if isinstance(res, dict):
        for clave in ("video", "videos", "output", "result"):
            if clave in res:
                u = _url_video(res[clave])
                if u:
                    return u
        u = res.get("url")
        if isinstance(u, str) and u.startswith("http"):
            return u
        for v in res.values():
            u = _url_video(v)
            if u:
                return u
    if isinstance(res, list):
        for v in res:
            u = _url_video(v)
            if u:
                return u
    return ""


def animar(imagen: Path, prompt: str, destino: Path, produccion: str = "", avisar=None) -> Path:
    """Imagen → clip de SEGUNDOS s. No comprueba el tope (eso lo hace animar_frase, que sabe del vídeo)."""
    if not disponible():
        raise ValueError("Falta la clave de Higgsfield (Herramientas → Higgsfield).")
    a = ajustes()
    url_imagen = _subir(imagen)
    r = requests.post(f"{BASE}/{a['modelo']}", headers=_cabeceras(), timeout=60,
                      json={"prompt": prompt[:1200], "image_url": url_imagen, "duration": SEGUNDOS})
    if r.status_code in (401, 403):
        raise ValueError("Higgsfield no aceptó la clave: revísala en cloud.higgsfield.ai.")
    if r.status_code == 402:
        raise ValueError("Tu saldo de la API de Higgsfield no alcanza: recarga en cloud.higgsfield.ai.")
    r.raise_for_status()
    pedido = r.json()
    estado_url = pedido.get("status_url") or f"{BASE}/requests/{pedido['request_id']}/status"
    fin = time.time() + 900
    while True:
        e = requests.get(estado_url, headers=_cabeceras(), timeout=30)
        e.raise_for_status()
        d = e.json()
        st = d.get("status", "")
        if st in FINALES:
            break
        if time.time() > fin:
            raise RuntimeError("Higgsfield tardó más de 15 minutos: vuelve a intentarlo luego.")
        if avisar:
            avisar("Higgsfield está animando" + (" (en cola)" if st == "queued" else ""), 50)
        time.sleep(6)
    if st == "nsfw":
        raise ValueError("El filtro de Higgsfield rechazó la imagen (no se cobra): prueba con otra.")
    if st != "completed":
        raise RuntimeError(f"Higgsfield no pudo hacer el clip ({st}).")
    url = _url_video(d)
    if not url:
        raise RuntimeError(f"Higgsfield terminó sin vídeo: {str(d)[:160]}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as v:
        v.raise_for_status()
        with destino.open("wb") as fh:
            for trozo in v.iter_content(1 << 20):
                fh.write(trozo)
    coste = SEGUNDOS * a["precio_segundo"]
    registro.apuntar("Higgsfield · imagen a vídeo", f"{a['modelo']} · {SEGUNDOS} s", cantidad=SEGUNDOS, unidad="segundos",
                     produccion=produccion, usd=coste)
    return destino


def comprobar(p: dict[str, Any]) -> None:
    """Antes de gastar: plan (cuántos clips por vídeo) y tope en dólares."""
    a = ajustes()
    h = p.get("higgsfield") or {}
    plan = PLANES[a["plan"]]
    if h.get("clips", 0) >= plan["clips"]:
        raise ValueError(f"Plan {plan['nombre']}: {plan['clips']} clip(s) por vídeo y ya están hechos. Cámbialo en Herramientas si quieres más.")
    if h.get("gastado", 0.0) + coste_clip() > a["tope"] + 1e-9:
        raise ValueError(f"Este clip ({coste_clip():.2f} $) pasaría el tope de {a['tope']:.2f} $ por vídeo (van {h.get('gastado', 0.0):.2f} $).")


def animar_frase(mid: str, n: int) -> None:
    """La imagen de la frase n → clip animado que la sustituye en el montaje (la imagen se guarda por si lo quitas)."""
    from . import montaje
    p = montaje.cargar(mid)
    f = next((x for x in p["frases"] if x["n"] == n), None)
    if not f or not f.get("imagen"):
        raise ValueError("Pon primero una imagen en esa frase (por ejemplo, la que hiciste en Google Flow).")
    comprobar(p)
    imagen = montaje.carpeta_imagenes(mid) / f["imagen"]["archivo"]
    prompt = (f"Cinematic subtle camera move, natural motion, keep the composition and style of the image. Scene: {f['texto'][:400]}. "
              "No text, no logos.")

    def fase():
        nombre = f"hf_{n:03d}_{int(time.time())}.mp4"
        animar(imagen, prompt, montaje.carpeta(mid) / "videos" / nombre, produccion=mid,
               avisar=lambda fase_, prog: montaje._avisar(mid, fase_, prog))
        coste = coste_clip()

        def cambio(q):
            fr = next((x for x in q["frases"] if x["n"] == n), None)
            if fr is not None:
                fr["video"] = {"archivo": nombre, "credito": "Animado con Higgsfield", "higgsfield": True}
            h = q.setdefault("higgsfield", {"gastado": 0.0, "clips": 0})
            h["gastado"] = round(h.get("gastado", 0.0) + coste, 4)
            h["clips"] = h.get("clips", 0) + 1
            q.update(previa="", final=None, short=None)
        montaje.modificar(mid, cambio)
    montaje._en_fondo(mid, "Higgsfield", fase)


def quitar_animacion(mid: str, n: int) -> None:
    """La frase vuelve a su imagen fija (lo gastado no se devuelve: ya se cobró)."""
    from . import montaje

    def cambio(q):
        fr = next((x for x in q["frases"] if x["n"] == n), None)
        if fr is not None and (fr.get("video") or {}).get("higgsfield"):
            fr.pop("video")
            q.update(previa="", final=None, short=None)
    montaje.modificar(mid, cambio)
