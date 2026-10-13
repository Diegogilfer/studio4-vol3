"""Fase 4 · Google Flow (tu suscripción): la extensión del navegador trae a STUDIO 4 cada vídeo o imagen
que generas en Flow, y aquí se coloca en su escena.

Flow saca varias variantes por prompt: todas se guardan como «tomas» de la escena y la primera queda
elegida (un vídeo siempre gana a una imagen). En el panel puedes elegir otra.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from . import config, medios, produccion, registro

logger = logging.getLogger("studio4.flow")
CONECTADA_S = 90          # la extensión saluda cada pocos segundos mientras Flow está abierto
LADO_MINIMO = 256

_extension: dict[str, Any] = {"ultima": 0.0, "version": ""}
_eventos: list[dict[str, Any]] = []   # lo último que vio, mandó o falló la extensión (para diagnosticar)
VERSION_EXTENSION = "2.2.0"           # la del manifest: si la cargada es más vieja, el panel pide recargarla

_EXT_POR_MIME = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
                 "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def latido(version: str = "") -> None:
    _extension["ultima"] = time.time()
    if version:
        _extension["version"] = version[:20]


def anotar_evento(tipo: str, detalle: str) -> None:
    _eventos.insert(0, {"t": time.strftime("%H:%M:%S"), "tipo": str(tipo)[:20], "detalle": str(detalle)[:300]})
    del _eventos[60:]
    if tipo in ("error", "rechazada"):
        logger.warning("Flow %s: %s", tipo, detalle)


def estado_extension() -> dict[str, Any]:
    ultima = _extension["ultima"]
    return {"conectada": bool(ultima) and time.time() - ultima < CONECTADA_S,
            "version": _extension["version"], "ultima": ultima, "eventos": _eventos[:25],
            "desactualizada": bool(_extension["version"]) and _extension["version"] != VERSION_EXTENSION}


def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", (texto or "").lower())}


def _escena_destino(p: dict[str, Any], pista: Optional[int], prompt: str) -> int:
    n = len(p["escenas"])
    if pista and 1 <= pista <= n:
        return pista
    recibidas = _palabras(prompt)
    if len(recibidas) >= 4:  # Flow a veces deja el prompt en la página: si coincide, manda él
        puntos = [(len(recibidas & _palabras(e["prompt_flow"])) / len(recibidas), e["orden"]) for e in p["escenas"]]
        mejor, orden = max(puntos)
        if mejor >= 0.6:
            return orden
    if 1 <= p.get("escena_activa", 0) <= n:
        return p["escena_activa"]
    sin_video = [e["orden"] for e in p["escenas"] if not any(t["tipo"] == "video" for t in e["tomas"])]
    return sin_video[0] if sin_video else n


def recibir(temporal: Path, mime: str, prompt: str = "", pista: Optional[int] = None, origen: str = "flow") -> dict[str, Any]:
    """Valida el archivo recibido y lo guarda como toma de la escena que corresponde."""
    pid = produccion.activa()
    if not pid:
        raise ValueError("No hay ninguna producción activa en STUDIO 4: crea una antes de generar en Flow.")
    p = produccion.cargar(pid)
    if not p["escenas"]:
        raise ValueError("La producción aún no tiene escenas: espera a que Gemini termine el plan.")

    inf = medios.info(temporal)
    tipo = "video" if mime.startswith("video/") or inf["duracion"] > 0.5 else "imagen"
    if min(inf["ancho"], inf["alto"]) < LADO_MINIMO:
        raise ValueError(f"Demasiado pequeña ({inf['ancho']}x{inf['alto']}): parece una miniatura de Flow.")

    h = hashlib.sha256()
    with temporal.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    sha = h.hexdigest()
    for e in p["escenas"]:
        if any(t.get("sha") == sha for t in e["tomas"]):
            return {"ok": True, "repetida": True, "escena": e["orden"]}

    ext = _EXT_POR_MIME.get(mime.split(";")[0].strip(), ".mp4" if tipo == "video" else ".png")
    if (pista is None and p.get("recoger_para") == "miniatura") or pista == 0:
        return _recibir_miniatura(pid, temporal, tipo, sha, origen)
    orden = _escena_destino(p, pista, prompt)
    (produccion.carpeta(pid) / "tomas").mkdir(exist_ok=True)

    def cambio(q):
        esc = q["escenas"][orden - 1]
        archivo = f"tomas/escena_{orden:02d}_{len(esc['tomas']) + 1:02d}_{sha[:6]}{ext}"
        shutil.move(str(temporal), produccion.carpeta(pid) / archivo)
        esc["tomas"].append({"archivo": archivo, "tipo": tipo, "duracion": round(inf["duracion"], 2),
                             "ancho": inf["ancho"], "alto": inf["alto"], "origen": origen,
                             "recibida": time.strftime("%H:%M:%S"), "sha": sha, "prompt": prompt[:300]})
        elegida = esc["tomas"][esc["elegida"]] if esc["elegida"] is not None else None
        if elegida is None or (elegida["tipo"] == "imagen" and tipo == "video"):
            esc["elegida"] = len(esc["tomas"]) - 1

    produccion.modificar(pid, cambio)
    registro.apuntar("Google Flow", f"{tipo} para escena {orden} ({inf['ancho']}x{inf['alto']})",
                     unidad="tomas", produccion=pid)
    logger.info("Flow → escena %d: %s %dx%d", orden, tipo, inf["ancho"], inf["alto"])
    return {"ok": True, "escena": orden, "tipo": tipo}


def _recibir_miniatura(pid: str, temporal: Path, tipo: str, sha: str, origen: str) -> dict[str, Any]:
    carpeta = produccion.carpeta(pid) / "miniaturas" / "fuentes"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"f_{sha[:10]}.jpg"
    if tipo == "video":  # de un vídeo, su fotograma central
        medios.ffmpeg("-ss", f"{medios.duracion(temporal) / 2:.2f}", "-i", str(temporal), "-frames:v", "1", "-q:v", "2", str(destino))
    else:
        from PIL import Image
        Image.open(temporal).convert("RGB").save(destino, "JPEG", quality=95)
    produccion.anadir_fuente_miniatura(pid, destino.relative_to(produccion.carpeta(pid)).as_posix(),
                                       "flow" if origen == "flow" else "subida")
    registro.apuntar("Google Flow", "imagen para la miniatura", unidad="tomas", produccion=pid)
    return {"ok": True, "escena": 0, "tipo": "miniatura"}


def marcar_miniatura() -> None:
    """Lo próximo que generes en Flow va a la miniatura (hasta que vuelvas a elegir una escena)."""
    pid = produccion.activa()
    if not pid:
        raise ValueError("No hay producción activa")
    produccion.modificar(pid, lambda p: p.update(recoger_para="miniatura"))
    _extension["armado"] = time.time()


def marcar_activa(orden: int) -> None:
    pid = produccion.activa()
    if not pid:
        raise ValueError("No hay producción activa")

    def cambio(p):
        if not 1 <= orden <= len(p["escenas"]):
            raise ValueError(f"No existe la escena {orden}")
        p["escena_activa"] = orden
        p["recoger_para"] = "escenas"
    produccion.modificar(pid, cambio)
    # Al elegir/copiar una escena (desde Flow o desde el panel), la extensión empieza a recoger lo nuevo.
    _extension["armado"] = time.time()


def _referencia(pid: str, esc: dict[str, Any]) -> Optional[str]:
    """Último fotograma de la toma elegida: pegado en Flow como imagen inicial, la escena siguiente encaja."""
    if esc.get("elegida") is None:
        return None
    toma = esc["tomas"][esc["elegida"]]
    if toma["tipo"] == "imagen":
        return f"/media/{pid}/{toma['archivo']}"
    base = produccion.carpeta(pid)
    ref = base / "ref" / (Path(toma["archivo"]).stem + "_fin.jpg")
    if not ref.exists():
        ref.parent.mkdir(exist_ok=True)
        try:
            medios.ultimo_fotograma(base / toma["archivo"], ref)
        except RuntimeError as e:
            logger.warning("Sin fotograma de referencia: %s", e)
            return None
    return f"/media/{pid}/ref/{ref.name}"


def sesion_para_extension() -> dict[str, Any]:
    """Lo que muestra la extensión dentro de Flow: la escena que toca, su prompt y la imagen de referencia."""
    pid = produccion.activa()
    if not pid:
        return {"viva": False}
    p = produccion.cargar(pid)
    if not p["escenas"]:
        return {"viva": False, "titulo": p["tema"], "preparando": p["trabajo"].get("fase", "")}
    activa = p["escenas"][p["escena_activa"] - 1]
    previa = p["escenas"][activa["orden"] - 2] if activa["orden"] > 1 else None
    siguiente = None
    if p.get("recoger_para") == "miniatura":
        m = p.get("miniaturas") or {}
        prompt = m.get("prompt_flow") or (
            f"Expressive close-up for a video thumbnail about: {p.get('titulo') or p['tema']}. High contrast, clean background, "
            f"subject large and centered, no text. Style: {p.get('estilo_en', '')}")
        siguiente = {"escena": 0, "estado": "miniatura", "prompt": prompt,
                     "voz": "Imagen para la miniatura: genera una IMAGEN (no un vídeo)", "referencia": None, "referencia_de": ""}
    return {
        "viva": True,
        "titulo": p["titulo"] or p["tema"],
        "total": len(p["escenas"]),
        "aspecto": config.FORMATOS[p["formato"]]["aspecto"],
        "escenas": [{"escena": e["orden"], "prompt": e["prompt_flow"], "voz": e["texto_voz"],
                     "tomas": len(e["tomas"]), "video": any(t["tipo"] == "video" for t in e["tomas"])}
                    for e in p["escenas"]],
        "armado": _extension.get("armado", 0),
        "siguiente": siguiente or {
            "escena": activa["orden"], "estado": "esperando", "prompt": activa["prompt_flow"],
            "voz": activa["texto_voz"],
            "referencia": _referencia(pid, previa) if previa else None,
            "referencia_de": f"el final de la escena {previa['orden']}" if previa else "",
        },
    }
