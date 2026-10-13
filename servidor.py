"""STUDIO 4 · panel local en http://127.0.0.1:8000

Solo escucha en este equipo y solo sirve la carpeta web/ y los medios de cada producción
(nunca el .env ni el código). La extensión de Flow entra con el código de emparejamiento.
"""

from __future__ import annotations

import json
import logging
import mimetypes

import requests
import os
import re
import sys
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from studio4 import config, flow, guion, miniaturas, produccion, registro, subtitulos, voz, youtube  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("studio4.servidor")

HOSTS = {f"127.0.0.1:{config.PUERTO}", f"localhost:{config.PUERTO}"}
ORIGENES_PANEL = {f"http://{h}" for h in HOSTS}
PAGINAS = {"/": "index.html", "/flow/emparejar": "emparejar.html", "/lateral": "lateral.html"}
MEDIOS_PERMITIDOS = re.compile(r"^(tomas/[\w.-]+|ref/[\w.-]+|voz\.wav|final\.mp4|miniaturas/(candidatos/|fuentes/)?[\w.-]+\.jpg)$")


class Error(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo


class Panel(BaseHTTPRequestHandler):
    server_version = "STUDIO4"

    def log_message(self, fmt, *args):  # noqa: D401 - el panel sondea cada 2 s: solo con STUDIO4_LOG_PETICIONES=1
        if os.getenv("STUDIO4_LOG_PETICIONES"):
            logger.info("%s · Origin=%s · %s", self.address_string(), self.headers.get("Origin", "-"), fmt % args)

    # --- respuestas -----------------------------------------------------------------------
    def _json(self, datos: Any, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _archivo(self, ruta: Path) -> None:
        if not ruta.is_file():
            raise Error(404, "No existe")
        tam = ruta.stat().st_size
        tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "application/json"):
            tipo += "; charset=utf-8"   # las tildes nunca dependen de lo que adivine el navegador
        ini, fin, codigo = 0, tam - 1, 200
        rango = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rango and tam:  # los <video> del navegador piden trozos para poder adelantar
            a, b = rango.groups()
            ini, fin = (int(a), int(b) if b else tam - 1) if a else (max(0, tam - int(b)), tam - 1)
            fin = min(fin, tam - 1)
            if ini > fin:
                raise Error(416, "Rango no válido")
            codigo = 206
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.send_header("Cache-Control", "no-cache")
        if codigo == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.end_headers()
        with ruta.open("rb") as f:
            f.seek(ini)
            pendiente = fin - ini + 1
            while pendiente > 0:
                bloque = f.read(min(1 << 20, pendiente))
                if not bloque:
                    break
                self.wfile.write(bloque)
                pendiente -= len(bloque)

    # --- seguridad --------------------------------------------------------------------------
    def _comprobar_host(self) -> None:
        # Bloquea el «DNS rebinding»: una web externa que se haga pasar por 127.0.0.1.
        if self.headers.get("Host", "") not in HOSTS:
            raise Error(403, "Host no permitido")

    def _solo_panel(self) -> None:
        origen = self.headers.get("Origin")
        if origen is not None and origen not in ORIGENES_PANEL:
            raise Error(403, "Solo el panel de STUDIO 4 puede hacer esto")

    def _solo_extension(self) -> None:
        import hmac
        recibido = self.headers.get("X-Studio4-Token", "")
        if not hmac.compare_digest(recibido.strip(), config.token_flow()):
            raise Error(401, "Código de emparejamiento no válido: vuelve a vincular la extensión")

    def _cuerpo_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise Error(413, "Demasiado grande")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError as e:
            raise Error(400, "JSON no válido") from e

    def _cuerpo_a_temporal(self) -> Path:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            raise Error(400, "No llegó ningún archivo")
        if n > config.MAX_BYTES_MEDIO:
            raise Error(413, "El archivo supera 400 MB")
        fd, nombre = tempfile.mkstemp(prefix="studio4_", dir=config.PRODUCCIONES)
        tmp = Path(nombre)
        with os.fdopen(fd, "wb") as f:  # mismo descriptor: en Windows un segundo open lo dejaría bloqueado
            while n > 0:
                bloque = self.rfile.read(min(1 << 20, n))
                if not bloque:
                    break
                f.write(bloque)
                n -= len(bloque)
        return tmp

    # --- rutas ------------------------------------------------------------------------------
    def _atender(self, metodo: str) -> None:
        try:
            self._comprobar_host()
            url = urllib.parse.urlparse(self.path)
            ruta, query = url.path, urllib.parse.parse_qs(url.query)
            if metodo == "GET":
                self._get(ruta)
            else:
                self._post(ruta, query)
        except Error as e:
            self._json({"error": str(e)}, e.codigo)
        except (ValueError, RuntimeError, FileNotFoundError, KeyError, IndexError) as e:
            self._json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            logger.exception("Error inesperado en %s", self.path)
            self._json({"error": f"Error interno: {e}"}, 500)

    def do_GET(self):  # noqa: N802
        self._atender("GET")

    def do_POST(self):  # noqa: N802
        self._atender("POST")

    def _redirigir(self, destino: str) -> None:
        self.send_response(302)
        self.send_header("Location", destino)
        self.end_headers()

    def _get(self, ruta: str) -> None:
        if ruta == "/youtube/conectar":
            return self._redirigir(youtube.url_autorizacion())
        if ruta == "/youtube/volver":  # Google vuelve aquí tras tu clic en «Permitir»
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "error" in q:
                return self._redirigir("/?youtube=cancelado")
            youtube.completar((q.get("code") or [""])[0], (q.get("state") or [""])[0])
            return self._redirigir("/?youtube=ok")
        if ruta == "/api/youtube":
            if not youtube.disponible():
                return self._json({"conectado": False})
            modo = "autorizado" if youtube.conectado() else "clave"
            try:
                return self._json({"conectado": True, "modo": modo, **youtube.canal()})
            except (RuntimeError, requests.RequestException) as e:
                # Con la clave sin canal, la búsqueda de temas funciona igual: solo falta saber tu canal.
                return self._json({"conectado": True, "modo": modo, "sin_canal": True, "error": str(e)})
        if ruta in PAGINAS:
            return self._archivo(config.WEB / PAGINAS[ruta])
        if ruta.startswith("/web/"):
            destino = (config.WEB / ruta[5:]).resolve()
            if config.WEB.resolve() not in destino.parents:
                raise Error(404, "No existe")
            return self._archivo(destino)
        m = re.fullmatch(r"/media/([\w-]+)/(.+)", ruta)
        if m:
            if not MEDIOS_PERMITIDOS.match(m.group(2)):
                raise Error(404, "No existe")
            return self._archivo(produccion.carpeta(m.group(1)) / m.group(2))
        if ruta == "/api/estado":
            return self._json(self._estado())
        if ruta == "/api/producciones":
            return self._json(produccion.listar())
        if ruta == "/api/sesion-flow":  # lo mismo que ve la extensión, para la vista lateral
            return self._json(flow.sesion_para_extension())
        raise Error(404, "No existe")

    def _estado(self) -> dict[str, Any]:
        pid = produccion.activa()
        p = produccion.cargar(pid) if pid else None
        if p:
            p["ia_detectada"] = guion.frases_prohibidas(p.get("guion", ""))
            p["hermanas"] = [x for x in produccion.listar() if p.get("familia") and x["familia"] == p["familia"]]
        return {
            "produccion": p,
            "extension": flow.estado_extension(),
            "codigo": config.token_flow(),
            "carpeta_extension": str(config.RAIZ / "extension-flow"),
            "consumo": registro.consumo_del_mes(),
            "elevenlabs_restantes": registro.creditos_elevenlabs_restantes(),
            "opciones": {
                "formatos": {k: v["nombre"] for k, v in config.FORMATOS.items()},
                "estilos": list(config.ESTILOS),
                "voces": {k: v for k, v in voz.PROVEEDORES.items() if k != "elevenlabs" or config.ELEVENLABS_API_KEY},
                "paletas": {k: v["nombre"] for k, v in subtitulos.PALETAS.items()},
                "gemini_ok": bool(config.GEMINI_API_KEY),
                "deepseek_ok": bool(config.DEEPSEEK_API_KEY),
                "sin_pago": config.SIN_PAGO,
                "versiones": config.VERSIONES,
                "salud": config.salud(),
                "plataformas": {k: v["nombre"] for k, v in miniaturas.PLATAFORMAS.items()},
            },
        }

    def _post(self, ruta: str, query: dict[str, list[str]]) -> None:
        # --- extensión de Flow (con código de emparejamiento) ---
        if ruta.startswith("/api/flow/") and ruta != "/api/flow/renovar":
            self._solo_extension()
            flow.latido(self.headers.get("X-Flow-Version", ""))
            if ruta == "/api/flow/hola":
                return self._json({"ok": True, "estudio": "STUDIO 4", "sesion": flow.sesion_para_extension()})
            if ruta == "/api/flow/activa":
                flow.marcar_activa(int(self._cuerpo_json().get("escena", 0)))
                return self._json({"ok": True, "sesion": flow.sesion_para_extension()})
            if ruta == "/api/flow/diagnostico":
                d = self._cuerpo_json()
                flow.anotar_evento(d.get("tipo", "info"), d.get("detalle", ""))
                return self._json({"ok": True})
            if ruta == "/api/flow/recibir":
                pista = self.headers.get("X-Flow-Escena", "")
                mime = self.headers.get("Content-Type", "")
                tmp = self._cuerpo_a_temporal()
                try:
                    res = flow.recibir(tmp, mime, prompt=urllib.parse.unquote(self.headers.get("X-Flow-Prompt", ""))[:1500],
                                       pista=int(pista) if pista.isdigit() else None)
                except (ValueError, RuntimeError) as e:
                    flow.anotar_evento("rechazada", f"{mime or 'archivo'}: {e}")
                    raise
                finally:
                    tmp.unlink(missing_ok=True)
                flow.anotar_evento("recibida", f"{res.get('tipo', '')} → escena {res['escena']}" + (" (repetida)" if res.get("repetida") else ""))
                return self._json(res)
            raise Error(404, "No existe")

        # --- panel ---
        self._solo_panel()
        if ruta == "/api/flow/renovar":
            return self._json({"ok": True, "codigo": config.renovar_token_flow()})
        if ruta == "/api/youtube/canal":
            return self._json({"ok": True, "canal": youtube.guardar_canal(str(self._cuerpo_json().get("canal", "")))})
        if ruta == "/api/youtube/desconectar":
            youtube.desconectar()
            return self._json({"ok": True})
        if ruta == "/api/producciones":
            d = self._cuerpo_json()
            idea = str(d.get("idea", "")).strip()
            propio = str(d.get("guion_propio", "")).strip()
            if len(idea) < 3 and not propio:
                raise Error(400, "Escribe la idea del vídeo o pega tu guion")
            segundos = {k: max(15, min(1200, int(v))) for k, v in (d.get("segundos") or {}).items() if str(v).isdigit()}
            pids = produccion.crear(idea, list(d.get("versiones") or ["corto"]), d.get("estilo", "cinematografico"),
                                    d.get("voz", "gemini"), segundos=segundos, guion_propio=propio,
                                    formato_propio=d.get("formato", "vertical"), tono=str(d.get("tono", "")),
                                    publico=str(d.get("publico", "")))
            return self._json({"ok": True, "ids": pids})
        if ruta == "/api/activar":
            pid = str(self._cuerpo_json().get("id", ""))
            produccion.cargar(pid)
            produccion.activar(pid)
            return self._json({"ok": True})

        pid = produccion.activa()
        if not pid:
            raise Error(409, "No hay producción activa")
        if ruta == "/api/guion":
            produccion.guardar_guion(pid, self._cuerpo_json().get("guion", ""))
            return self._json({"ok": True})
        if ruta == "/api/guion/aprobar":
            d = self._cuerpo_json()
            produccion.aprobar_guion(pid, d.get("guion"), forzar=bool(d.get("forzar")))
            return self._json({"ok": True})
        if ruta == "/api/guion/reabrir":
            produccion.reabrir_guion(pid, forzar=bool(self._cuerpo_json().get("forzar")))
            return self._json({"ok": True})
        if ruta == "/api/guion/reescribir":
            produccion.reescribir_guion(pid)
            return self._json({"ok": True})
        if ruta == "/api/escena":
            d = self._cuerpo_json()
            produccion.editar_escena(pid, int(d.pop("orden")), d)
            return self._json({"ok": True})
        if ruta == "/api/escena/activa":
            flow.marcar_activa(int(self._cuerpo_json().get("escena", 0)))
            return self._json({"ok": True})
        if ruta == "/api/visuales-api":
            d = self._cuerpo_json()
            limite = float(d.get("limite_usd", 0))
            if not 0 < limite <= 20:
                raise Error(400, "Indica un presupuesto entre 0 y 20 $")
            produccion.generar_visuales_api(pid, limite, [int(x) for x in d.get("video", [])])
            return self._json({"ok": True})
        if ruta == "/api/miniaturas/generar":
            produccion.generar_miniaturas(pid)
            return self._json({"ok": True})
        if ruta == "/api/miniaturas":
            produccion.ajustar_miniatura(pid, self._cuerpo_json())
            return self._json({"ok": True})
        if ruta == "/api/miniaturas/flow":
            flow.marcar_miniatura()
            return self._json({"ok": True})
        if ruta == "/api/subir":
            escena = int((query.get("escena") or ["0"])[0])  # 0 = imagen para la miniatura
            tmp = self._cuerpo_a_temporal()
            try:
                res = flow.recibir(tmp, self.headers.get("Content-Type", ""), pista=escena, origen="subida")
            finally:
                tmp.unlink(missing_ok=True)
            return self._json(res)
        if ruta == "/api/voz":
            produccion.rehacer_voz(pid, str(self._cuerpo_json().get("proveedor", "gemini")))
            return self._json({"ok": True})
        if ruta == "/api/subtitulos":
            produccion.ajustar_subtitulos(pid, self._cuerpo_json())
            return self._json({"ok": True})
        if ruta == "/api/render":
            produccion.renderizar(pid)
            return self._json({"ok": True})
        raise Error(404, "No existe")


def main() -> None:
    config.PRODUCCIONES.mkdir(parents=True, exist_ok=True)
    config.token_flow()  # crea el código de emparejamiento la primera vez
    for falta in config.salud():
        print(f"  ⚠ {falta}")
    if n := produccion.recuperar_trabajos_colgados():
        print(f"  ↺ {n} producción(es) tenían una fase a medias: quedan libres para relanzarla.")
    for resto in config.PRODUCCIONES.glob("studio4_*"):  # subidas que se cortaron
        resto.unlink(missing_ok=True)
    ThreadingHTTPServer.daemon_threads = True
    servidor = ThreadingHTTPServer(("127.0.0.1", config.PUERTO), Panel)
    print(f"\n  STUDIO 4 listo  →  http://127.0.0.1:{config.PUERTO}")
    print(f"  Vincular Flow   →  pulsa «Conectar Flow» en el panel\n")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
