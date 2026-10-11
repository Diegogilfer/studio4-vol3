"""
server.py - Servidor Web Local para STUDIO 4 Vol. 3
Permite visualizar videos generados, gestionar Google Flow con su extensión,
subir imágenes por escena, autocompletar con IA y renderizar en localhost:8000.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from typing import Any

# Compatibilidad de codificación en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("studio4.server")

import google_flow
from video_maker import ensamblar_video, preparar_visuales_escenas
from visual_generator import obtener_imagen_escena

PORT = 8000
BASE_DIR = Path(__file__).resolve().parent

# Estado de la generación en curso
ESTADO_GENERACION: dict[str, Any] = {
    "ocupado": False,
    "tema": "",
    "fase": "",
    "progreso": 0,
    "error": "",
    "video_url": "/output/video_final.mp4",
}


def ejecutar_produccion_thread(tema: str, duration: int, orientation: str, writer: str) -> None:
    """Ejecuta el pipeline completo de main.py en un hilo secundario."""
    global ESTADO_GENERACION
    ESTADO_GENERACION["ocupado"] = True
    ESTADO_GENERACION["tema"] = tema
    ESTADO_GENERACION["fase"] = "Iniciando producción..."
    ESTADO_GENERACION["progreso"] = 10
    ESTADO_GENERACION["error"] = ""

    try:
        cmd = [
            sys.executable, "main.py",
            tema,
            "--duration", str(duration),
            "--orientation", orientation,
            "--writer", writer,
        ]
        logger.info("Lanzando comando: %s", " ".join(cmd))
        ESTADO_GENERACION["fase"] = "Generando guion, escenas y audio con IA..."
        ESTADO_GENERACION["progreso"] = 35

        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if proc.returncode != 0:
            logger.error("Error en producción:\n%s", proc.stderr)
            ESTADO_GENERACION["error"] = proc.stderr[-500:] if proc.stderr else "Error desconocido durante la ejecución"
            ESTADO_GENERACION["fase"] = "Error en la producción"
        else:
            logger.info("Producción finalizada exitosamente.")
            ESTADO_GENERACION["fase"] = "¡Completado!"
            ESTADO_GENERACION["progreso"] = 100
    except Exception as exc:
        logger.exception("Excepción durante la producción:")
        ESTADO_GENERACION["error"] = str(exc)
        ESTADO_GENERACION["fase"] = "Error"
    finally:
        ESTADO_GENERACION["ocupado"] = False


def ejecutar_render_flow_thread() -> None:
    """Ensambla el video final usando las imágenes recibidas de Google Flow y el audio existente."""
    global ESTADO_GENERACION
    ESTADO_GENERACION["ocupado"] = True
    ESTADO_GENERACION["fase"] = "Ensamblando metraje con cinemática Ken Burns y subtítulos virales..."
    ESTADO_GENERACION["progreso"] = 60
    ESTADO_GENERACION["error"] = ""

    try:
        plan_file = BASE_DIR / "output" / "production_plan.json"
        audio_file = BASE_DIR / "output" / "audio.wav"

        if not plan_file.exists() or not audio_file.exists():
            raise FileNotFoundError("No se encontró el plan de producción o el audio maestro. Inicia una producción primero.")

        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        scenes = plan.get("scenes", [])

        out_video = BASE_DIR / "output" / "video_final.mp4"
        ensamblar_video(
            scenes=scenes,
            audio_path=str(audio_file),
            output_path=str(out_video),
            temp_folder="temp_clips",
            orientation=os.getenv("VIDEO_ORIENTATION", "landscape"),
        )

        ESTADO_GENERACION["progreso"] = 100
        ESTADO_GENERACION["fase"] = "¡Video final ensamblado con éxito!"
        logger.info("Video final ensamblado con éxito.")
    except Exception as exc:
        logger.exception("Error al ensamblar video desde Flow:")
        ESTADO_GENERACION["error"] = str(exc)
        ESTADO_GENERACION["fase"] = "Error al ensamblar video"
    finally:
        ESTADO_GENERACION["ocupado"] = False


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP con soporte para Google Flow, CORS, streaming y API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        # 1. API: Estado general
        if parsed.path == "/api/status":
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO_GENERACION).encode("utf-8"))
            return

        # 2. API: Plan de producción
        if parsed.path == "/api/production_plan":
            plan_file = BASE_DIR / "output" / "production_plan.json"
            if plan_file.exists():
                self.send_response(200)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(plan_file.read_bytes())
            else:
                self.send_response(404)
                self._set_cors_headers()
                self.end_headers()
            return

        # 3. API: Google Flow Estado
        if parsed.path == "/api/flow":
            st = google_flow.estado_flow()
            st["carpeta_extension"] = str((BASE_DIR / "extension-flow").resolve())
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(st, ensure_ascii=False).encode("utf-8"))
            return

        # 4. Página de emparejamiento con 1-clic
        if parsed.path == "/flow/emparejar":
            emp_file = BASE_DIR / "flow_emparejar.html"
            if emp_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(emp_file.read_bytes())
                return

        # 5. Servir index.html por defecto para la raíz
        if parsed.path in ("/", ""):
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Heartbeat de la extensión
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/hola":
            token_recibido = self.headers.get("X-Studio4-Token", "")
            if not google_flow.token_valido(token_recibido):
                self.send_response(401)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Token de emparejamiento no valido"}')
                return

            version = self.headers.get("X-Flow-Version", "")
            google_flow.latido(version)
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "estudio": "STUDIO 4 Vol. 3"}')
            return

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Recibir imagen desde la extensión
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/recibir":
            token_recibido = self.headers.get("X-Studio4-Token", "")
            if not google_flow.token_valido(token_recibido):
                self.send_response(401)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Token de emparejamiento no valido"}')
                return

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 25 * 1024 * 1024:
                self.send_response(413)
                self._set_cors_headers()
                self.end_headers()
                return

            image_bytes = self.rfile.read(content_length)
            prompt = urllib.parse.unquote(self.headers.get("X-Flow-Prompt", ""))[:1500]
            pagina = urllib.parse.unquote(self.headers.get("X-Flow-Pagina", ""))[:300]

            try:
                res = google_flow.recibir_imagen(image_bytes, prompt=prompt, pagina=pagina)
                self.send_response(200)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))
            except Exception as e:
                logger.error("Error al procesar imagen de Google Flow: %s", e)
                self.send_response(400)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Subida manual de imagen por escena (Drag & Drop / Selector)
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/subir":
            qs = urllib.parse.parse_qs(parsed.query)
            scene_order = int(qs.get("scene", [0])[0]) if "scene" in qs else None

            content_length = int(self.headers.get("Content-Length", 0))
            image_bytes = self.rfile.read(content_length)

            try:
                res = google_flow.recibir_imagen(image_bytes, prompt="Subida manual", scene_order=scene_order)
                self.send_response(200)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(res).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Completar escenas faltantes con IA (NVIDIA FLUX)
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/completar_ia":
            st = google_flow.estado_flow()
            escenas = st.get("sesion", {}).get("escenas", {})
            completadas = 0

            for ord_str, sc in escenas.items():
                if sc.get("estado") != "lista":
                    o = int(ord_str)
                    query = sc.get("prompt") or sc.get("query") or f"Cinematic scene {o}"
                    logger.info("Completando escena %d con IA...", o)
                    img_p = obtener_imagen_escena(o, query, folder="temp_clips", auto_fallback=True)
                    if img_p:
                        completadas += 1

            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "completadas": completadas}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Renderizar video final con las escenas actuales
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/renderizar":
            if ESTADO_GENERACION["ocupado"]:
                self.send_response(409)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Ya hay una operacion en curso"}')
                return

            threading.Thread(target=ejecutar_render_flow_thread, daemon=True).start()
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "mensaje": "Renderizado iniciado"}')
            return

        # ---------------------------------------------------------------------
        # API: Iniciar nueva producción completa
        # ---------------------------------------------------------------------
        if parsed.path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = urllib.parse.parse_qs(body)
                data = {k: v[0] for k, v in data.items()}

            tema = data.get("tema", "").strip()
            duration = int(data.get("duration", 20))
            orientation = data.get("orientation", "landscape")
            writer = data.get("writer", "gemini")

            if not tema:
                self.send_response(400)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "El tema es obligatorio"}')
                return

            if ESTADO_GENERACION["ocupado"]:
                self.send_response(409)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Ya hay una produccion en curso"}')
                return

            threading.Thread(
                target=ejecutar_produccion_thread,
                args=(tema, duration, orientation, writer),
                daemon=True,
            ).start()

            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "mensaje": "Produccion iniciada"}')
            return

        self.send_response(404)
        self._set_cors_headers()
        self.end_headers()


def run_server() -> None:
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StudioHandler) as httpd:
        print(f"\n=======================================================")
        print(f"  🎬 STUDIO 4 Vol. 3 - Servidor Local Activo")
        print(f"  URL: http://localhost:{PORT}")
        print(f"  Google Flow: http://localhost:{PORT}/flow/emparejar")
        print(f"=======================================================\n")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
