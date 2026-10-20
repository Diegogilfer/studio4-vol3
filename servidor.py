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

from studio4 import (aprender, archivo, canales, carpetas, config, flow, galeria, guion, ideas, miniaturas, produccion, referencias, registro,
                     render, subtitulos, tendencias, voz, youtube)  # noqa: E402

# Todo lo que pasa queda en producciones/servidor.log (y lo grave, también en caidas.log): si Studio 4 se cae,
# se puede saber por qué. Antes solo se veía en la ventana negra y se perdía al cerrarla.
import faulthandler  # noqa: E402
import threading as _hilos  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402

config.PRODUCCIONES.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
                    handlers=[logging.StreamHandler(),
                              RotatingFileHandler(config.PRODUCCIONES / "servidor.log", maxBytes=2_000_000, backupCount=3,
                                                  encoding="utf-8")], force=True)
_caidas = open(config.PRODUCCIONES / "caidas.log", "a", encoding="utf-8")  # noqa: SIM115 - abierto mientras viva el proceso
faulthandler.enable(_caidas)   # una caída del propio Python (memoria, librería nativa) deja aquí su rastro
_hilos.excepthook = lambda a: logging.getLogger("studio4.hilos").error(
    "Error no controlado en %s", a.thread.name if a.thread else "?", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
logger = logging.getLogger("studio4.servidor")

HOSTS = {f"127.0.0.1:{config.PUERTO}", f"localhost:{config.PUERTO}"}
ORIGENES_PANEL = {f"http://{h}" for h in HOSTS}
PAGINAS = {"/legal": "legal.html", "/": "index.html", "/flow/emparejar": "emparejar.html", "/lateral": "lateral.html",
           "/youtube": "youtube.html"}   # vista previa: tus vídeos y miniaturas como se verían en YouTube
MEDIOS_PERMITIDOS = re.compile(r"^(tomas/[\w.-]+|ref/[\w.-]+|voz\.wav|final\.mp4|muestras/[\w.-]+\.wav|entregas/[\w.-]+\.(mp4|jpg)|miniaturas/(candidatos/|fuentes/)?[\w.-]+\.jpg)$")


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
        sitio = self.headers.get("Sec-Fetch-Site")
        if sitio is not None and sitio not in ("same-origin", "none"):
            raise Error(403, "Solo el panel de STUDIO 4 puede hacer esto")
        ref = self.headers.get("Referer")
        if ref is not None and not any(ref == o or ref.startswith(o + "/") for o in ORIGENES_PANEL):
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
            logger.warning("Rechazado %s: %s", ruta, e)   # queda en servidor.log para saber por qué no se hizo
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
        if ruta.startswith("/material/"):
            try:
                return self._archivo(carpetas.archivo_material(urllib.parse.unquote(ruta[10:])))
            except FileNotFoundError as e:
                raise Error(404, "No existe") from e
        if ruta == "/api/material":
            return self._json({"items": carpetas.listar_material(canales.activo()["id"])})
        if ruta == "/api/estado":
            return self._json(self._estado())
        if ruta == "/api/producciones":
            return self._json(produccion.listar(canales.activo()["id"]))
        if ruta == "/api/tendencias":
            return self._json(tendencias.estado(canales.activo()["id"]))
        if ruta == "/api/manual":
            return self._json(aprender.estado(canales.activo()["id"]))
        if ruta == "/api/biblioteca":   # los guiones guardados del canal
            from studio4 import biblioteca
            cid = canales.activo()["id"]
            return self._json({"guiones": biblioteca.con_parecidos(biblioteca.leer(cid)), "plan": biblioteca.plan_con_estado(cid)})
        if ruta == "/api/ideas/diarias":   # 3 ideas listas cada día, preparadas solas
            return self._json(ideas.diarias(canales.activo()["id"]))
        if ruta == "/api/importar/vista":   # qué hay detrás del enlace, para confirmar antes de procesar
            from studio4 import importar
            q = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("url") or [""])[0].strip()
            return self._json(importar.vista_previa(q))
        if ruta == "/api/reales":   # capturas reales de las fuentes de confianza del canal
            q = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0].strip()
            return self._json({"fotos": galeria.buscar(canales.activo()["id"], q) if len(q) >= 2 else []})
        if ruta == "/api/archivo":
            q = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0].strip()
            return self._json({"fotos": archivo.buscar(q) if len(q) >= 2 else []})
        if ruta == "/api/panel":   # panel de control: todos los canales con sus redes y su YouTube
            leer = youtube.canal if youtube.disponible() else (lambda _u: None)
            return self._json({"activo": canales.activo()["id"],
                               "canales": [canales.resumen(c["id"], leer, produccion.listar(c["id"])) for c in canales.listar()]})
        if ruta == "/api/canales":
            return self._json({"canales": canales.listar(), "activo": canales.activo()["id"], "redes": canales.REDES})
        if ruta == "/api/voces/elevenlabs":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            forzar = (q.get("forzar") or [""])[0] in ("1", "true", "si")
            return self._json(voz.catalogo_elevenlabs(forzar=forzar))
        if ruta == "/api/voz/oir":   # frase de presentación de una voz (se graba una vez y se guarda)
            nombre = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("voz", [""])[0]
            if nombre.startswith("fal:"):   # voz de pago: la muestra se graba una vez (≈0,01 $) y se guarda
                return self._archivo(voz.muestra_fal(nombre[4:]))
            return self._archivo(voz.muestra_generica(nombre))
        if ruta == "/api/subtitulos/vista":   # fotograma de muestra con los subtítulos actuales
            pid = produccion.activa()
            if not pid:
                raise Error(404, "No hay producción activa")
            return self._archivo(render.vista_subtitulos(produccion.cargar(pid), produccion.carpeta(pid)))
        if ruta == "/api/flow/todo":   # toda la producción en un texto para pegar en Flow (Flow Agent)
            pid = produccion.activa()
            if not pid:
                raise Error(400, "No hay ninguna producción abierta.")
            return self._json({"texto": flow.todo_para_flow(produccion.cargar(pid))})
        if ruta == "/api/sesion-flow":  # lo mismo que ve la extensión, para la vista lateral
            return self._json(flow.sesion_para_extension())
        raise Error(404, "No existe")

    def _estado(self) -> dict[str, Any]:
        pid = produccion.activa()
        p = produccion.cargar(pid) if pid else None
        if p:
            p["ia_detectada"] = guion.frases_prohibidas(p.get("guion", ""))
            try:   # la carpeta de clips, a la vista: cuántos hay y a cuántas escenas van
                p["carpeta_clips"] = carpetas.estado(p) if p.get("carpeta") else None
            except OSError:
                p["carpeta_clips"] = None
            p["hermanas"] = [x for x in produccion.listar() if p.get("familia") and x["familia"] == p["familia"]]
            p["estimacion_voz"] = voz.estimar_voz(
                [e["texto_voz"] for e in p.get("escenas", [])],
                p.get("proveedor_voz", "gemini"),
                p.get("voice_id", ""),
            )
        canal = canales.activo()
        return {
            "produccion": p,
            "canal": canal,
            "manual_fecha": (aprender.leer(canal["id"]) or {}).get("fecha", ""),
            "fal": bool(config.FAL_KEY) and not config.SIN_PAGO,   # para ofrecer la voz de fal si Google no tiene saldo
            "canales": [{"id": c["id"], "nombre": c["nombre"]} for c in canales.listar()],
            "extension": flow.estado_extension(),
            "codigo": config.token_flow(),
            "carpeta_extension": str(config.RAIZ / "extension-flow"),
            "consumo": registro.consumo_del_mes(),
            "elevenlabs_restantes": registro.creditos_elevenlabs_restantes(),
            "opciones": {
                "formatos": {k: v["nombre"] for k, v in config.FORMATOS.items()},
                "estilos": list(config.ESTILOS),
                "voces": dict(voz.PROVEEDORES),
                "paletas": {k: v["nombre"] for k, v in subtitulos.PALETAS.items()},
                "gemini_ok": bool(config.GEMINI_API_KEY),
                "deepseek_ok": bool(config.DEEPSEEK_API_KEY or config.XIAOMIMIMO_API_KEY),
                "mimo_ok": bool(config.XIAOMIMIMO_API_KEY),
                "elevenlabs_ok": bool(config.ELEVENLABS_API_KEY),
                "elevenlabs_modelo": config.ELEVENLABS_MODEL,
                "elevenlabs_por_defecto": config.ELEVENLABS_VOICE_ID or voz.VOZ_ELEVENLABS_POR_DEFECTO,
                "sin_pago": config.SIN_PAGO,
                "voces_gemini": config.VOCES_GEMINI, "voz_por_defecto": config.VOZ_GEMINI,
                "voces_mimo": voz.VOCES_MIMO, "voces_fal": voz.VOCES_FAL, "voz_fal_por_defecto": voz.VOZ_FAL, "voz_mimo_por_defecto": voz.VOZ_MIMO_POR_DEFECTO,
                "versiones": config.VERSIONES,
                "salud": config.salud(),
                "plataformas": {k: v["nombre"] for k, v in miniaturas.PLATAFORMAS.items()},
            },
        }

    def _post(self, ruta: str, query: dict[str, list[str]]) -> None:
        # --- extensión de Flow (con código de emparejamiento) ---
        if ruta.startswith("/api/flow/") and ruta != "/api/flow/renovar":
            self._solo_extension()
            flow.latido(self.headers.get("X-Flow-Version", ""), self.headers.get("X-Flow-Abierto", "1") != "0")
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
        if ruta == "/api/extension/abrir":   # la carpeta de la extensión buena, para cargarla en Chrome
            os.startfile(str(config.RAIZ / "extension-flow"))  # noqa: S606 - abre el Explorador en tu propio PC
            return self._json({"ok": True})
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
                                    publico=str(d.get("publico", "")), voz_nombre=str(d.get("voz_nombre", "")),
                                    voice_id=str(d.get("voice_id", "")),
                                    voz_elevenlabs_nombre=str(d.get("voz_elevenlabs_nombre", "")),
                                    velocidad_voz=float(d.get("velocidad_voz") or 1.0),
                                    reparto=[{"nombre": str(r.get("nombre", ""))[:40], "ficha": str(r.get("ficha", ""))[:600]}
                                             for r in d.get("reparto") or [] if isinstance(r, dict) and r.get("nombre")],
                                    refs=referencias.preparar(d.get("referencias"), [
                                        {"id": str(i.get("id", "")), "tipo": i.get("tipo") if i.get("tipo") in ("foto", "documento") else "documento",
                                         "nombre": str(i.get("nombre", ""))[:80]} for i in (d.get("referencias") or {}).get("items") or []]))
            return self._json({"ok": True, "ids": pids})
        if ruta == "/api/canales":
            return self._json({"ok": True, "canal": canales.guardar(self._cuerpo_json())})
        if ruta == "/api/tendencias":
            tendencias.lanzar(canales.activo()["id"])
            return self._json({"ok": True})
        if ruta == "/api/manual":
            aprender.lanzar(canales.activo()["id"])
            return self._json({"ok": True})
        if ruta == "/api/modelo":   # «así quiero mis vídeos»: un vídeo de ejemplo que manda sobre el estilo
            d = self._cuerpo_json()
            url = str(d.get("url", "")).strip()
            if not url.startswith(("http://", "https://")):
                raise Error(400, "Pega el enlace del vídeo modelo.")
            return self._json(aprender.estudiar_modelo(canales.activo()["id"], url, str(d.get("nota", ""))[:600]))
        if ruta in ("/api/biblioteca", "/api/biblioteca/crear", "/api/biblioteca/quitar"):
            from studio4 import biblioteca
            d = self._cuerpo_json()
            cid = canales.activo()["id"]
            if ruta == "/api/biblioteca":   # pegar un paquete de guiones o el plan del mes
                return self._json(biblioteca.pegar(cid, str(d.get("texto", ""))))
            if ruta == "/api/biblioteca/quitar":
                biblioteca.quitar(cid, str(d.get("id", "")))
                return self._json({"ok": True})
            ids = [str(x) for x in d.get("ids") or []]
            pids = [produccion.desde_biblioteca(cid, i, str(d.get("voz", "gemini")), str(d.get("estilo", "")),
                                                float(d.get("velocidad_voz") or 1.0)) for i in ids]
            return self._json({"ok": True, "ids": pids})
        if ruta == "/api/clave-gemini":   # clave nueva de AI Studio: se prueba con una voz antes de guardarla
            from studio4 import gemini
            gemini.cambiar_clave(str(self._cuerpo_json().get("clave", "")))
            return self._json({"ok": True})
        if ruta == "/api/ideas/diarias":   # volver a preparar las 3 ideas de hoy
            ideas.lanzar_diarias(canales.activo()["id"])
            return self._json({"ok": True})
        if ruta == "/api/ideas/vivo":   # lo que más crece esta semana en el nicho del canal
            return self._json({"videos": ideas.en_vivo(canales.activo()["id"])})
        if ruta == "/api/ideas/inspirar":   # una idea original a partir de un vídeo en tendencia
            d = ideas.inspirar(canales.activo()["id"], self._cuerpo_json())
            return self._json({**d, "texto": ideas.como_texto(d)})
        if ruta == "/api/canales/parecidos":   # canales del mismo nicho para tomarlos de referencia
            c = canales.obtener(str(self._cuerpo_json().get("id", "")) or canales.activo()["id"])
            return self._json({"canales": tendencias.parecidos(c)})
        if ruta == "/api/canales/activar":
            return self._json({"ok": True, "canal": canales.activar(str(self._cuerpo_json().get("id", "")))})
        if ruta == "/api/referencias":   # foto o documento para el vídeo que se va a crear
            tmp = self._cuerpo_a_temporal()
            try:
                return self._json(referencias.subir(tmp, urllib.parse.unquote(self.headers.get("X-Nombre", "")),
                                                    self.headers.get("Content-Type", "")))
            finally:
                tmp.unlink(missing_ok=True)
        if ruta == "/api/importar":   # un vídeo ya hecho, por enlace (solo tuyo o con derechos)
            d = self._cuerpo_json()
            if not d.get("derechos"):
                raise Error(400, "Acepta los términos de uso para continuar.")
            return self._json({"ok": True, "id": produccion.importar_video(url=str(d.get("url", "")).strip(),
                                                                           completo=bool(d.get("completo")))})
        if ruta == "/api/importar/archivo":
            if (query.get("derechos") or [""])[0] != "1":
                raise Error(400, "Acepta los términos de uso para continuar.")
            tmp = self._cuerpo_a_temporal()
            try:
                return self._json({"ok": True, "id": produccion.importar_video(
                    archivo=tmp, nombre=urllib.parse.unquote(self.headers.get("X-Nombre", "")),
                    completo=(query.get("completo") or [""])[0] == "1")})
            finally:
                tmp.unlink(missing_ok=True)
        if ruta == "/api/guion/desde-archivo":   # tu guion en un archivo: se queda solo la narración
            tmp = self._cuerpo_a_temporal()
            try:
                return self._json(referencias.guion_de_archivo(tmp, urllib.parse.unquote(self.headers.get("X-Nombre", "")),
                                                               self.headers.get("Content-Type", "")))
            finally:
                tmp.unlink(missing_ok=True)
        if ruta == "/api/referencias/borrar":
            referencias.borrar(str(self._cuerpo_json().get("id", "")))
            return self._json({"ok": True})
        if ruta == "/api/crear-rapido":   # un clic desde una idea o un nicho: lo de siempre del canal
            d = self._cuerpo_json()
            return self._json({"ok": True, "ids": produccion.crear_rapido(str(d.get("idea", "")), str(d.get("version", "corto")),
                                                                          datos=str(d.get("datos", "")))})
        if ruta == "/api/producciones/eliminar":
            produccion.eliminar(str(self._cuerpo_json().get("id", "")))
            return self._json({"ok": True})
        if ruta == "/api/activar":
            pid = str(self._cuerpo_json().get("id", ""))
            canales.activar(produccion.cargar(pid)["canal"])   # abrir una producción abre su canal
            produccion.activar(pid)
            return self._json({"ok": True})
        if ruta == "/api/carpeta/abrir":
            d = self._cuerpo_json()
            video = str(d.get("video", "")).strip()
            if video:
                destino = carpetas.carpeta_material(canales.activo()["id"], video)
            else:
                pid = produccion.activa()
                if not pid:
                    raise Error(409, "No hay producción activa")
                base = produccion.preparar_carpeta(pid)
                sub = str(d.get("sub", ""))
                p_act = produccion.cargar(pid)
                destino = (base / carpetas.subcarpeta(p_act, sub)
                           if sub in (carpetas.CLIPS, carpetas.GUION, carpetas.ENTREGAS, carpetas.MATERIAL) else base)
            os.startfile(str(destino))  # noqa: S606 - abre el Explorador de Windows en tu propio PC
            return self._json({"ok": True, "ruta": str(destino)})

        pid = produccion.activa()
        if not pid:
            raise Error(409, "No hay producción activa")
        if ruta == "/api/personajes/afinar":
            produccion.afinar_personajes(pid)
            return self._json({"ok": True})
        if ruta == "/api/reintentar":
            produccion.reintentar(pid)
            return self._json({"ok": True})
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
        if ruta == "/api/edicion":   # transición, efecto, carátula y recorte (se aplican al volver a montar)
            produccion.editar(pid, self._cuerpo_json())
            return self._json({"ok": True})
        if ruta == "/api/escena/anadir":   # una escena tuya, después de la que digas (0 = al principio)
            d = self._cuerpo_json()
            produccion.anadir_escena(pid, int(d.get("despues", 0)), d.get("texto_voz", ""), d.get("que_se_ve", ""),
                                     d.get("tipo_clip", "video"))
            return self._json({"ok": True})
        if ruta == "/api/escena/quitar":
            produccion.quitar_escena(pid, int(self._cuerpo_json().get("orden", 0)))
            return self._json({"ok": True})
        if ruta == "/api/guion/original":   # deshace «Completar la historia»: tu texto tal cual
            produccion.volver_guion_original(pid)
            return self._json({"ok": True})
        if ruta == "/api/guion/completar":   # tu guion se queda corto: investigar y contar la historia completa
            produccion.completar_guion(pid)
            return self._json({"ok": True})
        if ruta == "/api/escena":
            d = self._cuerpo_json()
            produccion.editar_escena(pid, int(d.pop("orden")), d)
            return self._json({"ok": True})
        if ruta == "/api/escena/real":   # captura real de tus fuentes
            d = self._cuerpo_json()
            return self._json({"ok": True, "toma": produccion.poner_imagen_real(pid, int(d.get("orden", 0)), str(d.get("url", "")),
                                                                                 str(d.get("pagina", "")))})
        if ruta == "/api/reales/rellenar":   # gratis: una captura real para cada escena sin clip
            produccion.rellenar_reales(pid)
            return self._json({"ok": True})
        if ruta == "/api/escena/archivo":   # foto histórica de dominio público (Wikimedia Commons)
            d = self._cuerpo_json()
            return self._json({"ok": True, "toma": produccion.poner_foto_archivo(pid, int(d.get("orden", 0)), str(d.get("titulo", "")))})
        if ruta == "/api/escena/activa":
            flow.marcar_activa(int(self._cuerpo_json().get("escena", 0)))
            return self._json({"ok": True})
        if ruta == "/api/tarjetas":   # escenas gratis: tarjetas de diseño para las que no tienen clip
            produccion.rellenar_tarjetas(pid)
            return self._json({"ok": True})
        if ruta == "/api/visuales-api/estimar":
            return self._json(produccion.estimar_visuales_api(pid))
        if ruta == "/api/visuales-api":   # todas las escenas de una vez, por la API de pago de Google, con tope
            d = self._cuerpo_json()
            limite = float(d.get("limite_usd", 0))
            if not 0 < limite <= 60:
                raise Error(400, "Indica un tope de gasto entre 0 y 60 $")
            produccion.generar_visuales_api(pid, limite, solo_imagenes=bool(d.get("solo_imagenes")))
            return self._json({"ok": True})
        if ruta == "/api/entregas":
            produccion.preparar_entregas(pid)
            return self._json({"ok": True})
        if ruta == "/api/escenas/tipos":
            produccion.recomendar_tipos(pid)
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
        if ruta == "/api/voz/muestras":
            produccion.muestras_voz(pid, [str(v) for v in self._cuerpo_json().get("voces", [])])
            return self._json({"ok": True})
        if ruta == "/api/voz/elegir":
            produccion.elegir_voz(pid, str(self._cuerpo_json().get("voz", "")))
            return self._json({"ok": True})
        if ruta == "/api/voz/seleccionar":
            d = self._cuerpo_json()
            res = produccion.seleccionar_voz(
                pid,
                str(d.get("proveedor") or "gemini"),
                voice_id=str(d.get("voice_id") or ""),
                voz_nombre=str(d.get("voz_nombre") or ""),
            )
            return self._json({"ok": True, **res})
        if ruta == "/api/voz":
            d = self._cuerpo_json()
            produccion.rehacer_voz(
                pid,
                str(d.get("proveedor") or "gemini"),
                voice_id=str(d.get("voice_id") or ""),
                voz_nombre=str(d.get("voz_nombre") or ""),
            )
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
    for pid in produccion.recuperar_trabajos_colgados():   # lo que se cortó al cerrar, sigue donde se quedó
        logger.info("Retomando %s (se cortó al cerrar Studio 4)", pid)
        try:
            produccion.retomar(pid)
        except Exception as e:  # noqa: BLE001 - una que no se pueda retomar queda con «Reintentar»
            logger.warning("No se pudo retomar %s: %s", pid, e)
    referencias.limpiar_espera()
    for resto in config.PRODUCCIONES.glob("studio4_*"):  # subidas que se cortaron
        resto.unlink(missing_ok=True)
    # Vigilante: los clips que dejes en «1 Clips de Flow» de la producción activa entran solos en su escena.
    import threading
    import time as _t

    def vigilar():
        while True:
            _t.sleep(4)
            try:
                pid = produccion.activa()
                if pid and (n := produccion.importar_carpeta(pid)):
                    logger.info("Carpeta: %d clip(s) nuevos importados", n)
                    flow.anotar_evento("recibida", f"{n} clip(s) desde tu carpeta «1 Clips de Flow»")
            except Exception as e:  # noqa: BLE001 - el vigilante nunca se cae
                logger.warning("Vigilante de la carpeta: %s", e)
    threading.Thread(target=vigilar, name="studio4-carpeta", daemon=True).start()
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
