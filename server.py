"""
server.py - Servidor Web Local para STUDIO 4 Vol. 3
Permite:
1. Panel Glassy dinámico en localhost:8000 con selector de modelos y estilos gráficos.
2. Formatos listos para redes (Reels 9:16, YouTube 16:9, Feed 1:1).
3. Personalizador y arreglo de subtítulos ASS en tiempo real.
4. Centro de Finanzas: Gastos, Entradas (tokens/recursos) y Estadísticas de Movimientos auditables.
5. Google Flow en tiempo real vía extensión y subida drag-and-drop.
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
from typing import Any, Optional

# Compatibilidad de codificación en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("studio4.server")

import google_flow
import ledger
from subtitles import PALETAS_SUBTITULOS, construir_archivo_ass
from video_maker import ensamblar_video, preparar_visuales_escenas
from visual_generator import ESTILOS_GRAFICOS, MODELOS_IMAGEN, obtener_imagen_escena

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

# Configuración activa de subtítulos
CONFIG_SUBTITULOS: dict[str, Any] = {
    "palette_key": "viral_yellow",
    "position": "bottom",
    "size_scale": "normal",
    "show_hook": True,
    "hook_seconds": 4.0,
}


def ejecutar_produccion_thread(tema: str, duration: int, orientation: str, writer: str, style: str = "cinematic", image_model: str = "google_flow") -> None:
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


def ejecutar_render_flow_thread(orientation: str = "landscape", subtitle_cfg: Optional[dict] = None) -> None:
    """Ensambla el video final usando las imágenes de Google Flow y la configuración de subtítulos/formato."""
    global ESTADO_GENERACION
    ESTADO_GENERACION["ocupado"] = True
    ESTADO_GENERACION["fase"] = f"Ensamblando metraje en formato {orientation.upper()} con cinemática Ken Burns..."
    ESTADO_GENERACION["progreso"] = 55
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
            orientation=orientation,
            subtitle_config=subtitle_cfg or CONFIG_SUBTITULOS,
        )

        ESTADO_GENERACION["progreso"] = 100
        ESTADO_GENERACION["fase"] = f"¡Video {orientation.upper()} exportado con éxito!"
        logger.info("Video final ensamblado con éxito en formato %s.", orientation)
    except Exception as exc:
        logger.exception("Error al ensamblar video desde Flow:")
        ESTADO_GENERACION["error"] = str(exc)
        ESTADO_GENERACION["fase"] = "Error al ensamblar video"
    finally:
        ESTADO_GENERACION["ocupado"] = False


class StudioHandler(http.server.SimpleHTTPRequestHandler):
    """Manejador HTTP con soporte para Google Flow, Finanzas, Edición de Subtítulos y CORS."""

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

        # 4. API: Estadísticas Financieras, Entradas y Movimientos
        if parsed.path in ("/api/finanzas", "/api/movimientos"):
            stats = ledger.obtener_estadisticas_completas(max_movimientos=60)
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(stats, ensure_ascii=False).encode("utf-8"))
            return

        # 5. API: Catálogo de Estilos Gráficos y Modelos de Imagen
        if parsed.path == "/api/catalogos":
            catalog = {
                "estilos_graficos": ESTILOS_GRAFICOS,
                "modelos_imagen": MODELOS_IMAGEN,
                "paletas_subtitulos": PALETAS_SUBTITULOS,
                "subtitulos_config": CONFIG_SUBTITULOS,
            }
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(catalog, ensure_ascii=False).encode("utf-8"))
            return

        # 6. Página de emparejamiento con 1-clic
        if parsed.path == "/flow/emparejar":
            emp_file = BASE_DIR / "flow_emparejar.html"
            if emp_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(emp_file.read_bytes())
                return

        # 7. Servir index.html por defecto para la raíz
        if parsed.path in ("/", ""):
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))

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
        # GOOGLE FLOW: Subida manual de imagen por escena
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/subir":
            qs = urllib.parse.parse_qs(parsed.query)
            scene_order = int(qs.get("scene", [0])[0]) if "scene" in qs else None

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
        # SUBTÍTULOS: Actualizar Configuración y Regenerar ASS
        # ---------------------------------------------------------------------
        if parsed.path == "/api/subtitles/config":
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                CONFIG_SUBTITULOS.update(data)

                # Regenerar subtitulos.ass si existe plan de producción
                plan_file = BASE_DIR / "output" / "production_plan.json"
                if plan_file.exists():
                    plan = json.loads(plan_file.read_text(encoding="utf-8"))
                    scenes = plan.get("scenes", [])
                    ass_path = BASE_DIR / "temp_clips" / "subtitulos.ass"
                    construir_archivo_ass(
                        scenes=scenes,
                        output_ass_path=str(ass_path),
                        resolution=data.get("resolution", "1920x1080"),
                        hook_text=scenes[0].get("overlay_text", "") if scenes else "",
                        palette_key=CONFIG_SUBTITULOS.get("palette_key", "viral_yellow"),
                        position=CONFIG_SUBTITULOS.get("position", "bottom"),
                        size_scale=CONFIG_SUBTITULOS.get("size_scale", "normal"),
                        show_hook=CONFIG_SUBTITULOS.get("show_hook", True),
                    )

                self.send_response(200)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "config": CONFIG_SUBTITULOS}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # ESCENAS: Editar texto de subtítulos o gancho de una escena
        # ---------------------------------------------------------------------
        if parsed.path == "/api/scenes/update":
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                scene_order = int(data.get("order", 1))
                new_voice = data.get("voice_segment", "").strip()
                new_overlay = data.get("overlay_text", "").strip()

                plan_file = BASE_DIR / "output" / "production_plan.json"
                if plan_file.exists():
                    plan = json.loads(plan_file.read_text(encoding="utf-8"))
                    for sc in plan.get("scenes", []):
                        if int(sc.get("order", 0)) == scene_order:
                            if new_voice:
                                sc["voice_segment"] = new_voice
                            if new_overlay:
                                sc["overlay_text"] = new_overlay
                            break

                    plan_file.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

                    # Actualizar subtitulos.ass
                    ass_path = BASE_DIR / "temp_clips" / "subtitulos.ass"
                    construir_archivo_ass(
                        scenes=plan.get("scenes", []),
                        output_ass_path=str(ass_path),
                        palette_key=CONFIG_SUBTITULOS.get("palette_key", "viral_yellow"),
                        position=CONFIG_SUBTITULOS.get("position", "bottom"),
                        size_scale=CONFIG_SUBTITULOS.get("size_scale", "normal"),
                        show_hook=CONFIG_SUBTITULOS.get("show_hook", True),
                    )

                self.send_response(200)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true, "mensaje": "Escena actualizada"}')
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
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}

            style = data.get("style", "cinematic")
            st = google_flow.estado_flow()
            escenas = st.get("sesion", {}).get("escenas", {})
            completadas = 0

            for ord_str, sc in escenas.items():
                if sc.get("estado") != "lista":
                    o = int(ord_str)
                    query = sc.get("prompt") or sc.get("query") or f"Cinematic scene {o}"
                    logger.info("Completando escena %d con IA (estilo '%s')...", o, style)
                    img_p = obtener_imagen_escena(o, query, folder="temp_clips", style=style, auto_fallback=True)
                    if img_p:
                        completadas += 1

            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "completadas": completadas}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # GOOGLE FLOW: Renderizar video final con formato para redes
        # ---------------------------------------------------------------------
        if parsed.path == "/api/flow/renderizar":
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}

            orientation = data.get("orientation", "landscape")
            sub_cfg = data.get("subtitles") or CONFIG_SUBTITULOS

            if ESTADO_GENERACION["ocupado"]:
                self.send_response(409)
                self._set_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Ya hay una operacion en curso"}')
                return

            threading.Thread(
                target=ejecutar_render_flow_thread,
                args=(orientation, sub_cfg),
                daemon=True,
            ).start()

            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "formato": orientation}).encode("utf-8"))
            return

        # ---------------------------------------------------------------------
        # API: Iniciar nueva producción completa
        # ---------------------------------------------------------------------
        if parsed.path == "/api/generate":
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
            style = data.get("style", "cinematic")
            image_model = data.get("image_model", "google_flow")

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
                args=(tema, duration, orientation, writer, style, image_model),
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
