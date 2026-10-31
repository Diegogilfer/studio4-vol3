"""Vigilante de Studio 4: cada pocos minutos mira que todo marche y avisa en Windows cuando pasa algo.

Adaptado del guardián de SKAY, SIN su fallo: antes de arrancar el servidor comprueba que de verdad está caído, y
`iniciar.bat` a su vez no abre otro si el puerto 8000 ya responde. Así nunca se multiplica (lo de las 282 copias de ia1).

Qué hace cada ronda (nunca publica, nunca gasta en IA):
- Servidor caído DE VERDAD (nadie escucha en el puerto) → lo arranca en silencio, sin abrir el navegador. Un servidor
  lento (en pleno render) no cuenta como caído: antes se daba por muerto y se abría una pestaña nueva cada 10 min.
- Render parado (mismo progreso) demasiado tiempo → avisa, para que no esperes horas como pasó.
- Un vídeo terminó (final o previa) desde la ronda anterior → te avisa de que está listo.
- Poco disco libre → avisa (los vídeos ocupan mucho).
Los avisos no se repiten antes de `silencio_min` minutos. Si hay avisos por Telegram configurados, también salen allí.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import urllib.request
from typing import Any

from . import config, montaje

logger = logging.getLogger("studio4.vigilante")

ESTADO = config.PRODUCCIONES / "_vigilante.json"
PARADO_MIN = 20       # un render con el mismo progreso más de esto = atascado
DISCO_MIN_GB = 5
SILENCIO_MIN = 30     # el mismo aviso no se repite antes de esto
SIN_VENTANA = 0x08000000


def _estado() -> dict[str, Any]:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"progreso": {}, "avisos": {}}


def _guardar(e: dict[str, Any]) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")


def notificar_windows(titulo: str, texto: str) -> bool:
    """Un aviso del sistema (la campana de Windows). Falla en silencio si no se puede."""
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
          "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
          "$x=$t.GetElementsByTagName('text'); "
          "$x.Item(0).AppendChild($t.CreateTextNode($env:S4_TITULO)) | Out-Null; "
          "$x.Item(1).AppendChild($t.CreateTextNode($env:S4_TEXTO)) | Out-Null; "
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Studio 4').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
    try:
        import os
        entorno = dict(os.environ, S4_TITULO=str(titulo)[:120], S4_TEXTO=str(texto)[:250])
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           text=True, timeout=20, creationflags=SIN_VENTANA, env=entorno)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _puerto_ocupado() -> bool:
    """¿Hay alguien escuchando en el puerto del panel? (aunque tarde en contestar)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", config.PUERTO), timeout=3):
            return True
    except OSError:
        return False


def _servidor_vivo() -> bool:
    """Vivo si contesta o, al menos, si el puerto está ocupado: un render pesado puede hacer que tarde mucho."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{config.PUERTO}/api/estado", timeout=20)
        return True
    except Exception:  # noqa: BLE001
        return _puerto_ocupado()


def _arrancar_servidor() -> bool:
    """Arranca el servidor en segundo plano y SIN abrir el navegador (antes usaba iniciar.bat, que abre una pestaña)."""
    import sys
    from pathlib import Path
    if _puerto_ocupado():
        return True
    servidor = config.RAIZ / "servidor.py"
    if not servidor.exists():
        return False
    exe = Path(sys.executable)
    sin_consola = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
    try:
        subprocess.Popen([str(sin_consola), str(servidor)], cwd=str(config.RAIZ), creationflags=SIN_VENTANA | 0x00000008,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        for _ in range(15):
            time.sleep(2)
            if _servidor_vivo():
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning("Arrancar servidor: %s", e)
    return False


def _trabajos() -> list[dict[str, Any]]:
    salida = []
    if not montaje.raiz().exists():
        return salida
    for f in montaje.raiz().glob("*/proyecto.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        salida.append(p)
    return salida


def comprobar(ahora: float | None = None, avisar=notificar_windows, vivo=_servidor_vivo, arrancar=_arrancar_servidor) -> list[dict[str, str]]:
    """Una ronda. Devuelve la lista de avisos emitidos esta vez (para el registro y las pruebas)."""
    ahora = ahora if ahora is not None else time.time()
    e = _estado()
    nuevos: list[dict[str, str]] = []

    def avisa(clave: str, titulo: str, texto: str) -> None:
        ultimo = e["avisos"].get(clave, 0)
        if ahora - ultimo < SILENCIO_MIN * 60:
            return
        e["avisos"][clave] = ahora
        avisar(titulo, texto)
        nuevos.append({"clave": clave, "titulo": titulo, "texto": texto})

    if not vivo():
        avisa("servidor", "Studio 4", "El panel estaba caído: lo estoy arrancando." if arrancar()
              else "El panel está caído y no pude arrancarlo. Abre «iniciar.bat».")

    for p in _trabajos():
        mid = p.get("id", "")
        t = p.get("trabajo") or {}
        titulo = p.get("titulo", mid)[:50]
        if t.get("ocupado"):
            huella = f"{t.get('fase')}|{t.get('progreso')}"
            prev = e["progreso"].get(mid)
            if prev and prev["huella"] == huella and ahora - prev["desde"] > PARADO_MIN * 60:
                avisa(f"parado:{mid}", "Studio 4 · render parado",
                      f"«{titulo}» lleva {PARADO_MIN}+ min sin avanzar en: {t.get('fase')}. Mira si se atascó.")
            elif not prev or prev["huella"] != huella:
                e["progreso"][mid] = {"huella": huella, "desde": ahora}
        else:
            e["progreso"].pop(mid, None)
            hecho = p.get("final") or p.get("previa")
            marca = f"{p.get('actualizado', '')}|{bool(p.get('final'))}"
            if hecho and e.get("listos", {}).get(mid) != marca and t.get("fase", "").endswith("listo"):
                e.setdefault("listos", {})[mid] = marca
                que = "El vídeo final" if p.get("final") else "La previa"
                avisa(f"listo:{mid}", "Studio 4 · vídeo listo", f"{que} de «{titulo}» está listo para verlo.")

    libre = shutil.disk_usage(config.RAIZ).free / (1 << 30)
    if libre < DISCO_MIN_GB:
        avisa("disco", "Studio 4 · poco espacio", f"Quedan {libre:.1f} GB libres. Libera espacio o se cortarán los renders.")

    _guardar(e)
    if nuevos:
        logger.info("avisos: %s", ", ".join(a["clave"] for a in nuevos))
    return nuevos
