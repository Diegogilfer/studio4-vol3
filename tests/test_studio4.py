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
    monkeypatch.setattr(config, "FAL_KEY", "")   # nunca se gasta saldo de fal en una prueba
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    monkeypatch.setattr(config, "XIAOMIMIMO_API_KEY", "")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    from studio4 import secretos   # las pruebas nunca leen tus secretos reales del almacén de Windows
    monkeypatch.setattr(secretos, "_almacen", lambda: None)
    from studio4 import tarjetas   # las pruebas no abren el navegador: el render sale sin carátula

    def sin_navegador(*_a, **_k):
        raise RuntimeError("sin navegador en las pruebas")
    monkeypatch.setattr(tarjetas, "dibujar_caratula", sin_navegador)
    monkeypatch.setattr(youtube, "TOKEN", tmp_path / "youtube_token.json")
    # Las pruebas nunca salen a internet: lo que necesite Gemini o la investigación lo simula cada prueba.
    from studio4 import gemini, investigacion, sonidos

    def sin_red(*_a, **_k):
        raise RuntimeError("sin red en las pruebas")
    monkeypatch.setattr(gemini, "generar", sin_red)
    monkeypatch.setattr(gemini, "cliente", sin_red)
    monkeypatch.setattr(investigacion, "investigar", sin_red)
    monkeypatch.setattr(sonidos, "detectar", lambda *_a, **_k: [])
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


def test_la_voz_nunca_cambia_sola_de_proveedor(monkeypatch):
    """Con cualquier clave puesta, si la voz elegida falla no se sustituye por otra (el autor elige)."""
    for k in ("ELEVENLABS_API_KEY", "XIAOMIMIMO_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(config, k, "k")
    assert all(voz.reserva(p) is None for p in voz.PROVEEDORES)


def test_sin_servicios_de_voz_no_oficiales():
    """Ni la voz de TikTok por un servidor ajeno ni el TTS escondido del Traductor de Google."""
    codigo = (pathlib.Path(voz.__file__)).read_text(encoding="utf-8")
    assert "weilnet" not in codigo and "translate_tts" not in codigo and "es_mx_002" not in codigo


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
    _produccion("p2", trabajo={"ocupado": True, "nombre": "Render", "fase": "Render"}, estado="renderizando")
    _produccion("p2b", trabajo={"ocupado": True, "nombre": "Desde URL", "fase": "Transcribiendo"}, desde_url=True)
    assert produccion.recuperar_trabajos_colgados() == ["p2b"]   # solo lo importado se retoma solo
    p = produccion.cargar("p2")
    assert not p["trabajo"]["ocupado"] and p["estado"] == "rodando" and "Render" in p["trabajo"]["error"]
    assert p["trabajo"]["reintentable"]


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
    assert pedir("POST", "/api/producciones", {"Origin": "null"}, b"{}")[0] == 403
    assert pedir("POST", "/api/producciones", {"Sec-Fetch-Site": "cross-site"}, b"{}")[0] == 403
    assert pedir("POST", "/api/producciones", {"Referer": "https://evil.com/ataque"}, b"{}")[0] == 403
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
    [pid] = produccion.crear("", [], "documental", "gemini", segundos={"largo": 8}, guion_propio=texto, formato_propio="horizontal")
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
    monkeypatch.setattr(produccion, "completar_guion", lambda *_a, **_k: None)   # aquí se aprueba tal cual, sin completar
    [pid] = produccion.crear("", [], "documental", "gemini", guion_propio="Una frase que se ve. Otra frase que también se ve en un plano.")
    monkeypatch.setattr(director, "planificar", lambda texto, estilo, formato, produccion="", titulos_existentes=None, referencias_visuales=None, reparto=None, bloques=None, publico="": {
        "titulo": "T", "descripcion": "D", "hashtags": ["#a"], "biblia": {}, "estilo_en": "x",
        "avisos": [{"frase": "Otra", "problema": "abstracta", "sugerencia": "muéstralo"}],
        "escenas": [{"orden": 1, "texto_voz": texto, "prompt_flow": "p", "texto_pantalla": ""}]})
    recibido = {}

    def locutar(seg, destino, prov, produccion="", direcciones=None, voz_nombre=None, estilo_voz="", velocidad=1.0):
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
    class R:   # streaming: el JSON llega en dos trozos y el uso al final
        status_code = 200
        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": "{\\"corto\\": "}}]}'
            yield ""
            yield 'data: {"choices": [{"delta": {"content": "{\\"guion\\": \\"x\\"}}"}, "finish_reason": "stop"}]}'
            yield 'data: {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}'
            yield "data: [DONE]"
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


def test_presupuesto_para_antes_de_pasarse_y_devuelve_lo_fallido(aislado):
    from studio4 import visuales_api as v
    p = v.Presupuesto(0.10)
    p.reservar(0.039, "imagen"); p.reservar(0.039, "imagen")
    with pytest.raises(v.PresupuestoAgotado):
        p.reservar(0.039, "imagen")          # 0,117 $ > 0,10 $: no se hace
    p.devolver(0.039)
    assert p.gastado == pytest.approx(0.039)
    escenas = [{"elegida": None, "tipo_clip": "video", "segundos": 5.4}, {"elegida": None, "tipo_clip": "imagen", "segundos": 6},
               {"elegida": 0, "tipo_clip": "video", "segundos": 8}]                     # la que ya tiene clip no cuenta
    e = v.estimar(escenas, personajes=2)
    assert (e["escenas"], e["videos"], e["segundos_video"]) == (2, 1, 6)                 # 5,4 s de voz → clip de 6 s
    assert e["coste_imagenes"] == pytest.approx(4 * v.PRECIO_IMAGEN)
    assert e["coste_todo"] == pytest.approx(4 * v.PRECIO_IMAGEN + 6 * v.PRECIO_VIDEO_SEGUNDO)
    assert [v.segundos_clip(s) for s in (3.0, 4.1, 5.9, 7.9, 12)] == [4, 4, 6, 8, 8]   # 0,25 s de margen: cámara lenta imperceptible


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

    pids = produccion.crear("", [], "documental", "gemini", segundos={"corto": 4},
                            guion_propio="Un guion propio con más de diez palabras para probar las referencias.",
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
    hechos = []
    monkeypatch.setattr(produccion, "rellenar_tarjetas", lambda pid: hechos.append(("tarjetas", pid)))
    monkeypatch.setattr(produccion, "afinar_personajes", lambda pid: hechos.append(("personajes", pid)))
    monkeypatch.setattr(produccion, "completar_guion", lambda pid, seg: hechos.append(("completar", pid, seg)))
    for paso in ("Tarjetas", "Personajes"):
        produccion.modificar(p["id"], lambda q, s=paso: q["trabajo"].update(ocupado=False, nombre=s, error="x", reintentable=True))
        produccion.reintentar(p["id"])
    produccion.modificar(p["id"], lambda q: q.update(version="propio", trabajo={"ocupado": False, "nombre": "Guion", "error": "x"}))
    produccion.reintentar(p["id"])
    assert hechos == [("tarjetas", p["id"]), ("personajes", p["id"]), ("completar", p["id"], 20)]


def test_deepseek_sin_espacio_reintenta_una_vez_con_mas_margen(aislado, monkeypatch):
    from studio4 import deepseek
    monkeypatch.setattr(deepseek.config, "DEEPSEEK_API_KEY", "x")
    monkeypatch.setattr(deepseek.time, "sleep", lambda _s: None)
    pedidos = []

    class R:   # respuesta en streaming: un trozo vacío que acaba por falta de espacio
        status_code = 200
        def __init__(self, n): self.n = n
        def iter_lines(self, decode_unicode=True):
            yield 'data: {"choices": [{"delta": {"content": ""}, "finish_reason": "length"}]}'
            yield 'data: {"choices": [], "usage": {"completion_tokens": %d}}' % self.n
            yield "data: [DONE]"

    def post(url, json, timeout, headers, stream):
        assert stream and json["stream"]
        pedidos.append(json["max_tokens"])
        return R(json["max_tokens"])
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


# --- Personajes coherentes ------------------------------------------------------------------------------
def test_personaje_siempre_en_su_prompt_y_ficha_sin_nombre_repetido():
    biblia = {"personajes": [{"nombre": "GUY", "aspecto_en": "GUY: A man in his 30s, short brown hair, light blue shirt."}],
              "escenario_en": "Free City", "luz_en": "sunny", "paleta_en": "blue"}
    olvidado = {"tipo_clip": "video", "plano_en": "wide shot", "camara_en": "tracking", "accion_en": "He walks past a burning car",
                "personajes": []}
    prompt = director._prompt_flow(olvidado, biblia, "cine", "16:9")
    assert "keep exactly the same face" in prompt and "GUY is A man in his 30s" in prompt and "GUY: A man" not in prompt
    sin_gente = {**olvidado, "accion_en": "A burning car on an empty street"}
    assert "Characters" not in director._prompt_flow(sin_gente, biblia, "cine", "16:9")
    f = director.fichas(biblia, "cine")
    assert f[0]["nombre"] == "GUY" and f[0]["prompt"].startswith("Character reference portrait of GUY: A man in his 30s")


def test_imagen_inicial_solo_si_la_escena_continua(aislado, monkeypatch):
    from studio4 import flow
    p = _produccion("20261014-100000-npc", escenas=3)
    monkeypatch.setattr(flow, "_referencia", lambda pid, esc: "/media/x/fin.jpg")
    produccion.modificar(p["id"], lambda q: q.update(escena_activa=2))
    assert flow.sesion_para_extension()["siguiente"]["referencia"] is None          # escena nueva: plano libre
    produccion.modificar(p["id"], lambda q: q["escenas"][1].update(continua=True))
    assert flow.sesion_para_extension()["siguiente"]["referencia"] == "/media/x/fin.jpg"   # sigue sin corte


# --- Importar un vídeo ya hecho -----------------------------------------------------------------------
def test_importar_corta_escenas_en_frases_y_corrige_texto(aislado):
    from studio4 import importar
    texto = "Hola a todos. Hoy vamos a ver cómo se hace un faro, paso a paso, desde los cimientos hasta la luz. Empezamos ya."
    palabras = [{"palabra": w, "ini": i * 0.5, "fin": i * 0.5 + 0.4} for i, w in enumerate(texto.split())]
    tramos = importar.escenas(palabras, cortes=[], total=12.0)
    assert tramos[0]["ini"] == 0.0 and tramos[-1]["fin"] == 12.0
    assert all(a["fin"] == b["ini"] for a, b in zip(tramos, tramos[1:]))            # sin huecos entre escenas
    assert all(t["palabras"][-1]["palabra"].endswith((".", ",")) for t in tramos[:-1])  # cortan en frase o coma
    assert sum(len(t["palabras"]) for t in tramos) == len(palabras)
    nuevas = importar.retemporizar(palabras, tramos[0]["ini"], tramos[0]["fin"], "Hola a todas.")
    assert [w["palabra"] for w in nuevas[:3]] == ["Hola", "a", "todas."] and nuevas[3] == tramos[1]["palabras"][0]   # el resto, intacto

    p = _produccion("20261014-100000-importado-faro", escenas=2, version="importado",
                    voz={"archivo": "voz.wav", "duracion": 3.0, "escenas": [{"ini": 0, "fin": 1.5}, {"ini": 1.5, "fin": 3.0}],
                         "palabras": [{"palabra": "frase", "ini": 0.1, "fin": 0.5}, {"palabra": "dos", "ini": 1.6, "fin": 2.0}]})
    produccion.editar_escena(p["id"], 1, {"texto_voz": "frase corregida"})
    q = produccion.cargar(p["id"])
    assert q["voz"] is not None and [w["palabra"] for w in q["voz"]["palabras"]] == ["frase", "corregida", "dos"]


# --- Eliminar una producción: queda desvinculada de todo ---------------------------------------------------
def test_eliminar_produccion_la_desvincula(aislado):
    vieja = _produccion("20261014-080000-vieja", escenas=2)
    nueva = _produccion("20261014-090000-nueva", escenas=2)
    produccion.activar(vieja["id"])
    produccion.eliminar(vieja["id"])
    assert [x["id"] for x in produccion.listar()] == ["20261014-090000-nueva"]     # ya no se ve
    assert produccion.activa() == "20261014-090000-nueva"                          # ni queda abierta
    assert (config.PRODUCCIONES / "_papelera" / vieja["id"] / "proyecto.json").exists()   # recuperable a mano
    produccion.modificar(nueva["id"], lambda q: q["trabajo"].update(ocupado=True))
    with pytest.raises(ValueError):
        produccion.eliminar(nueva["id"])   # trabajando: no se elimina


def test_crear_rapido_usa_lo_de_siempre_del_canal(aislado, monkeypatch):
    from studio4 import canales
    canales.guardar({**canales.obtener("fourlevel"), "tono": "intrigante", "voz_nombre": "Puck"})
    llamadas = []
    monkeypatch.setattr(produccion, "crear", lambda idea, versiones, estilo, voz, **k: llamadas.append((idea, versiones, estilo, k)) or ["x"])
    assert produccion.crear_rapido("  El faro de Alejandría ", "largo") == ["x"]
    idea, versiones, estilo, k = llamadas[0]
    assert (idea, versiones, estilo, k["tono"], k["voz_nombre"]) == ("El faro de Alejandría", ["largo"], "cinematografico", "intrigante", "Puck")
    with pytest.raises(ValueError):
        produccion.crear_rapido("x")


# --- Fuentes de confianza del canal ------------------------------------------------------------------
def test_fuentes_elige_paginas_del_tema_y_se_guardan_en_el_canal(aislado):
    from studio4 import canales, fuentes
    urls = ["https://www.gtabase.com/gta-6/characters/lucia", "https://www.gtabase.com/gta-6/characters/jason",
            "https://www.gtabase.com/gta-6/vehicles/dinka-jester", "https://www.gtabase.com/gta-6/map"]
    assert fuentes.elegir(urls, ["lucia", "jason", "gta 6"]) == urls[:2]
    assert fuentes.elegir(urls, ["helicopter"]) == []
    c = canales.guardar({**canales.obtener("fourlevel"), "fuentes": ["https://www.gtabase.com/gta-6/", "no es web"]})
    assert c["fuentes"] == ["https://www.gtabase.com/gta-6/"]


def test_referentes_del_canal_y_su_formula_en_el_informe(aislado):
    from studio4 import canales, tendencias
    c = canales.guardar({**canales.obtener("fourlevel"), "referentes": ["https://www.youtube.com/@leyendasyvideojuegos", "@leyendasyvideojuegos", "otro"]})
    assert c["referentes"] == ["@leyendasyvideojuegos", "@otro"]
    m = tendencias.metricas([{"id": "1", "titulo": "t", "canal": "c", "categoria": "", "etiquetas": [], "segundos": 40, "hd": True,
                              "vistas": 10, "vistas_hora": 5, "horas": 2, "origen": "España · General", "url": ""}])
    ref = [{"canal": "Leyendas & Videojuegos", "suscriptores": 759000,
            "videos": [{"titulo": "La leyenda de Herobrine", "vistas_hora": 900, "segundos": 610}]}]
    texto = tendencias._texto_para_gemini({**c, "id": "fourlevel"}, m, [], ref)
    assert "CANAL DE REFERENCIA «Leyendas & Videojuegos»" in texto and "La leyenda de Herobrine" in texto
    assert "nunca el contenido" in texto


def test_archivo_compone_sin_recortar():
    """La foto de archivo entra entera en el formato vertical y deja margen para el acercamiento del montaje."""
    from PIL import Image
    from studio4 import archivo
    foto = Image.new("RGB", (1600, 900), (200, 30, 30))
    c = archivo.componer(foto, 1080, 1920)
    assert c.size == (1080, 1920)
    assert c.getpixel((540, 960))[0] > 150            # el centro es la foto
    assert c.getpixel((30, 960))[0] < 120              # el borde es el fondo oscurecido, no la foto


def test_flow_anima_la_imagen_de_api():
    """Escena de vídeo con imagen de API y sin vídeo: Flow recibe esa imagen como inicial y un prompt de movimiento."""
    from studio4 import flow
    esc = {"orden": 3, "tipo_clip": "video", "segundos": 5.2, "prompt_flow": "LUCIA walks through prison gates.",
           "tomas": [{"archivo": "tomas/a.png", "tipo": "imagen", "origen": "api"}], "elegida": 0}
    assert flow.por_animar(esc)
    assert "Bring this exact image to life as a 5-second shot. LUCIA walks" in flow.prompt_animar(esc)
    assert not flow.por_animar({**esc, "tipo_clip": "imagen"})
    assert not flow.por_animar({**esc, "tomas": esc["tomas"] + [{"tipo": "video", "origen": "flow"}]})
    assert not flow.por_animar({**esc, "tomas": [{"archivo": "tomas/t.png", "tipo": "imagen", "origen": "tarjeta"}]})


def test_escena_rechazada_por_el_filtro_se_suaviza_y_no_tumba_el_lote(aislado, monkeypatch, tmp_path):
    """El filtro rechaza el plano de la pistola: se pide sin lo explícito; si una escena falla igual, las demás siguen."""
    from studio4 import visuales_api as v
    pedidos = []

    def imagen(prompt, aspecto, destino, presupuesto, **_):
        pedidos.append(prompt)
        if "pistol" in prompt and v.SUAVIZAR not in prompt or "door" in prompt:
            raise v.Moderada("filtro")
        destino.write_bytes(b"png")
        return destino
    monkeypatch.setattr(v, "imagen", imagen)
    monkeypatch.setattr(v, "revisar", lambda *a, **k: {"ok": True})
    recibidas = []
    escenas = [{"orden": 1, "elegida": None, "prompt_flow": "LUCIA aims a pistol."},
               {"orden": 2, "elegida": None, "prompt_flow": "LUCIA kicks a door."},
               {"orden": 3, "elegida": None, "prompt_flow": "A motel at night."}]
    res = v.generar_escenas(escenas, "9:16", v.Presupuesto(1), recibir=lambda a, m, n: recibidas.append(n))
    assert recibidas == [1, 3]
    assert [f["orden"] for f in res["fallidas"]] == [2]
    assert pedidos[1].endswith(v.SUAVIZAR)


def test_quita_franjas_negras(tmp_path):
    from PIL import Image
    from studio4 import visuales_api as v
    im = Image.new("RGB", (100, 200), (0, 0, 0))
    im.paste((180, 90, 40), (0, 30, 100, 170))
    ruta = tmp_path / "a.png"
    im.save(ruta)
    assert v.quitar_franjas(ruta)
    assert Image.open(ruta).size == (100, 140)
    assert not v.quitar_franjas(ruta)


def test_caratula_lleva_titulo_marca_y_las_dos_imagenes(tmp_path):
    from studio4 import tarjetas
    h = tarjetas.html_caratula("Bonnie nunca disparó", "Lo que GTA 6 le debe", "FourLevel", tmp_path / "a.jpg", tmp_path / "b.png", 1080, 1920)
    assert "Bonnie nunca <em>disparó</em>" in h and "FOURLEVEL" in h and "GTA 6" in h
    assert (tmp_path / "a.jpg").as_uri() in h and (tmp_path / "b.png").as_uri() in h
    ht = tarjetas.html_tarjeta({"titular": "El caso FOURLEVEL"}, 1, 1080, 1920, marca="Arigab")
    assert "El caso FOURLEVEL" in ht and '<div class="marca">ARIGAB</div>' in ht


def test_anadir_y_quitar_escena_a_mano(aislado):
    """Escena tuya en medio: se renumera todo, el guion la incluye, la voz se rehace y lleva la ficha del personaje."""
    pid = produccion.crear("Idea", [], "cinematografico", "gemini", guion_propio=" ".join(["palabra"] * 200))[0]

    def preparar(p):
        p["biblia"] = {"escenario_en": "Florida", "luz_en": "neon", "paleta_en": "pink",
                       "personajes": [{"nombre": "Lucia", "aspecto_en": "long wavy hair", "edad": "29"}]}
        p["escenas"] = [{"orden": i, "texto_voz": f"Frase {i}.", "plano_en": "wide", "camara_en": "static", "accion_en": "a street",
                         "tomas": [], "elegida": None, "segundos": 3} for i in (1, 2)]
        p["voz"], p["escena_activa"] = {"duracion": 6}, 2
    produccion.modificar(pid, preparar)
    produccion.anadir_escena(pid, 1, "Lucía sale de la cárcel.", "Lucia walks out of a prison gate", "imagen")
    p = produccion.cargar(pid)
    assert [e["orden"] for e in p["escenas"]] == [1, 2, 3]
    assert p["escenas"][1]["texto_voz"] == "Lucía sale de la cárcel." and p["escena_activa"] == 3
    assert p["guion"] == "Frase 1. Lucía sale de la cárcel. Frase 2." and p["voz"] is None
    assert "LUCIA is" in p["escenas"][1]["prompt_flow"] and "Florida" in p["escenas"][1]["prompt_flow"]
    produccion.quitar_escena(pid, 1)
    p = produccion.cargar(pid)
    assert [e["texto_voz"] for e in p["escenas"]] == ["Lucía sale de la cárcel.", "Frase 2."]


def test_guion_pegado_corto_se_completa_con_investigacion(aislado, monkeypatch):
    from studio4 import guion
    assert guion.corto_de_mas("Bonnie nunca disparó. Lucía sí.", 50)
    assert not guion.corto_de_mas(" ".join(["x"] * 110), 50)
    llamadas = []
    monkeypatch.setattr(produccion, "completar_guion", lambda pid, seg: llamadas.append((pid, seg)))
    pid = produccion.crear("Bonnie y Lucía", [], "cinematografico", "gemini", guion_propio="Bonnie nunca disparó. Lucía sí.")[0]
    assert llamadas == [(pid, 48)]   # el corto por defecto: 6 clips de 8 s


def test_modo_sin_pago_y_ssrf_enlaces(monkeypatch, tmp_path):
    from studio4 import referencias, visuales_api as v
    monkeypatch.setattr(config, "FAL_KEY", "clave-fal")
    monkeypatch.setattr(config, "SIN_PAGO", True)
    assert not v.con_fal()
    with pytest.raises(v.SinFacturacion, match="STUDIO4_SIN_PAGO"):
        v.imagen("un faro", "9:16", tmp_path / "a.png", v.Presupuesto(1))
    with pytest.raises(v.SinFacturacion, match="STUDIO4_SIN_PAGO"):
        v.video("un faro", "9:16", tmp_path / "a.mp4", v.Presupuesto(1))
    for interna in ("http://127.0.0.1:8000/api/estado", "http://localhost:8000/", "http://192.168.1.1/admin", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            referencias._url_publica(interna)


def test_fiabilidad_timeouts_y_voz_402_429(aislado, monkeypatch):
    import subprocess
    from studio4 import gemini
    monkeypatch.setattr(medios.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(a[0], 5)))
    with pytest.raises(RuntimeError, match="tardó más"):
        medios.ffmpeg("-version", timeout=5)
    with pytest.raises(ValueError, match="tardó demasiado"):
        medios.info("x.mp4", timeout=5)

    esperas, intentos = [], []
    monkeypatch.setattr("time.sleep", lambda s: esperas.append(s))

    class Part:
        inline_data = type("D", (), {"data": b"\x00\x00" * 100})()

    class Resp:
        candidates = [type("C", (), {"content": type("Ct", (), {"parts": [Part()]})()})()]

    def gen(model, contents, config):
        intentos.append(model)
        if len(intentos) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 3.5s.")
        return Resp()

    monkeypatch.setattr(gemini, "cliente", lambda: type("Cli", (), {"models": type("M", (), {"generate_content": staticmethod(gen)})()})())
    voz._gemini("Hola mundo", aislado / "v.wav", "p1")
    assert intentos == [config.MODELO_TTS, config.MODELO_TTS] and esperas == [pytest.approx(4.5)]

    monkeypatch.setattr(gemini, "cliente", lambda: type("Cli", (), {"models": type("M", (), {
        "generate_content": staticmethod(lambda **_: (_ for _ in ()).throw(RuntimeError("402 Out of prepayment credits")))})()})())
    with pytest.raises(RuntimeError, match="SIN facturación"):
        voz._gemini("Hola", aislado / "v2.wav", "p1")


def test_aprender_con_reserva_gemini_y_foto_archivo(servidor, monkeypatch):
    from studio4 import aprender, archivo, canales, gemini, youtube
    pedir, _ = servidor
    canales.guardar({**canales.obtener("fourlevel"), "nicho": "videojuegos"})
    monkeypatch.setattr(youtube, "disponible", lambda: True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(aprender, "elegir_videos", lambda _c: [{
        "id": "v1", "titulo": "El secreto de GTA", "canal": "Ref", "vistas": 50000, "segundos": 60, "url": "https://youtu.be/v1"}])
    monkeypatch.setattr(aprender, "transcripcion", lambda _u: {"texto": " ".join(["palabra"] * 40), "palabras": 40, "segundos": 20, "ritmo": 2.0})
    respuestas = [
        json.dumps({"gancho": "Nadie miró detrás de la puerta.", "por_que_engancha": "curiosidad", "voz": "cercana",
                    "presenta_lo_desconocido": "con dato", "estructura": ["1", "2"], "recursos": ["giro"], "cierre": "fin", "temas": "gta"}),
        json.dumps({"resumen": "Arrancan en la escena.", "voz": "directa", "ganchos": [{"patron": "dato", "ejemplo": "Nadie miró", "de": "Ref"}],
                    "presentar": "en acción", "estructuras": [{"nombre": "corto", "para": "corto", "pasos": ["a", "b"]}],
                    "recursos": ["cifra"], "cierres": ["seco"], "temas_que_funcionan": ["gta"], "evitar": ["saludos"],
                    "reglas": ["Entra directo al plano."]}),
    ]
    monkeypatch.setattr(gemini, "generar", lambda *a, **k: respuestas.pop(0))
    datos = aprender.estudiar("fourlevel")
    assert datos["manual"]["reglas"] == ["Entra directo al plano."]
    assert "MANUAL DEL CANAL" in aprender.para_guion("fourlevel")
    st, body = pedir("GET", "/api/manual")
    assert st == 200 and json.loads(body)["datos"]["manual"]["resumen"] == "Arrancan en la escena."

    p = _produccion("p-archivo", escenas=2)
    monkeypatch.setattr(archivo, "buscar", lambda q: [{"titulo": "File:Faro.jpg", "url": "https://x/f.jpg", "ancho": 800, "alto": 600, "fecha": "1920"}])
    monkeypatch.setattr(archivo, "toma", lambda titulo, carp, orden, an, al: {
        "archivo": "tomas/escena_01_archivo.png", "tipo": "imagen", "origen": "archivo", "fuente": titulo, "sha": "abc"})
    st, body = pedir("GET", "/api/archivo?q=faro")
    assert st == 200 and json.loads(body)["fotos"][0]["titulo"] == "File:Faro.jpg"
    st, body = pedir("POST", "/api/escena/archivo", {"Content-Type": "application/json"}, json.dumps({"orden": 1, "titulo": "File:Faro.jpg"}).encode())
    assert st == 200 and produccion.cargar(p["id"])["escenas"][0]["tomas"][0]["origen"] == "archivo"





def test_tope_de_ffmpeg_crece_con_la_duracion(monkeypatch, tmp_path):
    """Un FFmpeg colgado no bloquea para siempre, pero un largo de 5 min nunca se corta por el tope."""
    video = tmp_path / "largo.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(medios, "duracion", lambda _r: 300.0)
    assert medios._limite(("-i", str(video), "salida.mp4"), None) == 600 + 40 * 300
    assert medios._limite(("-loop", "1", "-i", "foto.png", "-t", "2.5", "s.mp4"), None) == 600 + 100
    assert medios._limite(("-f", "lavfi", "-i", "color=c=black", "s.mp4"), None) == 600


def test_volver_a_mi_guion_deshace_completar(aislado, monkeypatch):
    monkeypatch.setattr(produccion, "completar_guion", lambda *_a, **_k: None)
    [pid] = produccion.crear("", [], "documental", "gemini", guion_propio="Bonnie nunca disparó. Lucía sí. Y eso lo cambia todo.")
    with pytest.raises(ValueError, match="ya es el tuyo"):
        produccion.volver_guion_original(pid)
    produccion.modificar(pid, lambda p: p.update(guion_original=p["guion"], guion="Historia completa y larga.", autor_guion="Tú + DeepSeek"))
    produccion.volver_guion_original(pid)
    p = produccion.cargar(pid)
    assert p["guion"].startswith("Bonnie nunca disparó") and p["autor_guion"] == "Tú"


def test_enlace_que_redirige_a_tu_pc_se_rechaza(monkeypatch):
    from studio4 import referencias

    class Resp:
        is_redirect, headers = True, {"Location": "http://127.0.0.1:8000/api/estado"}

        def close(self):
            pass
    monkeypatch.setattr(referencias, "_url_publica", lambda u: (_ for _ in ()).throw(ValueError("interna")) if "127.0.0.1" in u else u)
    monkeypatch.setattr(referencias.requests, "get", lambda *a, **k: Resp())
    with pytest.raises(ValueError, match="interna"):
        referencias._texto_web("https://ejemplo.com/pagina")


def test_reserva_de_texto_cuando_gemini_no_tiene_saldo(monkeypatch):
    """402 de Google: el paso lo hace DeepSeek con el mismo esquema, y Gemini queda en pausa (sin más esperas)."""
    from pydantic import BaseModel
    from studio4 import deepseek, gemini

    class Plan(BaseModel):
        titulo: str
        escenas: list[str]

    llamadas = []

    def cliente():
        llamadas.append(1)
        raise RuntimeError("402 Your prepayment credits are depleted.")
    monkeypatch.setattr(gemini, "cliente", lambda: type("C", (), {"models": type("M", (), {
        "generate_content": staticmethod(lambda **_: cliente())})()})())
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(gemini, "_bloqueo", {"hasta": 0.0, "motivo": ""})
    monkeypatch.setattr(deepseek, "disponible", lambda: True)
    pedidos = []
    monkeypatch.setattr(deepseek, "generar_json", lambda s, p, **k: pedidos.append(p) or {"titulo": "T", "escenas": ["a", "b"]})
    monkeypatch.setattr(deepseek, "generar_texto", lambda s, p, **k: "texto de reserva")

    assert json.loads(gemini.generar("Planifica", esquema=Plan, detalle="escenas")) == {"titulo": "T", "escenas": ["a", "b"]}
    assert '"escenas"' in pedidos[0] and len(llamadas) == 1          # el esquema viaja a la reserva; un solo intento a Google
    assert gemini.generar("Resume", detalle="x") == "texto de reserva"
    assert len(llamadas) == 1 and "402" in gemini.bloqueado()          # en pausa: ya no se le pregunta
    with pytest.raises(RuntimeError, match="402"):                     # con imágenes no hay reserva posible
        gemini.generar("Mira", imagenes=[b"x"])
    with pytest.raises(RuntimeError, match="402"):                     # quien ya viene de DeepSeek no vuelve a él
        gemini.generar("Guion", reserva=False)


def test_guion_por_clips_de_flow():
    """48 s → 6 clips de 8 s; el guion se trocea en bloques de ~18 palabras sin partir frases que caben."""
    from studio4 import clips
    assert clips.plan(48) == {"clips": 6, "segundos": 48, "palabras": 108}
    assert clips.plan(50)["clips"] == 6 and clips.plan(5)["clips"] == 2
    frase = "Bonnie Parker murió en 1934 en una carretera de Luisiana junto a Clyde."   # 13 palabras
    bloques = clips.trocear(" ".join([frase] * 4))
    assert bloques == [frase] * 4                       # dos frases juntas (26) no caben: una por clip
    largo = "Uno dos tres cuatro cinco seis siete ocho nueve diez, once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve veinte, veintiuno veintidós veintitrés veinticuatro."
    assert len(clips.trocear(" ".join([largo] * 2))) >= 3                     # una frase enorme se parte por comas
    assert all(len(b.split()) <= clips.TOPE + 6 for b in clips.trocear(largo))   # (un final diminuto se une al anterior)
    assert " ".join(clips.trocear(largo)) == largo
    assert clips.trocear("Una frase con bastantes palabras para llenar casi un clip entero de ocho. Fin.") == [
        "Una frase con bastantes palabras para llenar casi un clip entero de ocho. Fin."]   # el resto diminuto se une


def test_director_una_escena_por_clip(monkeypatch):
    """Si Gemini junta dos clips en una escena, cada clip sigue teniendo su escena (y continúa el mismo plano)."""
    bloques = ["Primer clip con su texto.", "Segundo clip con su texto.", "Tercer clip con su texto."]
    escenas = [{"texto_voz": "[Clip 1] Primer clip con su texto. [Clip 2] Segundo clip con su texto.", "accion_en": "A"},
               {"texto_voz": "Tercer clip con su texto.", "accion_en": "B"}]
    salida = director._ajustar_a_bloques([{**e, "texto_voz": director._sin_etiqueta(e["texto_voz"])} for e in escenas], bloques)
    assert [e["texto_voz"] for e in salida] == bloques
    assert [e["accion_en"] for e in salida] == ["A", "A", "B"] and [e["continua"] for e in salida] == [False, True, False]
    assert [e["texto_voz"] for e in director._ajustar_a_bloques(escenas[:1] * 3, bloques)] == bloques


def test_identidad_del_canal_llega_al_guion():
    from studio4 import guion
    assert guion.identidad_del_canal({"nombre": "X"}) == ""
    t = guion.identidad_del_canal({"arquetipo": "Monarca de autoridad", "arco": "timidez → autoridad", "cta": "Comenta REINO"})
    assert "Monarca de autoridad" in t and "timidez → autoridad" in t and "«Comenta REINO»" in t
    assert "IDENTIDAD DEL CANAL" in guion._peticion("idea", "dossier", {"corto": 48}, identidad=t)
    assert "6 clips de 8 s" in guion._peticion("idea", "dossier", {"corto": 48})


def test_copiar_todo_para_flow_y_estado_de_la_carpeta(aislado):
    """Un solo texto con personajes y una escena por clip; la carpeta dice cuántos clips hay y a qué escenas van."""
    from studio4 import carpetas, flow
    p = _produccion("p-flow", escenas=2)
    produccion.modificar("p-flow", lambda q: q.update(titulo="Bonnie", fichas=[{"nombre": "LUCIA", "prompt": "portrait of Lucia"}]))
    p = produccion.cargar("p-flow")
    texto = flow.todo_para_flow(p)
    assert "STUDIO 4 · «Bonnie» · 2 escenas" in texto and "- LUCIA: portrait of Lucia" in texto
    assert texto.index("Escena 1 ·") < texto.index("Escena 2 ·") and p["escenas"][1]["prompt_flow"] in texto
    produccion.preparar_carpeta("p-flow")
    p = produccion.cargar("p-flow")
    clips_dir = carpetas.ruta(p) / carpetas.subcarpeta(p, carpetas.CLIPS)
    (clips_dir / "Bonnie - escena 02.mp4").write_bytes(b"x")
    (clips_dir / "notas.txt").write_text("no es un clip")
    e = carpetas.estado(p)
    assert (e["archivos"], e["escenas_en_carpeta"], e["total"]) == (1, 1, 2)


def test_guardar_canal_no_borra_lo_que_el_formulario_no_trae(aislado):
    from studio4 import canales
    c = canales.obtener("fourlevel")
    canales.guardar({**c, "tono": "cómplice", "voz_nombre": "Charon", "arquetipo": "gamer veterano"})
    canales.guardar({"id": "fourlevel", "nombre": c["nombre"], "nicho": "videojuegos", "cta": "Comenta tu juego"})
    g = canales.obtener("fourlevel")
    assert (g["tono"], g["voz_nombre"], g["arquetipo"], g["nicho"], g["cta"]) == ("cómplice", "Charon", "gamer veterano", "videojuegos", "Comenta tu juego")


def test_velocidad_de_la_voz(tmp_path):
    """1,1×: caben más palabras por clip; FFmpeg acelera la voz sin cambiar el tono."""
    from studio4 import clips
    assert clips.palabras_por_clip(1.0) == 18 and clips.palabras_por_clip(1.1) == 20 and clips.palabras_por_clip(0.9) == 16
    texto = " ".join(["Una frase de siete palabras para medir."] * 12)
    assert len(clips.trocear(texto, 1.2)) < len(clips.trocear(texto, 0.9))
    if shutil.which("ffmpeg"):
        wav = tmp_path / "v.wav"
        medios.ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav))
        voz.acelerar(wav, 1.2)
        assert abs(medios.duracion(wav) - 2 / 1.2) < 0.1


def test_idea_en_tendencia_es_original_y_detallada(aislado, monkeypatch):
    from studio4 import aprender, ideas
    monkeypatch.setattr(aprender, "transcripcion", lambda url: {"texto": "¿Recuerdan a este youtuber? " * 5, "palabras": 25})
    pedidos = []
    monkeypatch.setattr(aprender, "_generar_json", lambda s, p, **k: pedidos.append(p) or {
        "idea": "Dinamarca en Minecraft", "por_que": "contraste", "original": "una habitación copiada",
        "gancho": "¿Sabes quién lo hizo?", "estructura": ["gancho", "dato", "apuesta"], "detalles": ["2014", "1:1"], "formato": "corto"})
    d = ideas.inspirar("fourlevel", {"titulo": "SON IGUALES", "canal": "MrRelevante", "vistas": 6000000, "url": "https://youtu.be/x"})
    assert d["leido"] and "¿Recuerdan a este youtuber?" in pedidos[0] and "6.000.000 vistas" in pedidos[0]
    t = ideas.como_texto(d)
    assert "SON IGUALES" not in t and "MrRelevante" not in t   # el guionista nunca ve el vídeo ni el canal de origen
    assert "gancho → dato → apuesta" in t and "- 1:1" in t


def test_edicion_transiciones_y_efectos():
    ed = {**render.EDICION_POR_DEFECTO, "transicion": "fundido", "efecto": "cine"}
    medio = render._acabado(ed, 5.0, primero=False, ultimo=False, video=True, ancho=1080, alto=1920)
    assert medio[0].startswith("eq=") and "fade=t=in:st=0" in medio[1] and "fade=t=out:st=4.780" in medio[2]
    assert not any("fade=t=in" in f for f in render._acabado(ed, 5.0, primero=True, ultimo=False, video=True, ancho=1, alto=1))
    assert render._acabado({**ed, "transicion": "destello", "efecto": "zoom"}, 5.0, False, True, video=False, ancho=1, alto=1) == [
        "fade=t=in:st=0:d=0.25:color=white"]                      # el zoom no se aplica a imágenes (ya llevan el suyo)
    assert render._acabado(render.EDICION_POR_DEFECTO, 5.0, False, False, True, 1, 1) == []   # por defecto, nada cambia


def test_editar_valida_y_recorte_minimo(aislado, tmp_path):
    _produccion("p-ed", escenas=1)
    produccion.editar("p-ed", {"transicion": "fundido", "efecto": "inventado", "inicio": "1.5", "final": -3, "caratula": False})
    ed = produccion.cargar("p-ed")["edicion"]
    assert (ed["transicion"], ed["efecto"], ed["inicio"], ed["final"], ed["caratula"]) == ("fundido", "ninguno", 1.5, 0.0, False)
    if shutil.which("ffmpeg"):
        v = tmp_path / "v.mp4"
        medios.ffmpeg("-f", "lavfi", "-i", "color=c=black:s=320x240:d=6", "-f", "lavfi", "-i", "sine=d=6", "-shortest", str(v))
        render.recortar_final(v, 1.0, 1.0)
        assert abs(medios.duracion(v) - 4.0) < 0.2
        with pytest.raises(ValueError, match="quedarían"):
            render.recortar_final(v, 2.0, 1.5)


@hay_ffmpeg
def test_quitar_escena_de_video_importado_corta_su_audio(aislado):
    p = _produccion("p-imp", escenas=3, version="importado")
    wav = produccion.carpeta("p-imp") / "voz.wav"
    medios.ffmpeg("-f", "lavfi", "-i", "sine=d=9", str(wav))
    voz_ = {"archivo": "voz.wav", "duracion": 9.0, "escenas": [{"ini": 0, "fin": 3}, {"ini": 3, "fin": 6}, {"ini": 6, "fin": 9}],
            "palabras": [{"palabra": "a", "ini": 1, "fin": 2}, {"palabra": "b", "ini": 4, "fin": 5}, {"palabra": "c", "ini": 7, "fin": 8}]}
    produccion.modificar("p-imp", lambda q: q.update(voz=voz_))
    produccion.quitar_escena("p-imp", 2)
    q = produccion.cargar("p-imp")
    assert [e["texto_voz"] for e in q["escenas"]] == ["frase 1", "frase 3"] and q["voz"] is not None
    assert q["voz"]["escenas"] == [{"ini": 0, "fin": 3}, {"ini": 3.0, "fin": 6.0}]
    assert [w["palabra"] for w in q["voz"]["palabras"]] == ["a", "c"] and q["voz"]["palabras"][1]["ini"] == 4.0
    assert abs(medios.duracion(wav) - 6.0) < 0.15


def test_video_modelo_manda_en_el_guion_y_en_la_voz(aislado, monkeypatch):
    from studio4 import aprender
    monkeypatch.setattr(aprender, "transcripcion", lambda url: {"texto": "Rockstar acaba de revelar " * 10, "ritmo": 2.6})
    monkeypatch.setattr(aprender, "_generar_json", lambda *a, **k: {
        "resumen": "análisis narrado", "narrador": "Loquendo", "voz": "Voz sintética estilo Loquendo",
        "estructura": ["noticia", "bloques"], "ritmo": "rápido", "visual": "material del juego", "datos": "cifras",
        "cierre": "balance", "reglas": ["Usa narrador no humano"]})
    aprender.estudiar_modelo("fourlevel", "https://youtu.be/m", "así quiero mis vídeos")
    aprender.estudiar_modelo("fourlevel", "https://youtu.be/m", "nota nueva")   # el mismo vídeo se reemplaza, no se duplica
    texto = aprender.para_guion("fourlevel")
    assert texto.startswith("VÍDEO MODELO (de otro canal") and "Nota del autor: nota nueva" in texto
    assert "youtu.be" not in texto and "nunca menciones a ese canal" in texto   # ni su enlace ni su nombre
    assert texto.count("VÍDEO MODELO") == 1 and "- Usa narrador no humano" in texto
    assert aprender.voz_modelo("fourlevel") == "Voz sintética estilo Loquendo"


def test_plataforma_del_enlace():
    from studio4 import importar
    casos = {"https://www.youtube.com/watch?v=a": "youtube", "https://youtu.be/a": "youtube", "https://fb.watch/a": "facebook",
             "https://www.tiktok.com/@a/video/1": "tiktok", "https://www.instagram.com/reel/a": "instagram", "https://ejemplo.org/v": ""}
    assert {u: importar.plataforma(u) for u in casos} == casos
    with pytest.raises(ValueError):
        importar.vista_previa("no es un enlace")



@hay_ffmpeg
def test_importacion_cortada_no_repite_descarga_ni_transcripcion(aislado, monkeypatch):
    """Studio 4 se cerró a mitad: al retomar se usan el vídeo y la transcripción que ya estaban."""
    from studio4 import importar
    _produccion("p-ret", escenas=1, version="importado", origen={"url": "https://youtu.be/x"}, desde_url=True)
    base = produccion.carpeta("p-ret")
    medios.ffmpeg("-f", "lavfi", "-i", "testsrc=s=320x240:d=4", "-f", "lavfi", "-i", "sine=d=4", "-shortest", str(base / "origen.mp4"))
    (base / "transcripcion.json").write_text(json.dumps([{"palabra": "hola", "ini": 0.5, "fin": 1.0},
                                                         {"palabra": "mundo", "ini": 1.2, "fin": 1.8}]), encoding="utf-8")
    monkeypatch.setattr(importar, "descargar", lambda *a, **k: pytest.fail("no debe volver a descargar"))
    monkeypatch.setattr(importar, "transcribir", lambda *a, **k: pytest.fail("no debe volver a transcribir"))
    monkeypatch.setattr(produccion, "_fase_render", lambda pid: None)
    produccion._fase_importar("p-ret", "https://youtu.be/x", completo=True)
    q = produccion.cargar("p-ret")
    assert q["voz"]["palabras"][0]["palabra"] == "hola" and q["escenas"]


def test_cola_de_descargas_deja_tres_a_la_vez():
    assert produccion.MAX_DESCARGAS == 3
    assert all(produccion._cola_descargas.acquire(blocking=False) for _ in range(3))
    assert not produccion._cola_descargas.acquire(blocking=False)   # la cuarta espera su turno
    for _ in range(3):
        produccion._cola_descargas.release()


def test_escenas_con_tiempos_de_whisper_desordenados():
    """Palabras solapadas o desordenadas: ninguna escena sale con duración cero o negativa."""
    from studio4 import importar
    palabras = [{"palabra": "Hola.", "ini": 0.0, "fin": 3.2}, {"palabra": "Otra.", "ini": 3.1, "fin": 3.15},
                {"palabra": "frase.", "ini": 2.9, "fin": 6.5}, {"palabra": "Fin.", "ini": 6.6, "fin": 9.0}]
    tramos = importar.escenas(palabras, [], 8.9)
    assert all(t["fin"] - t["ini"] >= 0.3 for t in tramos)
    assert tramos[0]["ini"] == 0 and all(a["fin"] == b["ini"] for a, b in zip(tramos, tramos[1:]))


def test_error_dice_el_motivo_el_paso_y_guarda_el_detalle(aislado):
    _produccion("p-err", escenas=1)

    def falla():
        produccion._avisar("p-err", "Preparando la escena 50 de 120", 77)
        raise RuntimeError("No se pudo cortar la escena 50 (300.1-299.9 s del vídeo): FFmpeg falló: -to menor que -ss")
    produccion._en_fondo("p-err", "Desde URL", falla)
    for _ in range(100):
        t = produccion.cargar("p-err")["trabajo"]
        if not t.get("ocupado"):
            break
        _time.sleep(0.05)
    assert "No se pudo cortar la escena 50" in t["error"] and t["fase_fallida"] == "Preparando la escena 50 de 120"
    assert t["detalle"].startswith("RuntimeError: No se pudo cortar") and t["reintentable"]


def test_corregir_texto_de_escena_importada_no_toca_el_audio(aislado):
    """«Jason Dubal» → «Jason Duval»: cambian los subtítulos de esa escena; la voz original sigue."""
    _produccion("p-txt", escenas=2, version="importado")
    voz_ = {"archivo": "voz.wav", "duracion": 6.0, "escenas": [{"ini": 0, "fin": 3}, {"ini": 3, "fin": 6}],
            "palabras": [{"palabra": "frase", "ini": 0.2, "fin": 1.0}, {"palabra": "1", "ini": 1.1, "fin": 2.0},
                         {"palabra": "Jason", "ini": 3.2, "fin": 4.0}, {"palabra": "Dubal", "ini": 4.1, "fin": 5.0}]}
    produccion.modificar("p-txt", lambda q: q.update(voz=voz_))
    produccion.editar_escena("p-txt", 2, {"texto_voz": "Jason Duval"})
    q = produccion.cargar("p-txt")
    assert q["voz"] is not None and q["escenas"][1]["texto_voz"] == "Jason Duval"
    assert [w["palabra"] for w in q["voz"]["palabras"]] == ["frase", "1", "Jason", "Duval"]
    assert all(3.0 <= w["ini"] and w["fin"] <= 6.0 for w in q["voz"]["palabras"][2:]) and q["guion"].endswith("Jason Duval")


def test_transcripcion_va_diciendo_por_donde_va(monkeypatch, tmp_path):
    """En un vídeo largo la barra avanza con el tiempo transcrito («6:30 de 17:45»), no se queda quieta."""
    from studio4 import importar

    class Palabra:
        def __init__(self, w, a, b):
            self.word, self.start, self.end = w, a, b

    class Seg:
        def __init__(self, fin, palabras):
            self.end, self.words = fin, palabras

    class Modelo:
        def transcribe(self, *a, **k):
            return iter([Seg(390.0, [Palabra(" hola", 1, 2)]), Seg(1065.8, [Palabra(" fin", 1060, 1065)])]), type("I", (), {"duration": 1065.8})()
    monkeypatch.setattr(importar, "_whisper", Modelo())
    pasos = []
    palabras = importar.transcribir(tmp_path / "a.wav", avance=lambda fr, t: pasos.append((round(fr, 2), t)))
    assert [w["palabra"] for w in palabras] == ["hola", "fin"]
    assert pasos == [(0.37, "Transcribiendo el vídeo · 6:30 de 17:45"), (1.0, "Transcribiendo el vídeo · 17:45 de 17:45")]


def test_imagenes_reales_de_las_fuentes(monkeypatch):
    """De cada imagen se queda la versión más grande; fuera logos e iconos; cada escena recibe la que mejor encaja."""
    from PIL import Image
    from studio4 import fuentes, galeria
    pagina = ('<img src="/images/jch-optimize/logo.avif"><img src="/img/menu/icon-gta.png">'
              '<a href="/igallery/lucia-caminos-01-1080.jpg"><img src="/igallery/lucia-caminos-01-468.jpg"></a>'
              '<a href="/igallery/jason-duval-truck-1080.jpg"></a><meta property="og:image" content="/igallery/vice-beach-02-468.jpg">')
    monkeypatch.setattr(fuentes, "_get", lambda url: type("R", (), {"text": pagina})())
    imgs = galeria.imagenes_de("https://www.gtabase.com/gta-6/characters/lucia")
    assert sorted(i["url"].rsplit("/", 1)[-1] for i in imgs) == ["jason-duval-truck-1080.jpg", "lucia-caminos-01-1080.jpg",
                                                                   "vice-beach-02-468.jpg"]
    escenas = [{"orden": 1, "texto_voz": "Jason la espera junto a su camioneta", "elegida": None, "personajes": ["JASON"]},
               {"orden": 2, "texto_voz": "Lucía sale de la cárcel", "elegida": None, "accion_en": "LUCIA walks out", "personajes": ["LUCIA"]},
               {"orden": 3, "texto_voz": "ya tiene clip", "elegida": 0}]
    reparto = galeria.repartir(escenas, imgs)
    assert reparto[1]["url"].endswith("jason-duval-truck-1080.jpg") and reparto[2]["url"].endswith("lucia-caminos-01-1080.jpg")
    assert 3 not in reparto
    vertical = galeria.encajar(Image.new("RGB", (1920, 1080), "red"), 1080, 1920)   # captura 16:9 en un vertical: entera
    horizontal = galeria.encajar(Image.new("RGB", (1920, 1080), "red"), 1920, 1080)  # misma forma: llena
    assert vertical.size == (1080, 1920) and vertical.getpixel((20, 960))[0] < 150 and horizontal.getpixel((5, 5)) == (255, 0, 0)


def test_voz_larga_se_graba_por_trozos_y_se_une(monkeypatch, tmp_path):
    """15 minutos no caben en una llamada: se graba por trozos de escenas enteras y los tiempos se recolocan."""
    escenas = [("palabra " * 120).strip() for _ in range(6)]          # ~840 caracteres cada escena
    assert voz.trozos(escenas, limite=2000) == [(0, 2), (2, 4), (4, 6)]
    assert voz.trozos(["x" * 5000]) == [(0, 1)]                          # una escena enorme no se parte
    if not shutil.which("ffmpeg"):
        return
    llamadas = []

    def uno(segs, destino, proveedor, produccion, direcciones, voz_nombre, estilo_voz, velocidad, contexto=("", "")):
        llamadas.append((len(segs), bool(contexto[0]), bool(contexto[1])))
        medios.ffmpeg("-f", "lavfi", "-i", "sine=d=4", "-ar", "24000", "-ac", "1", str(destino))
        return {"proveedor": proveedor, "duracion": 4.0, "escenas": [{"ini": 0, "fin": 2}, {"ini": 2, "fin": 4}],
                "palabras": [{"palabra": "a", "ini": 0.5, "fin": 1.0}], "dirigida": False, "voz_nombre": ""}
    monkeypatch.setattr(voz, "_locutar_uno", uno)
    monkeypatch.setattr(voz, "LIMITE_TROZO", 2000)
    r = voz.locutar(escenas, tmp_path / "voz.wav", "fal")
    assert llamadas == [(2, False, True), (2, True, True), (2, True, False)]   # cada trozo sabe qué va antes y después
    assert [e["ini"] for e in r["escenas"]] == [0, 2, 4.0, 6.0, 8.0, 10.0] and r["palabras"][2]["ini"] == 8.5
    assert abs(r["duracion"] - 12.0) < 0.15 and r["trozos"] == 3 and not list(tmp_path.glob("voz_trozo*"))


def test_mas_escenas_que_imagenes_se_reusan_en_vez_de_dejar_huecos():
    from studio4 import galeria
    imgs = [{"url": f"https://x/{n}-1080.jpg", "descripcion": n, "pagina": "p"} for n in ("lucia", "jason")]
    escenas = [{"orden": i, "texto_voz": "algo", "elegida": None} for i in range(1, 6)]
    reparto = galeria.repartir(escenas, imgs)
    assert sorted(reparto) == [1, 2, 3, 4, 5] and reparto[1]["url"] != reparto[2]["url"]



def test_vídeo_modelo_sin_frases_literales_del_otro_canal():
    from studio4 import aprender
    t = aprender._sin_citas('Saluda con “Espero les guste y comenzamos”. Prueba literal: abre con «Rockstar acaba de revelar».')
    assert "Espero les guste" not in t and "Rockstar acaba" not in t and "Saluda con" in t


def test_ideas_del_dia_tres_de_canales_distintos_sin_nombrar_el_origen(aislado, monkeypatch):
    from studio4 import ideas, youtube
    monkeypatch.setattr(youtube, "disponible", lambda: True)
    videos = [{"id": f"v{i}", "titulo": f"Vídeo {i}", "canal": c, "vistas": 1000, "vistas_hora": 100 - i, "segundos": 30,
               "url": f"https://youtu.be/v{i}"} for i, c in enumerate(["MrRelevante", "MrRelevante", "Otro", "Tercero", "Cuarto"])]
    monkeypatch.setattr(ideas, "en_vivo", lambda cid, n=12: videos)
    monkeypatch.setattr(ideas, "inspirar", lambda cid, v: {"idea": f"Idea de {v['id']}", "por_que": "porque sí",
        "original": "lista rápida", "gancho": "¿Sabías…?", "estructura": ["a", "b"], "detalles": ["x"], "formato": "corto",
        "fuente": {"titulo": v["titulo"], "canal": v["canal"], "url": v["url"]}})
    monkeypatch.setattr(ideas, "imagen_de", lambda cid, idea: {})
    d = ideas.generar_diarias("fourlevel")
    assert [x["idea"] for x in d["ideas"]] == ["Idea de v0", "Idea de v2", "Idea de v3"]   # un solo vídeo por canal
    assert d["ideas"][0]["miniatura"] == ""   # nunca la miniatura del vídeo ajeno
    for x in d["ideas"]:
        assert x["fuente"]["canal"] not in x["texto"] and x["fuente"]["titulo"] not in x["texto"]   # el guionista no lo ve
    assert ideas.diarias("fourlevel")["hoy"] and len(ideas.diarias("fourlevel")["ideas"]) == 3


def test_voz_y_material_se_guardan_en_la_carpeta_del_video(aislado):
    from studio4 import carpetas
    _produccion("p-mat", escenas=2, titulo="Armas de GTA 6", carpeta="",
                investigacion={"fuentes": [{"url": "https://www.gtabase.com/gta-6/weapons"}]})
    base = produccion.carpeta("p-mat")
    (base / "tomas").mkdir()
    (base / "voz.wav").write_bytes(b"RIFF voz")
    (base / "tomas" / "e1.png").write_bytes(b"imagen 1")
    (base / "tomas" / "e1_original.jpg").write_bytes(b"original 1")
    (base / "tomas" / "e2.mp4").write_bytes(b"clip 2")

    def preparar(q):
        q["voz"] = {"archivo": "voz.wav", "proveedor": "fal", "duracion": 900.0}
        q["escenas"][0].update(tomas=[{"archivo": "tomas/e1.png", "tipo": "imagen", "origen": "real", "url": "https://x/lucia-1080.jpg",
                                       "fuente": "https://www.gtabase.com/gta-6/characters/lucia", "original": "tomas/e1_original.jpg"}], elegida=0)
        q["escenas"][1].update(tomas=[{"archivo": "tomas/e2.mp4", "tipo": "video", "origen": "flow"}], elegida=0)
    produccion.modificar("p-mat", preparar)
    destino = carpetas.guardar_material(produccion.cargar("p-mat"), base)
    nombres = sorted(str(f.relative_to(destino)).replace("\\\\", "/") for f in destino.rglob("*") if f.is_file())
    assert any(n.endswith("- Voz.wav") for n in nombres) and any("escena 01 - original.jpg" in n for n in nombres)
    assert any("escena 02.mp4" in n for n in nombres)
    creditos = next(destino.glob("* - Fuentes y créditos.txt")).read_text(encoding="utf-8")
    assert "lucia-1080.jpg" in creditos and "gtabase.com/gta-6/weapons" in creditos and "fal" in creditos



def test_investigar_en_las_fuentes_de_punta_a_punta(monkeypatch):
    """Elegir páginas, leerlas y resumirlas: el guion recibe los datos de tus páginas recomendadas."""
    from studio4 import fuentes, gemini
    monkeypatch.setattr(fuentes, "claves", lambda idea, produccion="": ["weapons", "vehicles"])
    monkeypatch.setattr(fuentes, "indice", lambda f: ["https://g.com/gta-6/weapons/flashbang", "https://g.com/gta-6/vehicles/cheetah",
                                                        "https://g.com/gta-6/animals/alligator"])
    monkeypatch.setattr(fuentes, "texto_de", lambda u: f"Página {u} " + "dato " * 100)
    monkeypatch.setattr(gemini, "generar", lambda *a, **k: "- La Cheetah Classic está confirmada [2]")
    r = fuentes.investigar("armas y autos de GTA 6", ["https://g.com/gta-6/"], n_paginas=10)
    assert r["texto"].startswith("- La Cheetah") and sorted(f["url"].rsplit("/", 1)[-1] for f in r["fuentes"]) == ["cheetah", "flashbang"]


PAQUETE = """Aquí tienes el paquete FL-001.

=== FL-001 | LARGO ===
TÍTULO: GTA 6: armas, autos y rarezas confirmadas
DESCRIPCIÓN: Todo lo confirmado por Rockstar.
HASHTAGS: #GTA6 #Rockstar #Leonida
GUION:
""" + "Esta frase del guion largo habla de armas y autos nuevos confirmados por Rockstar. " * 30 + """

=== FL-001 | CORTO a ===
TÍTULO: El arma más rara de GTA 6
DESCRIPCIÓN: Una sola arma.
HASHTAGS: #GTA6
GUION:
""" + "El arma más rara que veremos en Leonida tiene una historia curiosa. " * 4


def test_biblioteca_de_guiones(aislado):
    from studio4 import biblioteca
    items = biblioteca.anadir("fourlevel", PAQUETE)
    assert [(x["codigo"], x["tipo"], x["etiqueta"]) for x in items] == [("FL-001", "largo", ""), ("FL-001", "corto", "a")]
    assert items[0]["titulo"] == "GTA 6: armas, autos y rarezas confirmadas" and items[0]["hashtags"] == ["#GTA6", "#Rockstar", "#Leonida"]
    assert "TÍTULO" not in items[0]["guion"] and items[1]["palabras"] > 40
    assert len(biblioteca.anadir("fourlevel", PAQUETE)) == 2          # pegar lo mismo otra vez no duplica
    with pytest.raises(ValueError, match="=== FL-001"):
        biblioteca.parsear("un texto sin marcas")
    pids = [produccion.desde_biblioteca("fourlevel", x["id"]) for x in items]   # dos en el mismo segundo: no chocan
    assert len(set(pids)) == 2
    largo, corto = produccion.cargar(pids[0]), produccion.cargar(pids[1])
    assert (largo["formato"], corto["formato"]) == ("horizontal", "vertical") and largo["hashtags"] == ["#GTA6", "#Rockstar", "#Leonida"]
    assert all(x["producido"] for x in biblioteca.leer("fourlevel"))



def test_biblioteca_lee_el_formato_que_ponen_los_chats():
    """Negritas, títulos markdown, bloques de código y rayas en vez de barra: el paquete se lee igual."""
    from studio4 import biblioteca
    g = "Esta es una frase del guion con datos de armas nuevas y autos de GTA seis. " * 5
    for texto in (f"**=== FL-002 | LARGO ===**\n**TÍTULO:** Armas de GTA 6\n**GUION:**\n{g}",
                  f"### === FL-002 | LARGO ===\nTÍTULO: Armas de GTA 6\nGUION:\n{g}",
                  f"```\n=== FL-002 | LARGO ===\nTÍTULO: Armas de GTA 6\nGUION:\n{g}\n```",
                  f"=== FL-002 — LARGO ===\nTÍTULO: Armas de GTA 6\nGUION:\n{g}"):
        r = biblioteca.parsear(texto)
        assert r[0]["titulo"] == "Armas de GTA 6" and r[0]["palabras"] == 80 and "`" not in r[0]["guion"] and "*" not in r[0]["guion"]



def test_biblioteca_no_mete_fuentes_ni_control_en_el_ultimo_guion():
    from studio4 import biblioteca
    g = "Esta es una frase del guion corto con datos del arma más rara de Leonida. " * 3
    texto = (f"=== FL-003 | CORTO e ===\nTÍTULO: Comparación\nGUION:\n{g}\n\nFUENTES:\n- https://www.gtabase.com/gta-6/weapons\n"
             "CONTROL DE CALIDAD:\n[x] Datos verificables\n[x] Español latino")
    r = biblioteca.parsear(texto)
    assert "gtabase" not in r[0]["guion"] and "CONTROL" not in r[0]["guion"] and r[0]["guion"].endswith("Leonida.")



def test_metodologia_es_la_misma_para_todos_los_modelos_y_para_el_chat():
    """DeepSeek, Gemini y la reserva escriben con el mismo sistema, y el prompt del asistente por chat no se separa."""
    import re as _re
    from studio4 import guion, metodologia
    assert metodologia.para_sistema() in guion.SISTEMA
    chat = " ".join((config.RAIZ / "PROMPTS_AGRON.md").read_text(encoding="utf-8").split())
    for regla in metodologia.reglas()[:-2] + metodologia.CONTROL:   # LARGO y CORTO van reformulados en el paso 2
        assert " ".join(regla.split()) in chat, regla
    assert not any(p.lower() in metodologia.para_sistema().lower() for p in guion.PROHIBIDO)



def test_idea_del_dia_usa_imagen_real_del_tema_y_nunca_la_miniatura_ajena(aislado, monkeypatch):
    import json as _json
    from studio4 import ideas
    monkeypatch.setattr(ideas, "en_vivo", lambda cid, n: [{"id": "abc123", "canal": "Otro", "titulo": "t", "url": "u",
                                                          "vistas_hora": 10, "segundos": 30}])
    monkeypatch.setattr(ideas, "inspirar", lambda cid, v: {"idea": "El Cheetah Classic de GTA 6", "fuente": {}})
    monkeypatch.setattr(ideas.galeria, "buscar", lambda *a, **k: [{"url": "https://www.gtabase.com/x/cheetah.jpg",
                                                                  "pagina": "https://www.gtabase.com/gta-6/vehicles",
                                                                  "aciertos": ["cheetah", "gta"]}])
    d = ideas.generar_diarias("fourlevel")["ideas"][0]
    assert d["miniatura"] == "https://www.gtabase.com/x/cheetah.jpg" and d["miniatura_fuente"] == "www.gtabase.com"
    assert "ytimg" not in _json.dumps(d)



def test_biblioteca_guarda_las_fuentes_del_paquete():
    from studio4 import biblioteca
    g = "Esta es una frase del guion corto con datos del Cheetah Classic de Leonida. " * 3
    texto = (f"=== FL-001 | CORTO a ===\nTÍTULO: Autos\nGUION:\n{g}\n\nFUENTES:\n\nhttps://www.gtabase.com/gta-6/vehicles/\n"
             " (Registro de vehículos, Cheetah Classic).\nhttps://www.rockstargames.com/VI\n (Web oficial).\n\n"
             "CONTROL DE CALIDAD: [x] Datos verificables")
    r = biblioteca.parsear(texto)[0]
    assert [f["url"] for f in r["fuentes"]] == ["https://www.gtabase.com/gta-6/vehicles/", "https://www.rockstargames.com/VI"]
    assert r["fuentes"][0]["titulo"].startswith("Registro de vehículos") and "gtabase" not in r["guion"]



def test_imagenes_primero_de_las_paginas_del_guion_si_son_de_confianza(aislado, monkeypatch):
    from studio4 import galeria
    from studio4 import canales
    monkeypatch.setattr(canales, "de_produccion", lambda p: {"fuentes": ["https://www.gtabase.com/gta-6/"]})
    monkeypatch.setattr(galeria, "imagenes_de", lambda u: [{"url": u + "a.jpg", "pagina": u, "descripcion": "a"}])
    p = {"investigacion": {"fuentes": [{"url": "https://www.gtabase.com/gta-6/vehicles/"},
                                       {"url": "https://es.wikipedia.org/wiki/Grand_Theft_Auto_VI"}]}}
    assert [i["url"] for i in produccion._imagenes_de_sus_fuentes(p)] == ["https://www.gtabase.com/gta-6/vehicles/a.jpg"]



def test_imagen_de_la_idea_solo_si_encaja(aislado, monkeypatch):
    from studio4 import ideas
    generica = {"url": "https://www.gtabase.com/igallery/GTA5_Contender_Main.jpg", "pagina": "https://www.gtabase.com/gta-6/",
                "aciertos": ["gta"]}
    captura6 = {"url": "https://www.gtabase.com/igallery/gta-6-screenshots-trailer/gta6-beach.jpg",
                "pagina": "https://www.gtabase.com/gta-6/", "aciertos": ["gta"]}
    auto = {"url": "https://www.gtabase.com/images/gta-6/vehicles/cheetah-classic.jpg",
            "pagina": "https://www.gtabase.com/gta-6/vehicles/", "aciertos": ["gta", "cheetah"]}
    monkeypatch.setattr(ideas.archivo, "buscar", lambda *a, **k: [{"titulo": "File:Vampire painting.jpg", "url": "x"}])
    monkeypatch.setattr(ideas.galeria, "buscar", lambda *a, **k: [generica, auto])
    assert ideas.imagen_de("fourlevel", "El Cheetah Classic de GTA 6")["url"] == auto["url"]
    monkeypatch.setattr(ideas.galeria, "buscar", lambda *a, **k: [generica, captura6])
    assert ideas.imagen_de("fourlevel", "Miami o Vice City en GTA 6")["url"] == captura6["url"]
    assert ideas.imagen_de("fourlevel", "El vampiro de Red Dead Redemption 2") == {}   # mejor sin imagen


def test_imagen_de_wikipedia_solo_del_articulo_del_tema(aislado, monkeypatch):
    from studio4 import ideas

    class R:
        def __init__(self, paginas):
            self.p = paginas

        def json(self):
            return {"query": {"pages": {str(i): x for i, x in enumerate(self.p)}}}
    paginas = [{"index": 1, "title": "Mary Elizabeth McGlynn", "thumbnail": {"source": "https://x/actriz.jpg"}},
               {"index": 2, "title": "Nintendo Switch 2", "thumbnail": {"source": "https://x/switch2.png?utm=1"}}]
    monkeypatch.setattr(ideas.fuentes, "claves", lambda idea, p: ["nintendo switch 2", "mario"])
    monkeypatch.setattr(ideas.requests, "get", lambda *a, **k: R(paginas))
    assert ideas._de_wikipedia("El bundle de Switch 2 de Nintendo") == {"url": "https://x/switch2.png",
                                                                       "fuente": "Wikipedia · Nintendo Switch 2"}
    paginas.pop()
    assert ideas._de_wikipedia("El bundle de Switch 2 de Nintendo") == {}   # la actriz no tiene nada que ver



def test_plan_del_mes_de_agron_en_la_biblioteca(aislado):
    from studio4 import biblioteca
    tabla = ("Aquí tienes el plan:\n\n| Código | Tema | Juego | Por qué ahora | Fuentes |\n|---|---|---|---|---|\n"
             "| **FL-001** | GTA 6: armas y autos | GTA 6 | Tráiler 2 | https://www.gtabase.com/gta-6/weapons/ |\n"
             "| FL-002 | El vampiro de Saint Denis | RDR2 | Halloween | https://www.gtabase.com/red-dead-redemption-2/ |\n")
    r = biblioteca.pegar("fourlevel", tabla)
    assert [p["codigo"] for p in r["plan"]] == ["FL-001", "FL-002"] and r["temas_nuevos"] == 2
    assert r["plan"][0]["tema"] == "GTA 6: armas y autos" and "gtabase" in r["plan"][0]["fuentes"]
    g = "Esta es una frase del guion corto con datos del Cheetah Classic de Leonida. " * 3
    r = biblioteca.pegar("fourlevel", f"=== FL-001 | CORTO a ===\nTÍTULO: Autos\nGUION:\n{g}")
    assert r["plan"][0]["guiones"] == 1 and r["plan"][1]["guiones"] == 0 and r["temas_nuevos"] == 0
    with pytest.raises(ValueError):
        biblioteca.pegar("fourlevel", "hola")



def test_biblioteca_acepta_marcas_como_las_escribe_cada_chat():
    from studio4 import biblioteca
    g = "Esta es una frase del guion con datos de armas nuevas y autos de GTA seis. " * 3
    for marca in ("=== FL-001 · LARGO ===", "FL-001 | LARGO", "Guion FL-001 — LARGO", "=== FL 001 / LARGO ===",
                  "== FL-1 | LARGO ==", "**FL-001 | LARGO**"):
        r = biblioteca.parsear(f"{marca}\nTÍTULO: Armas\nGUION:\n{g}")
        assert (r[0]["codigo"], r[0]["tipo"]) == ("FL-001", "largo"), marca
    r = biblioteca.parsear(f"=== FL-002 | CORTO a: lo más llamativo ===\nGUION:\n{g}\n=== FL-002 | CORTO b ===\nGUION:\n{g}")
    assert [x["etiqueta"] for x in r] == ["a: lo más llamativo", "b"]
    # una fila del plan del mes no se confunde con un guion
    assert biblioteca.parsear_plan("| FL-003 | Largo viaje por Leonida | GTA 6 | x | y |")[0]["tema"] == "Largo viaje por Leonida"


def test_biblioteca_guion_en_la_misma_linea_y_plan_sin_barra_inicial(aislado):
    from studio4 import biblioteca
    g = "Esta es una frase del guion con datos de armas nuevas y autos de GTA seis. " * 3
    r = biblioteca.parsear(f"=== FL-001 | LARGO ===\nTÍTULO: Armas\nGUION: {g}")
    assert r[0]["guion"].startswith("Esta es una frase") and "GUION" not in r[0]["guion"]
    r = biblioteca.pegar("fourlevel", "FL-003 | Largo viaje por Leonida | GTA 6 | x | https://www.gtabase.com/gta-6/")
    assert r["temas_nuevos"] == 1 and not r["guiones"]



def test_biblioteca_paquete_pegado_en_una_sola_linea_y_con_comillas(aislado):
    """Tal cual lo pegó el autor: marca entre «», y título, descripción, hashtags y guion en la misma línea."""
    from studio4 import biblioteca
    g = ("El primer avance oficial de Grand Theft Auto 6 superó las noventa millones de reproducciones en solo "
         "veinticuatro horas. Hoy les traigo un análisis completo sobre cada arma, cada vehículo nuevo y cada rareza.")
    texto = (f"«=== FL-001 | LARGO ===» TÍTULO: GTA 6: Todas las armas DESCRIPCIÓN: Analizamos a fondo los vehículos. "
             f"HASHTAGS: #GTA6 #ViceCity GUION: {g} «=== FL-001 | CORTO a ===» TÍTULO: El arma rara GUION: {g} "
             "FUENTES: https://www.gtabase.com/gta-6/weapons/ (armas) CONTROL DE CALIDAD: [x] Datos verificables")
    r = biblioteca.pegar("fourlevel", texto)["guiones"]
    assert [(x["codigo"], x["tipo"]) for x in r] == [("FL-001", "largo"), ("FL-001", "corto")]
    assert r[0]["titulo"] == "GTA 6: Todas las armas" and r[0]["hashtags"] == ["#GTA6", "#ViceCity"]
    assert r[0]["guion"] == g and r[1]["guion"] == g
    assert r[0]["fuentes"][0]["url"] == "https://www.gtabase.com/gta-6/weapons/"



def test_biblioteca_avisa_de_guiones_repetidos_entre_temas(aislado):
    from studio4 import biblioteca
    vice = ("Vice City de 2002 tenía Ocean Drive con sus hoteles art deco y neón rosa. GTA 6 vuelve a esa calle "
            "con playas llenas de gente, tráfico real y reflejos en el agua que cambian con la hora del día. ") * 2
    otro = ("Red Dead Redemption 2 tiene doscientas especies de animales con comportamiento propio, cazadores, "
            "presas y carroñeros que reaccionan al clima y a las estaciones del juego. ") * 2
    biblioteca.pegar("fourlevel", f"=== FL-001 | CORTO e ===\nTÍTULO: Vice City vs GTA 6\nGUION:\n{vice}")
    r = biblioteca.pegar("fourlevel", f"=== FL-006 | CORTO a ===\nTÍTULO: Ocean Drive en GTA 6\nGUION:\n{vice}\n"
                                      f"=== FL-006 | CORTO b ===\nTÍTULO: Animales\nGUION:\n{otro}")
    assert r["repetidos"] == ["FL-006 corto a se parece a FL-001 corto e"]
    por_id = {g["id"]: g for g in r["guiones"]}
    assert por_id["FL-001-corto-e"]["parecido_a"] == ["FL-006 corto a"] and not por_id["FL-006-corto-b"]["parecido_a"]



def test_clave_gemini_nueva_se_prueba_antes_de_guardarse(aislado, monkeypatch, tmp_path):
    from studio4 import gemini

    class Modelos:
        def __init__(self, error):
            self.error = error

        def generate_content(self, **k):
            if self.error:
                raise RuntimeError(self.error)

    class Cliente:
        error = ""

        def __init__(self, api_key):
            self.models = Modelos(Cliente.error)
    monkeypatch.setattr(gemini.genai, "Client", Cliente)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "vieja")
    clave = "AIza" + "x" * 35
    with pytest.raises(ValueError, match="no parece"):
        gemini.cambiar_clave("hola")
    Cliente.error = "402 Your prepayment credits are depleted"
    with pytest.raises(ValueError, match="proyecto NUEVO"):
        gemini.cambiar_clave(clave)
    assert config.GEMINI_API_KEY == "vieja" and not (tmp_path / ".env").exists()   # la mala no se guarda
    Cliente.error = ""
    gemini._bloquear(1800, "sin saldo")
    gemini.cambiar_clave(clave)
    assert config.GEMINI_API_KEY == clave and clave in (tmp_path / ".env").read_text() and not gemini.bloqueado()


def test_biblioteca_de_material_y_seguridad_de_rutas(servidor, aislado, monkeypatch):
    import os
    import urllib.parse
    pedir, _ = servidor
    for i, pid in enumerate(("p-mat-1", "p-mat-2"), 1):
        _produccion(pid, escenas=2, titulo=f"Vídeo {i} de GTA 6", creado=f"2026-10-1{i} 10:00:00")
        base = produccion.carpeta(pid)
        (base / "tomas").mkdir()
        (base / "voz.wav").write_bytes(f"RIFF voz {i}".encode())
        (base / "tomas" / "e1.png").write_bytes(b"misma imagen repetida")
        (base / "tomas" / "e2.mp4").write_bytes(f"clip {i}".encode())

        def armar(q, n=i):
            q["voz"] = {"archivo": "voz.wav", "proveedor": "gemini", "duracion": 12.0}
            q["escenas"][0].update(tomas=[{"archivo": "tomas/e1.png", "tipo": "imagen", "origen": "real",
                                           "url": "https://www.gtabase.com/x/cheetah.jpg"}], elegida=0)
            q["escenas"][1].update(tomas=[{"archivo": "tomas/e2.mp4", "tipo": "video", "origen": "flow"}], elegida=0)
        produccion.modificar(pid, armar)
        carpetas.guardar_material(produccion.cargar(pid), base)

    estado, cuerpo = pedir("GET", "/api/material")
    assert estado == 200
    items = json.loads(cuerpo)["items"]
    assert [x["tipo"] for x in items].count("voz") == 2
    assert [x["tipo"] for x in items].count("imagen") == 2
    assert [x["tipo"] for x in items].count("clip") == 2
    repetidas = [x for x in items if x["usos"] > 1]
    assert len(repetidas) == 2 and all(x["tipo"] == "imagen" and x["videos_usado"] == 2 for x in repetidas)

    # Se puede descargar un archivo válido de material, pero no textos ni salir con ../ o rutas absolutas.
    ruta_ok = urllib.parse.quote(items[0]["ruta"])
    assert pedir("GET", f"/material/{ruta_ok}")[0] == 200
    env_abs = urllib.parse.quote(str((config.RAIZ / ".env").resolve()))
    txt_rel = urllib.parse.quote(f"{items[0]['ruta'].rsplit('/', 1)[0]}/créditos.txt")
    for mala in ("/material/../../.env", "/material/..%2F..%2F.env", f"/material/{env_abs}",
                 "/material/C:/Windows/win.ini", f"/material/{txt_rel}"):
        assert pedir("GET", mala)[0] == 404, mala

    # /api/carpeta/abrir solo abre carpetas de Studio 4 calculadas por el servidor; rechaza rutas libres.
    abiertas = []
    monkeypatch.setattr(os, "startfile", lambda r: abiertas.append(r), raising=False)
    cab = {"Content-Type": "application/json"}
    assert pedir("POST", "/api/carpeta/abrir", cab, json.dumps({"video": items[0]["video"]}).encode())[0] == 200
    assert abiertas and Path(abiertas[-1]).resolve().is_relative_to(carpetas.RAIZ_USUARIO.resolve())
    for intento in ("../..", "C:\\Windows", "FourLevel/../../secreto"):
        assert pedir("POST", "/api/carpeta/abrir", cab, json.dumps({"video": intento}).encode())[0] == 400


def test_panel_muestra_material_en_inicio_sin_retrasar_precarga():
    html = (config.WEB / "index.html").read_text(encoding="utf-8")
    js = (config.WEB / "panel.js").read_text(encoding="utf-8")
    assert html.index('id="lista"') < html.index('id="material-bib"') < html.index('class="motor"')
    assert 'id="material-bib" hidden' in html
    assert '["usado", "Lo más usado"]' in js and "let visiblesMaterial = 12;" in js
    assert "data-sin-precarga" in js and '!i.dataset.sinPrecarga' in js
    assert '<audio controls preload="none"' in js and '<video src="${src}" controls preload="none">' in js


def test_catalogo_seleccion_y_generacion_voces_elevenlabs(servidor, monkeypatch):
    """El catálogo se abre sin generar TTS, guarda el voice_id sin locutar y la generación final usa ese voice_id."""
    import base64
    import time
    pedir, _ = servidor
    _produccion("p-el", escenas=2)

    # 1. Sin clave, el catálogo informa el motivo y entrega las voces predeterminadas sin llamar a TTS.
    tts_llamadas = []
    elevenlabs_real = voz._elevenlabs
    monkeypatch.setattr(voz, "_elevenlabs", lambda *a, **k: tts_llamadas.append((a, k)) or {})
    estado, cuerpo = pedir("GET", "/api/voces/elevenlabs")
    assert estado == 200
    d0 = json.loads(cuerpo)
    assert not d0["ok"] and d0["codigo_error"] == "sin_clave" and d0["voces"]
    assert not tts_llamadas

    # 2. Con clave, consulta /v1/voices, normaliza campos, guarda en caché y respeta preview_url.
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "xi-clave-prueba")
    consultas_cat = []

    class RespCat:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "voices": [
                    {
                        "voice_id": "voz_cuenta_123",
                        "name": "Mateo Documental",
                        "category": "cloned",
                        "description": "Narrador en español neutro",
                        "labels": {"language": "es", "accent": "latino", "gender": "male", "use_case": "narration"},
                        "preview_url": "https://storage.googleapis.com/eleven-public/muestra.mp3",
                    },
                    {
                        "voice_id": "voz_sin_muestra_456",
                        "name": "Voz Sin Muestra",
                        "category": "generated",
                        "description": "Sin audio de muestra",
                        "labels": {"language": "es"},
                        "preview_url": None,
                    },
                ]
            }

    def get_mock(url, headers=None, timeout=15):
        consultas_cat.append((url, headers))
        return RespCat()

    monkeypatch.setattr(voz.requests, "get", get_mock)
    estado, cuerpo = pedir("GET", "/api/voces/elevenlabs")
    assert estado == 200
    cat = json.loads(cuerpo)
    assert cat["ok"] and not cat["cache"] and len(consultas_cat) == 1
    mateo = next(v for v in cat["voces"] if v["voice_id"] == "voz_cuenta_123")
    sin_m = next(v for v in cat["voces"] if v["voice_id"] == "voz_sin_muestra_456")
    assert mateo["nombre"] == "Mateo Documental" and mateo["idioma"] == "es" and mateo["acento"] == "latino"
    assert mateo["preview_url"].startswith("https://") and sin_m["preview_url"] == ""
    assert not tts_llamadas   # abrir el catálogo nunca ejecuta TTS

    # Segunda consulta usa la caché en disco sin volver a pedir a ElevenLabs.
    cat2 = json.loads(pedir("GET", "/api/voces/elevenlabs")[1])
    assert cat2["ok"] and cat2["cache"] and len(consultas_cat) == 1

    # 3. Errores de autenticación (401) y cuota (429) en el catálogo se informan con claridad.
    class RespErr:
        def __init__(self, code, txt):
            self.status_code = code
            self.text = txt

    monkeypatch.setattr(voz.requests, "get", lambda *a, **k: RespErr(401, "invalid_api_key"))
    err_auth = json.loads(pedir("GET", "/api/voces/elevenlabs?forzar=1")[1])
    assert not err_auth["ok"] and err_auth["codigo_error"] == "autenticacion"
    monkeypatch.setattr(voz.requests, "get", lambda *a, **k: RespErr(429, "quota_exceeded"))
    err_cuota = json.loads(pedir("GET", "/api/voces/elevenlabs?forzar=1")[1])
    assert not err_cuota["ok"] and err_cuota["codigo_error"] == "cuota"

    # 4. Seleccionar una voz guarda el voice_id en el proyecto, devuelve el costo estimado y NO ejecuta TTS.
    cab = {"Content-Type": "application/json"}
    est_sel, c_sel = pedir("POST", "/api/voz/seleccionar", cab, json.dumps({
        "proveedor": "elevenlabs",
        "voice_id": "voz_cuenta_123",
        "voz_nombre": "Mateo Documental",
    }).encode())
    assert est_sel == 200
    r_sel = json.loads(c_sel)
    assert r_sel["ok"] and r_sel["voice_id"] == "voz_cuenta_123"
    assert r_sel["estimacion"]["estimable"] and r_sel["estimacion"]["creditos"] == len("frase 1 frase 2")
    assert not tts_llamadas

    # Persiste al recargar el proyecto o pedir /api/estado.
    cargado = produccion.cargar("p-el")
    assert cargado["proveedor_voz"] == "elevenlabs" and cargado["voice_id"] == "voz_cuenta_123"
    assert cargado["voz_elevenlabs_nombre"] == "Mateo Documental"

    # 5. La generación definitiva (POST /api/voz) envía exactamente el voice_id seleccionado al endpoint TTS.
    urls_post = []

    class RespTts:
        status_code = 200
        text = "ok"

        def json(self):
            return {"audio_base64": base64.b64encode(b"mp3-falso").decode(), "alignment": {}}

    def post_tts(url, params=None, headers=None, json=None, timeout=180):
        urls_post.append((url, headers, json))
        return RespTts()

    monkeypatch.setattr(voz, "_elevenlabs", elevenlabs_real)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "xi-clave-prueba")
    monkeypatch.setattr(voz.requests, "post", post_tts)
    monkeypatch.setattr(voz.medios, "ffmpeg", lambda *a: Path(a[-1]).write_bytes(b"RIFF wav"))
    monkeypatch.setattr(voz.medios, "duracion", lambda _p: 3.0)
    monkeypatch.setattr(voz.medios, "silencios", lambda _p: [(1.4, 1.6)])

    voz.locutar(["frase 1", "frase 2"], produccion.carpeta("p-el") / "voz.wav", "elevenlabs",
                produccion="p-el", voice_id=produccion.cargar("p-el")["voice_id"])
    assert urls_post and "/v1/text-to-speech/voz_cuenta_123/with-timestamps" in urls_post[0][0]
    assert urls_post[0][1]["xi-api-key"] == "xi-clave-prueba"


def test_xiaomi_mimo_tts_y_reserva(aislado, monkeypatch):
    """Xiaomi MiMo TTS (mimo-v2.5-tts) genera audio WAV usando rol assistant y sirve de reserva gratuita."""
    import base64
    monkeypatch.setattr(config, "XIAOMIMIMO_API_KEY", "sk-mimo-prueba")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    assert voz.reserva("gemini") is None   # nunca cambia sola de voz
    enviados = []

    class RespMimo:
        status_code = 200
        text = "ok"

        def json(self):
            return {"choices": [{"message": {"role": "assistant", "audio": {"data": base64.b64encode(b"RIFF wav").decode()}}}]}

    monkeypatch.setattr(voz.requests, "post", lambda url, headers=None, json=None, timeout=180: enviados.append((url, json)) or RespMimo())
    monkeypatch.setattr(voz.medios, "ffmpeg", lambda *a: Path(a[-1]).write_bytes(b"RIFF wav"))
    monkeypatch.setattr(voz.medios, "duracion", lambda _p: 2.5)
    monkeypatch.setattr(voz.medios, "silencios", lambda _p: [])
    res = voz.locutar(["Hola desde Xiaomi MiMo."], aislado / "mimo.wav", "mimo", voice_id="Milo")
    assert res["proveedor"] == "mimo" and res["voice_id"] == "Milo"
    assert enviados[0][1]["model"] == "mimo-v2.5-tts"
    assert enviados[0][1]["messages"][-1] == {"role": "assistant", "content": "Hola desde Xiaomi MiMo."}
    assert enviados[0][1]["audio"] == {"voice": "Milo", "format": "wav"}





def test_imagenes_reales_en_grande_y_nunca_miniaturas(aislado, monkeypatch):
    """Las miniaturas de los listados (192×108, 320×180) se cambian por su original y una imagen pequeña se rechaza."""
    import io as _io
    from PIL import Image
    from studio4 import galeria
    assert galeria.grande("https://www.gtabase.com/igallery/gta-6-screens/resized/ocean-drive-468_192x108.jpg") == \
        "https://www.gtabase.com/igallery/gta-6-screens/ocean-drive-468.jpg"
    assert galeria.grande("https://www.gtabase.com/igallery/x/lucia-01-1080.jpg") == "https://www.gtabase.com/igallery/x/lucia-01-1080.jpg"
    html = ('<img src="/igallery/g/resized/vice_192x108.jpg"><img src="/igallery/g/resized/vice_320x180.jpg">'
            '<img src="/images/a/otra-1080.jpg">')
    monkeypatch.setattr(galeria.fuentes, "_get", lambda u: type("R", (), {"text": html})())
    urls = sorted(i["url"] for i in galeria.imagenes_de("https://www.gtabase.com/gta-6/"))
    assert urls == ["https://www.gtabase.com/igallery/g/vice.jpg", "https://www.gtabase.com/images/a/otra-1080.jpg"]

    def imagen(ancho, alto):
        b = _io.BytesIO()
        Image.new("RGB", (ancho, alto), "red").save(b, "JPEG")
        return type("R", (), {"content": b.getvalue()})()
    monkeypatch.setattr(galeria.fuentes, "_get", lambda u: imagen(320, 180))
    with pytest.raises(ValueError, match="pequeña"):
        galeria.toma("https://x/a_320x180.jpg", "https://x/", aislado, 1, 1080, 1920)
    monkeypatch.setattr(galeria.fuentes, "_get", lambda u: imagen(832, 468))
    assert galeria.toma("https://x/a.jpg", "https://x/", aislado, 1, 1080, 1920)["origen"] == "real"


def test_estilos_del_panel_son_los_de_config():
    import re as _re
    js = (pathlib.Path(__file__).resolve().parent.parent / "web" / "panel.js").read_text(encoding="utf-8")
    bloque = js[js.index("const ESTILOS = {"): js.index("};", js.index("const ESTILOS = {"))]
    assert _re.findall(r"^\s+(\w+): \[", bloque, _re.MULTILINE) == list(config.ESTILOS)
    assert config.estilo_valido("viejo") == config.ESTILO_POR_DEFECTO and config.estilo_valido("comic") == "comic"


def test_musica_de_fondo_se_elige_por_nombre_y_baja_con_la_voz(aislado, monkeypatch, tmp_path):
    from studio4 import carpetas
    monkeypatch.setattr(carpetas, "RAIZ_USUARIO", tmp_path)
    assert carpetas.elegir_musica("misterio en GTA") is None   # sin carpeta de música, sin música
    (tmp_path / "Música").mkdir()
    for n in ("alegre_pop.mp3", "tension_misterio.mp3"):
        (tmp_path / "Música" / n).write_bytes(b"x")
    assert carpetas.elegir_musica("Los misterios de Vice City").name == "tension_misterio.mp3"
    extra, filtro = render._mezcla("aresample=48000", 0.15, 30.0, tmp_path / "Música" / "alegre_pop.mp3")
    assert "-stream_loop" in extra and "sidechaincompress" in filtro and "[mus]" in filtro
    assert render._mezcla("aresample=48000", 0.15, 30.0, None)[0] == []
    assert render.musica_de({"edicion": {"musica": False}, "tema": "misterio"}) is None


def test_imagenes_fijas_con_movimiento_distinto(tmp_path):
    """Cada imagen fija se mueve distinto (acercar, derecha, alejar, izquierda) y el vídeo sale con su duración."""
    from PIL import Image
    img = tmp_path / "a.png"
    Image.new("RGB", (640, 360), "blue").save(img)
    filtros = {m: render._zoompan(m, 30, 320, 180) for m in render.MOVIMIENTOS}
    assert len(set(filtros.values())) == 4
    destino = tmp_path / "s.mp4"
    render._segmento_imagen(img, destino, 1.0, 320, 180, movimiento="izquierda")
    assert abs(medios.duracion(destino) - 1.0) < 0.15



def test_voz_de_fal_usa_la_que_eliges(aislado, monkeypatch):
    """«Yo pago, yo escojo»: la voz de ElevenLabs por fal es la elegida, no siempre George; la muestra se graba una vez."""
    pedidos = []
    monkeypatch.setattr(config, "FAL_KEY", "k")
    monkeypatch.setattr(config, "SIN_PAGO", False)
    from studio4 import visuales_api
    monkeypatch.setattr(visuales_api, "_fal", lambda modelo, cuerpo, limite_s=0: pedidos.append(cuerpo) or {"audio": {"url": "u"}})
    monkeypatch.setattr(visuales_api, "_bajar", lambda url, destino: destino.write_bytes(b"mp3"))
    monkeypatch.setattr(voz.medios, "ffmpeg", lambda *a: pathlib.Path(a[-1]).write_bytes(b"wav"))
    voz._fal_tts("Hola", aislado / "a.wav", "", voz="Brian")
    voz._fal_tts("Hola", aislado / "b.wav", "", voz="Inventada")
    assert [c["voice"] for c in pedidos] == ["Brian", voz.VOZ_FAL]
    voz.muestra_fal("Daniel"); voz.muestra_fal("Daniel")
    assert [c["voice"] for c in pedidos][2:] == ["Daniel"]   # la segunda vez se oye la guardada, sin pagar
    with pytest.raises(ValueError):
        voz.muestra_fal("Nadie")


def test_animacion_de_pestanas_y_sus_sonidos(tmp_path):
    """Las tarjetas llevan un whoosh al entrar y un pop en su rótulo; la página lleva las escenas y su tamaño."""
    from studio4 import animacion
    esc = [{"ini": 0.0, "fin": 3.0, "imagenes": [{"src": "a.jpg", "etiqueta": "VICE CITY · 2002", "color": "rosa"},
                                                 {"src": "b.jpg", "etiqueta": "GTA 6", "color": "cian"}]},
           {"ini": 3.0, "fin": 5.0, "titulo": "Leonida", "imagenes": []}]
    assert [m[1] for m in animacion.sonidos_de(esc)] == ["whoosh", "pop", "whoosh", "pop", "whoosh"]
    html = animacion._html(esc, 1080, 1920)
    assert "VICE CITY · 2002" in html and "#ff3ea5" in html and "__W__" not in html and "1920" in html
    fx = animacion.efectos(tmp_path)
    assert all(medios.duracion(f) > 0.05 for f in fx.values())


def test_animacion_puentes_con_el_video(tmp_path):
    """Un panel sale del último fotograma del plano anterior y acaba en el primero del siguiente, sin comprimir;
    la página se diseña a 1920×1080 y la previa la reduce con zoom."""
    from studio4 import animacion, medios, montaje
    video = tmp_path / "v.mp4"
    medios.ffmpeg("-f", "lavfi", "-i", "color=c=red:s=320x180:d=0.5,format=yuv420p", "-f", "lavfi",
                  "-i", "color=c=blue:s=320x180:d=0.5,format=yuv420p", "-filter_complex", "[0][1]concat=n=2:v=1[v]",
                  "-map", "[v]", str(video))
    from PIL import Image
    primero = Image.open(montaje._fotograma(video, tmp_path / "a.png", ultimo=False)).convert("RGB").getpixel((5, 5))
    ultimo = Image.open(montaje._fotograma(video, tmp_path / "b.png", ultimo=True)).convert("RGB").getpixel((5, 5))
    assert primero[0] > 200 > primero[2] and ultimo[2] > 200 > ultimo[0]
    html = animacion._html([{"ini": 0, "fin": 3, "entra": "a.png", "sale": "b.png", "etiqueta": "GTA 6", "color": "rosa",
                             "panel": {"titulo": "Lo que sabemos", "items": ["Vice City"], "iconos": ["mapa"]}}], 960, 540)
    assert '"entra": "a.png"' in html and '"sale": "b.png"' in html and "zoom: 0.5000" in html and "1920" in html
    assert animacion.ACENTO in html and "#ff3ea5" in html
    # sin iconos elegidos, se deducen del texto; si nada encaja, va el número
    assert [animacion.icono_para(t) for t in ("Sale el 19-11-2026", "Vice City", "Lucía y Jason", "Cuatro tornillos", "Hola")] \
        == ["calendario", "mapa", "pareja", "herramienta", ""]
    html = animacion._html([{"ini": 0, "fin": 2, "panel": {"titulo": "T", "items": ["Vice City", "Hola"]}}], 1920, 1080)
    assert '"iconos": ["mapa", "2"]' in html


def test_extractor_detecta_planos_y_corta_sin_audio(tmp_path):
    """Un vídeo con dos planos (rojo y azul): se detecta el corte y el fragmento sale sin audio."""
    from studio4 import extractor
    v = tmp_path / "v.mp4"
    medios.ffmpeg("-f", "lavfi", "-i", "color=red:s=320x180:d=2", "-f", "lavfi", "-i", "color=blue:s=320x180:d=2",
                  "-f", "lavfi", "-i", "sine=d=4", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
                  "-map", "[v]", "-map", "2:a", "-pix_fmt", "yuv420p", str(v))
    pl = extractor.planos(v)
    assert len(pl) == 2 and abs(pl[0][1] - 2.0) < 0.2
    trozo = extractor.cortar(v, pl[1][0], pl[1][1], tmp_path / "t.mp4")
    import subprocess as _sp
    pistas = _sp.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(trozo)],
                     capture_output=True, text=True).stdout.split()
    assert abs(medios.duracion(trozo) - 2.0) < 0.2 and pistas == ["video"]   # fuera su audio
    assert extractor.opciones_ytdlp()["js_runtimes"] == {"node": {}}


def test_clave_gemini_acepta_el_formato_nuevo(aislado, monkeypatch, tmp_path):
    from studio4 import gemini

    class Cliente:
        def __init__(self, api_key):
            self.models = type("M", (), {"generate_content": lambda *a, **k: None})()
    monkeypatch.setattr(gemini.genai, "Client", Cliente)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    gemini.cambiar_clave("AQ." + "Ab8_x" * 8)
    assert config.GEMINI_API_KEY.startswith("AQ.")


# --- Montaje 16:9 (panel nuevo) ----------------------------------------------------------------------------------
def _banco_falso(tmp_path, monkeypatch, fid="fuenteA", n=4):
    """Una fuente en el banco: un vídeo de colores con `n` planos de 2 s, sin descargar nada."""
    from studio4 import extractor
    monkeypatch.setattr(extractor, "CACHE", tmp_path / "_fv")
    extractor.CACHE.mkdir(exist_ok=True)
    colores = ["red", "blue", "green", "yellow", "white", "purple"][:n]
    entradas = sum((["-f", "lavfi", "-i", f"color={c}:s=640x360:d=2:r=30"] for c in colores), [])
    v = extractor.CACHE / f"{fid}_360p.mp4"
    medios.ffmpeg(*entradas, "-filter_complex", "".join(f"[{k}:v]" for k in range(n)) + f"concat=n={n}:v=1[v]",
                  "-map", "[v]", "-pix_fmt", "yuv420p", str(v))
    meta = {"id": fid, "url": "https://example.com/v", "titulo": "Fuente", "nombre": "Fuente", "canal": "",
            "desde": 0.0, "hasta": 2.0 * n, "baja": v.name, "planos": [{"n": k + 1, "ini": 2.0 * k, "fin": 2.0 * k + 2} for k in range(n)]}
    (extractor.CACHE / f"{fid}.banco.json").write_text(json.dumps(meta), encoding="utf-8")
    return v


def test_montaje_parte_el_guion_en_bloques_y_frases():
    from studio4 import montaje
    f = montaje.partir("En The Warriors robar era un trabajo. Sí.\n\nVeinte años después GTA 6 hace algo parecido con el auto entero. Según los avances.")
    assert [(x["n"], x["bloque"]) for x in f] == [(1, 0), (2, 1)]
    assert f[0]["texto"].endswith("Sí.") and "Según los avances." in f[1]["texto"]   # las cortas se juntan
    assert montaje.revisar("GTA 6 tiene autos nuevos.") and not montaje.revisar("Según el tráiler, GTA 6 tiene autos.")


def test_montaje_propone_planos_y_previa_sin_colarse(aislado, tmp_path, monkeypatch):
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch)
    mid = montaje.crear("Prueba", "Primera frase del vídeo con seis palabras. Segunda frase también con seis palabras.")
    montaje.usar_fuente(mid, "fuenteA")
    assert montaje.proponer(mid) == 2
    p = montaje.cargar(mid)
    # el primero y el último de un vídeo corto (clasificación y logo de un tráiler) se saltan
    assert [f["clip"]["plano"] for f in p["frases"]] == [2, 3] and montaje.paso_actual(p) == 4
    montaje.asignar(mid, 2, "fuenteA", 4, rotulo="GTA 6")
    # un plano de 2 s para 3 s de frase: va más lento y no entra el plano siguiente (amarillo → blanco no existe)
    seg = tmp_path / "s.mp4"
    montaje._segmento(tmp_path / "_fv" / "fuenteA_360p.mp4", 0.0, 2.0, 3.0, 320, 180, seg)
    assert abs(medios.duracion(seg) - 3.0) < 0.15
    from PIL import Image
    medios.ffmpeg("-ss", "2.8", "-i", str(seg), "-frames:v", "1", str(tmp_path / "ult.png"))
    r, g, b = Image.open(tmp_path / "ult.png").convert("RGB").getpixel((160, 90))
    assert r > 200 and g < 60 and b < 60   # sigue siendo el plano rojo
    assert montaje._rotulo_png("GTA 6", "#2ee6ff", tmp_path / "r.png", 0.5).exists()


def test_montaje_se_salta_planos_malos_al_proponer(aislado, tmp_path, monkeypatch):
    """Negros, lisos, muy cortos y, en tráilers, la clasificación del principio y el logo del final."""
    from studio4 import montaje, extractor
    _banco_falso(tmp_path, monkeypatch, n=5)
    carpeta_m = extractor.CACHE / "fuenteA_planos"
    carpeta_m.mkdir()
    from PIL import Image, ImageDraw
    for k in range(1, 6):
        im = Image.new("RGB", (320, 180), "black" if k == 3 else "gray")
        if k != 3:
            ImageDraw.Draw(im).rectangle([40, 40, 200, 140], fill="white")
        im.save(carpeta_m / f"{k:03d}.jpg")
    meta = montaje.fuente("fuenteA")
    assert [pl["n"] for pl in meta["planos"] if pl["pobre"]] == [1, 3, 5]
    mid = montaje.crear("P", "Una frase con seis palabras justas aquí. Otra frase con seis palabras justas aquí.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.proponer(mid)
    assert [f["clip"]["plano"] for f in montaje.cargar(mid)["frases"]] == [2, 4]


def test_logo_del_canal_en_circulo_transparente(aislado, monkeypatch, tmp_path):
    from PIL import Image
    from studio4 import montaje
    monkeypatch.setattr(config, "PRODUCCIONES", tmp_path)
    (tmp_path / "_canales" / "c").mkdir(parents=True)
    Image.new("RGB", (200, 200), "black").save(tmp_path / "_canales" / "c" / "logo.png")
    r = Image.open(montaje.logo_de("c"))
    assert r.mode == "RGBA" and r.getpixel((2, 2))[3] == 0 and r.getpixel((100, 100))[3] == 255
    assert montaje.logo_de("sin-logo") is None



def test_montaje_libera_solo_temporales(aislado, monkeypatch, tmp_path):
    from studio4 import montaje
    base = montaje.raiz() / "v1" / "render"
    base.mkdir(parents=True)
    for n in ("cuerpo.mp4", "subs.ass", "s001.mp4", "t002.jpg"):
        (base / n).write_bytes(b"x" * 1000)
    (montaje.raiz() / "v1" / "render_previa").mkdir()
    (montaje.raiz() / "v1" / "render_previa" / "s.mp4").write_bytes(b"x" * 500)
    (montaje.raiz() / "v1" / "final_16x9.mp4").write_bytes(b"x")
    assert montaje.espacio()["liberable"] == 2500
    assert montaje.liberar() == 2500
    assert sorted(f.name for f in base.iterdir()) == ["cuerpo.mp4", "subs.ass"]
    assert (montaje.raiz() / "v1" / "final_16x9.mp4").exists() and not (montaje.raiz() / "v1" / "render_previa").exists()


def test_descargador_dice_si_esta_viejo():
    from studio4 import extractor
    d = extractor.descargador()
    assert d["version"] and isinstance(d["viejo"], bool) and d["dias"] >= 0


def test_imagen_de_wikipedia_de_una_palabra_solo_si_es_un_videojuego(aislado, monkeypatch):
    from studio4 import ideas

    class R:
        def __init__(self, p):
            self.p = p

        def json(self):
            return {"query": {"pages": {"0": self.p}}}
    monkeypatch.setattr(ideas.fuentes, "claves", lambda idea, p: ["ghost leviathan"])
    libro = {"index": 1, "title": "Leviathan (Hobbes book)", "description": "1651 book by Thomas Hobbes", "thumbnail": {"source": "https://x/l.jpg"}}
    monkeypatch.setattr(ideas.requests, "get", lambda *a, **k: R(libro))
    assert ideas._de_wikipedia("El Ghost Leviathan de Subnautica") == {}
    juego = {"index": 1, "title": "Leviathan", "description": "2019 video game", "thumbnail": {"source": "https://x/j.jpg"}}
    monkeypatch.setattr(ideas.requests, "get", lambda *a, **k: R(juego))
    assert ideas._de_wikipedia("El Ghost Leviathan de Subnautica")["url"] == "https://x/j.jpg"


def test_linea_de_tiempo_corregida_valida_y_detecta_errores(aislado, tmp_path, monkeypatch):
    from studio4 import linea, montaje
    # el modelo del autor, corregido: datos generales, ids, in/out de la fuente, transform con unidades, estilo
    tl = {"version": 1, "fps": 30, "width": 1920, "height": 1080, "duration": 5.0, "tracks": [
        {"id": "video-track-1", "type": "video", "clips": [{"id": "c1", "start": 0, "end": 5, "source": "clip1.mp4", "in": 12.0, "out": 17.0,
         "speed": 1.0, "transform": {"x": 0.5, "y": 0.5, "scale": 1, "rotation": 0, "opacity": 1, "anchor": "center"}}]},
        {"id": "text-track-1", "type": "text", "clips": [{"id": "t1", "start": 1, "end": 4, "content": "Hola",
         "style": {"font": "Arial Bold", "size": 46, "color": "#ff3ea5", "position": "bottom-left"},
         "animation": {"in": "fade", "out": "fade", "duration": 0.3}}]}]}
    assert linea.validar(tl) == []
    tl["tracks"][0]["clips"].append({"id": "c2", "start": 4, "end": 6, "source": "x.mp4", "in": 0, "out": 2})
    errores = linea.validar(tl)
    assert any("se pisa" in e for e in errores) and any("después del final" in e for e in errores)
    # la de un vídeo del panel
    _banco_falso(tmp_path, monkeypatch)
    mid = montaje.crear("P", "Una frase con seis palabras justas aquí.\n\nOtra frase con seis palabras justas aquí.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.proponer(mid)
    montaje.asignar(mid, 1, rotulo="GTA 6")
    p = montaje.cargar(mid)
    t2 = linea.desde_montaje(p, {"fuenteA": montaje.fuente("fuenteA")})
    assert linea.validar(t2) == []
    v = t2["tracks"][0]["clips"]
    assert [c["id"] for c in v] == ["frase-1", "frase-2"] and "transitionIn" in v[1] and v[0]["in"] == 2.0
    assert t2["tracks"][2]["clips"][0]["content"] == "GTA 6"


def test_panel_nuevo_no_carga_el_estudio_antiguo():
    """Muro entre los dos paneles: el panel nuevo (montaje, línea de tiempo y sus rutas) no arrastra el código del
    estudio antiguo. Si alguien lo mezcla, esta prueba falla."""
    import subprocess as _sp
    import sys as _sys
    codigo = ("import sys; import studio4.rutas_montaje; "
              "print(' '.join(sorted(m.split('.')[1] for m in sys.modules if m.startswith('studio4.'))))")
    cargados = set(_sp.run([_sys.executable, "-c", codigo], capture_output=True, text=True,
                           cwd=str(pathlib.Path(__file__).resolve().parent.parent)).stdout.split())
    antiguos = {"produccion", "flow", "director", "render", "entregas", "miniaturas", "referencias", "visuales_api", "tarjetas", "importar"}
    assert cargados and not (cargados & antiguos), cargados & antiguos



def test_montaje_voz_elegible_y_conexiones_sin_claves(aislado, monkeypatch):
    from studio4 import montaje
    mid = montaje.crear("P", "Una frase con seis palabras justas aquí. Otra frase con seis palabras justas aquí.")
    assert montaje.coste_voz(montaje.cargar(mid)) == 0   # Google, gratis
    montaje.elegir_voz(mid, "fal", "Brian")
    p = montaje.cargar(mid)
    assert p["voz_proveedor"] == "fal" and montaje.coste_voz(p) > 0
    with pytest.raises(ValueError):
        montaje.elegir_voz(mid, "fal", "Inventada")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "AIza-secreta")
    texto = json.dumps(montaje.conexiones())
    assert "secreta" not in texto and "Google (Gemini)" in texto


def test_montaje_solo_corta_a_planos_elegidos_y_en_una_pausa():
    """Nunca se encadena un plano que nadie eligió (el siguiente del tráiler es otra escena): con un solo plano la frase
    es un plano. Con planos extra elegidos, el corte cae en la pausa entre palabras más cercana."""
    from studio4 import montaje
    meta = {"planos": [{"n": 1, "ini": 0, "fin": 3}, {"n": 2, "ini": 3, "fin": 3.5}, {"n": 3, "ini": 5, "fin": 8}]}
    assert [(c["n"], d) for c, d in montaje._cadena(meta, {"plano": 1}, 6.0)] == [(1, 6.0)]
    cadena = montaje._cadena(meta, {"plano": 1, "mas": [3]}, 6.0, pausas=[1.1, 2.7, 4.4])
    assert [c["n"] for c, _ in cadena] == [1, 3] and abs(cadena[0][1] - 2.7) < 1e-9
    assert abs(sum(d for _, d in cadena) - 6.0) < 1e-9


def test_montaje_parte_oraciones_largas_en_la_coma():
    from studio4 import montaje
    o = ("Durante veinte años, en GTA, robar un auto estacionado era casi magia: un botón, la puerta se abría "
         "y el motor arrancaba.")
    partes = montaje._trocear(o)
    assert len(partes) == 2 and partes[0].endswith("magia:") and " ".join(partes) == o
    assert montaje._trocear("Una frase corta y normal.") == ["Una frase corta y normal."]
    frases = montaje.partir(o + " Y no es algo que pase seguido.\n\nOtro bloque aquí con varias palabras.")
    assert [montaje._pausa(frases, k) for k in range(len(frases))] == [0.0, montaje.PAUSA_FRASE, montaje.PAUSA_BLOQUE, 0.0]


def test_montaje_la_voz_respira_entre_frases(tmp_path):
    """Se mete silencio entre oraciones y entre bloques; las palabras se mueven con su frase."""
    from studio4 import medios, montaje
    wav = tmp_path / "voz.wav"
    # dos oraciones con un silencio de verdad entre ellas (1,9-2,1 s), como una voz
    medios.ffmpeg("-f", "lavfi", "-i", "aevalsrc='0.5*sin(2*PI*300*t)*(lt(t,1.9)+gte(t,2.1))':d=4:s=24000",
                  "-ac", "1", str(wav))
    e = montaje.ENTRADA
    frases = [{"bloque": 0, "texto": "Uno dos tres."}, {"bloque": 1, "texto": "Cuatro cinco seis."}]
    # «cuatro» viene con su inicio algo adelantado (1,95 s, antes del silencio): va con su frase por su centro
    palabras = [{"palabra": "uno", "ini": e + 0.1, "fin": e + 0.5}, {"palabra": "cuatro", "ini": e + 1.95, "fin": e + 2.6}]
    tiempos, pal = montaje._respirar(wav, [(e, e + 1.9), (e + 2.1, e + 4)], palabras, frases, tmp_path / "p.wav")
    assert abs(medios.duracion(tmp_path / "p.wav") - (4 + montaje.PAUSA_BLOQUE)) < 0.05
    assert tiempos[0] == (e, e + 1.9) and abs(tiempos[1][0] - (e + 2.1 + montaje.PAUSA_BLOQUE)) < 1e-9
    assert pal[0]["ini"] == e + 0.1 and abs(pal[1]["ini"] - (e + 1.95 + montaje.PAUSA_BLOQUE)) < 1e-9


def test_montaje_arranque_plano_y_cola_son_el_mismo_movimiento(tmp_path):
    """Arranque (tarjeta), plano (pantalla completa) y cola (tarjeta) salen de una sola pasada y seguidos: el último
    cuadro de uno y el primero del siguiente son cuadros consecutivos del mismo plano."""
    from studio4 import medios, montaje
    fuente = tmp_path / "f.mp4"
    medios.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=4", "-pix_fmt", "yuv420p", str(fuente))
    a, s, c = tmp_path / "a.mp4", tmp_path / "s.mp4", tmp_path / "c.mp4"
    montaje._segmentos(fuente, 0.5, 3.8, [(0.8, a), (1.5, s), (0.8, c)], 320, 180)
    assert [round(medios.duracion(x), 1) for x in (a, s, c)] == [0.8, 1.5, 0.8]
    unido = tmp_path / "u.mp4"
    lista = tmp_path / "l.txt"
    lista.write_text("".join(f"file '{x.as_posix()}'\n" for x in (a, s, c)), encoding="utf-8")
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(unido))
    log = medios.ffmpeg("-i", str(unido), "-vf", "freezedetect=n=0.001:d=0.05", "-f", "null", "-")
    assert "freeze_start" not in log   # ni cuadros repetidos en las uniones


def test_montaje_corta_la_voz_en_su_silencio():
    """La pausa se mete en el silencio real entre dos oraciones, no en el punto medio aproximado (que caía a mitad de
    palabra y se oía como un corte del guion)."""
    import array
    from studio4 import montaje
    hz = 16000
    voz = array.array("h", [8000 if (k // 40) % 2 else -8000 for k in range(hz * 2)])   # 2 s de «voz»
    for k in range(int(1.30 * hz), int(1.45 * hz)):   # el silencio de verdad está en 1,30-1,45 s
        voz[k] = 0
    assert 1.30 <= montaje._silencio_cerca(voz, hz, 1.0) <= 1.45


def test_subtitulos_no_dejan_palabras_colgadas():
    """«VUELVE A VICE CITY CON» no: una línea no acaba en «con», «no ha»… ni parte «Vice | City»."""
    from studio4 import subtitulos

    def w(t):
        return [{"palabra": x, "ini": k * 0.32, "fin": k * 0.32 + 0.3} for k, x in enumerate(t.split())]
    lineas = lambda t: [" ".join(p["palabra"] for p in li) for li in subtitulos._lineas(w(t), 5)]  # noqa: E731
    assert lineas("Y Rockstar todavía no ha contado todo.") == ["Y Rockstar todavía", "no ha contado todo."]
    assert all(not li.endswith((" a", " con", " Vice")) for li in lineas("GTA 6 vuelve a Vice City con más vida que nunca."))


def test_sonido_efectos_cama_y_master(tmp_path):
    import re
    from studio4 import sonido
    fx = sonido.biblioteca(tmp_path / "_fx")
    assert set(fx) == {"impacto", "subida", "whoosh", "cruce", "pop"} and all(f.exists() for f in fx.values())
    assert abs(medios.duracion(sonido.cama(6, tmp_path / "c.wav")) - 6) < 0.1
    assert abs(medios.duracion(sonido.pista([(1, "impacto", 1), (-1, "subida", 1)], 5, tmp_path / "p.wav")) - 5) < 0.1
    # el volumen final se mide y se aplica parejo: −11 LUFS sin compresores que bombeen
    mezcla = tmp_path / "m.wav"
    medios.ffmpeg("-f", "lavfi", "-i", "sine=f=220:d=6", "-af", "volume=0.05", "-ac", "2", str(mezcla))
    hecho = sonido.masterizar(mezcla, tmp_path / "f.wav")
    medida = medios.ffmpeg("-i", str(hecho), "-af", "ebur128", "-f", "null", "-")
    assert abs(float(re.findall(r"I:\s+(-?[\d.]+) LUFS", medida)[-1]) + 11) < 1.0


def test_musica_cataloga_etiqueta_y_elige_por_animo(aislado):
    """Las pistas de la Biblioteca de audio se catalogan solas (título, artista, volumen) y la automática elige
    por el ánimo del guion; los créditos llevan la atribución si la pista la pide."""
    from studio4 import musica
    carpeta = musica.carpeta()
    medios.ffmpeg("-f", "lavfi", "-i", "sine=f=220:d=2", "-af", "volume=0.05", str(carpeta / "Noche en Coney - Artista Uno.mp3"))
    medios.ffmpeg("-f", "lavfi", "-i", "sine=f=330:d=2", "-af", "volume=7", str(carpeta / "Sol de verano.mp3"))
    pistas = {p["archivo"]: p for p in musica.catalogo()}
    noche = pistas["Noche en Coney - Artista Uno.mp3"]
    assert (noche["titulo"], noche["artista"]) == ("Noche en Coney", "Artista Uno") and noche["licencia"] == musica.LICENCIA
    assert musica.ganancia(noche) > musica.ganancia(pistas["Sol de verano.mp3"])   # la floja se sube más
    musica.etiquetar("Noche en Coney - Artista Uno.mp3", animo=["tensión", "oscura", "inventado"], atribucion="Music by Uno")
    musica.etiquetar("Sol de verano.mp3", animo=["alegre"])
    guion = {"titulo": "Robar de noche", "guion": "La policía te persigue por la calle de noche: robar tenía riesgo."}
    assert musica.elegir(guion)["archivo"] == "Noche en Coney - Artista Uno.mp3"
    assert musica.elegir({**guion, "musica": "cama"}) is None and musica.elegir({**guion, "musica": "nada"}) is None
    assert musica.elegir({**guion, "musica": "Sol de verano.mp3"})["archivo"] == "Sol de verano.mp3"
    assert musica.credito(musica.elegir(guion)) == "Music by Uno"
    assert musica.ruta("../.env") is None and musica.ruta("Sol de verano.mp3")
    (carpeta / "Sol de verano.mp3").unlink()
    assert [p["archivo"] for p in musica.catalogo()] == ["Noche en Coney - Artista Uno.mp3"]   # se olvida la borrada


def test_montaje_rehace_solo_lo_que_cambia(aislado, tmp_path, monkeypatch):
    """Volver a montar sin cambios no monta ningún plano; cambiar el plano de una frase monta solo esa frase."""
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch)
    mid = montaje.crear("Prueba", "Primera frase del vídeo con seis palabras. Segunda frase también con seis palabras.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.asignar(mid, 1, "fuenteA", 2)
    montaje.asignar(mid, 2, "fuenteA", 3)
    llamadas, original = [], montaje._segmentos

    def contar(*a, **k):
        llamadas.append(a[1])
        return original(*a, **k)
    monkeypatch.setattr(montaje, "_segmentos", contar)
    montaje._render(mid, False, lambda *_: None)
    assert len(llamadas) == 2
    llamadas.clear()
    montaje._render(mid, False, lambda *_: None)
    assert llamadas == []   # nada cambió: nada se vuelve a montar
    montaje.asignar(mid, 2, "fuenteA", 4)
    llamadas.clear()
    montaje._render(mid, False, lambda *_: None)
    assert llamadas == [6.0]   # solo la frase 2, con su plano nuevo (el 4 empieza en el segundo 6)
    assert medios.duracion(montaje.carpeta(mid) / "previa.mp4") > 3
    assert len(list((montaje.carpeta(mid) / "cache_previa").iterdir())) == 2   # el trozo viejo se borró


def test_montaje_resumen_storyboard_srt_y_automatico_con_guardas(aislado, tmp_path, monkeypatch):
    """El resumen cuenta escenas y capítulos; el storyboard sale en segundos; el .srt tiene sus tiempos; el modo
    automático no arranca con frases sin imagen ni con una voz de pago sin el sí del autor."""
    from studio4 import montaje, subtitulos
    _banco_falso(tmp_path, monkeypatch)
    mid = montaje.crear("Prueba", "Primera frase del vídeo con seis palabras.\n\nSegunda frase también con seis palabras.")
    montaje.usar_fuente(mid, "fuenteA")
    r = montaje.resumen(montaje.cargar(mid))
    assert (r["frases"], r["capitulos"], r["con_imagen"]) == (2, 2, 0) and r["estimada"] and r["duracion"] > 3
    with pytest.raises(ValueError):
        montaje.automatico(mid)   # faltan imágenes
    montaje.asignar(mid, 1, "fuenteA", 2)
    montaje.asignar(mid, 2, "fuenteA", 3, panel=None)
    montaje.asignar(mid, 2, "", 0, panel={"titulo": "Datos", "items": ["Vice City"]})
    assert montaje.storyboard(mid).stat().st_size > 10_000
    monkeypatch.setattr(montaje, "coste_voz", lambda p: 0.4)
    with pytest.raises(ValueError, match="de pago"):
        montaje.automatico(mid)
    assert montaje.tramo_short({"voz": {"pausas": {"tiempos": [(0.25, 30), (30.3, 50), (50.3, 70)]}}, "frases": []}) == (0.0, 50.4)
    srt = subtitulos.srt([{"palabra": w, "ini": k * 0.5, "fin": k * 0.5 + 0.4} for k, w in enumerate("Hola a todos. Esto es FourLevel.".split())],
                         tmp_path / "s.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,000 --> ") and "Hola a todos." in srt and "\n2\n" in srt


def test_escaleta_para_flow_y_paquete_de_vuelta(aislado, tmp_path, monkeypatch):
    """La escaleta reparte cada frase en escenas de 4/6/8 s y recuerda qué escena es de qué frase; el paquete
    que exporta la herramienta de Flow (ZIP con escena_NNN.mp4 + escenas.json) entra como fuente y cada frase
    recibe sus escenas."""
    import zipfile
    from studio4 import escaleta, extractor, montaje
    monkeypatch.setattr(extractor, "CACHE", tmp_path / "_fv")
    assert escaleta.tomas(3.0) == [4] and escaleta.tomas(5.2) == [6] and escaleta.tomas(9.5) == [6, 6] and escaleta.tomas(16) == [8, 8]
    mid = montaje.crear("El faro", "Elena mira el mar desde el faro con miedo. Mateo llega con las cartas viejas del abuelo "
                                   "y le cuenta todo lo que sabe del naufragio, sin dejarse ni un solo detalle de aquella noche.")
    e = escaleta.exportar(mid, con_ia=False)   # sin red en las pruebas: sin personajes, pero con sus escenas
    assert e["escaleta_studio4"] == 1 and e["formato"] == "16:9" and all(x["duracion"] in (4, 6, 8) for x in e["escenas"])
    relacion = montaje.cargar(mid)["escaleta"]["escenas"]
    assert relacion[0]["frase"] == 1 and relacion[-1]["frase"] == len(montaje.cargar(mid)["frases"])
    paquete = tmp_path / "flow.zip"
    with zipfile.ZipFile(paquete, "w") as z:
        for r in relacion:
            clip = tmp_path / f"escena_{r['n']:03d}.mp4"
            medios.ffmpeg("-f", "lavfi", "-i", f"color=c={'red' if r['frase'] == 1 else 'blue'}:s=640x360:d=1:r=24",
                          "-pix_fmt", "yuv420p", str(clip))
            z.write(clip, f"escenas/{clip.name}")
        z.writestr("escenas.json", json.dumps({"escaleta_studio4": 1, "escenas": e["escenas"]}))
    r = escaleta.importar(mid, paquete)
    p = montaje.cargar(mid)
    assert r["escenas"] == len(relacion) and r["fuente"] in p["fuentes"] and p["ia"]
    assert all(f.get("clip", {}).get("fuente") == r["fuente"] for f in p["frases"])
    meta = montaje.fuente(r["fuente"])
    assert (extractor.CACHE / meta["alta"]).exists() and len(meta["planos"]) == len(relacion)
    assert montaje.storyboard(mid).exists()


def test_montaje_imagen_en_una_frase(aislado, tmp_path, monkeypatch):
    """Una frase puede llevar una imagen (archivo o enlace): se guarda en el vídeo, sale en el storyboard y en el
    montaje se mueve despacio; si no es apaisada, va como tarjeta sobre la misma imagen desenfocada."""
    import base64
    import io
    from PIL import Image
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch)
    mid = montaje.crear("Prueba", "Primera frase del vídeo con seis palabras. Segunda frase también con seis palabras.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.asignar(mid, 1, "fuenteA", 2)
    caja = io.BytesIO()
    Image.new("RGB", (600, 900), (200, 30, 30)).save(caja, "PNG")   # vertical, como la caja de un juego
    img = montaje.poner_imagen(mid, 2, datos_b64="data:image/png;base64," + base64.b64encode(caja.getvalue()).decode(), credito="Arte oficial")
    p = montaje.cargar(mid)
    assert p["frases"][1]["imagen"]["archivo"] == img["archivo"] and montaje.paso_actual(p) == 4
    with pytest.raises(ValueError):
        montaje.poner_imagen(mid, 2, url="no-es-un-enlace")
    seg = tmp_path / "img.mp4"
    montaje._segmento_imagen(montaje.carpeta_imagenes(mid) / img["archivo"], 2.0, 320, 180, seg)
    assert abs(medios.duracion(seg) - 2.0) < 0.1
    medios.ffmpeg("-ss", "1", "-i", str(seg), "-frames:v", "1", str(tmp_path / "f.png"))
    borde = Image.open(tmp_path / "f.png").convert("RGB").getpixel((5, 90))
    assert borde != (0, 0, 0) and borde[0] > borde[2]   # sin bandas negras: el fondo es la misma imagen desenfocada
    assert montaje.storyboard(mid).exists()
    montaje.asignar(mid, 2, "fuenteA", 3)   # un plano quita la imagen
    assert "imagen" not in montaje.cargar(mid)["frases"][1]


def test_enlace_de_la_herramienta_de_flow(aislado):
    from studio4 import escaleta
    assert escaleta.herramienta() == ""
    assert escaleta.guardar_herramienta(" https://labs.google/fx/tools/flow/tool/abc ") == "https://labs.google/fx/tools/flow/tool/abc"
    assert escaleta.herramienta() == "https://labs.google/fx/tools/flow/tool/abc"
    with pytest.raises(ValueError):
        escaleta.guardar_herramienta("https://otra-web.com/x")


def test_material_solo_original_y_nunca_el_trabajo_de_otros_creadores():
    from studio4 import material
    bien = [("Grand Theft Auto VI Trailer 2", "Rockstar Games", 167),
            ("The Warriors - FULL GAME - No Commentary", "SourceSpy91", 25399),
            ("Grand Theft Auto VI - Tráiler de lanzamiento", "Rockstar Games España", 91),
            ("GTA San Andreas Burger Shot gameplay sin comentarios", "Alguien", 600)]
    mal = [("MI REACCIÓN AL TRÁILER 2 DE GTA VI", "Otro", 12343), ("500 DETALLES de GTA 6 gameplay", "Otro", 900),
           ("GTA 6 trailer analysis", "Otro", 700), ("The Rockstar Classic That Started It All For Me: The Warriors gameplay", "Otro", 2540),
           ("GTA 6 trailer #shorts", "Otro", 20), ("This is what happens if Arthur drinks 100 Hair Tonics before a Cutscene", "Otro", 90), ("Mi vlog de hoy", "Otro", 600), ("Top 10 GTA 6 trailer secrets", "Otro", 600)]
    assert all(material.apto({"titulo": t, "canal": c, "duracion": d}) for t, c, d in bien)
    assert not any(material.apto({"titulo": t, "canal": c, "duracion": d}) for t, c, d in mal)
    oficial = material.puntos({"titulo": "Grand Theft Auto V: The Official Trailer", "canal": "Rockstar Games"})
    movil = material.puntos({"titulo": "GTA San Andreas Mobile gameplay", "canal": "Alguien"})
    assert oficial > movil


def test_material_inventario_y_lo_que_recibe_el_guionista(monkeypatch):
    from studio4 import gemini, material
    monkeypatch.setattr(gemini, "generar", lambda *a, **k: '{"escenas": [{"juego": "GTA San Andreas", "que": "Burger Shot",'
                        ' "busqueda": "sa burger"}, {"juego": "GTA V", "que": "tráiler", "busqueda": "gta v"},'
                        ' {"juego": "Inventado", "que": "nada", "busqueda": "nada"}]}')
    res = {"sa burger": [{"id": "a1", "url": "u1", "titulo": "GTA San Andreas Burger Shot gameplay no commentary", "canal": "X", "duracion": 600},
                         {"id": "a2", "url": "u2", "titulo": "Burger Shot REACCIÓN", "canal": "Y", "duracion": 600}],
           "gta v": [{"id": "a1", "url": "u1", "titulo": "GTA San Andreas Burger Shot gameplay no commentary", "canal": "X", "duracion": 600},
                     {"id": "b1", "url": "u3", "titulo": "Grand Theft Auto V: The Official Trailer", "canal": "Rockstar Games", "duracion": 61}],
           "nada": []}
    monkeypatch.setattr(material, "buscar", lambda q, n=8: res[q])
    inv = material.inventario("Burger Shot en GTA")
    assert [[v["id"] for v in e["videos"]] for e in inv] == [["a1"], ["b1"], []]   # sin reacciones ni repetidos
    texto = material.para_guion(inv)
    assert texto.startswith("MATERIAL QUE EXISTE") and "Burger Shot" in texto and "Official Trailer" in texto
    assert "Inventado" not in texto and "REACCIÓN" not in texto
    monkeypatch.setattr(gemini, "generar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin cupo")))
    assert all(e["busqueda"].startswith("tema") for e in material.escenas("tema x"))   # sin Gemini, busca el tema tal cual


def test_montaje_busca_material_del_tema_para_anadirlo(aislado, monkeypatch):
    from studio4 import material, montaje
    monkeypatch.setattr(material, "inventario", lambda tema, guion="", produccion="": [
        {"juego": "GTA V", "que": tema, "busqueda": "q", "videos": [{"id": "b1", "url": "u", "titulo": "t", "canal": "c", "duracion": 61}]}])
    mid = montaje.crear("Burger Shot", "Una frase con seis palabras justas aquí.")
    montaje.buscar_material(mid)
    fin = _time.time() + 10
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _time.time() < fin:
        _time.sleep(0.05)
    p = montaje.cargar(mid)
    assert not p["trabajo"]["error"] and p["material_sugerido"][0]["videos"][0]["id"] == "b1"
    assert "sugeridoHTML" in (config.RAIZ / "web" / "montaje.js").read_text(encoding="utf-8")


def test_panel_no_se_redibuja_entero_con_cada_aviso_de_progreso():
    """Los avisos de progreso cambian «actualizado»; el panel no debe volver a pintar imágenes y vídeos por eso."""
    js = (config.RAIZ / "web" / "montaje.js").read_text(encoding="utf-8")
    assert "const { trabajo, actualizado, ...resto } = datos.video;" in js


def test_mientras_se_monta_el_portatil_no_entra_en_espera(monkeypatch):
    """Espera moderna: con la pantalla apagada el PC se dormía y el render se congelaba horas."""
    import ctypes
    import os as _os
    from studio4 import montaje
    if _os.name != "nt":
        pytest.skip("solo Windows")
    pedidos = []
    monkeypatch.setattr(ctypes.windll.kernel32, "SetThreadExecutionState", lambda f: pedidos.append(f) or 1)
    montaje._despierto(True)
    montaje._despierto(False)
    assert pedidos == [0x80000003, 0x80000000]   # sistema y pantalla mientras trabaja; nada al acabar


def test_plantilla_de_detalles_completa():
    """El desmontaje del vídeo de referencia se guarda como plantilla para sacar cortos: todas las medidas presentes."""
    d = json.loads((config.RAIZ / "studio4" / "plantillas" / "detalles.json").read_text(encoding="utf-8"))
    for clave in ("unidad", "ritmo", "congelados", "zoom", "senalar", "voz", "sonido", "subtitulos"):
        assert clave in d, clave
    assert 20 <= d["unidad"]["segundos_detalle_contado"][0] < d["unidad"]["segundos_detalle_contado"][1] <= 60


def test_servidor_manda_los_videos_por_trozos(servidor):
    """Un <video> pide «bytes=0-»: mandar el archivo entero atascaba la conexión y el panel se quedaba a medio cargar."""
    import servidor as srv
    from studio4 import montaje
    pedir, _ = servidor
    mid = montaje.crear("P", "Una frase con seis palabras justas aquí.")
    (montaje.carpeta(mid) / "previa.mp4").write_bytes(b"\0" * (srv.TROZO * 2 + 10))
    estado, cuerpo = pedir("GET", f"/m/{mid}/previa.mp4", {"Range": "bytes=0-"})
    assert estado == 206 and len(cuerpo) == srv.TROZO
    estado, cuerpo = pedir("GET", f"/m/{mid}/previa.mp4", {"Range": f"bytes={srv.TROZO * 2}-"})
    assert estado == 206 and len(cuerpo) == 10   # el último trozo, completo


def test_linea_de_tiempo_no_pide_planos_de_las_frases_con_imagen():
    """Las frases con imagen pedían /fv/imagen:…/undefined.jpg (404 en cada carga del paso Previa)."""
    js = (config.RAIZ / "web" / "montaje.js").read_text(encoding="utf-8")
    assert 'fid.startsWith("imagen:")' in js


WIKI_PRUEBA = """{{Title|Trailers}}
==Trailer 9==
The song used in the trailer is "[[Cancion X]]" by [[Alguien]].
{{YouTube|AAAAAAAAAAA|align=center}}
===Transcript===
{{Scriptbox
|
{{Line
|time       = 0:00
|background = The [[Rockstar Games]] logo appears.
|image      = [[File:X.png|thumb|center|270px]]
|name       =
|dialogue   =
}}
{{Line
|time       = 0:03
|background = A [[Sandking XT]] tows a [[Seashark (second generation)|Seashark]] into [[Key Lento]].
|name       = [[Jason Duval|Jason]]
|dialogue   = I got in some ''trouble''.
}}
{{Line
|time       = 0:05
|background = Lucia in [[Leonida Penitentiary]]<br>looking out.
|name       = Lucia
|dialogue   =
}}
}}
==See Also==
"""


def test_escenas_de_la_wiki_por_segundo_y_plano(monkeypatch):
    """La transcripción de la wiki → escenas con su segundo, texto limpio y el plano de la fuente que las enseña."""
    from studio4 import escenas
    d = escenas.parsear(WIKI_PRUEBA)
    tr = d["AAAAAAAAAAA"]
    assert tr["cancion"] == "Cancion X" and [e["t"] for e in tr["escenas"]] == [0, 3, 5]
    e = tr["escenas"][1]
    assert e["que"] == "A Sandking XT tows a Seashark into Key Lento." and e["quien"] == "Jason" and e["dice"] == "I got in some trouble."
    assert e["fin"] == 5 and tr["escenas"][2]["que"] == "Lucia in Leonida Penitentiary looking out."
    planos = [{"n": 1, "ini": 0, "fin": 2.5, "pobre": True}, {"n": 2, "ini": 2.5, "fin": 4.0}, {"n": 3, "ini": 4.0, "fin": 9.0}]
    meta = {"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "desde": 0, "hasta": 9, "planos": planos}
    assert [x["plano"] for x in escenas.de_fuente(meta, d)] == [2, 2, 3]   # el logo (pobre) salta al primer plano bueno
    tramo = {**meta, "desde": 3.0, "planos": [{"n": 1, "ini": 0, "fin": 1.5}, {"n": 2, "ini": 1.5, "fin": 6}]}
    assert [(x["t"], x["plano"]) for x in escenas.de_fuente(tramo, d)] == [(0, 1), (2, 2)]   # un tramo empieza en 0
    monkeypatch.setattr(escenas, "indice", lambda red=True: d)
    texto = escenas.para_guion([{**meta, "nombre": "Tráiler 9"}])
    assert "[0:03] A Sandking XT" in texto and "Jason: «I got in some trouble.»" in texto and "nunca copies" in texto


def test_planos_por_escenas_y_credito(aislado, tmp_path, monkeypatch):
    import time as _t
    from studio4 import escenas, extractor, gemini, montaje
    _banco_falso(tmp_path, monkeypatch, n=6)
    meta = json.loads((extractor.CACHE / "fuenteA.banco.json").read_text(encoding="utf-8"))
    meta["url"] = "https://www.youtube.com/watch?v=AAAAAAAAAAA"
    (extractor.CACHE / "fuenteA.banco.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(escenas, "indice", lambda red=True: escenas.parsear(WIKI_PRUEBA))
    monkeypatch.setattr(gemini, "generar", lambda *a, **k: '{"asignaciones": [{"n": 1, "escena": "E3"}, {"n": 2, "escena": "E2"}]}')
    mid = montaje.crear("P", "Lucía mira por la ventana de la cárcel. Jason llega remolcando una moto de agua.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.planos_por_escenas(mid)
    fin = _t.time() + 10
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _t.time() < fin:
        _t.sleep(0.05)
    p = montaje.cargar(mid)
    assert not p["trabajo"]["error"], p["trabajo"]["error"]
    assert [f["clip"]["plano"] for f in p["frases"]] == [3, 2] and p["escenas_wiki"]   # escena 0:05 → plano 3; 0:03 → 2
    base = tmp_path / "c"
    base.mkdir()
    montaje._creditos(base, p, [])
    assert "GTA Wiki" in (base / "Fuentes y créditos.txt").read_text(encoding="utf-8")


RSS_PRUEBA = """<rss><channel><title>Feed X</title>
<item><title>GTA 6 gets a new trailer and fans love it</title></item>
<item><title>Call of Duty Modern Warfare 4 release date leaked</title></item>
<item><title>Mass Effect 5 is in development at BioWare</title></item>
</channel></rss>"""


def test_radar_detecta_juegos_en_varias_fuentes_sin_partir_nombres(monkeypatch):
    from studio4 import radar
    feeds = {"a": RSS_PRUEBA, "b": RSS_PRUEBA.replace("Feed X", "Feed Y"),
             "c": "<rss><channel><title>Z</title><item><title>GTA 6 is the biggest game ever</title></item></channel></rss>"}
    cfg = {**radar.POR_DEFECTO, "rss": [{"id": k, "nombre": k, "url": k} for k in feeds], "wiki_api": ""}
    monkeypatch.setattr(radar, "_titulares_rss", lambda f, m: radar.re.findall(r"<title>(.*?)</title>", feeds[f["id"]])[1:])
    monkeypatch.setattr(radar, "_titulos_wiki", lambda c: [])
    s = radar.escanear(cfg)
    temas = [x["tema"] for x in s]
    assert "GTA 6" == s[0]["tema"] and s[0]["caliente"] and s[0]["n_fuentes"] == 3   # en las 3 fuentes y es caliente
    assert "Call of Duty Modern Warfare 4" in temas and "Mass Effect 5" in temas   # nombre entero, no «Call»/«Duty»
    assert "Warfare" not in temas and "Duty" not in temas   # sin fragmentos sueltos


def test_radar_guardadas_lee_lo_ultimo_sin_red(monkeypatch, tmp_path):
    from studio4 import radar
    monkeypatch.setattr(radar, "SENALES", tmp_path / "_radar.jsonl")
    assert radar.guardadas() == []
    monkeypatch.setattr(radar, "escanear", lambda cfg=None, cid=None: [{"tema": "GTA 6", "fuerza": 30, "n_fuentes": 4, "caliente": True, "fuentes": [], "titulares": []}])
    radar.señales(n=5, guardar=True)   # día de hoy
    g = radar.guardadas()
    assert len(g) == 1 and g[0]["tema"] == "GTA 6" and g[0]["dia"]


def test_vigilante_avisa_render_parado_y_video_listo_y_no_repite(aislado, monkeypatch, tmp_path):
    import time as _t
    from studio4 import montaje, vigilante
    monkeypatch.setattr(vigilante, "ESTADO", tmp_path / "_vig.json")
    avisos = []
    kw = dict(avisar=lambda tit, txt: avisos.append(tit) or True, vivo=lambda: True, arrancar=lambda: True)
    mid = montaje.crear("Mi vídeo", "Una frase con seis palabras justas aquí.")
    montaje.modificar(mid, lambda p: p["trabajo"].update(ocupado=True, fase="Plano 5 de 10", progreso=40))
    t0 = _t.time()
    assert vigilante.comprobar(ahora=t0, **kw) == []                       # primera vez: solo anota el progreso
    assert vigilante.comprobar(ahora=t0 + 10 * 60, **kw) == []             # 10 min igual: aún no
    r = vigilante.comprobar(ahora=t0 + 21 * 60, **kw)                      # 21 min sin avanzar: avisa
    assert any(a["clave"].startswith("parado:") for a in r)
    assert vigilante.comprobar(ahora=t0 + 22 * 60, **kw) == []             # no repite antes de 30 min
    # ahora termina con un final listo
    (montaje.carpeta(mid) / "final_16x9.mp4").write_bytes(b"x")
    montaje.modificar(mid, lambda p: (p["trabajo"].update(ocupado=False, fase="Automático: listo"), p.update(final={"hecho": "x"})))
    r2 = vigilante.comprobar(ahora=t0 + 60 * 60, **kw)
    assert any(a["clave"] == f"listo:{mid}" for a in r2)
    assert not any(a["clave"] == f"listo:{mid}" for a in vigilante.comprobar(ahora=t0 + 61 * 60, **kw))   # no repite


def test_servidor_keepalive_vacia_el_cuerpo_del_post(servidor):
    """HTTP/1.1: un POST cuyo cuerpo no se lea corrompía la petición siguiente de la misma conexión (501 «{}GET»)."""
    import http.client
    import servidor as srv
    _, puerto = servidor
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=10)
    # POST a una acción que no lee el cuerpo, con cuerpo JSON; luego un GET en la MISMA conexión
    c.request("POST", "/api/youtube/desconectar", body=b'{"x":1}', headers={"Content-Type": "application/json"})
    r1 = c.getresponse(); r1.read()
    c.request("GET", "/api/estado")   # reutiliza la conexión
    r2 = c.getresponse(); cuerpo = r2.read()
    assert r2.status == 200 and b"libre" in cuerpo or r2.status == 200   # el GET llega entero, no corrupto
    assert srv.Panel.protocol_version == "HTTP/1.1"
    c.close()


def test_render_basico_aplica_lo_esencial_y_pide_los_3_formatos(aislado, tmp_path, monkeypatch):
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch, n=4)
    mid = montaje.crear("P", "Primera frase con seis palabras justas aqui. Segunda frase con seis palabras justas.")
    montaje.usar_fuente(mid, "fuenteA")
    llamado = {}
    monkeypatch.setattr(montaje, "automatico", lambda m, pago_ok=False: llamado.update(mid=m, pago=pago_ok))
    montaje.render_basico(mid, {"musica": montaje.musica.NADA, "subtitulos": {"activos": False, "estilo": "cine"},
                                "cuadrado": True, "voz_original": True, "pago_ok": False})
    p = montaje.cargar(mid)
    assert p["subtitulos"]["activos"] is False and p["subtitulos"]["estilo"] == "cine"
    assert p["formatos"]["cuadrado"] is True and p["voz_original"] is True
    assert all(f.get("clip") for f in p["frases"])   # rellenó los planos que faltaban
    assert llamado["mid"] == mid   # lanzó el "hacerlo todo"


def test_editor_reordenar_y_quitar_clip(aislado, tmp_path, monkeypatch):
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch, n=4)
    mid = montaje.crear("P", "Primera frase con seis palabras justas aqui. Segunda frase con seis palabras justas.")
    montaje.usar_fuente(mid, "fuenteA")
    montaje.proponer(mid)
    antes = [f["n"] for f in montaje.cargar(mid)["frases"]]
    montaje.mover_frase(mid, antes[0], +1)   # baja la primera
    despues = [f["n"] for f in montaje.cargar(mid)["frases"]]
    assert despues == [antes[1], antes[0]] and montaje.cargar(mid)["final"] is None
    montaje.mover_frase(mid, antes[0], -1)   # sube la que bajamos, vuelve al orden original
    assert [f["n"] for f in montaje.cargar(mid)["frases"]] == antes
    assert montaje.cargar(mid)["frases"][0].get("clip")
    montaje.quitar_clip(mid, antes[0])
    f0 = next(f for f in montaje.cargar(mid)["frases"] if f["n"] == antes[0])
    assert "clip" not in f0 and "texto" in f0   # sin clip, pero la frase y su texto siguen


def test_desde_url_crea_video_y_baja_el_material(aislado, monkeypatch):
    from studio4 import montaje
    bajado = {}
    monkeypatch.setattr(montaje, "anadir_fuente", lambda mid, url, *a, **k: bajado.update(mid=mid, url=url))
    mid = montaje.desde_url("https://www.youtube.com/watch?v=abc")
    p = montaje.cargar(mid)
    assert p["id"] == mid and bajado["mid"] == mid and "abc" in bajado["url"]
    import pytest
    with pytest.raises(ValueError):
        montaje.desde_url("no-es-un-enlace")


def test_panel_tiene_pestana_planes_producto():
    """La cáscara de producto: pestaña Planes con tarjetas (gratis/pro/studio)."""
    js = (config.RAIZ / "web" / "montaje.js").read_text(encoding="utf-8")
    html = (config.RAIZ / "web" / "montaje.html").read_text(encoding="utf-8")
    assert "planes: vistaPlanes" in js and "/api/m/planes" in js   # los planes salen de studio4/planes.py (costes)
    assert 'data-vista="planes"' in html


def test_desde_idea_respeta_corto_y_sus_segundos(aislado, monkeypatch):
    """Una idea «corto de 70 segundos» pedía 5 minutos de guion: ahora pide la versión corta con sus segundos."""
    import time as _t
    from studio4 import canales, escenas, guion, ideas, investigacion, material, montaje
    idea = {"idea": "Un corto de 70 segundos sobre el piano de Mario 64", "formato": "corto", "texto": ""}
    monkeypatch.setattr(ideas, "diarias", lambda cid: {"ideas": [idea]})
    monkeypatch.setattr(investigacion, "investigar", lambda *a, **k: {"dossier": "datos"})
    monkeypatch.setattr(material, "inventario", lambda *a, **k: [])
    monkeypatch.setattr(escenas, "para_guion", lambda metas: "")
    pedido = {}

    def escribir(idea_txt, dossier, versiones, **k):
        pedido.update(versiones)
        v = next(iter(versiones))
        return {v: {"guion": "Una frase con seis palabras justas aqui."}, "titulo_provisional": "Piano"}
    monkeypatch.setattr(guion, "escribir", escribir)
    real = canales.obtener
    monkeypatch.setattr(canales, "obtener", lambda cid: {**real(cid), "fuentes": []})
    mid = montaje.desde_idea(0)
    fin = _t.time() + 10
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _t.time() < fin:
        _t.sleep(0.05)
    assert pedido == {"corto": 70}, pedido
    assert montaje.cargar(mid)["frases"]


def test_mover_escena_entre_bloques_no_desordena_transiciones(aislado, tmp_path, monkeypatch):
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch, n=4)
    mid = montaje.crear("P", "Primera frase con seis palabras justas aqui.\n\nSegunda frase con seis palabras justas aqui.")
    antes = [(f["n"], f["bloque"]) for f in montaje.cargar(mid)["frases"]]
    assert [b for _, b in antes] == [0, 1]
    montaje.mover_frase(mid, antes[0][0], +1)
    despues = montaje.cargar(mid)["frases"]
    assert [f["n"] for f in despues] == [antes[1][0], antes[0][0]]
    assert [f["bloque"] for f in despues] == [0, 1]   # los bloques siguen en su sitio: una sola transición


def _video_prueba(destino, segundos=4):
    """Un MP4 de verdad (dos colores = un cambio de plano) para probar la subida."""
    medios.ffmpeg("-f", "lavfi", "-i", f"color=red:s=640x360:d={segundos / 2}:r=30", "-f", "lavfi",
                  "-i", f"color=blue:s=640x360:d={segundos / 2}:r=30", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
                  "-map", "[v]", "-pix_fmt", "yuv420p", str(destino))
    return destino


def test_subir_video_de_tu_pc_crea_material_en_alta(servidor, tmp_path, monkeypatch):
    """Arrastrar/Examinar: el archivo llega, se prepara en alta + baja + planos y queda como fuente del vídeo."""
    import time as _t
    import http.client
    from studio4 import extractor, montaje
    monkeypatch.setattr(extractor, "CACHE", tmp_path / "_fv")
    _, puerto = servidor
    datos = _video_prueba(tmp_path / "mi gameplay.mp4").read_bytes()
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    c.request("POST", "/api/m/subir", body=datos, headers={"X-Nombre": "mi%20gameplay.mp4", "Content-Type": "video/mp4"})
    r = c.getresponse(); d = json.loads(r.read())
    assert r.status == 200, d
    mid = d["id"]
    fin = _t.time() + 60
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _t.time() < fin:
        _t.sleep(0.1)
    p = montaje.cargar(mid)
    assert not p["trabajo"]["error"], p["trabajo"]["error"]
    fid = p["fuentes"][0]
    meta = montaje.fuente(fid)
    assert fid.startswith("local_") and meta["alta"] and meta["local"] and len(meta["planos"]) >= 1
    assert (extractor.CACHE / meta["alta"]).exists() and (extractor.CACHE / meta["baja"]).exists()
    assert p["titulo"] == "mi gameplay"
    # lo que no es vídeo se rechaza
    c.request("POST", "/api/m/subir", body=b"hola", headers={"X-Nombre": "notas.txt"})
    r2 = c.getresponse(); r2.read()
    assert r2.status == 400
    c.close()


def test_leer_y_guardar_el_proyecto_a_la_vez_no_falla(aislado):
    """Panel leyendo mientras un trabajo reescribe proyecto.json: en Windows daba PermissionError."""
    import threading as _th
    from studio4 import montaje
    mid = montaje.crear("P", "Una frase con seis palabras justas aqui.")
    errores, parar = [], _th.Event()

    def escribir():
        while not parar.is_set():
            montaje.modificar(mid, lambda p: p["trabajo"].update(progreso=(p["trabajo"].get("progreso") or 0) + 1))
    h = _th.Thread(target=escribir); h.start()
    try:
        for _ in range(400):
            try:
                montaje.cargar(mid)
            except Exception as e:  # noqa: BLE001
                errores.append(e)
    finally:
        parar.set(); h.join()
    assert not errores, errores[:2]


def _ia_falsa(monkeypatch, pedido):
    from studio4 import escenas, guion, investigacion, material
    monkeypatch.setattr(investigacion, "investigar", lambda *a, **k: {"dossier": "datos verificados"})
    monkeypatch.setattr(material, "inventario", lambda *a, **k: [])
    monkeypatch.setattr(escenas, "para_guion", lambda metas: "")

    def escribir(tema, dossier, versiones, **k):
        pedido.update(versiones=versiones, dossier=dossier, tono=k.get("tono"))
        v = next(iter(versiones))
        return {v: {"guion": "Primera frase con seis palabras justas aqui. Segunda frase con seis palabras justas.",
                    "ganchos": ["Gancho fuerte"]}, "titulo_provisional": "Título IA"}
    monkeypatch.setattr(guion, "escribir", escribir)


def _esperar_mid(mid, s=15):
    import time as _t
    from studio4 import montaje
    fin = _t.time() + s
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _t.time() < fin:
        _t.sleep(0.05)
    return montaje.cargar(mid)


def test_crear_con_ia_escribe_guion_y_resumen(aislado, monkeypatch):
    from studio4 import montaje
    pedido = {}
    _ia_falsa(monkeypatch, pedido)
    mid = montaje.crear_con_ia("Secretos de la Mansión de Boo", {"duracion": 45, "formato": "9:16", "tono": "misterio",
                                                                   "modo": "inventar"})
    p = _esperar_mid(mid)
    assert not p["trabajo"]["error"], p["trabajo"]["error"]
    assert pedido["versiones"] == {"corto": 30} or pedido["versiones"] == {"corto": 60}   # 45 → duración permitida más cercana
    assert "MODO HISTORIA" in pedido["dossier"] and pedido["tono"].startswith("misterio")
    assert "Estilo de producción" in pedido["tono"]   # el guionista sabe cómo escribir según el estilo
    assert p["frases"] and p["titulo"] == "Título IA" and p["formato_principal"] == "9:16"
    assert p["resumen_ia"]["gancho"] == "Gancho fuerte" and p["resumen_ia"]["plataforma"] == "YouTube Shorts"


def test_guion_con_ia_para_un_video_que_solo_tiene_material(aislado, tmp_path, monkeypatch):
    from studio4 import montaje
    _banco_falso(tmp_path, monkeypatch, n=4)
    pedido = {}
    _ia_falsa(monkeypatch, pedido)
    mid = montaje.crear("trailer lanzamiento gta vi", "", sin_guion=True)
    montaje.usar_fuente(mid, "fuenteA")
    montaje.guion_con_ia(mid, {"duracion": 300})
    p = _esperar_mid(mid)
    assert not p["trabajo"]["error"], p["trabajo"]["error"]
    assert pedido["versiones"] == {"largo": 300} and "MATERIAL QUE YA TIENE EL VÍDEO" in pedido["dossier"]
    assert p["frases"] and all(f.get("clip") for f in p["frases"])   # además pone un plano en cada frase


def test_investigacion_web_de_deepseek_filtra_autoridad_y_cita(monkeypatch):
    """Búsqueda web (solo si se activa): se queda con fuentes de autoridad, lee las mejores y arma el dossier."""
    from studio4 import investigacion
    monkeypatch.setattr(investigacion.config, "BUSQUEDA_WEB", True)
    monkeypatch.setattr(investigacion.config, "DEEPSEEK_API_KEY", "x")
    llamadas = []

    def tool(nombre, cuerpo, produccion):
        llamadas.append(nombre)
        if nombre == "search":
            return {"results": [{"url": "https://www.rockstargames.com/a", "title": "Oficial", "authority": 4, "rerank_score": 2.5, "content": "c" * 2000},
                                {"url": "https://spam.example/b", "title": "Spam", "authority": 0, "rerank_score": 0.2, "content": "x"}]}
        return {"content": "artículo completo"}
    monkeypatch.setattr(investigacion, "_deepseek_tool", tool)
    textos = []

    def gen(prompt, **k):
        textos.append(prompt)
        return '{"consultas": ["gta vi trailer"]}' if "búsquedas web" in prompt else "HECHOS [F1]"
    monkeypatch.setattr(investigacion.gemini, "generar", gen)
    r = investigacion.investigar("GTA VI tráiler")
    assert r["metodo"] == "DeepSeek (web)" and [f["url"] for f in r["fuentes"]] == ["https://www.rockstargames.com/a"]
    assert "spam.example" not in textos[-1] and r["dossier"] == "HECHOS [F1]"


def test_chat_ejecuta_acciones_reales_y_rechaza_inventadas(aislado, tmp_path, monkeypatch):
    from studio4 import chat, montaje
    _banco_falso(tmp_path, monkeypatch, n=4)
    mid = montaje.crear("P", "Primera frase con seis palabras justas aqui.\n\nSegunda frase con seis palabras justas aqui.")
    montaje.usar_fuente(mid, "fuenteA")
    n1 = montaje.cargar(mid)["frases"][0]["n"]
    respuesta = {"respuesta": "Listo: planos, voz y subtítulos.", "acciones": [
        {"accion": "proponer_planos", "args": {}},
        {"accion": "cambiar_voz", "args": {"nombre": "Charon"}},
        {"accion": "subtitulos", "args": {"estilo": "cine", "posicion": "arriba"}},
        {"accion": "mover_escena", "args": {"n": n1, "direccion": 1}},
        {"accion": "borrar_disco", "args": {}}]}
    r = chat.responder(mid, "pon planos, voz Charon, subtítulos cine arriba y baja la primera escena", pensar=lambda *a: respuesta)
    p = montaje.cargar(mid)
    assert len(r["hechas"]) == 4 and any("borrar_disco" in e for e in r["errores"])
    assert all(f.get("clip") for f in p["frases"]) and p["voz_nombre"] == "Charon"
    assert p["subtitulos"]["estilo"] == "cine" and p["subtitulos"]["posicion"] == "arriba"
    assert p["frases"][1]["n"] == n1   # la escena bajó
    assert [m["quien"] for m in p["chat"][-2:]] == ["tú", "IA"]
    # voz inexistente / de pago: error, no se cambia
    r2 = chat.responder(mid, "pon la voz de pago", pensar=lambda *a: {"respuesta": "ok", "acciones": [{"accion": "cambiar_voz", "args": {"nombre": "Rachel"}}]})
    assert r2["errores"] and montaje.cargar(mid)["voz_nombre"] == "Charon"


def test_chat_solo_un_trabajo_en_segundo_plano_por_mensaje(aislado, monkeypatch):
    from studio4 import chat, montaje
    mid = montaje.crear("P", "Una frase con seis palabras justas aqui.")
    lanzados = []
    monkeypatch.setitem(chat.ACCIONES, "hacer_previa", {**chat.ACCIONES["hacer_previa"], "fn": lambda m, a: lanzados.append("previa") or "previa"})
    monkeypatch.setitem(chat.ACCIONES, "buscar_material", {**chat.ACCIONES["buscar_material"], "fn": lambda m, a: lanzados.append("material") or "material"})
    r = chat.responder(mid, "todo", pensar=lambda *a: {"respuesta": "", "acciones": [{"accion": "hacer_previa"}, {"accion": "buscar_material"}]})
    assert lanzados == ["previa"] and r["errores"]


def test_formatos_diarios_recorta_negro_y_saca_los_3(tmp_path):
    """Conteo diario: 3 escenas (logo, cuenta atrás, redes) + negro al final → 9x16, 9x16 zoom y 1x1 sin el negro."""
    import sys as _sys
    _sys.path.insert(0, str(config.RAIZ / "scripts"))
    import formatos_diarios as fd
    v = tmp_path / "conteo dia 1.mp4"
    medios.ffmpeg("-f", "lavfi", "-i", "color=red:s=640x360:d=1:r=30", "-f", "lavfi", "-i", "color=blue:s=640x360:d=2:r=30",
                  "-f", "lavfi", "-i", "color=green:s=640x360:d=1:r=30", "-f", "lavfi", "-i", "color=black:s=640x360:d=3:r=30",
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=7", "-filter_complex",
                  "[0:v][1:v][2:v][3:v]concat=n=4:v=1[v]", "-map", "[v]", "-map", "4:a", "-pix_fmt", "yuv420p", "-shortest", str(v))
    assert abs(fd.fin_de_imagen(v) - 4.0) < 0.2   # el negro del final no cuenta
    hechos = fd.hacer(v)
    nombres = sorted(h.name for h in hechos)
    assert nombres == ["conteo dia 1 - 1x1.mp4", "conteo dia 1 - 9x16 zoom.mp4", "conteo dia 1 - 9x16.mp4",
                       "conteo dia 1 - textos YouTube.txt"]
    for h in hechos[:-1]:
        assert abs(fd.duracion(h) - 4.0) < 0.3
    textos = hechos[-1].read_text(encoding="utf-8")
    assert "GTA 6: falta 1 DÍA para el lanzamiento" in textos and "¡Solo 1 día para GTA 6!" in textos and "ETIQUETAS" in textos
    assert "faltan 25 DÍAS" in fd.textos(Path("conteo dia 25.mp4"))


def test_tu_voz_se_alinea_con_el_guion_aunque_whisper_oiga_algo_distinto():
    """Tu locución subida: los tiempos salen de lo que oyó Whisper y el texto, del guion (sin faltas de oído)."""
    from studio4 import montaje
    oidas = [{"palabra": w, "ini": i * 0.5, "fin": i * 0.5 + 0.4}
             for i, w in enumerate("Faltan veintiséis días para GTA seis. Lucía es la protagonista.".split())]
    t = montaje.alinear_voz(["Faltan 26 días para GTA 6.", "Lucia es la protagonista."], oidas, 6.0)
    assert [w["palabra"] for w in t["palabras"]][:3] == ["Faltan", "26", "días"]
    assert t["escenas"][0]["ini"] == 0.0 and t["escenas"][1]["ini"] == 3.0   # «Lucia» casa con «Lucía»
    assert all(a["fin"] <= b["ini"] + 1e-6 for a, b in zip(t["escenas"], t["escenas"][1:]))
    assert t["palabras"][1]["ini"] >= t["palabras"][0]["ini"]   # «26» (oído «veintiséis») cae en su sitio
    with pytest.raises(ValueError):
        montaje.alinear_voz(["Hola."], [], 1.0)


def test_subir_tu_voz_y_tu_musica_y_escuchar_las_muestras(servidor, tmp_path, monkeypatch):
    """«Examinar»: tu voz queda elegida (y se puede oír); tu canción entra en tu música y queda elegida; el fondo
    suave del Studio se puede escuchar antes de elegirlo."""
    import http.client
    from studio4 import medios, montaje, musica
    monkeypatch.setattr(musica, "carpeta", lambda: (tmp_path / "musica").mkdir(exist_ok=True) or tmp_path / "musica")
    pedir, puerto = servidor
    mid = montaje.crear("Voz propia", "Una frase con seis palabras justas aqui.")
    audio = tmp_path / "mi voz.wav"
    medios.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=2", str(audio))
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    c.request("POST", f"/api/m/subir-voz?id={mid}", body=audio.read_bytes(), headers={"X-Nombre": "mi%20voz.wav"})
    r = c.getresponse(); d = json.loads(r.read())
    assert r.status == 200, d
    p = montaje.cargar(mid)
    assert p["voz_proveedor"] == "propia" and p["voz_propia"]["archivo"] == "mi voz.wav" and montaje.coste_voz(p) == 0
    estado, cuerpo = pedir("GET", f"/m/{mid}/voz_propia.wav")
    assert estado == 200 and cuerpo[:4] == b"RIFF"
    c.request("POST", f"/api/m/subir-musica?id={mid}", body=audio.read_bytes(), headers={"X-Nombre": "Mi%20cancion.wav"})
    r = c.getresponse(); d = json.loads(r.read())
    assert r.status == 200 and d["archivo"] == "Mi cancion.wav", d
    assert montaje.cargar(mid)["musica"] == "Mi cancion.wav" and (tmp_path / "musica" / "Mi cancion.wav").exists()
    c.request("POST", f"/api/m/subir-voz?id={mid}", body=b"hola", headers={"X-Nombre": "notas.txt"})
    r = c.getresponse(); r.read()
    assert r.status == 400
    c.close()
    estado, cuerpo = pedir("GET", "/api/m/musica/cama")
    assert estado == 200 and cuerpo[:4] == b"RIFF"


def test_la_voz_subida_queda_guardada_para_otros_videos_y_la_velocidad_se_elige(servidor, tmp_path):
    """Tu voz subida entra en la biblioteca (una sola vez aunque la subas dos veces) y otro vídeo la puede usar;
    la velocidad solo admite los valores del panel."""
    import http.client
    from studio4 import medios, montaje
    pedir, puerto = servidor
    a = montaje.crear("Uno", "Una frase con seis palabras justas aqui.")
    b = montaje.crear("Dos", "Otra frase distinta para el segundo video.")
    audio = tmp_path / "Diego narrador.wav"
    medios.ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:duration=2", str(audio))
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    for _ in range(2):
        c.request("POST", f"/api/m/subir-voz?id={a}", body=audio.read_bytes(), headers={"X-Nombre": "Diego%20narrador.wav"})
        r = c.getresponse(); r.read()
        assert r.status == 200
    c.close()
    guardadas = montaje.voces_guardadas()
    assert len(guardadas) == 1 and guardadas[0]["nombre"] == "Diego narrador"
    vid = guardadas[0]["id"]
    estado, cuerpo = pedir("GET", f"/api/m/voces-guardadas/{vid}.wav")
    assert estado == 200 and cuerpo[:4] == b"RIFF"
    montaje.usar_voz_guardada(b, vid)
    p = montaje.cargar(b)
    assert p["voz_proveedor"] == "propia" and p["voz_propia"]["huella"] == vid
    assert (montaje.carpeta(b) / montaje.VOZ_PROPIA).exists()
    montaje.elegir_velocidad(b, 1.2)
    assert montaje.cargar(b)["voz_velocidad"] == 1.2
    with pytest.raises(ValueError):
        montaje.elegir_velocidad(b, 3)
    with pytest.raises(ValueError):
        montaje.usar_voz_guardada(b, "../../secreto")


def test_shorts_con_emoji_por_frase_y_la_marca_4l_en_los_formatos(aislado, tmp_path, monkeypatch):
    """Cada frase del Short lleva el emoji de lo que dice (sin repetir el mismo seguido); la marca del canal va en
    todos los formatos, arriba a la izquierda en vertical."""
    from studio4 import canales, montaje
    assert montaje.emoji_de("Faltan 26 días para GTA 6") == "⏳"
    assert montaje.emoji_de("Cuesta 79.99 dólares") == "💰"
    assert montaje.emoji_de("Una frase sin nada especial aquí") == ""
    q = {"canal": canales.activo()["id"], "frases": [{"texto": "Faltan 3 días."}, {"texto": "Quedan pocos días."}],
         "voz": {"tiempos": [(0.0, 1.0), (1.5, 2.5)]}}
    monkeypatch.setattr(montaje, "_png_emoji", lambda e: tmp_path / "e.png")   # sin navegador en la prueba
    entradas, cadena = montaje._capas_marca(q, 0.0, 3.0, 1080, 1920, "[base]", 2, emojis=True)
    assert cadena.endswith("null[v]") and cadena.count("between(") == 1   # el mismo emoji seguido no se repite
    assert "between(t,0.00,1.50)" in cadena   # se queda hasta la frase siguiente


def _montado_de_prueba(tmp_path):
    """Un vídeo «ya montado» mínimo: cuerpo, mezcla, voz con sus palabras y el final hecho."""
    from studio4 import montaje
    mid = montaje.crear("Montado", "Lucia llega a Vice City. Faltan pocos días.")
    trabajo = montaje.carpeta(mid) / "render"
    trabajo.mkdir(parents=True)
    medios.ffmpeg("-f", "lavfi", "-i", "color=blue:s=1920x1080:d=4:r=30", "-pix_fmt", "yuv420p", str(trabajo / "cuerpo.mp4"))
    medios.ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=4", "-ac", "2", str(trabajo / "mezcla.wav"))
    palabras = [{"palabra": w, "ini": 0.3 + k * 0.4, "fin": 0.6 + k * 0.4}
                for k, w in enumerate("Lucia llega a Vice City. Faltan pocos días.".split())]
    montaje.modificar(mid, lambda p: p.update(voz={"palabras": [dict(w) for w in palabras], "tiempos": [(0.3, 2.2), (2.3, 3.5)],
                                                   "pausas": {"palabras": [dict(w) for w in palabras], "tiempos": [(0.3, 2.2), (2.3, 3.5)]}},
                                              final={"archivo": "final_16x9.mp4", "hecho": "ayer"}))
    return mid


def _esperar_montaje(mid, segundos=120):
    import time as _t
    from studio4 import montaje
    fin = _t.time() + segundos
    while montaje.cargar(mid)["trabajo"].get("ocupado") and _t.time() < fin:
        _t.sleep(0.1)
    return montaje.cargar(mid)


def test_subtitulos_se_corrigen_y_se_rehacen_sin_volver_a_montar(aislado, tmp_path):
    """Corregir una palabra («Lucia» → «Lucía») o cambiar el estilo solo rehace la última pasada: el vídeo final
    sale de nuevo desde el cuerpo y la mezcla guardados, y el .srt lleva la palabra corregida."""
    from studio4 import montaje
    mid = _montado_de_prueba(tmp_path)
    assert montaje.corregir_subtitulo(mid, "lucia", "Lucía") == 2   # en las palabras y en las de las pausas
    p = _esperar_montaje(mid)
    assert not p["trabajo"]["error"], p["trabajo"]["error"]
    final = montaje.carpeta(mid) / "final_16x9.mp4"
    assert final.exists() and abs(medios.duracion(final) - 4.0) < 0.3
    assert "Lucía" in (montaje.carpeta(mid) / "subtitulos.srt").read_text(encoding="utf-8")
    assert p["final"]["hecho"] != "ayer"
    with pytest.raises(ValueError):
        montaje.corregir_subtitulo(mid, "Inexistente", "Otra")
    montaje.subtitulos_rapido(mid, {"estilo": "cine", "posicion": "centro"})
    p = _esperar_montaje(mid)
    assert p["subtitulos"]["estilo"] == "cine" and p["final"] and not p["trabajo"]["error"]
    with pytest.raises(ValueError):
        montaje.subtitulos_rapido(mid, {"estilo": "comic"})
    vista = montaje.vista_subtitulos(mid, {"tamano": "grande"}, "9x16")
    assert vista.exists() and vista.stat().st_size > 1000


def test_chat_adjunta_imagenes_y_las_miniaturas_se_eligen_viendolas(servidor, tmp_path):
    """Una imagen soltada en el chat queda en el vídeo (y se puede ver); lo que no es imagen se rechaza; una
    miniatura candidata se elige y pasa a ser la miniatura."""
    import http.client
    from PIL import Image
    from studio4 import montaje
    pedir, puerto = servidor
    mid = montaje.crear("Adjuntos", "Una frase con seis palabras justas aqui.")
    img = tmp_path / "portada.png"
    Image.new("RGB", (64, 36), (255, 0, 80)).save(img)
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=30)
    c.request("POST", f"/api/m/adjuntar?id={mid}", body=img.read_bytes(), headers={"X-Nombre": "portada.png"})
    r = c.getresponse(); d = json.loads(r.read())
    assert r.status == 200, d
    assert montaje.cargar(mid)["adjuntos"][0]["archivo"] == d["archivo"]
    estado, cuerpo = pedir("GET", f"/m/{mid}/adjuntos/{d['archivo']}")
    assert estado == 200 and cuerpo[:2] == b"\xff\xd8"
    c.request("POST", f"/api/m/adjuntar?id={mid}", body=b"hola", headers={"X-Nombre": "notas.exe"})
    r = c.getresponse(); r.read()
    assert r.status == 400
    c.close()
    Image.new("RGB", (1280, 720)).save(montaje.carpeta(mid) / "miniatura_c2.jpg")
    montaje.elegir_miniatura(mid, "miniatura_c2.jpg")
    assert montaje.cargar(mid)["miniatura"] == "miniatura.jpg" and (montaje.carpeta(mid) / "miniatura.jpg").exists()
    with pytest.raises(ValueError):
        montaje.elegir_miniatura(mid, "../proyecto.json")
    with pytest.raises(ValueError):
        montaje.adjunto(mid, "../../.env")


def test_empaque_titulo_con_miniatura_capitulos_validos_y_gancho():
    """Título + miniatura como pareja (sin repetirse, con dato, sin gritar), capítulos que YouTube acepta y gancho."""
    from studio4 import empaque
    bueno = empaque.revisar_titulo("GTA 6 a 79,99 $: lo que trae la caja", "SIN DISCO")
    malo = empaque.revisar_titulo("INCREÍBLE!!! TODO lo que NO SABÍAS de GTA", "TODO LO QUE NO SABÍAS DE GTA")
    assert bueno["nota"] > malo["nota"] and not bueno["mal"]
    assert any("repite" in m for m in malo["mal"]) and any("MAYÚSCULAS" in m for m in malo["mal"])
    assert any("no dice nada" in m for m in malo["mal"]) and any("palabras en la miniatura" in m for m in malo["mal"])
    caps, aviso = empaque.capitulos_validos(["0:03 Intro", "0:08 Muy pegado", "0:25 Jason", "0:44 Justice"], 61.5)
    assert caps == ["0:00 Intro", "0:25 Jason", "0:44 Justice"] and not aviso   # empieza en 0:00 y sin tramos de < 10 s
    assert empaque.capitulos_validos(["0:00 a", "0:05 b"], 20) == ([], "Vídeo demasiado corto para capítulos (YouTube pide 3 o más de 10 s).")
    g = empaque.revisar_gancho("Faltan 26 días para GTA 6 y llega sin disco.", "GTA 6 llega sin disco")
    assert g["nota"] >= 90 and not g["mal"]
    assert empaque.revisar_gancho("hola a todos y bienvenidos otra vez a mi canal de siempre donde hablamos de muchas cosas interesantes cada semana", "GTA 6")["mal"]


def test_biblioteca_con_chat_propone_guiones_solo_con_fuentes_encontradas(aislado, monkeypatch):
    """El chat de la Biblioteca busca en las bases y propone guiones; una idea que cita una fuente que no se
    encontró se descarta; las ideas se guardan, se quitan y se convierten en vídeo con sus fuentes."""
    from studio4 import buscador, canales, deepseek, montaje
    cid = canales.activo()["id"]
    monkeypatch.setattr(deepseek, "disponible", lambda: True)
    hallado = [{"base": "es.wikipedia.org", "titulo": "Mecanismo de Anticitera", "resumen": "artefacto griego",
                "url": "https://es.wikipedia.org/wiki/Mecanismo_de_Anticitera"}]
    monkeypatch.setattr(buscador, "buscar_en_bases", lambda consultas: hallado)

    def generar_json(sistema, prompt, **_):
        if "búsquedas" in sistema:
            return {"consultas": ["mecanismo de Anticitera"]}
        assert "Mecanismo_de_Anticitera" in prompt
        return {"respuesta": "Dos ideas.", "ideas": [
            {"titulo": "El ordenador de hace 2.000 años", "gancho": "En 1901…", "angulo": "eclipses", "formato": "corto",
             "fuentes": ["https://es.wikipedia.org/wiki/Mecanismo_de_Anticitera"]},
            {"titulo": "Inventada", "gancho": "x", "angulo": "y", "formato": "largo", "fuentes": ["https://falsa.example/x"]}]}
    monkeypatch.setattr(deepseek, "generar_json", generar_json)
    r = buscador.conversar(cid, "misterios de la Grecia antigua")
    assert [i["titulo"] for i in r["ideas"]] == ["El ordenador de hace 2.000 años"]   # la de fuente inventada fuera
    idea = r["ideas"][0]["id"]
    buscador.guardar_idea(cid, idea)
    assert [i["id"] for i in buscador.leer(cid)["guardadas"]] == [idea]
    pedido = {}
    monkeypatch.setattr(montaje, "crear_con_ia", lambda tema, o: pedido.update(tema=tema, o=o) or "vid-1")
    assert buscador.crear_video(cid, idea) == "vid-1"
    assert pedido["o"]["fuentes"] == ["https://es.wikipedia.org/wiki/Mecanismo_de_Anticitera"] and pedido["o"]["duracion"] == 60
    assert montaje._opciones_ia({"fuentes": ["https://a.org/x", "javascript:alert(1)"]})["fuentes"] == ["https://a.org/x"]
    buscador.quitar_idea(cid, idea)
    assert not buscador.leer(cid)["guardadas"]
    assert buscador.guardar_bases(cid, ["https://www.britannica.com/", "no-es-url"]) == ["https://www.britannica.com/"]
    with pytest.raises(ValueError):
        buscador.conversar(cid, "  ")


def test_cada_canal_tiene_su_radar_y_sus_videos_sin_mezclarse(aislado, monkeypatch):
    """FourLevel conserva su radar de juegos; un canal de misterios usa webs de historia agrupadas por grandes
    temas; las señales de uno no aparecen en el otro; la lista de vídeos es solo del canal activo; un vídeo a medias
    se archiva (no se borra)."""
    from studio4 import canales, config, montaje, radar
    monkeypatch.setattr(radar, "CONFIG", aislado / "_radar.json")
    monkeypatch.setattr(radar, "SENALES", aislado / "_radar.jsonl")
    canales.guardar({"id": "fourlevel", "nombre": "FourLevel", "nicho": "Video juegos"})
    canales.guardar({"id": "arigab", "nombre": "ARIGAB", "nicho": "Misterios sin resolver de la historia y mitología"})
    assert radar.config_radar("fourlevel")["wiki_api"] and not radar.config_radar("arigab").get("wiki_api")
    assert radar.config_radar("arigab").get("temas")
    titulares = {"a": ["Roman forum found under hotel", "Una tumba romana en Hispania"], "b": ["Roman legion camp", "Viking runes"]}
    monkeypatch.setattr(radar, "_titulares_rss", lambda f, m: titulares.get(f["id"], []))
    cfg = {**radar.config_radar("arigab"), "rss": [{"id": "a", "url": "a"}, {"id": "b", "url": "b"}]}
    s = radar.escanear(cfg)
    assert s[0]["tema"] == "Roma antigua" and s[0]["n_fuentes"] == 3 and s[0]["caliente"]
    radar._guardar(s, "arigab")
    radar._guardar([{"tema": "GTA 6", "fuerza": 9, "fuentes": ["ign"], "n_fuentes": 2, "caliente": True, "titulares": []}], "fourlevel")
    assert [x["tema"] for x in radar.guardadas(12, "arigab")][0] == "Roma antigua"
    assert [x["tema"] for x in radar.guardadas(12, "fourlevel")] == ["GTA 6"]   # nada se mezcla
    canales.activar("arigab")
    mio = montaje.crear("Expediente 001", "Una frase con seis palabras justas aqui.")
    canales.activar("fourlevel")
    otro = montaje.crear("GTA", "Otra frase con seis palabras justas aqui.")
    assert {v["id"]: v["canal"] for v in montaje.listar()} == {mio: "arigab", otro: "fourlevel"}
    montaje.archivar(otro)
    assert otro not in [v["id"] for v in montaje.listar()]
    assert (config.PRODUCCIONES / "_papelera" / f"montaje_{otro}" / "proyecto.json").exists()


def test_nube_sube_canales_videos_ideas_y_tendencias_con_la_cuenta_del_dueno(aislado, monkeypatch):
    """Sin cuenta no hace nada; con cuenta inicia sesión una vez y sube cada tabla (las tendencias sin repetirse
    por día). Nunca toca la base real en la prueba."""
    from studio4 import canales, montaje, nube
    for k in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_EMAIL", "SUPABASE_CLAVE"):
        monkeypatch.delenv(k, raising=False)
    assert not nube.disponible()
    with pytest.raises(ValueError):
        nube.sincronizar()
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_prueba")
    monkeypatch.setenv("SUPABASE_EMAIL", "yo@ejemplo.com")
    monkeypatch.setenv("SUPABASE_CLAVE", "secreta")
    nube._sesion.clear()
    canales.guardar({"id": "fourlevel", "nombre": "FourLevel"})
    montaje.crear("Mi vídeo", "Una frase con seis palabras justas aqui.")
    peticiones = []

    class R:
        def __init__(self, code, data=None):
            self.status_code, self._d, self.text = code, data or {}, ""

        def json(self):
            return self._d

    def post(url, **kw):
        peticiones.append((url, kw))
        if "/auth/v1/token" in url:
            assert kw["json"]["email"] == "yo@ejemplo.com"
            return R(200, {"access_token": "tok", "expires_in": 3600})
        assert kw["headers"]["Authorization"] == "Bearer tok"
        return R(201)
    monkeypatch.setattr(nube.requests, "post", post)
    subidos = nube.sincronizar()
    assert subidos["canales"] >= 1 and subidos["videos"] == 1
    assert sum(1 for u, _ in peticiones if "/auth/v1/token" in u) == 1   # una sola sesión
    tablas = [u.rsplit("/", 1)[1] for u, _ in peticiones if "/rest/v1/" in u]
    assert tablas[:2] == ["canales", "videos"] and nube.estado["ultima"]


def test_secretos_salen_del_env_y_se_leen_del_almacen(tmp_path, monkeypatch):
    """Un secreto se pasa del .env al almacén (y desaparece del .env); se lee del almacén y, si no está, del entorno."""
    from studio4 import secretos
    caja = {}

    class Falso:
        def get_password(self, servicio, nombre):
            return caja.get((servicio, nombre))

        def set_password(self, servicio, nombre, valor):
            caja[(servicio, nombre)] = valor
    monkeypatch.setattr(secretos, "_almacen", lambda: Falso())
    env = tmp_path / ".env"
    env.write_text("OTRA=1\nSUPABASE_CLAVE=secreta\nY=2\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_CLAVE", "secreta")
    assert secretos.mover_del_env("SUPABASE_CLAVE", str(env))
    assert "SUPABASE_CLAVE" not in env.read_text(encoding="utf-8") and "OTRA=1" in env.read_text(encoding="utf-8")
    assert secretos.leer("SUPABASE_CLAVE") == "secreta"
    assert not secretos.mover_del_env("NO_EXISTE", str(env))
    monkeypatch.setenv("SOLO_ENV", "x")
    assert secretos.leer("SOLO_ENV") == "x"


def test_planes_salen_de_los_costes_y_ninguno_pierde_dinero(servidor):
    """Cada plan de pago deja margen aunque el cliente gaste todo su cupo; el cliente ve precio y cupos, nunca los
    costes ni los márgenes."""
    from studio4 import planes
    for p in planes.PLANES:
        if p["precio"]:
            assert planes.margen(p) >= 0.4, (p["nombre"], planes.margen(p))
    assert next(p for p in planes.PLANES if p["id"] == "ilimitado")["cupos"]["video"] is None   # ilimitado de verdad
    pedir, _ = servidor
    estado, cuerpo = pedir("GET", "/api/m/planes")
    d = json.loads(cuerpo)
    assert estado == 200 and [p["id"] for p in d["planes"]] == ["basico", "pro", "ilimitado"]
    texto = json.dumps(d)
    assert "coste" not in texto and "margen" not in texto
    assert d["prueba"]["dias"] == 3 and d["prueba"]["plan"] == "Básico"   # sin plan gratis: prueba de 3 días
    assert planes.coste_prueba() <= 0.05   # la prueba solo usa el PC del cliente: no se invierte en pruebas
    assert planes.PRUEBA["solo_estilos"] == "claude" and not planes.PRUEBA["cupos"]["imagen"]


def test_estilos_de_produccion_guian_guion_y_recomiendan_modelo(aislado):
    """Cada estilo dice cómo escribir, quién lo hace (Claude con código o un modelo) y qué modelo usar; el estilo
    pedido manda y, si no hay, el del canal; los estilos visuales de Flow salen de la misma ficha."""
    from studio4 import canales, config, estilos, montaje
    cat = estilos.catalogo()
    assert cat[0]["hecho_por"] == "claude"   # primero los gratis
    for e in cat:
        assert e["imagen"] and e["video"] and e["coste"] in ("gratis", "bajo", "medio", "alto")
    assert estilos.ESTILOS["stickman"]["hecho_por"] == "claude" and estilos.ESTILOS["cinematografico"]["hecho_por"] == "modelo"
    assert "logo" in estilos.ESTILOS["mundo_abierto"]["visual"]   # «no logos»: estética propia
    assert config.ESTILOS["cinematografico"] == estilos.ESTILOS["cinematografico"]["visual"] and "motion" not in config.ESTILOS
    assert "videojuego" in config.ESTILOS   # los vídeos viejos con ese estilo siguen funcionando
    canales.guardar({"id": canales.activo()["id"], "estilo": "noir"})
    assert montaje._opciones_ia({})["estilo"] == "noir"                  # el del canal
    assert montaje._opciones_ia({"estilo": "anime"})["estilo"] == "anime"   # el pedido manda
    assert montaje._opciones_ia({"estilo": "inventado"})["estilo"] == "noir"
    assert "Noir" in estilos.para_guion("noir")


def test_cuenta_del_negocio_cubre_gastos_con_pocos_clientes():
    """Con gastos fijos, comisiones, pruebas gratis y la IA de cada cliente, el negocio cubre gastos con pocos
    clientes y cada plan deja dinero aunque el cliente gaste todo."""
    from studio4 import planes
    for p in planes.PLANES:
        assert planes.contribucion(p, 1.0) > 0, p["nombre"]
    assert planes.equilibrio() <= 10 and planes.equilibrio(uso=1.0) <= 15
    e = planes.economia(100)
    assert e["beneficio"] > 0 and e["ingresos"] == 60 * 17 + 30 * 49 + 10 * 100
    assert planes.coste_captacion() < 10


def test_chat_de_inicio_empieza_sin_guion_y_pregunta_el_estilo(aislado, monkeypatch):
    """La portada empieza hablando: analiza nichos, propone ideas, enseña tendencias y crea el vídeo; si no se dijo
    el estilo, lo pregunta en vez de crear; la historia es de cada canal."""
    from studio4 import asistente, canales, deepseek, montaje, nichos
    cid = canales.activo()["id"]
    monkeypatch.setattr(deepseek, "disponible", lambda: True)
    monkeypatch.setattr(nichos, "analizar", lambda temas: [{"tema": t, "videos": 50, "mediana_vistas": 400000, "grandes_1M": 3,
                                                           "top3_cuota": 0.4, "pequenos_que_explotan": 15, "ejemplo": "",
                                                           "veredicto": "Hueco: canales nuevos rompen"} for t in temas])
    creados = []
    monkeypatch.setattr(montaje, "crear_con_ia", lambda tema, o: creados.append((tema, o)) or "vid-9")
    respuestas = iter([
        {"respuesta": "Miro esos nichos.", "accion": "nicho", "args": {"temas": ["misterios sin resolver"]}},
        {"respuesta": "¿En qué estilo?", "accion": "crear", "args": {"tema": "El mecanismo de Anticitera", "duracion": 60}},
        {"respuesta": "Creándolo.", "accion": "crear", "args": {"tema": "El mecanismo de Anticitera", "estilo": "collage", "duracion": 60}},
    ])
    pensar = lambda canal, historia, mensaje: next(respuestas)   # noqa: E731
    r = asistente.responder(cid, "busca un nicho de misterios", pensar=pensar)
    assert r["resultado"]["tipo"] == "nicho" and r["resultado"]["nichos"][0]["veredicto"].startswith("Hueco")
    r = asistente.responder(cid, "hazme un short del mecanismo de Anticitera", pensar=pensar)
    assert r["resultado"]["tipo"] == "estilo" and not creados   # sin estilo no crea: pregunta
    r = asistente.responder(cid, "en collage", pensar=pensar)
    assert r["resultado"] == {"tipo": "video", "id": "vid-9", "estilo": "Collage documental"}
    assert creados[0][1]["estilo"] == "collage"
    assert [m["quien"] for m in asistente.leer(cid)] == ["tú", "IA"] * 3
    assert nichos.veredicto({"mediana_vistas": 5000, "pequenos_que_explotan": 0, "top3_cuota": 0.9, "grandes_1M": 0}) == "Poca demanda"
    asistente.limpiar(cid)
    assert asistente.leer(cid) == []


def test_isometrico_3d_hecho_con_codigo_y_modo_ligero(aislado, monkeypatch):
    """El estilo isométrico lo hace Claude con código: la escena que llega de la IA se sanea (tipos, números,
    colores, máximo de objetos) y se dibuja en SVG encuadrado; sin IA hay escena de reserva. El modo ligero se
    puede forzar o apagar."""
    from studio4 import config, estilos, isometrico
    assert estilos.ESTILOS["isometrico"]["hecho_por"] == "claude" and estilos.ESTILOS["isometrico"]["generador"] == "isometrico"
    sucia = {"paleta": "inventada", "objetos": [{"tipo": "caja", "x": 99, "h": "alto", "color": "rojo", "ventanas": True},
                                               {"tipo": "dragon"}] + [{"tipo": "luz"}] * 40}
    e = isometrico.validar(sucia)
    assert e["paleta"] == "noche" and len(e["objetos"]) == isometrico.MAX_OBJETOS - 1   # el dragón fuera; 30 como mucho
    assert e["objetos"][0]["x"] == 14 and e["objetos"][0]["h"] == 1 and e["objetos"][0]["color"].startswith("#")
    s = isometrico.svg(isometrico.escena_de_reserva("Faltan 26 días"), semilla="x")
    assert s.startswith("<svg") and "<polygon" in s and 'filter="url(#brillo)"' in s
    assert isometrico.escena_de_reserva("a") != isometrico.escena_de_reserva("b")   # cada frase, su maqueta
    monkeypatch.setenv("STUDIO4_LIGERO", "1")
    assert config._equipo_ligero() is True
    monkeypatch.setenv("STUDIO4_LIGERO", "0")
    assert config._equipo_ligero() is False
