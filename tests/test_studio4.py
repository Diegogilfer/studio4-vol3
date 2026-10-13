"""Pruebas de STUDIO 4. Sin red: Gemini y la extensión se simulan. Las de FFmpeg se saltan si no está instalado.

    python -m pytest -q
"""

from __future__ import annotations

import http.client
import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from studio4 import config, director, flow, medios, produccion, registro, render, subtitulos, voz

hay_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg no está instalado")


@pytest.fixture()
def aislado(tmp_path, monkeypatch):
    """Cada prueba con su propia carpeta de producciones y su propio registro."""
    monkeypatch.setattr(config, "PRODUCCIONES", tmp_path)
    monkeypatch.setattr(produccion, "_ACTIVA", tmp_path / "activa.txt")
    monkeypatch.setattr(registro, "_MOVIMIENTOS", tmp_path / "movimientos.jsonl")
    monkeypatch.setattr(registro, "_CONSUMO", tmp_path / "consumo.json")
    return tmp_path


def _produccion(pid: str, escenas: int = 3, **extra) -> dict:
    p = {"id": pid, "creado": "2026-10-12 10:00:00", "tema": "prueba", "segundos": 20, "formato": "vertical",
         "estilo": "documental", "proveedor_voz": "gemini", "estado": "rodando", "trabajo": {}, "guion": "x",
         "titulo": "", "descripcion": "", "hashtags": [], "biblia": {}, "escena_activa": 1, "voz": None,
         "subtitulos": dict(subtitulos.POR_DEFECTO), "final": None,
         "escenas": [{"orden": i + 1, "texto_voz": f"frase {i + 1}", "texto_pantalla": "",
                      "prompt_flow": f"wide shot of a red lighthouse number {i + 1} on a cliff", "tomas": [], "elegida": None}
                     for i in range(escenas)]}
    p.update(extra)
    produccion.carpeta(pid).mkdir(parents=True)
    produccion.guardar(p)
    produccion.activar(pid)
    return p


# --- Voz: cortes de escena --------------------------------------------------------------------
def test_cortes_eligen_pausas_largas_aunque_la_proporcion_falle(monkeypatch):
    monkeypatch.setattr(voz.medios, "duracion", lambda _: 20.0)
    # Comas (pausas cortas) y dos fines de frase (pausas largas) en 5,25 s y 10,15 s.
    monkeypatch.setattr(voz.medios, "silencios", lambda _: [(2.0, 2.15), (4.9, 5.6), (7.0, 7.12), (9.8, 10.5), (15, 15.1)])
    texto, spans = voz._spans_escenas(["aaaa bbbb cccc dddd eeee, ffff", "gggg hhhh iiii, jjjj kkkk",
                                       "llll mmmm nnnn oooo pppp qqqq rrrr ssss"])
    assert [round(c, 2) for c in voz._cortes_por_silencio("x", texto, spans)] == [0.0, 5.25, 10.15]


def test_cortes_sin_pausas_usan_proporcion(monkeypatch):
    monkeypatch.setattr(voz.medios, "duracion", lambda _: 10.0)
    monkeypatch.setattr(voz.medios, "silencios", lambda _: [])
    texto, spans = voz._spans_escenas(["aaaa", "bbbb"])
    assert voz._cortes_por_silencio("x", texto, spans) == [0.0, 5.0]


def test_alineacion_elevenlabs_da_cortes_exactos():
    texto, spans = voz._spans_escenas(["Hola mundo.", "Adiós."])
    ini = [i * 0.1 for i in range(len(texto))]
    cortes, palabras = voz._tiempos_alineados(texto, spans, {
        "character_start_times_seconds": ini, "character_end_times_seconds": [t + 0.1 for t in ini]}, 2.0)
    assert cortes == [0.0, pytest.approx(1.2)]
    assert [p["palabra"] for p in palabras] == ["Hola", "mundo.", "Adiós."]


def test_reserva_de_voz(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    assert voz.reserva("gemini") is None
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "k")
    assert voz.reserva("gemini") == "elevenlabs"


# --- Subtítulos ---------------------------------------------------------------------------------
def test_subtitulos_nunca_se_encima_una_linea(tmp_path):
    palabras = [{"palabra": f"p{i}.", "ini": i * 0.4, "fin": i * 0.4 + 0.39} for i in range(20)]
    ass = subtitulos.construir(palabras, tmp_path / "s.ass", 1080, 1920, gancho="GANCHO")
    tiempos = []
    for linea in ass.read_text(encoding="utf-8").splitlines():
        if linea.startswith("Dialogue: 0"):
            _, ini, fin = linea.split(",")[:3]
            a = lambda t: sum(float(x) * m for x, m in zip(t.split(":"), (3600, 60, 1)))  # noqa: E731
            tiempos.append((a(ini), a(fin)))
    assert tiempos and all(b[0] >= a[1] - 1e-6 for a, b in zip(tiempos, tiempos[1:]))
    assert "GANCHO" in ass.read_text(encoding="utf-8")


def test_subtitulos_limpian_llaves_ass(tmp_path):
    ass = subtitulos.construir([{"palabra": "{\\b1}hola", "ini": 0, "fin": 1}], tmp_path / "s.ass", 1920, 1080)
    assert "{\\b1}HOLA" not in ass.read_text(encoding="utf-8")


# --- Director -----------------------------------------------------------------------------------
def test_prompt_de_flow_lleva_la_biblia_completa():
    biblia = {"escenario_en": "foggy coast", "luz_en": "blue hour", "paleta_en": "teal, amber",
              "personajes": [{"nombre": "LEO", "aspecto_en": "old keeper, grey beard, yellow raincoat"}]}
    esc = {"plano_en": "wide", "camara_en": "slow dolly-in", "accion_en": "LEO climbs the stairs", "personajes": ["leo"]}
    p = director._prompt_flow(esc, biblia, "cinematic", "9:16")
    for trozo in ("LEO is old keeper, grey beard, yellow raincoat", "foggy coast", "blue hour", "9:16", "no dialogue"):
        assert trozo in p


# --- Flow: a qué escena va cada clip ------------------------------------------------------------
def test_destino_por_pista_prompt_activa_y_hueco():
    p = {"escena_activa": 2, "escenas": [
        {"orden": 1, "prompt_flow": "wide shot red lighthouse cliff storm waves", "tomas": [{"tipo": "video"}]},
        {"orden": 2, "prompt_flow": "macro shot of old brass gears turning", "tomas": []},
        {"orden": 3, "prompt_flow": "aerial view of night city lights", "tomas": []}]}
    assert flow._escena_destino(p, 3, "") == 3
    assert flow._escena_destino(p, None, "Aerial view of night city lights, cinematic") == 3
    assert flow._escena_destino(p, None, "") == 2
    p["escena_activa"] = 0
    assert flow._escena_destino(p, None, "") == 2


@hay_ffmpeg
def test_recibir_guarda_toma_y_descarta_repetidas_y_miniaturas(aislado):
    _produccion("p1")
    clip = aislado / "clip.mp4"
    medios.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=720x1280:r=24:d=1", "-pix_fmt", "yuv420p", str(clip))
    copia = aislado / "copia.mp4"
    shutil.copy(clip, copia)
    assert flow.recibir(clip, "video/mp4")["escena"] == 1
    assert flow.recibir(copia, "video/mp4")["repetida"] is True
    mini = aislado / "mini.png"
    medios.ffmpeg("-f", "lavfi", "-i", "color=red:s=64x64", "-frames:v", "1", str(mini))
    with pytest.raises(ValueError, match="pequeña"):
        flow.recibir(mini, "image/png")
    p = produccion.cargar("p1")
    assert p["escenas"][0]["elegida"] == 0 and len(p["escenas"][0]["tomas"]) == 1


# --- Producción ---------------------------------------------------------------------------------
def test_recuperar_trabajos_colgados(aislado):
    _produccion("p2", trabajo={"ocupado": True, "fase": "Render"}, estado="renderizando")
    assert produccion.recuperar_trabajos_colgados() == 1
    p = produccion.cargar("p2")
    assert not p["trabajo"]["ocupado"] and p["estado"] == "rodando" and "Render" in p["trabajo"]["error"]


def test_borrar_toma_elegida_reajusta_la_eleccion(aislado):
    _produccion("p3")
    (aislado / "p3" / "tomas").mkdir()
    def tomas(p):
        p["escenas"][0]["tomas"] = [{"archivo": f"tomas/{i}.mp4", "tipo": "video"} for i in range(3)]
        p["escenas"][0]["elegida"] = 2
    produccion.modificar("p3", tomas)
    produccion.editar_escena("p3", 1, {"borrar_toma": 2})
    assert produccion.cargar("p3")["escenas"][0]["elegida"] == 1
    with pytest.raises(ValueError):
        produccion.editar_escena("p3", 9, {"elegida": 0})


def test_ids_de_produccion_no_permiten_salir_de_la_carpeta():
    for malo in ("../x", "..\\x", "a/b", ""):
        with pytest.raises(ValueError):
            produccion.carpeta(malo)


# --- Render -------------------------------------------------------------------------------------
@hay_ffmpeg
def test_render_ajusta_cada_clip_a_su_voz(aislado):
    p = _produccion("p4", escenas=2)
    base = aislado / "p4"
    (base / "tomas").mkdir()
    medios.ffmpeg("-f", "lavfi", "-i", "sine=f=300:d=3", "-ar", "24000", "-ac", "1", str(base / "voz.wav"))
    medios.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=24:d=1", "-pix_fmt", "yuv420p", str(base / "tomas/a.mp4"))
    medios.ffmpeg("-f", "lavfi", "-i", "mandelbrot=s=512x512", "-frames:v", "1", str(base / "tomas/b.png"))
    p["escenas"][0].update(tomas=[{"archivo": "tomas/a.mp4", "tipo": "video"}], elegida=0)
    p["escenas"][1].update(tomas=[{"archivo": "tomas/b.png", "tipo": "imagen"}], elegida=0)
    p["voz"] = {"archivo": "voz.wav", "duracion": 3.0, "escenas": [{"ini": 0, "fin": 1.6}, {"ini": 1.6, "fin": 3.0}],
                "palabras": [{"palabra": "hola", "ini": 0.1, "fin": 0.5}, {"palabra": "mundo", "ini": 1.7, "fin": 2.2}]}
    final = render.renderizar(p, base)
    inf = medios.info(final)
    assert (inf["ancho"], inf["alto"]) == (1080, 1920) and inf["audio"]
    assert inf["duracion"] == pytest.approx(3.0 + render.COLA_FINAL, abs=0.15)


def test_render_dice_que_escena_falta(aislado):
    p = _produccion("p5", escenas=2, voz={"archivo": "voz.wav", "duracion": 2, "escenas": [{}, {}], "palabras": []})
    with pytest.raises(RuntimeError, match="1, 2"):
        render.renderizar(p, aislado / "p5")


# --- Servidor: seguridad ------------------------------------------------------------------------
@pytest.fixture()
def servidor(aislado, monkeypatch):
    import servidor as srv
    monkeypatch.setenv(config.VAR_TOKEN, "codigo-de-prueba")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Panel)
    puerto = httpd.server_address[1]
    monkeypatch.setattr(srv, "HOSTS", {f"127.0.0.1:{puerto}"})
    monkeypatch.setattr(srv, "ORIGENES_PANEL", {f"http://127.0.0.1:{puerto}"})
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def pedir(metodo, ruta, cabeceras=None, cuerpo=None):
        c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
        c.request(metodo, ruta, body=cuerpo, headers=cabeceras or {})
        r = c.getresponse()
        return r.status, r.read()
    yield pedir, puerto
    httpd.shutdown()


def test_servidor_no_entrega_secretos_ni_codigo(servidor):
    pedir, _ = servidor
    for ruta in ("/.env", "/servidor.py", "/studio4/config.py", "/web/../.env", "/media/x/../../.env", "/media/x/proyecto.json"):
        assert pedir("GET", ruta)[0] == 404, ruta


def test_servidor_rechaza_host_origen_y_extension_sin_codigo(servidor):
    pedir, puerto = servidor
    assert pedir("GET", "/api/estado", {"Host": "evil.com"})[0] == 403
    assert pedir("POST", "/api/producciones", {"Origin": "https://evil.com"}, b"{}")[0] == 403
    assert pedir("POST", "/api/flow/hola")[0] == 401
    estado, cuerpo = pedir("POST", "/api/flow/hola", {"X-Studio4-Token": "codigo-de-prueba"})
    assert estado == 200 and json.loads(cuerpo)["ok"]
    assert pedir("GET", "/", {"Host": f"127.0.0.1:{puerto}"})[0] == 200


def test_copiar_escena_arma_la_extension_y_queda_registro(servidor):
    pedir, _ = servidor
    _produccion("p6")
    cab = {"X-Studio4-Token": "codigo-de-prueba", "Content-Type": "application/json"}
    antes = json.loads(pedir("POST", "/api/flow/hola", cab)[1])["sesion"]["armado"]
    sesion = json.loads(pedir("POST", "/api/flow/activa", cab, b'{"escena": 2}')[1])["sesion"]
    assert sesion["armado"] > antes and sesion["siguiente"]["escena"] == 2
    pedir("POST", "/api/flow/diagnostico", cab, json.dumps({"tipo": "error", "detalle": "prueba"}).encode())
    pedir("POST", "/api/flow/recibir", {"X-Studio4-Token": "codigo-de-prueba", "Content-Type": "video/mp4"}, b"no es un video")
    eventos = flow.estado_extension()["eventos"]
    assert eventos[0]["tipo"] == "rechazada" and eventos[1]["detalle"] == "prueba"
