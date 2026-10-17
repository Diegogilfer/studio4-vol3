"""Aprender del nicho: el canal estudia CÓMO cuentan los vídeos que ya funcionan y lo convierte en su manual.

No basta con mirar títulos y vistas: aquí se leen los vídeos de verdad (los subtítulos de YouTube, gratis y sin
descargar el vídeo) de los canales referentes y de lo más visto del nicho. De cada uno se estudia cómo engancha,
cómo presenta lo que el público no conoce, su estructura, su ritmo y su cierre. Con todo junto se escribe el
MANUAL DEL CANAL: reglas concretas con ejemplos literales que el guionista usa en cada vídeo.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import canales, config, deepseek, gemini, registro, tendencias, youtube

logger = logging.getLogger("studio4.aprender")
_lock = threading.Lock()
_estado: dict[str, dict[str, Any]] = {}

POR_REFERENTE = 3          # vídeos más vistos de cada referente
DEL_NICHO = 3              # y los más vistos de la semana en el nicho
PALABRAS_POR_VIDEO = 2200  # lo que se estudia de cada uno: el arranque entero y buena parte del cuerpo

SISTEMA_VIDEO = """Eres analista de guiones de YouTube, Shorts y TikTok. Te doy la transcripción de un vídeo que
funciona (con sus vistas). Explica CÓMO está contado, con frases LITERALES del vídeo como prueba. Nada genérico:
si no se ve en la transcripción, no lo digas. Devuelve JSON con:
{"gancho": "las 1-3 primeras frases literales", "por_que_engancha": "...",
 "voz": "quién habla y cómo (persona, registro, tuteo o vosotros, humor, complicidad) con 2 citas",
 "presenta_lo_desconocido": "cómo explica personas, juegos o hechos que el público no conoce, con una cita",
 "estructura": ["paso 1 ...", "paso 2 ...", "..."],
 "recursos": ["recurso concreto con cita (bucles abiertos, comparaciones, chistes, cifras, giros...)"],
 "cierre": "cómo termina, literal o casi", "temas": "de qué trata y qué ángulo elige"}"""

SISTEMA_MANUAL = """Eres jefe de guion de un canal de vídeo en español. Te doy el análisis de los vídeos que mejor
funcionan en su nicho. Escribe el MANUAL DEL CANAL: lo que su guionista debe hacer para contar como ellos (sin
copiar sus temas ni sus frases). El canal no sale en cámara: es voz en off sobre vídeo generado, así que lo que
hacen los presentadores (mirar a cámara, señalar) se traduce a voz y montaje. Todo concreto y con ejemplos
literales de los vídeos estudiados. Devuelve JSON con:
{"resumen": "3 frases: qué tienen en común los vídeos que funcionan",
 "voz": "cómo debe sonar el narrador (persona, registro, humor), con un ejemplo",
 "ganchos": [{"patron": "...", "ejemplo": "literal de un vídeo", "de": "canal"}],
 "presentar": "cómo presentar a quien el público no conoce, con ejemplo",
 "estructuras": [{"nombre": "...", "para": "corto o largo", "pasos": ["..."]}],
 "recursos": ["..."], "cierres": ["..."], "temas_que_funcionan": ["tema o ángulo con su dato de vistas"],
 "evitar": ["..."], "reglas": ["8 a 12 reglas imperativas para el guionista, concretas"]}"""


def _archivo(cid: str) -> Path:
    return config.PRODUCCIONES / f"manual_{cid}.json"


def leer(cid: str) -> dict[str, Any] | None:
    try:
        return json.loads(_archivo(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _generar_json(sistema: str, prompt: str, *, temperatura: float, detalle: str, produccion: str) -> dict[str, Any]:
    if deepseek.disponible():
        try:
            return deepseek.generar_json(sistema, prompt, temperatura=temperatura, detalle=detalle, produccion=produccion)
        except RuntimeError as e:
            logger.warning("%s: uso Gemini de reserva.", e)
    crudo = gemini.generar(prompt + "\n\nResponde solo con el JSON.", sistema=sistema, temperatura=temperatura,
                           detalle=f"{detalle} (reserva)", produccion=produccion, reserva=False)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    return json.loads(m.group(0) if m else crudo)


def transcripcion(url: str) -> dict[str, Any] | None:
    """Subtítulos de YouTube (los del autor o los automáticos en español) sin descargar el vídeo:
    {"texto", "palabras", "segundos", "ritmo"} o None si el vídeo no tiene."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "es.*,es",
                        "--sub-format", "json3", "-o", str(Path(d) / "%(id)s.%(ext)s"), url],
                       capture_output=True, text=True, timeout=180, check=False)
        archivos = sorted(Path(d).glob("*.json3"), key=lambda f: ("orig" not in f.name, f.name))
        if not archivos:
            return None
        eventos = json.loads(archivos[0].read_text(encoding="utf-8")).get("events", [])
    trozos = [(e.get("tStartMs", 0), "".join(s.get("utf8", "") for s in e["segs"])) for e in eventos if e.get("segs")]
    texto = " ".join(" ".join(t for _, t in trozos).split())
    if len(texto.split()) < 30:
        return None
    hablado = max(1.0, (trozos[-1][0] - trozos[0][0]) / 1000)
    return {"texto": texto, "palabras": len(texto.split()), "segundos": round(hablado),
            "ritmo": round(len(texto.split()) / hablado, 2)}


def elegir_videos(canal: dict[str, Any]) -> list[dict[str, Any]]:
    """Los vídeos que mejor funcionan: los más vistos de cada referente (cortos y largos) y lo más visto del nicho."""
    elegidos: list[dict[str, Any]] = []
    for usuario in canal.get("referentes") or []:
        try:
            r = tendencias.del_referente(usuario)
        except Exception as e:  # noqa: BLE001 - un referente que falla no para el estudio
            logger.warning("Referente %s: %s", usuario, e)
            continue
        por_vistas = sorted(r["videos"], key=lambda v: -v["vistas"])
        cortos = [v for v in por_vistas if v["segundos"] <= 90][:1]
        elegidos += cortos + [v for v in por_vistas if v not in cortos][:POR_REFERENTE - len(cortos)]
    if canal.get("nicho"):
        try:
            elegidos += sorted(tendencias._del_nicho(canal["nicho"]), key=lambda v: -v["vistas"])[:DEL_NICHO]
        except Exception as e:  # noqa: BLE001
            logger.warning("Nicho %s: %s", canal["nicho"], e)
    vistos, salida = set(), []
    for v in elegidos:
        if v["id"] not in vistos:
            vistos.add(v["id"])
            salida.append(v)
    return salida


def _analizar(v: dict[str, Any], t: dict[str, Any], cid: str) -> dict[str, Any]:
    palabras = t["texto"].split()
    muestra = " ".join(palabras[:PALABRAS_POR_VIDEO])
    if len(palabras) > PALABRAS_POR_VIDEO:   # y el final, para ver cómo cierra
        muestra += " […] " + " ".join(palabras[-250:])
    a = _generar_json(SISTEMA_VIDEO, f"Vídeo: «{v['titulo']}» de {v['canal']} · {v['vistas']:,} vistas · "
                      f"{v['segundos']} s · {t['ritmo']} palabras por segundo\n\nTRANSCRIPCIÓN:\n{muestra}".replace(",", "."),
                      temperatura=0.3, detalle=f"aprender · {v['canal']}", produccion=cid)
    return {**a, "titulo": v["titulo"], "canal": v["canal"], "vistas": v["vistas"], "segundos": v["segundos"],
            "ritmo": t["ritmo"], "url": v["url"]}


def estudiar(cid: str, avisar: Callable[[str, int], None] = lambda *_: None) -> dict[str, Any]:
    """Lee los vídeos que funcionan en el nicho del canal y escribe su manual. Usa DeepSeek o Gemini (gratis)."""
    canal = canales.obtener(cid)
    if not youtube.disponible():
        raise RuntimeError("Hace falta la conexión con YouTube (clave o cuenta) para buscar los vídeos del nicho.")
    if not deepseek.disponible() and not config.GEMINI_API_KEY:
        raise RuntimeError("Hace falta DEEPSEEK_API_KEY o GEMINI_API_KEY para estudiar los guiones.")
    if not canal.get("referentes") and not canal.get("nicho"):
        raise ValueError("Pon en el canal su nicho o algún canal referente para saber qué estudiar.")
    avisar("Buscando los vídeos que mejor funcionan en tu nicho", 5)
    videos = elegir_videos(canal)
    estudiados = []
    cache_ruta = config.PRODUCCIONES / f"aprender_cache_{cid}.json"   # un vídeo ya estudiado no se paga dos veces
    try:
        cache = json.loads(cache_ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    for i, v in enumerate(videos):
        avisar(f"Leyendo «{v['titulo'][:50]}» ({v['canal']})", 10 + int(70 * i / max(1, len(videos))))
        if v["id"] in cache:
            estudiados.append(cache[v["id"]])
            continue
        try:
            t = transcripcion(v["url"])
            if t:
                estudiados.append(_analizar(v, t, cid))
                cache[v["id"]] = estudiados[-1]
                tmp_c = cache_ruta.with_suffix(".tmp")
                tmp_c.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                tmp_c.replace(cache_ruta)
        except Exception as e:  # noqa: BLE001 - un vídeo sin subtítulos o que falla no para el resto
            logger.warning("No pude estudiar %s: %s", v["url"], e)
    if not estudiados:
        raise RuntimeError("Ningún vídeo del nicho tenía subtítulos que leer. Prueba con otros referentes.")
    avisar(f"Escribiendo el manual con {len(estudiados)} vídeos estudiados", 85)
    manual = _generar_json(
        SISTEMA_MANUAL, f"Canal: {canal['nombre']} · nicho: {canal.get('nicho') or '—'} · tono: {canal.get('tono') or '—'}\n\n"
        "ANÁLISIS DE LOS VÍDEOS QUE FUNCIONAN:\n" + json.dumps(estudiados, ensure_ascii=False),
        temperatura=0.4, detalle="manual del canal", produccion=cid)
    datos = {"canal": cid, "fecha": time.strftime("%Y-%m-%d %H:%M"), "manual": manual,
             "videos": [{k: e[k] for k in ("titulo", "canal", "vistas", "segundos", "ritmo", "url", "gancho")} for e in estudiados],
             "ritmo": round(sum(e["ritmo"] for e in estudiados) / len(estudiados), 2)}
    ruta = _archivo(cid)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)
    registro.apuntar("Aprender del nicho", f"{len(estudiados)} vídeos estudiados para {canal['nombre']}", unidad="manuales")
    return datos


SISTEMA_MODELO = """Eres jefe de guion. El autor del canal te da un VÍDEO MODELO: así quiere que sean sus vídeos.
Estudia cómo está hecho (con frases literales de la transcripción como prueba) y tradúcelo a instrucciones para su
guionista y su montaje. La nota del autor manda. No copies el tema ni las frases: copia la FORMA. Devuelve JSON:
{"resumen": "2-3 frases: qué es y por qué es el modelo", "narrador": "cómo habla el narrador (y si es voz sintética)",
 "voz": "instrucción breve para la voz en off (timbre, ritmo, emoción)", "estructura": ["paso 1", "..."],
 "ritmo": "cómo de rápido va y cómo pasa de un dato a otro", "visual": "qué se ve en pantalla y cómo se mezcla",
 "datos": "cómo presenta cifras, nombres y detalles", "cierre": "cómo termina", "reglas": ["6 a 10 reglas imperativas"]}"""


def estudiar_modelo(cid: str, url: str, nota: str = "") -> dict[str, Any]:
    """Un vídeo que el autor pone de ejemplo («así quiero mis vídeos»): se estudia y se guarda en el manual del canal;
    manda sobre todo lo demás al escribir y al locutar."""
    canal = canales.obtener(cid)
    t = transcripcion(url)
    texto = " ".join(t["texto"].split()[:PALABRAS_POR_VIDEO]) if t else "(sin subtítulos: guíate por la nota del autor)"
    a = _generar_json(SISTEMA_MODELO, f"Canal: {canal['nombre']} · nicho: {canal.get('nicho') or '—'}\n"
                      f"Vídeo modelo: {url}\nNOTA DEL AUTOR (manda): {nota or '—'}\n"
                      + (f"Ritmo medido: {t['ritmo']} palabras por segundo\n" if t else "") + f"\nTRANSCRIPCIÓN:\n{texto}",
                      temperatura=0.3, detalle="vídeo modelo", produccion=cid)
    modelo = {**a, "url": url, "nota": nota, "leido": bool(t), "fecha": time.strftime("%Y-%m-%d %H:%M")}
    d = leer(cid) or {"canal": cid, "fecha": "", "manual": {}, "videos": [], "ritmo": 0}
    d["modelos"] = [m for m in d.get("modelos", []) if m.get("url") != url] + [modelo]
    ruta = _archivo(cid)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)
    return modelo


def _sin_citas(texto: str) -> str:
    """Quita las frases literales entre comillas (son del otro canal) y los nombres propios de canales."""
    texto = re.sub(r"[“\"«][^”\"»]{0,240}[”\"»]", "…", str(texto))
    return re.sub(r"\s*(?:Prueba literal|Literal de referencia)[^.]*\.", "", texto).strip()


def voz_modelo(cid: str) -> str:
    """Cómo debe sonar la voz según los vídeos modelo del canal ("" si no hay)."""
    return " ".join(m.get("voz", "") for m in (leer(cid) or {}).get("modelos", []) if m.get("voz"))


def lanzar(cid: str) -> None:
    canales.obtener(cid)
    with _lock:
        if _estado.get(cid, {}).get("ocupado"):
            return
        _estado[cid] = {"ocupado": True, "fase": "Empezando", "error": ""}

    def correr():
        try:
            estudiar(cid, avisar=lambda f, _n=0: _estado[cid].update(fase=f))
            _estado[cid].update(ocupado=False, fase="")
        except Exception as e:  # noqa: BLE001
            logger.exception("Manual de %s", cid)
            _estado[cid].update(ocupado=False, error=str(e))
    threading.Thread(target=correr, name=f"studio4-manual-{cid}", daemon=True).start()


def estado(cid: str) -> dict[str, Any]:
    return {"datos": leer(cid), **_estado.get(cid, {"ocupado": False, "fase": "", "error": ""})}


def para_guion(cid: str) -> str:
    """El manual en texto, para el guionista ("" si el canal aún no ha estudiado su nicho)."""
    d = leer(cid)
    if not d:
        return ""
    previas = []
    for mo in d.get("modelos", []):   # el vídeo que el autor puso de ejemplo manda sobre todo lo demás
        # Es de OTRO canal: se toman sus ideas y su forma, nunca su nombre, su enlace ni sus frases.
        previas += ["VÍDEO MODELO (de otro canal; así quiere el autor sus vídeos). Toma solo IDEAS y FORMA: nunca "
                    "menciones a ese canal ni a su autor, no copies su contenido ni ninguna de sus frases:",
                    f"Nota del autor: {_sin_citas(mo.get('nota', ''))}", f"Qué es: {_sin_citas(mo.get('resumen', ''))}",
                    f"Narrador: {_sin_citas(mo.get('narrador', ''))}", f"Ritmo: {_sin_citas(mo.get('ritmo', ''))}",
                    f"Visual: {_sin_citas(mo.get('visual', ''))}", f"Datos: {_sin_citas(mo.get('datos', ''))}",
                    "Estructura: " + " → ".join(_sin_citas(x) for x in mo.get("estructura") or []),
                    f"Cierre: {_sin_citas(mo.get('cierre', ''))}"] + [f"- {_sin_citas(r)}" for r in mo.get("reglas") or []] + [""]
    if not d.get("manual"):
        return "\n".join(previas)
    m = d["manual"]
    lineas = previas + [f"MANUAL DEL CANAL (aprendido el {d['fecha']} de {len(d['videos'])} vídeos que funcionan en su nicho; "
              "manda sobre el estilo por defecto):", f"Lo que tienen en común: {m.get('resumen', '')}",
              f"Voz del narrador: {m.get('voz', '')}", f"Presentar lo desconocido: {m.get('presentar', '')}"]
    lineas += ["Ganchos que funcionan:"] + [f"- {g.get('patron', '')} (ej.: «{g.get('ejemplo', '')}»)" for g in m.get("ganchos", [])]
    lineas += ["Estructuras:"] + [f"- {e.get('nombre', '')} ({e.get('para', '')}): {' → '.join(e.get('pasos', []))}"
                                  for e in m.get("estructuras", [])]
    lineas += ["Recursos:"] + [f"- {r}" for r in m.get("recursos", [])]
    lineas += ["Cierres:"] + [f"- {c}" for c in m.get("cierres", [])]
    lineas += ["Evitar:"] + [f"- {e}" for e in m.get("evitar", [])]
    lineas += ["REGLAS:"] + [f"- {r}" for r in m.get("reglas", [])]
    return "\n".join(lineas)
