"""Pruebas de STUDIO 4. Sin red: Gemini y la extensión se simulan. Las de FFmpeg se saltan si no está instalado.

    python -m pytest -q
"""

from __future__ import annotations

import http.client
import json
import pathlib
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
    from studio4 import carpetas, youtube   # las pruebas nunca consultan YouTube ni escriben en tus Vídeos
    monkeypatch.setattr(carpetas, "RAIZ_USUARIO", tmp_path / "Videos")
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "")
    monkeypatch.setattr(youtube, "TOKEN", tmp_path / "youtube_token.json")
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


# --- Miniaturas -----------------------------------------------------------------------------------
from studio4 import miniaturas  # noqa: E402


def _foto(ruta: Path, ancho=1920, alto=1080) -> Path:
    from PIL import Image
    Image.radial_gradient("L").resize((ancho, alto)).convert("RGB").save(ruta)
    return ruta


@pytest.mark.parametrize("pl", list(miniaturas.PLATAFORMAS))
def test_miniatura_tamano_peso_y_texto_dentro_de_su_zona(tmp_path, pl, monkeypatch):
    cajas = []
    original = miniaturas._texto

    def espiar(lienzo, texto, resalte, zona, alinear):
        antes = lienzo.copy()
        original(lienzo, texto, resalte, zona, alinear)
        from PIL import ImageChops
        cajas.append(ImageChops.difference(antes.convert("RGB"), lienzo.convert("RGB")).getbbox())
    monkeypatch.setattr(miniaturas, "_texto", espiar)
    salida = miniaturas.componer(_foto(tmp_path / "f.jpg"), tmp_path / f"{pl}.jpg", pl, "EL TERCER CORAZÓN SE PARA", "CORAZÓN")
    from PIL import Image
    p = miniaturas.PLATAFORMAS[pl]
    assert Image.open(salida).size == (p["ancho"], p["alto"])
    assert salida.stat().st_size < 2 * 1024 * 1024          # límite de YouTube
    x0, y0, x1, y1 = cajas[0]
    margen = 0.03                                            # contorno y sombra
    assert y0 >= (p["zona"][1] - margen) * p["alto"] and y1 <= (p["zona"][3] + margen) * p["alto"]
    if pl == "reels":                                        # dentro del recorte 3:4 del perfil (y 240..1680)
        assert y0 >= 240 and y1 <= 1680


def test_encuadre_sigue_al_sujeto():
    from PIL import Image
    im = Image.new("RGB", (1920, 1080), "black")
    im.paste((255, 0, 0), (1700, 400, 1800, 600))           # sujeto rojo pegado a la derecha
    recorte = miniaturas._encuadrar(im, 1080, 1920, fx=1750 / 1920, fy=0.5)
    assert recorte.size == (1080, 1920)
    assert recorte.getpixel((recorte.width - 200, 960))[0] > 200 or any(
        recorte.getpixel((x, 960))[0] > 200 for x in range(0, 1080, 20))


def test_plataformas_por_formato():
    assert miniaturas.plataformas("vertical") == ["shorts", "reels"]
    assert miniaturas.plataformas("horizontal") == ["youtube"]


@hay_ffmpeg
def test_imagen_de_flow_para_miniatura_se_compone(aislado):
    _produccion("p7", recoger_para="miniatura", titulo="El faro sin farero")
    foto = _foto(aislado / "flow.png", 1024, 1024)
    res = flow.recibir(foto, "image/png")
    assert res["tipo"] == "miniatura"
    p = produccion.cargar("p7")
    assert p["miniaturas"]["salidas"] == {"shorts": "miniaturas/shorts.jpg", "reels": "miniaturas/reels.jpg"}
    assert (aislado / "p7" / "miniaturas" / "reels.jpg").exists()
    produccion.ajustar_miniatura("p7", {"texto": "NADIE LO APAGÓ", "resalte": "NADIE"})
    assert produccion.cargar("p7")["miniaturas"]["texto"] == "NADIE LO APAGÓ"
    flow.marcar_activa(1)                                    # volver a una escena deja de recoger para la miniatura
    assert produccion.cargar("p7")["recoger_para"] == "escenas"


# --- Guion: investigación + DeepSeek, tu aprobación y escenas ---------------------------------------
import time as _time  # noqa: E402

from studio4 import deepseek, guion, investigacion  # noqa: E402


def _esperar(pid, segundos=10):
    fin = _time.time() + segundos
    while _time.time() < fin:
        if not produccion.cargar(pid)["trabajo"].get("ocupado"):
            return produccion.cargar(pid)
        _time.sleep(0.05)
    raise AssertionError("el trabajo no terminó")


def test_tu_guion_se_respeta_tal_cual_y_espera_aprobacion(aislado):
    texto = "El faro de Cabo Sur siguió encendido cuarenta años.   Nadie subía a cambiar la lámpara. Y aun así, cada noche, giraba."
    [pid] = produccion.crear("", [], "documental", "gemini", guion_propio=texto, formato_propio="horizontal")
    p = produccion.cargar(pid)
    assert p["guion"] == " ".join(texto.split()) and p["autor_guion"] == "Tú"
    assert p["estado"] == "guion_listo" and not p["guion_aprobado"] and p["formato"] == "horizontal"


def test_idea_investiga_una_vez_y_escribe_corto_y_largo(aislado, monkeypatch):
    llamadas = {"investigar": 0, "deepseek": 0}

    def investigar(idea, produccion=""):
        llamadas["investigar"] += 1
        return {"dossier": "HECHOS CLAVE: el faro se automatizó en 1981.", "fuentes": [{"titulo": "a", "url": "https://a"}]}

    def escribir_json(sistema, prompt, **_):
        llamadas["deepseek"] += 1
        assert "1981" in prompt and "\"corto\"" in prompt and "\"largo\"" in prompt   # escribe CON la investigación
        largo = " ".join(["El farero se fue en 1981 y la luz siguió encendida."] * 30)
        return {"titulo_provisional": "El faro solo",
                "corto": {"guion": "En 1981 el último farero cerró la puerta. La lámpara siguió girando sola. Cuarenta años.",
                          "ganchos": ["G1", "G2", "G3"]},
                "largo": {"guion": largo, "ganchos": ["L1"]}}
    monkeypatch.setattr(investigacion, "investigar", investigar)
    monkeypatch.setattr(deepseek, "disponible", lambda: True)
    monkeypatch.setattr(deepseek, "generar_json", escribir_json)
    monkeypatch.setattr(guion, "_ajustar_largo", lambda texto, objetivo, produccion: texto)  # se prueba aparte
    pids = produccion.crear("El faro sin farero", ["corto", "largo"], "documental", "gemini")
    corto, largo = (_esperar(pid) for pid in pids)
    assert llamadas == {"investigar": 1, "deepseek": 1}
    assert corto["familia"] == largo["familia"] and (corto["formato"], largo["formato"]) == ("vertical", "horizontal")
    assert corto["estado"] == "guion_listo" and corto["ganchos"] == ["G1", "G2", "G3"] and corto["autor_guion"] == "DeepSeek"
    assert len(largo["guion"].split()) > len(corto["guion"].split()) and corto["investigacion"]["fuentes"]


def test_aprobar_guion_crea_escenas_y_voz(aislado, monkeypatch):
    [pid] = produccion.crear("", [], "documental", "gemini", guion_propio="Una frase que se ve. Otra frase que también se ve en un plano.")
    monkeypatch.setattr(director, "planificar", lambda texto, estilo, formato, produccion="", titulos_existentes=None, referencias_visuales=None: {
        "titulo": "T", "descripcion": "D", "hashtags": ["#a"], "biblia": {}, "estilo_en": "x",
        "avisos": [{"frase": "Otra", "problema": "abstracta", "sugerencia": "muéstralo"}],
        "escenas": [{"orden": 1, "texto_voz": texto, "prompt_flow": "p", "texto_pantalla": ""}]})
    recibido = {}

    def locutar(seg, destino, prov, produccion="", direcciones=None, voz_nombre=None):
        recibido["direcciones"] = direcciones
        return {"proveedor": prov, "duracion": 3.0, "escenas": [{"ini": 0, "fin": 3.0}], "palabras": []}
    monkeypatch.setattr(voz, "locutar", locutar)
    produccion.aprobar_guion(pid, "Una frase que se ve. Otra frase que también se ve en un plano, editada.")
    p = _esperar(pid)
    assert p["guion_aprobado"] and p["estado"] == "rodando" and p["guion"].endswith("editada.")
    assert len(p["escenas"]) == 1 and p["voz"]["duracion"] == 3.0 and p["avisos"][0]["frase"] == "Otra"
    assert recibido["direcciones"] == [{"tono": "narrativo", "ritmo": "normal"}]   # la dirección viaja hasta la voz
    with pytest.raises(ValueError, match="aprobado"):
        produccion.guardar_guion(pid, "cambio " * 20)


def test_rehacer_escenas_con_clips_pide_confirmacion(aislado):
    _produccion("p8", guion="uno dos tres cuatro cinco seis siete ocho nueve diez once", guion_aprobado=True)
    produccion.modificar("p8", lambda p: p["escenas"][0]["tomas"].append({"archivo": "tomas/x.mp4", "tipo": "video"}))
    with pytest.raises(ValueError, match="clips"):
        produccion.aprobar_guion("p8")


def test_limpieza_y_frases_que_suenan_a_ia():
    assert guion._limpiar("**Hola** [música tensa] mundo (pausa dramática).") == "Hola mundo ."
    assert guion.frases_prohibidas("Imagina un faro. ¿Sabías que nadie lo apagó?") == ["Imagina", "¿Sabías que"]


def test_deepseek_lee_json_y_apunta_tokens(aislado, monkeypatch):
    class R:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '{"corto": {"guion": "x"}}'}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(deepseek.requests, "post", lambda *a, **k: R())
    assert deepseek.generar_json("s", "p", detalle="guion") == {"corto": {"guion": "x"}}
    assert registro.consumo_del_mes()["DeepSeek"]["total"] == 15


def test_peticion_de_guion_lleva_tono_publico_y_youtube():
    yt = {"competencia": [{"titulo": "Pulpos: 3 corazones", "canal": "Ciencia X", "vistas": 1200000}],
          "tu_canal": {"nombre": "Mi canal", "mas_vistos": [{"titulo": "El faro maldito", "vistas": 50000}]}}
    p = guion._peticion("pulpos", "dossier", {"corto": 50}, tono="con humor", publico="jóvenes", youtube=yt)
    for trozo in ("Tono: con humor", "Público: jóvenes", "Pulpos: 3 corazones", "1.200.000", "El faro maldito", "busca un ángulo"):
        assert trozo in p


def test_youtube_desconectado_no_bloquea_el_guion(aislado, monkeypatch):
    from studio4 import youtube
    assert youtube.disponible() is False and youtube.contexto_para_guion("pulpos") == {}


def test_guion_fuera_de_largo_se_ajusta_y_solo_si_mejora(monkeypatch):
    monkeypatch.setattr(deepseek, "disponible", lambda: True)
    corto = "palabra " * 50
    monkeypatch.setattr(deepseek, "generar_json", lambda *a, **k: {"guion": "palabra " * 98})
    assert len(guion._ajustar_largo(corto, 100, "").split()) == 98          # 50 → 98: se acerca, se acepta
    monkeypatch.setattr(deepseek, "generar_json", lambda *a, **k: {"guion": "palabra " * 20})
    assert len(guion._ajustar_largo(corto, 100, "").split()) == 50          # 50 → 20: empeora, se queda el original
    assert guion._ajustar_largo("palabra " * 95, 100, "") == "palabra " * 95  # dentro del 15 %: ni se toca


def test_texto_dirigido_solo_etiqueta_cuando_cambia_el_tono():
    t = voz._texto_dirigido(["Uno.", "Dos.", "Tres."], [{"tono": "tenso", "ritmo": "lento"},
                            {"tono": "tenso", "ritmo": "lento"}, {"tono": "emocionante", "ritmo": "rapido"}])
    assert t == "[tense, suspenseful, slowly] Uno. Dos. [excited, energetic, fast] Tres."
    assert voz._texto_dirigido(["Uno."], None) == "Uno."


def test_presupuesto_para_antes_de_pasarse_y_devuelve_lo_fallido():
    from studio4 import visuales_api as v
    p = v.Presupuesto(0.10)
    p.reservar(0.039, "imagen"); p.reservar(0.039, "imagen")
    with pytest.raises(v.PresupuestoAgotado):
        p.reservar(0.039, "imagen")          # 0,117 $ > 0,10 $: no se hace
    p.devolver(0.039)
    assert p.gastado == pytest.approx(0.039)
    assert v.estimar(23, 1) == pytest.approx(23 * 0.039 + 8 * 0.03)


def test_intercalar_gancho_en_video_y_nunca_tres_imagenes_seguidas():
    esc = [{"tipo_clip": t} for t in ("imagen", "imagen", "imagen", "imagen", "video", "imagen", "imagen", "imagen")]
    director._intercalar(esc)
    tipos = [e["tipo_clip"] for e in esc]
    assert tipos[0] == "video"
    assert "imagen,imagen,imagen" not in ",".join(tipos)
    p = director._prompt_flow({"tipo_clip": "imagen", "plano_en": "close-up", "camara_en": "slow dolly-in",
                               "accion_en": "a hanko stamp on paper"}, {}, "cinematic", "16:9")
    assert "Single still photograph" in p and "dolly" not in p


# --- Carpeta de la producción y entregas ---------------------------------------------------------------
from studio4 import carpetas, entregas  # noqa: E402


def _prod_con_clips(aislado, pid="p9", n=4, formato="horizontal"):
    """Producción sintética: n escenas de 2 s con clip, voz de 8 s y palabras (para render y recortes)."""
    p = _produccion(pid, escenas=n, formato=formato, guion_aprobado=True, titulo="Prueba: el faro")
    base = aislado / pid
    (base / "tomas").mkdir()
    medios.ffmpeg("-f", "lavfi", "-i", f"sine=f=300:d={2 * n}", "-ar", "24000", "-ac", "1", str(base / "voz.wav"))
    for e in p["escenas"]:
        clip = f"tomas/e{e['orden']}.mp4"
        medios.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=24:d=2", "-pix_fmt", "yuv420p", str(base / clip))
        e.update(tomas=[{"archivo": clip, "tipo": "video"}], elegida=0)
    p["voz"] = {"archivo": "voz.wav", "duracion": 2.0 * n,
                "escenas": [{"ini": 2.0 * i, "fin": 2.0 * (i + 1)} for i in range(n)],
                "palabras": [{"palabra": f"p{i}", "ini": 0.5 * i, "fin": 0.5 * i + 0.4} for i in range(4 * n)]}
    produccion.guardar(p)
    return p, base


@hay_ffmpeg
def test_clip_dejado_en_la_carpeta_entra_en_su_escena(aislado, monkeypatch):
    monkeypatch.setattr(carpetas, "RAIZ_USUARIO", aislado / "Videos")
    p, _ = _prod_con_clips(aislado, "p10")
    p["escenas"][2].update(tomas=[], elegida=None)
    produccion.guardar(p)
    base = produccion.preparar_carpeta("p10")
    p = produccion.cargar("p10")
    c = carpetas.corto(p)
    clips = base / carpetas.subcarpeta(p, carpetas.CLIPS)
    assert clips.name == f"1 Clips de Flow · {c}"                                    # el nombre del vídeo va en todo
    assert (clips / f"{c} - LEEME.txt").exists()
    assert (base / carpetas.subcarpeta(p, carpetas.GUION) / f"{c} - Escenas para Flow.txt").exists()
    medios.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=720x1280:r=24:d=1", "-pix_fmt", "yuv420p", str(clips / f"{c} - escena 03.mp4"))
    assert produccion.importar_carpeta("p10") == 1
    assert produccion.cargar("p10")["escenas"][2]["elegida"] == 0
    assert produccion.importar_carpeta("p10") == 0          # el mismo archivo no se importa dos veces


@hay_ffmpeg
def test_recorte_vertical_dura_lo_que_sus_escenas(aislado):
    p, base = _prod_con_clips(aislado, "p11")
    salida = render.recorte(p, base, 2, 3, base / "entregas" / "reels.mp4", 360, 640, gancho="EL FARO")
    inf = medios.info(salida)
    assert (inf["ancho"], inf["alto"]) == (360, 640) and inf["audio"]
    assert inf["duracion"] == pytest.approx(4.0 + 0.35, abs=0.25)


@hay_ffmpeg
def test_paquete_de_entregas_completo_reels_y_shorts(aislado, monkeypatch):
    monkeypatch.setattr(carpetas, "RAIZ_USUARIO", aislado / "Videos")
    p, base = _prod_con_clips(aislado, "p12")
    p["final"] = {"archivo": "final.mp4"}
    shutil.copy(base / "tomas" / "e1.mp4", base / "final.mp4")
    texto = {"titulo": "T", "descripcion": "D", "hashtags": ["#a"]}
    monkeypatch.setattr(entregas, "elegir", lambda p: {"youtube": texto,
        "reels": {**texto, "desde": 1, "hasta": 2, "gancho": "EL FARO", "duracion": 4.0},
        "shorts": [{**texto, "desde": 2, "hasta": 4, "gancho": "SIN FARERO", "duracion": 6.0}]})
    res = entregas.preparar(p, base)
    claves = [z["clave"] for z in res["piezas"]]
    assert claves == ["completo", "reels", "short_1"]
    for z in res["piezas"]:
        assert (base / z["video"]).exists() and (base / z["portada"]).exists()
    c = carpetas.corto(p)
    entregadas = sorted(f.name for f in pathlib.Path(res["carpeta"]).iterdir())
    assert f"{c} - Descripciones para publicar.txt" in entregadas
    assert all(nombre.startswith(f"{c} - ") for nombre in entregadas)                 # todo con el nombre del vídeo


def test_ajustar_momento_respeta_duraciones(aislado):
    p = {"escenas": [{}] * 10, "voz": {"escenas": [{"ini": 10.0 * i, "fin": 10.0 * (i + 1)} for i in range(10)]}}
    assert entregas._ajustar(p, {"desde": 1, "hasta": 9}, 15, 45)["hasta"] == 4      # 90 s → recorta a 40 s
    assert entregas._ajustar(p, {"desde": 5, "hasta": 5}, 20, 58)["hasta"] == 6      # 10 s → amplía a 20 s


def test_al_renderizar_se_preparan_solos_los_3_formatos(aislado, monkeypatch):
    _produccion("p13", guion_aprobado=True)
    llamadas = []
    monkeypatch.setattr(render, "renderizar", lambda p, base, avisar=None: base / "final.mp4")
    monkeypatch.setattr(entregas, "preparar", lambda p, base, avisar=None: llamadas.append(p["id"]) or
                        {"piezas": [{"clave": "completo"}, {"clave": "reels"}, {"clave": "short_1"}], "carpeta": "x"})
    produccion.renderizar("p13")
    p = _esperar("p13")
    assert p["final"]["archivo"] == "final.mp4" and llamadas == ["p13"]
    assert [z["clave"] for z in p["entregas"]["piezas"]] == ["completo", "reels", "short_1"]


def test_numero_de_escena_aunque_el_titulo_tenga_numeros():
    p = {"titulo": "Las 2 bombas de 1945"}
    assert carpetas.numero_de_escena(p, "Las 2 bombas de 1945 - escena 07.mp4") == 7
    assert carpetas.numero_de_escena(p, "Las 2 bombas de 1945 - 12.png") == 12
    assert carpetas.numero_de_escena(p, "Escena3.mp4") == 3


# --- Canales: cada uno con lo suyo ----------------------------------------------------------------
def test_canales_por_defecto_y_alta(aislado):
    from studio4 import canales
    assert [c["nombre"] for c in canales.listar()] == ["FourLevel", "ARIGAB"]
    assert canales.activo()["redes"]["youtube"] == "@Four4Level"
    c = canales.guardar({"nombre": "Mi Canal", "redes": {"tiktok": "https://www.tiktok.com/@mi.canal", "instagram": "mi_canal"}})
    assert c["id"] == "mi-canal" and c["redes"] == {"tiktok": "@mi.canal", "instagram": "@mi_canal"}
    assert canales.guardar({"nombre": "Mi Canal"})["id"] == "mi-canal-2"   # no pisa al que ya existe
    canales.guardar({**c, "redes": {**c["redes"], "facebook": "https://facebook.com/profile.php?id=1"}})
    assert canales.obtener("mi-canal")["redes"]["facebook"] == "https://facebook.com/profile.php?id=1"
    with pytest.raises(ValueError):
        canales.guardar({"nombre": " "})


def test_producciones_separadas_por_canal(aislado):
    from studio4 import canales
    _produccion("20261012-100000-viejo")                        # de antes de los canales → del primero
    canales.activar("arigab")
    assert produccion.activa() is None                          # ARIGAB no ve la de FourLevel
    _produccion("20261012-110000-ari", canal="arigab")
    assert [x["id"] for x in produccion.listar("arigab")] == ["20261012-110000-ari"]
    assert [x["id"] for x in produccion.listar("fourlevel")] == ["20261012-100000-viejo"]
    canales.activar("fourlevel")
    assert produccion.activa() == "20261012-100000-viejo"      # al volver, se abre la última de ese canal
    assert produccion._nueva("20261012-120000-nueva")["canal"] == "fourlevel"


def test_carpeta_va_dentro_de_su_canal_y_se_mueve_la_vieja(aislado):
    from studio4 import carpetas
    vieja = carpetas.RAIZ_USUARIO / "2026-10-12 · Faro"
    (vieja / "1 Clips de Flow · Faro").mkdir(parents=True)
    (vieja / "1 Clips de Flow · Faro" / "Faro - escena 01.mp4").write_bytes(b"x")
    p = _produccion("20261012-100000-faro", titulo="Faro", carpeta=str(vieja), canal="arigab")
    base = carpetas.preparar(p)
    assert base == carpetas.RAIZ_USUARIO / "ARIGAB" / "2026-10-12 · Faro"
    assert (base / "1 Clips de Flow · Faro" / "Faro - escena 01.mp4").exists() and not vieja.exists()


# --- Tendencias -----------------------------------------------------------------------------------
def test_tendencias_cifras_y_pautas_para_el_guion(aislado):
    from studio4 import guion, tendencias
    assert tendencias._segundos("PT1H2M3S") == 3723 and tendencias._segundos("PT45S") == 45 and tendencias._segundos("P1D") == 86400
    videos = [{"id": str(i), "titulo": t, "canal": "c", "categoria": "27", "etiquetas": ["Historia", "misterio"],
               "segundos": s, "hd": hd, "vistas": 1000, "vistas_hora": vh, "horas": 10, "origen": "x", "url": ""}
              for i, (t, s, hd, vh) in enumerate([("¿Por qué 3 corazones?", 40, True, 900), ("El faro", 50, True, 800),
                                                   ("DOCUMENTAL ENTERO", 3000, False, 10), ("Un mapa", 300, True, 50)])]
    m = tendencias.metricas(videos)
    assert m["total"] == 4 and m["hd"] == 75 and m["duraciones"]["Hasta 1 min"] == 50 and m["duraciones"]["Más de 20 min"] == 25
    assert m["titulos"]["con_pregunta"] == 25 and m["etiquetas"][0] in ("historia", "misterio")
    assert tendencias.metricas([]) == {"total": 0}
    assert tendencias.para_guion("fourlevel") == {}          # sin informe guardado no consulta nada
    informe = {"resumen": "r", "nichos": [], "ideas": [], "duracion_corto": "30 a 45 s", "duracion_largo": "8 a 12 min",
               "calidad": "1080p", "titulos": "con números", "consejos": ["gancho en 2 s"], "evitar": ["saludos largos"]}
    archivo = tendencias._archivo("fourlevel")
    archivo.parent.mkdir(parents=True)
    archivo.write_text(json.dumps({"fecha": "2026-10-01 10:00:00", "informe": informe, "metricas": m, "rapidos": []}), encoding="utf-8")
    t = tendencias.para_guion("fourlevel")
    texto = guion._peticion("faros", "dossier", {"corto": 40}, youtube={"tendencias": t})
    assert "2026-10-01" in texto and "30 a 45 s" in texto and "gancho en 2 s" in texto and "Evita: saludos largos" in texto
    assert tendencias.estado("fourlevel")["caducado"] is True


def test_resumen_del_canal_para_el_panel(aislado):
    from studio4 import canales
    datos = {"nombre": "FourLevel", "suscriptores": 10, "vistas": 99, "videos": 2, "mas_vistos": []}
    r = canales.resumen("fourlevel", lambda u: {**datos, "pedido": u},
                        [{"estado": "terminado"}, {"estado": "rodando"}, {"estado": "guion_listo"}])
    assert r["youtube"]["pedido"] == "@Four4Level" and r["error"] == ""
    assert r["producciones"] == {"total": 3, "terminadas": 1, "en_flow": 1}

    def falla(_u):
        raise RuntimeError("cuota agotada")
    assert canales.resumen("arigab", falla, [])["error"] == "cuota agotada"   # un canal sin datos no tumba el panel


# --- Referencias del autor ------------------------------------------------------------------------
def test_referencias_suben_se_copian_y_llegan_al_guion(aislado, tmp_path):
    from studio4 import guion, referencias
    foto = tmp_path / "subida.bin"
    foto.write_bytes(bytes([0xFF, 0xD8]) + b" foto falsa")
    r = referencias.subir(foto, "Abuelo 1945.jpg", "image/jpeg")
    assert r["tipo"] == "foto" and r["nombre"] == "Abuelo 1945.jpg"
    with pytest.raises(ValueError):
        referencias.subir(foto, "virus.exe", "application/x-msdownload")
    refs = referencias.preparar({"enlaces": ["https://es.wikipedia.org/wiki/Faro", "no-es-enlace"], "datos": " Nació en 1916 "}, [r])
    assert refs["enlaces"] == ["https://es.wikipedia.org/wiki/Faro"] and refs["datos"] == "Nació en 1916"
    with pytest.raises(ValueError):
        referencias.preparar({}, [{"id": "0" * 16, "tipo": "foto", "nombre": "x"}])   # subida que ya no existe

    pids = produccion.crear("", [], "documental", "gemini", guion_propio="Un guion propio con más de diez palabras para probar las referencias.",
                            refs=refs)
    p = produccion.cargar(pids[0])
    assert p["referencias"]["items"][0]["archivo"].startswith("referencias/")
    assert (produccion.carpeta(pids[0]) / p["referencias"]["items"][0]["archivo"]).exists()
    assert not list((config.PRODUCCIONES / "_referencias").glob(f"{r['id']}.*"))   # la espera queda limpia

    p["referencias"]["material"] = [{"tipo": "foto", "nombre": "Abuelo", "resumen": "Hombre de 30 años con gafas redondas."},
                                    {"tipo": "lugar", "nombre": "Bar Pepe", "resumen": "Lugar o negocio del vídeo: Bar Pepe."}]
    bloque = referencias.para_guion(p["referencias"])
    assert "DATOS QUE NO PUEDEN FALTAR" in bloque and "Bar Pepe" in bloque
    assert referencias.visuales(p["referencias"]) == ["Hombre de 30 años con gafas redondas."]
    assert "MATERIAL QUE APORTA EL AUTOR" in guion._peticion("faros", "", {"corto": 40}, referencias=bloque)


def test_enlace_de_google_maps_da_nombre_y_ubicacion():
    from studio4 import referencias
    assert referencias.es_maps("https://maps.app.goo.gl/AbC123") and not referencias.es_maps("https://es.wikipedia.org/wiki/Mapa")
    sitio = referencias.lugar_de_maps("https://www.google.com/maps/place/Moviraider+Sevilla/@37.3891,-5.9845,17z/data=!3m1")
    assert sitio["nombre"] == "Moviraider Sevilla" and (sitio["lat"], sitio["lng"]) == (37.3891, -5.9845)


# --- Errores claros y reintentar --------------------------------------------------------------------
def test_error_legible_y_reintentar(aislado, monkeypatch):
    assert produccion._error_legible("Investigación y guion", RuntimeError("DeepSeek no respondió: Expecting value: line 1 column 1")) == (
        "No se pudo escribir el guion: el servicio está saturado o sin conexión; suele bastar con esperar un minuto. Pulsa «Reintentar».")
    assert "Expecting" not in produccion._error_legible("Render", ValueError("Expecting value"))
    assert produccion._error_legible("Render", ValueError("Primero renderiza el vídeo completo.")) == "Primero renderiza el vídeo completo."
    p = _produccion("20261013-100000-corto-faro", version="corto", familia="20261013-100000", guion="", investigacion={"dossier": "d"},
                    trabajo={"ocupado": False, "nombre": "Investigación y guion", "error": "x", "reintentable": True})
    llamadas = []
    monkeypatch.setattr(produccion, "_investigar_y_escribir", lambda pids, idea, seg, dossier=None: llamadas.append((pids, seg, dossier)))
    produccion.reintentar(p["id"])
    for _ in range(50):
        if llamadas and not produccion.cargar(p["id"])["trabajo"]["ocupado"]:
            break
        import time; time.sleep(.05)
    assert llamadas == [(["20261013-100000-corto-faro"], {"corto": 20}, {"dossier": "d"})]   # aprovecha la investigación
    with pytest.raises(ValueError):
        produccion.reintentar(p["id"])   # ya salió bien: no hay nada que reintentar


def test_deepseek_sin_espacio_reintenta_una_vez_con_mas_margen(aislado, monkeypatch):
    from studio4 import deepseek
    monkeypatch.setattr(deepseek.config, "DEEPSEEK_API_KEY", "x")
    monkeypatch.setattr(deepseek.time, "sleep", lambda _s: None)
    pedidos = []

    class R:
        status_code = 200
        def __init__(self, cuerpo): self.cuerpo = cuerpo
        def json(self): return self.cuerpo

    def post(url, json, timeout, headers):
        pedidos.append(json["max_tokens"])
        return R({"choices": [{"message": {"content": ""}, "finish_reason": "length"}], "usage": {"completion_tokens": json["max_tokens"]}})
    monkeypatch.setattr(deepseek.requests, "post", post)
    with pytest.raises(RuntimeError):
        deepseek.generar_json("s", "p")
    assert pedidos == [16000, 32000]   # no repite igual: un reintento con el doble y se rinde


# --- Subtítulos de cine y de sonidos ----------------------------------------------------------------
def test_subtitulos_de_cine_con_sonidos(tmp_path):
    texto = ("A las ocho y cuarto de la mañana, Yamaguchi vio un destello enorme sobre el cielo de Hiroshima. "
             "Después, silencio.").split()
    pal = [{"palabra": w, "ini": i * 0.4, "fin": i * 0.4 + 0.35} for i, w in enumerate(texto)]
    ass = subtitulos.construir(pal, tmp_path / "c.ass", 1920, 1080, {"estilo": "cine"},
                               sonidos=[{"ini": 2.0, "fin": 4.0, "texto": "Explosión lejana"}]).read_text(encoding="utf-8")
    dialogos = [l.split(",0,0,0,,", 1)[1] for l in ass.splitlines() if l.startswith("Dialogue: 0")]
    assert dialogos[0].endswith("Hiroshima.") and r"\N" in dialogos[0]      # frase entera en dos líneas, sin palabra suelta
    assert dialogos[1] == "Después, silencio." and r"\c" not in ass           # sin resaltes de color en cine
    assert "Sonido,,0,0,0,,[Explosión lejana]" in ass and ",-1,0,0,100" in ass.split("Style: Sonido")[1][:80]
    sin = subtitulos.construir(pal, tmp_path / "s.ass", 1920, 1080, {"estilo": "cine", "sonidos": False},
                               sonidos=[{"ini": 2.0, "fin": 4.0, "texto": "Explosión"}]).read_text(encoding="utf-8")
    assert "[Explosión]" not in sin


def test_sonidos_se_colocan_en_su_arranque_real_y_no_se_pisan():
    from studio4 import sonidos
    tramos = sonidos._tramos_con_sonido([(0.0, 3.01), (4.21, 7.01)], 12.0)
    assert tramos == [(3.01, 4.21), (7.01, 12.0)]
    ajustados = sonidos.ajustar([{"ini": 0.0, "fin": 3.0, "texto": "Viento"}, {"ini": 9.5, "fin": 10, "texto": "Pitido"}], tramos)
    assert [s["ini"] for s in ajustados] == [3.01, 7.01]
    limpios = sonidos.limpiar([{"ini": 5, "fin": 5.1, "texto": "golpe."}, {"ini": 5.5, "fin": 9, "texto": "Eco"},
                               {"ini": 7, "fin": 20, "texto": "[Música]"}, {"ini": 11.9, "fin": 13, "texto": "Tarde"}], 12.0)
    assert limpios == [{"ini": 5.0, "fin": 6.2, "texto": "Golpe"}, {"ini": 7.0, "fin": 11.0, "texto": "Música"}]


# --- Duración de cada escena en Flow ---------------------------------------------------------------
def test_duracion_de_cada_escena_en_el_prompt():
    assert [director.duracion_clip(s) for s in (2.0, 5.4, 7.9, 11.7)] == [4, 6, 8, 8]
    biblia = {"personajes": [], "escenario_en": "Hiroshima, 1945", "luz_en": "dawn", "paleta_en": "amber"}
    escenas = [{"orden": 1, "tipo_clip": "video", "plano_en": "wide shot", "camara_en": "slow push-in", "accion_en": "a flash"},
               {"orden": 2, "tipo_clip": "imagen", "plano_en": "portrait", "camara_en": "", "accion_en": "a man"},
               {"orden": 3, "tipo_clip": "video", "plano_en": "close-up", "camara_en": "static", "accion_en": "hands",
                "prompt_flow": "mi prompt", "prompt_editado": True}]
    director.poner_duraciones(escenas, [{"ini": 0, "fin": 5.4}, {"ini": 5.4, "fin": 11.3}, {"ini": 11.3, "fin": 15}], biblia, "cine", "16:9")
    assert [e["segundos"] for e in escenas] == [5.4, 5.9, 3.7]
    assert "continuous 6-second shot" in escenas[0]["prompt_flow"]
    assert "second" not in escenas[1]["prompt_flow"] and "Single still photograph" in escenas[1]["prompt_flow"]
    assert escenas[2]["prompt_flow"] == "mi prompt"        # el que editaste a mano no se toca
