"""
server.py - Servidor Web Local para STUDIO 4 Vol. 3
Permite visualizar los videos generados y lanzar nuevas producciones desde el navegador.
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
import urllib.parse

# Compatibilidad de codificación en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("studio4.server")

PORT = 8000
BASE_DIR = Path(__file__).resolve().parent

# Estado de la generación en curso
ESTADO_GENERACION = {
    "ocupado": False,
    "tema": "",
    "fase": "",
    "progreso": 0,
    "error": "",
}


def ejecutar_produccion_thread(tema: str, duration: int, orientation: str, writer: str) -> None:
    """Ejecuta el pipeline de main.py en un hilo secundario."""
    global ESTADO_GENERACION
    ESTADO_GENERACION["ocupado"] = True
    ESTADO_GENERACION["tema"] = tema
    ESTADO_GENERACION["fase"] = "Iniciando producción..."
    ESTADO_GENERACION["progreso"] = 10
    ESTADO_GENERACION["error"] = ""

    try:
        cmd = [
            "python", "main.py",
            tema,
            "--duration", str(duration),
            "--orientation", orientation,
            "--writer", writer,
        ]
        logger.info("Lanzando comando: %s", " ".join(cmd))
        ESTADO_GENERACION["fase"] = "Generando guion, escenas y audio con Gemini..."
        ESTADO_GENERACION["progreso"] = 40

        proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")

        if proc.returncode != 0:
            logger.error("Error en producción:\n%s", proc.stderr)
            ESTADO_GENERACION["error"] = proc.stderr[-400:] if proc.stderr else "Error desconocido durante la ejecución"
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


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP con soporte para archivos estáticos y API de generación."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(ESTADO_GENERACION).encode("utf-8"))
            return

        if parsed.path == "/api/production_plan":
            plan_file = BASE_DIR / "output" / "production_plan.json"
            if plan_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(plan_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Servir index.html por defecto para la raíz
        if parsed.path in ("/", ""):
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = urllib.parse.parse_qs(body)
                data = {k: v[0] for k, v in data.items()}

            tema = data.get("tema", "").strip()
            duration = int(data.get("duration", 15))
            orientation = data.get("orientation", "landscape")
            writer = data.get("writer", "gemini")

            if not tema:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "El tema es obligatorio"}')
                return

            if ESTADO_GENERACION["ocupado"]:
                self.send_response(409)
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
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "mensaje": "Produccion iniciada"}')
            return

        self.send_response(404)
        self.end_headers()


def run_server() -> None:
    # Permitir reusar dirección inmediatamente
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), StudioHandler) as httpd:
        print(f"\n=======================================================")
        print(f"  🎬 STUDIO 4 Vol. 3 - Servidor Local Activo")
        print(f"  URL: http://localhost:{PORT}")
        print(f"=======================================================\n")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
