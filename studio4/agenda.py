"""Agenda de vídeos: cada vídeo con su fecha de publicar. Unos días antes (ANTELACION_DIAS) Studio 4 lo crea solo con
la IA (investiga, escribe el guion, busca material oficial y pone un plano en cada frase) y te avisa para revisarlo.

Nunca publica ni gasta en voz, imagen o vídeo de pago: solo lo mismo que «Crear vídeo» (DeepSeek o Gemini para el
guion). Un vídeo cada vez, y solo si no hay otro trabajando. Los vídeos se crean en el canal de cada fila, sin cambiar
el canal que tengas abierto.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import date, timedelta
from typing import Any, Callable

from . import canales, config

logger = logging.getLogger("studio4.agenda")
ARCHIVO = config.PRODUCCIONES / "agenda.json"
ANTELACION_DIAS = 3
CADA_MIN = 30
_lock = threading.Lock()


def _leer() -> list[dict[str, Any]]:
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8")).get("videos", [])
    except (OSError, ValueError):
        return []


def _escribir(videos: list[dict[str, Any]]) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"videos": sorted(videos, key=lambda v: v["fecha"])}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARCHIVO)


def _crear_en(v: dict[str, Any]) -> str:
    return (date.fromisoformat(v["fecha"]) - timedelta(days=ANTELACION_DIAS)).isoformat()


def listar(canal: str = "") -> list[dict[str, Any]]:
    """Las filas (de un canal o de todos), con el día en que se crearán."""
    return [{**v, "crear_en": _crear_en(v)} for v in _leer() if not canal or v["canal"] == canal]


def anadir(fecha: str, tema: str, canal: str, opciones: dict[str, Any] | None = None) -> dict[str, Any]:
    tema = (tema or "").strip()
    if len(tema) < 4:
        raise ValueError("Escribe el tema del vídeo.")
    try:
        date.fromisoformat(fecha)
    except ValueError as e:
        raise ValueError("La fecha va como AAAA-MM-DD.") from e
    canales.obtener(canal)
    v = {"id": uuid.uuid4().hex[:8], "fecha": fecha, "tema": tema[:200], "canal": canal,
         "opciones": opciones or {}, "estado": "pendiente", "video": ""}
    with _lock:
        videos = _leer()
        videos.append(v)
        _escribir(videos)
    return v


def quitar(vid: str) -> None:
    with _lock:
        _escribir([v for v in _leer() if v["id"] != vid])


def _ocupado() -> bool:
    from . import vigilante
    return any((p.get("trabajo") or {}).get("ocupado") for p in vigilante._trabajos())


def lanzar(vid: str, crear: Callable[..., str] | None = None) -> str:
    """Crea ya el vídeo de esa fila (botón «Crear ya» o la revisión automática). Devuelve el id del vídeo."""
    from . import montaje
    crear = crear or montaje.crear_con_ia
    with _lock:
        videos = _leer()
        v = next((x for x in videos if x["id"] == vid), None)
        if not v:
            raise ValueError("Ese vídeo ya no está en la agenda.")
        if v.get("video"):
            return v["video"]
        mid = crear(v["tema"], v.get("opciones") or {}, canal=v["canal"])
        v.update(estado="creado", video=mid, creado=time.strftime("%Y-%m-%d %H:%M"))
        try:   # el vídeo sabe que es de la agenda: su entrega va aparte, a «Programados»
            from . import montaje
            montaje.modificar(mid, lambda q: q.update(programado={"publicar": v["fecha"], "fila": v["id"]}))
        except Exception:  # noqa: BLE001 - en las pruebas, `crear` es falso y no hay vídeo
            pass
        _escribir(videos)
    return mid


def revisar(hoy: date | None = None, crear: Callable[..., str] | None = None, avisar: Callable[[str, str], Any] | None = None,
            ocupado: Callable[[], bool] = _ocupado) -> str:
    """Una ronda: si toca crear alguno (y no hay otro vídeo trabajando), crea el más próximo. Devuelve su id o ""."""
    hoy = hoy or date.today()
    toca = [v for v in _leer() if v["estado"] == "pendiente" and _crear_en(v) <= hoy.isoformat()]
    if not toca or ocupado():
        return ""
    v = min(toca, key=lambda x: x["fecha"])
    mid = lanzar(v["id"], crear)
    if avisar is None:
        from . import vigilante
        avisar = vigilante.notificar_windows
    nombre = canales.obtener(v["canal"])["nombre"]
    avisar(f"Studio 4 · {nombre}", f"Empecé el vídeo del {v['fecha']}: «{v['tema'][:60]}». Te aviso cuando esté para revisar.")
    logger.info("Agenda: creado %s para %s", mid, v["fecha"])
    return mid


def vigilar() -> None:
    """Hilo del servidor: una ronda cada CADA_MIN minutos (la primera, 2 min después de arrancar)."""
    time.sleep(120)
    while True:
        try:
            revisar()
        except Exception as e:  # noqa: BLE001 - la agenda nunca tumba el servidor
            logger.warning("Agenda: %s", e)
        time.sleep(CADA_MIN * 60)
