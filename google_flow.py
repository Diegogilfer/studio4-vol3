"""
google_flow.py - Receptor e Integrador de Google Flow para STUDIO 4 Vol. 3
Inspirado en la tecnología de producción de STUDIO #4 y la extensión de navegador de Diego.

Funcionalidad:
1. Gestiona el emparejamiento seguro con la extensión de Google Flow mediante STUDIO4_FLOW_TOKEN.
2. Expone la cola de escenas ordenadas con prompts de continuidad para Google Flow.
3. Recibe automáticamente cada imagen generada en Google Flow (vía extensión o subida manual).
4. Asigna cada imagen recibida a la escena correspondiente (Escena 1, 2, 3...) sin saltos bruscos.
5. Permite drag & drop / subida manual directa desde el dashboard localhost:8000.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Optional
from dotenv import load_dotenv, set_key
from PIL import Image, UnidentifiedImageError

load_dotenv()

logger = logging.getLogger("studio4.google_flow")

VAR_TOKEN = "STUDIO4_FLOW_TOKEN"
ENV_FILE = Path(__file__).resolve().parent / ".env"
CONECTADA_TIMEOUT_S = 15 * 60  # 15 minutos sin latido = desconectada
MAX_BYTES = 25 * 1024 * 1024  # 25 MB max

_lock = threading.Lock()
_SESSION_FILE = Path("temp_clips/_flow_session.json")

# Memoria de la sesión actual
_ESTADO: dict[str, Any] = {
    "ultima_conexion": 0.0,
    "version": "",
    "sesion": {
        "titulo": "",
        "estilo": "cinematografico realista 4K",
        "total_escenas": 0,
        "escena_actual": 1,
        "escenas": {},  # { "1": {"order": 1, "prompt": "...", "estado": "esperando", "image_path": "..."} }
    }
}


def cargar_estado():
    global _ESTADO
    with _lock:
        if _SESSION_FILE.exists():
            try:
                data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
                _ESTADO["sesion"] = data.get("sesion", _ESTADO["sesion"])
                _ESTADO["ultima_conexion"] = data.get("ultima_conexion", 0.0)
                _ESTADO["version"] = data.get("version", "")
            except Exception as e:
                logger.warning("Error leyendo _flow_session.json: %s", e)


def guardar_estado():
    with _lock:
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            _SESSION_FILE.write_text(json.dumps(_ESTADO, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Error guardando _flow_session.json: %s", e)


cargar_estado()


def token() -> str:
    """Devuelve el token de emparejamiento; si no existe, crea uno y lo guarda en .env."""
    return os.getenv(VAR_TOKEN) or renovar_token()


def renovar_token() -> str:
    """Genera un token nuevo y lo persiste en .env (la extensión tendrá que volver a vincularse)."""
    import secrets
    nuevo = secrets.token_urlsafe(18)
    os.environ[VAR_TOKEN] = nuevo
    _ESTADO["ultima_conexion"] = 0.0  # la extensión con el código viejo ya no cuenta como conectada
    try:
        set_key(str(ENV_FILE), VAR_TOKEN, nuevo)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo guardar %s en .env: %s", VAR_TOKEN, e)
    return nuevo


def token_valido(recibido: str) -> bool:
    """Verifica si el token recibido por la extensión coincide."""
    actual = token()
    if not actual:
        return False
    return hmac.compare_digest(str(recibido or "").strip(), actual.strip())


def latido(version: str = ""):
    """Registra un latido de conexión de la extensión de Google Flow."""
    with _lock:
        _ESTADO["ultima_conexion"] = time.time()
        if version:
            _ESTADO["version"] = str(version)[:20]
    guardar_estado()


def iniciar_sesion_flow(scenes: list[dict[str, Any]], title: str = "", style: str = ""):
    """
    Inicializa una sesión de producción para Google Flow con la lista de escenas.
    Crea los prompts enriquecidos con continuidad y activa la escena 1 en espera.
    """
    with _lock:
        estilo_base = style or "cinematic realistic, 4K, 8K, highly detailed, dramatic lighting"
        escenas_dict: dict[str, Any] = {}

        for sc in scenes:
            order = int(sc.get("order", 1))
            query = sc.get("broll_query_en") or sc.get("voice_segment") or ""
            overlay = sc.get("overlay_text") or ""
            dur = sc.get("duration_sec", 4)

            # Prompt cinematográfico optimizado para Google Flow
            prompt_flow = (
                f"{query}. {estilo_base}. "
                f"Scene {order} of {len(scenes)}. "
                f"Continuity: consistent cinematic universe, photorealistic, sharp focus, 35mm lens."
            )

            escenas_dict[str(order)] = {
                "order": order,
                "duration_sec": dur,
                "query": query,
                "overlay_text": overlay,
                "voice_segment": sc.get("voice_segment", ""),
                "prompt": prompt_flow,
                "estado": "esperando" if order == 1 else "pendiente",
                "image_path": None,
                "image_url": None,
                "recibida_en": None,
            }

            # Si ya existe una imagen previa en temp_clips, registrarla
            img_cand_png = Path(f"temp_clips/scene_{order:02d}.png")
            img_cand_jpg = Path(f"temp_clips/scene_{order:02d}.jpg")
            if img_cand_png.exists() and img_cand_png.stat().st_size > 5000:
                escenas_dict[str(order)]["image_path"] = str(img_cand_png)
                escenas_dict[str(order)]["image_url"] = f"/temp_clips/{img_cand_png.name}"
                escenas_dict[str(order)]["estado"] = "lista"
            elif img_cand_jpg.exists() and img_cand_jpg.stat().st_size > 5000:
                escenas_dict[str(order)]["image_path"] = str(img_cand_jpg)
                escenas_dict[str(order)]["image_url"] = f"/temp_clips/{img_cand_jpg.name}"
                escenas_dict[str(order)]["estado"] = "lista"

        _ESTADO["sesion"] = {
            "titulo": title or "Producción STUDIO 4",
            "estilo": estilo_base,
            "total_escenas": len(scenes),
            "escenas": escenas_dict,
        }
        _actualizar_escena_actual_unlocked()

    guardar_estado()


def _actualizar_escena_actual_unlocked():
    """Calcula cuál es la siguiente escena que espera imagen."""
    sesion = _ESTADO.get("sesion", {})
    escenas = sesion.get("escenas", {})
    if not escenas:
        sesion["escena_actual"] = 1
        return

    orders = sorted([int(k) for k in escenas.keys()])
    encontrada = False
    for o in orders:
        sc = escenas[str(o)]
        if sc.get("estado") in ("esperando", "pendiente"):
            sc["estado"] = "esperando"
            sesion["escena_actual"] = o
            encontrada = True
            # las posteriores quedan en pendiente
            for rest in orders:
                if rest > o and escenas[str(rest)].get("estado") != "lista":
                    escenas[str(rest)]["estado"] = "pendiente"
            break

    if not encontrada:
        sesion["escena_actual"] = None  # ¡Todas completadas!


def verificar_imagen(datos: bytes) -> tuple[str, int, int]:
    """Valida los bytes de la imagen y devuelve (formato, ancho, alto)."""
    if not datos:
        raise ValueError("No se recibieron datos de imagen.")
    if len(datos) > MAX_BYTES:
        raise ValueError("La imagen supera los 25 MB permitidos.")

    try:
        with Image.open(io.BytesIO(datos)) as im:
            im.verify()
        with Image.open(io.BytesIO(datos)) as im:
            formato = (im.format or "").upper()
            ancho, alto = im.size
    except Exception as e:
        raise ValueError("El archivo recibido no es una imagen válida.") from e

    if formato not in ("JPEG", "JPG", "PNG", "WEBP"):
        raise ValueError(f"Formato no admitido ({formato}). Usa JPEG, PNG o WebP.")
    if ancho < 200 or alto < 200:
        raise ValueError(f"Imagen demasiado pequeña ({ancho}x{alto}).")

    return formato, ancho, alto


def recibir_imagen(datos: bytes, prompt: str = "", pagina: str = "", scene_order: Optional[int] = None) -> dict[str, Any]:
    """
    Recibe una imagen (desde la extensión de Flow o subida manual) y la asigna a la escena correspondiente.
    """
    formato, ancho, alto = verificar_imagen(datos)
    ext = ".png" if formato == "PNG" else (".webp" if formato == "WEBP" else ".jpg")

    with _lock:
        sesion = _ESTADO.get("sesion", {})
        escenas = sesion.get("escenas", {})
        total = sesion.get("total_escenas", 0)

        # Determinar a qué escena asignar
        if scene_order is not None and str(scene_order) in escenas:
            target_order = scene_order
        else:
            target_order = sesion.get("escena_actual")
            if target_order is None:
                # Si todas están listas, buscar la primera vacía o sobreescribir la 1
                pendientes = [int(k) for k, v in escenas.items() if v.get("estado") != "lista"]
                target_order = pendientes[0] if pendientes else 1

        out_dir = Path("temp_clips").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        target_path = out_dir / f"scene_{target_order:02d}{ext}"

        # Guardar en disco
        target_path.write_bytes(datos)

        # Actualizar escena en la sesión
        sc_data = escenas.setdefault(str(target_order), {
            "order": target_order,
            "duration_sec": 4,
            "query": prompt,
            "prompt": prompt,
        })
        sc_data["estado"] = "lista"
        sc_data["image_path"] = str(target_path)
        sc_data["image_url"] = f"/temp_clips/{target_path.name}?t={int(time.time())}"
        sc_data["recibida_en"] = time.strftime("%H:%M:%S")
        sc_data["ancho"] = ancho
        sc_data["alto"] = alto

        _ESTADO["ultima_conexion"] = time.time()
        _actualizar_escena_actual_unlocked()

    guardar_estado()

    # Registrar movimiento en el libro mayor
    try:
        import ledger
        ledger.registrar_movimiento(
            fase="Google Flow Receptor",
            proveedor="GOOGLE FLOW",
            modelo="labs.google",
            detalle=f"Imagen para Escena {target_order} ({ancho}x{alto})",
            coste_usd=0.0,
            ahorro_usd=0.0398,
            tipo="imagen",
        )
    except Exception as e:
        logger.debug("Error registrando movimiento en ledger: %s", e)

    logger.info("Imagen de Google Flow recibida con éxito para Escena %d (%dx%d)", target_order, ancho, alto)
    return {
        "ok": True,
        "scene": target_order,
        "image_url": sc_data["image_url"],
        "siguiente_escena": _ESTADO["sesion"].get("escena_actual"),
        "total_listas": sum(1 for v in escenas.values() if v.get("estado") == "lista"),
        "total_escenas": total,
    }


def estado_flow() -> dict[str, Any]:
    """Devuelve el estado completo del subsistema de Google Flow."""
    with _lock:
        ahora = time.time()
        ultima = _ESTADO.get("ultima_conexion", 0.0)
        conectada = bool(ultima) and (ahora - ultima < CONECTADA_TIMEOUT_S)

        sesion = _ESTADO.get("sesion", {})
        escenas = sesion.get("escenas", {})
        total = sesion.get("total_escenas", 0)
        listas = sum(1 for v in escenas.values() if v.get("estado") == "lista")
        actual_order = sesion.get("escena_actual")

        prompt_actual = ""
        query_actual = ""
        if actual_order and str(actual_order) in escenas:
            sc = escenas[str(actual_order)]
            prompt_actual = sc.get("prompt", "")
            query_actual = sc.get("query", "")

        return {
            "emparejada": bool(token()),
            "codigo": token(),
            "conectada": conectada,
            "version": _ESTADO.get("version", "1.1.0"),
            "ultima_conexion": ultima,
            "sesion": {
                "titulo": sesion.get("titulo", ""),
                "estilo": sesion.get("estilo", ""),
                "total_escenas": total,
                "listas": listas,
                "todas_listas": total > 0 and listas >= total,
                "escena_actual": actual_order,
                "prompt_actual": prompt_actual,
                "query_actual": query_actual,
                "escenas": escenas,
            }
        }


def obtener_imagenes_para_montaje(scenes: list[dict[str, Any]]) -> list[Optional[str]]:
    """
    Retorna la lista de rutas de imágenes existentes para las escenas dadas.
    """
    with _lock:
        escenas_sesion = _ESTADO.get("sesion", {}).get("escenas", {})

    paths: list[Optional[str]] = []
    for sc in scenes:
        order = int(sc.get("order", 1))
        # 1. Mirar en la sesión de Flow
        flow_sc = escenas_sesion.get(str(order), {})
        flow_path = flow_sc.get("image_path")
        if flow_path and Path(flow_path).exists() and Path(flow_path).stat().st_size > 5000:
            paths.append(flow_path)
            continue

        # 2. Buscar archivos scene_XX en temp_clips
        cand_png = Path(f"temp_clips/scene_{order:02d}.png")
        cand_jpg = Path(f"temp_clips/scene_{order:02d}.jpg")
        cand_webp = Path(f"temp_clips/scene_{order:02d}.webp")

        if cand_png.exists() and cand_png.stat().st_size > 5000:
            paths.append(str(cand_png))
        elif cand_jpg.exists() and cand_jpg.stat().st_size > 5000:
            paths.append(str(cand_jpg))
        elif cand_webp.exists() and cand_webp.stat().st_size > 5000:
            paths.append(str(cand_webp))
        else:
            paths.append(None)

    return paths

