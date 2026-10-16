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

from . import config, director, medios, produccion, registro

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


def recibir(temporal: Path, mime: str, prompt: str = "", pista: Optional[int] = None, origen: str = "flow",
            pid: Optional[str] = None) -> dict[str, Any]:
    """Valida el archivo recibido y lo guarda como toma de la escena que corresponde. Flow y las subidas van a la
    producción activa; la API y las carpetas dicen la suya (`pid`): si cambias de producción a mitad, no se mezclan."""
    pid = pid or produccion.activa()
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
    ext = _EXT_POR_MIME.get(mime.split(";")[0].strip(), ".mp4" if tipo == "video" else ".png")
    if (pista is None and p.get("recoger_para") == "miniatura") or pista == 0:
        for e in p["escenas"]:
            if any(t.get("sha") == sha for t in e["tomas"]):
                return {"ok": True, "repetida": True, "escena": e["orden"]}
        return _recibir_miniatura(pid, temporal, tipo, sha, origen)
    (produccion.carpeta(pid) / "tomas").mkdir(exist_ok=True)
    resultado: dict[str, Any] = {}

    def cambio(q):
        for e in q["escenas"]:
            if any(t.get("sha") == sha for t in e["tomas"]):
                resultado.update(ok=True, repetida=True, escena=e["orden"])
                return
        orden = _escena_destino(q, pista, prompt)
        esc = q["escenas"][orden - 1]
        nombre_video = re.sub(r"[^a-z0-9]+", "-", q.get("titulo", "").lower()).strip("-")[:40] or "video"
        archivo = f"tomas/{nombre_video}_escena_{orden:02d}_toma_{len(esc['tomas']) + 1:02d}_{sha[:6]}{ext}"
        shutil.move(str(temporal), produccion.carpeta(pid) / archivo)
        esc["tomas"].append({"archivo": archivo, "tipo": tipo, "duracion": round(inf["duracion"], 2),
                             "ancho": inf["ancho"], "alto": inf["alto"], "origen": origen,
                             "recibida": time.strftime("%H:%M:%S"), "sha": sha, "prompt": prompt[:300]})
        elegida = esc["tomas"][esc["elegida"]] if esc["elegida"] is not None else None
        if elegida is None or (elegida["tipo"] == "imagen" and tipo == "video"):
            esc["elegida"] = len(esc["tomas"]) - 1
        resultado.update(ok=True, escena=orden, tipo=tipo)

    produccion.modificar(pid, cambio)
    if resultado.get("repetida"):
        return resultado
    orden = resultado["escena"]
    servicio = {"api": "Imágenes por API", "carpeta": "Carpeta importada", "subida": "Subida a mano"}.get(origen, "Google Flow")
    registro.apuntar(servicio, f"{tipo} para escena {orden} ({inf['ancho']}x{inf['alto']})",
                     unidad="tomas", produccion=pid)
    logger.info("Flow → escena %d: %s %dx%d", orden, tipo, inf["ancho"], inf["alto"])
    return resultado


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


def por_animar(esc: dict[str, Any]) -> bool:
    """Escena de vídeo que ya tiene su imagen (generada por API) pero aún no su vídeo: se anima gratis en Flow."""
    if esc.get("tipo_clip", "video") != "video" or esc.get("elegida") is None:
        return False
    toma = esc["tomas"][esc["elegida"]]
    return toma["tipo"] == "imagen" and toma.get("origen") == "api" and not any(t["tipo"] == "video" for t in esc["tomas"])


def prompt_animar(esc: dict[str, Any]) -> str:
    """Para «Fotogramas a vídeo»: la imagen ya fija caras, ropa y luz; el prompt solo describe lo que se mueve."""
    segundos = max(4, min(8, round(esc.get("segundos") or 8)))
    return (f"Bring this exact image to life as a {segundos}-second shot. {esc['prompt_flow']} "
            "Keep the same framing, faces, hair, clothes and lighting as the image; natural, fluid motion; "
            "no text, no new characters.")


def todo_para_flow(p: dict[str, Any]) -> str:
    """Toda la producción en un solo texto para pegarlo en Flow (Flow Agent): primero los personajes, que se crean
    una vez como ingredientes, y después una escena por clip, en orden, con su prompt completo."""
    if not p.get("escenas"):
        raise ValueError("Primero aprueba el guion: hacen falta las escenas.")
    aspecto = config.FORMATOS[p["formato"]]["aspecto"]
    lineas = [f"STUDIO 4 · «{p.get('titulo') or p['tema']}» · {len(p['escenas'])} escenas · formato {aspecto}", "",
              f"Genera UN vídeo por escena, en orden y en formato {aspecto}. Mantén idénticos a los personajes usando sus "
              "ingredientes. Sin texto en pantalla, sin voz ni música (solo sonido ambiente). "
              "Nombra cada clip «Escena N» con su número.", ""]
    if p.get("fichas"):
        lineas += ["PERSONAJES (crea primero su imagen y guárdala como ingrediente):"]
        lineas += [f"- {f['nombre']}: {f['prompt']}" for f in p["fichas"]] + [""]
    for e in p["escenas"]:
        tipo = "imagen" if e.get("tipo_clip") == "imagen" else f"vídeo de {director.duracion_clip(e.get('segundos') or 8)} s"
        lineas += [f"Escena {e['orden']} · {tipo} · voz: «{e['texto_voz']}»",
                   prompt_animar(e) if por_animar(e) else e["prompt_flow"], ""]
    return "\n".join(lineas).strip()


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
        "escenas": [{"escena": e["orden"], "prompt": prompt_animar(e) if por_animar(e) else e["prompt_flow"], "voz": e["texto_voz"],
                     "tipo": e.get("tipo_clip", "video"),
                     "tomas": len(e["tomas"]), "video": any(t["tipo"] == "video" for t in e["tomas"])}
                    for e in p["escenas"]],
        "armado": _extension.get("armado", 0),
        "siguiente": siguiente or ({
            "escena": activa["orden"], "estado": "esperando", "prompt": prompt_animar(activa), "tipo": "video",
            "motivo": "Dale vida a su imagen", "voz": activa["texto_voz"],
            "referencia": _referencia(pid, activa), "referencia_de": "la imagen de esta escena",
        } if por_animar(activa) else {
            "escena": activa["orden"], "estado": "esperando", "prompt": activa["prompt_flow"],
            "tipo": activa.get("tipo_clip", "video"), "motivo": activa.get("motivo_tipo", ""),
            "voz": activa["texto_voz"],
            # La imagen inicial fuerza el mismo plano: solo cuando la escena sigue a la anterior sin corte.
            "referencia": _referencia(pid, previa) if previa and activa.get("continua") else None,
            "referencia_de": f"el final de la escena {previa['orden']}" if previa else "",
        }),
    }
