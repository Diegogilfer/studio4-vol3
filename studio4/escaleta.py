"""El puente con tu herramienta de Google Flow («Studio 4 · Guion a vídeo», ver PROMPT_FLOW_HERRAMIENTA.md).

1. «Escaleta para Flow»: cada frase del guion, con su duración real (la de la voz si ya está grabada), se reparte en
   escenas de 4, 6 u 8 s (lo que hace Veo) y se le añaden personajes, ambientes, acción, plano y cámara. Sale un
   JSON que se pega en la herramienta. Studio guarda qué escena va con qué frase.
2. «Importar de Flow»: el paquete que exporta la herramienta (escenas numeradas + escenas.json, sueltas o en un
   ZIP) entra como una fuente más del vídeo, y cada frase recibe sus escenas. Desde ahí, el acabado es el de
   siempre: voz, subtítulos, logo, música, paneles, Short, textos, miniatura y revisión.

Flow no se automatiza: el autor pega la escaleta y descarga el paquete con su cuenta y sus créditos.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from . import carpetas, extractor, medios, montaje

TOMAS = (4, 6, 8)   # duraciones que genera Veo
ESTILO = "Cinematográfico realista"
SISTEMA = """Eres director de fotografía de vídeos narrados para YouTube. Recibes las escenas de un vídeo (cada una con
el texto que dirá la voz en off) y devuelves SOLO un JSON con:
{"personajes": [{"nombre", "descripcion"}], "ambientes": [{"nombre", "descripcion"}],
 "escenas": [{"n", "personajes": [nombres], "ambiente": nombre, "accion", "plano", "camara"}]}
Reglas: personajes y ambientes inventados y coherentes con el guion (nunca personas reales ni personajes o marcas
con derechos de autor); la descripción de un personaje fija su cara, pelo, edad, complexión y ropa exacta con
colores; la de un ambiente, época, hora, luz, colores y elementos clave. Cada escena: una acción visual concreta
que ilustre su narración (sin texto ni letreros en pantalla), un plano (general, medio, primer plano, detalle) y
un movimiento de cámara sencillo. Escenas seguidas de la misma frase continúan la misma acción. En español."""


def tomas(d: float) -> list[int]:
    """Cuántas escenas de Veo cubren `d` segundos y de cuánto: las mínimas, parejas y que no se queden cortas."""
    n = max(1, math.ceil(d / 8 - 0.05))
    cada = d / n
    return [next((t for t in TOMAS if t >= cada - 0.25), 8)] * n


def _tiempos(p: dict[str, Any]) -> list[tuple[float, float]]:
    t = (p.get("voz") or {}).get("pausas", {}).get("tiempos") or montaje._tiempos_estimados(p)
    return [(0.0 if k == 0 else a, t[k + 1][0] if k + 1 < len(t) else b + 1.2) for k, (a, b) in enumerate(t)]


def _enriquecer(p: dict[str, Any], escenas: list[dict[str, Any]]) -> dict[str, Any]:
    """Personajes, ambientes y lo visual de cada escena, con Gemini (gratis; si no, su reserva)."""
    from . import gemini
    lista = "\n".join(f"{e['n']}. [{e['capitulo']}] {e['narracion']}" for e in escenas)
    crudo = gemini.generar(f"Título: {p['titulo']}\n\nESCENAS:\n{lista}", sistema=SISTEMA, temperatura=0.5,
                           detalle="escaleta para Flow", produccion=p["id"])
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    return json.loads(m.group(0) if m else crudo)


def exportar(mid: str, estilo: str = ESTILO, con_ia: bool = True) -> dict[str, Any]:
    """La escaleta para pegar en la herramienta de Flow (y la relación escena → frase, guardada en el vídeo)."""
    p = montaje.cargar(mid)
    if not p["frases"]:
        raise ValueError("El vídeo aún no tiene guion.")
    escenas = []
    for f, (a, b) in zip(p["frases"], _tiempos(p)):
        for j, dur in enumerate(tomas(b - a)):
            escenas.append({"n": len(escenas) + 1, "frase": f["n"], "capitulo": f"Capítulo {f['bloque'] + 1}",
                            "duracion": dur, "narracion": f["texto"] if j == 0 else f"(continúa) {f['texto']}",
                            "personajes": [], "ambiente": "", "accion": "", "plano": "", "camara": "", "dialogo": ""})
    personajes, ambientes = [], []
    if con_ia:
        try:
            extra = _enriquecer(p, escenas)
            personajes = [{"nombre": str(x.get("nombre", "")), "descripcion": str(x.get("descripcion", ""))}
                          for x in extra.get("personajes", []) if x.get("nombre")]
            ambientes = [{"nombre": str(x.get("nombre", "")), "descripcion": str(x.get("descripcion", ""))}
                         for x in extra.get("ambientes", []) if x.get("nombre")]
            por_n = {int(x.get("n", 0)): x for x in extra.get("escenas", []) if str(x.get("n", "")).isdigit()}
            for e in escenas:
                x = por_n.get(e["n"], {})
                e.update(personajes=[str(n) for n in x.get("personajes", [])], ambiente=str(x.get("ambiente", "")),
                         accion=str(x.get("accion", "")), plano=str(x.get("plano", "")), camara=str(x.get("camara", "")))
        except Exception:  # noqa: BLE001 - sin IA la escaleta sigue valiendo: la herramienta rellena lo visual
            montaje.logger.warning("Escaleta para Flow sin enriquecer", exc_info=True)
    escaleta = {"escaleta_studio4": 1, "titulo": p["titulo"], "estilo": estilo, "formato": "16:9",
                "personajes": personajes, "ambientes": ambientes,
                "escenas": [{k: v for k, v in e.items() if k != "frase"} for e in escenas]}
    montaje.modificar(mid, lambda q: q.update(escaleta={"hecha": time.strftime("%Y-%m-%d %H:%M"),
                                                       "escenas": [{"n": e["n"], "frase": e["frase"], "duracion": e["duracion"]}
                                                                   for e in escenas]}))
    return escaleta


# --- Importar el paquete que exporta la herramienta -----------------------------------------------------------------
def carpeta_importar() -> Path:
    c = carpetas.RAIZ_USUARIO / "Flow" / "Importar"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _paquete(origen: Path) -> tuple[Path, Path | None, Path | None]:
    """La carpeta con las escenas (descomprime el ZIP más reciente si hace falta), su escenas.json y la carpeta
    temporal del ZIP descomprimido (para borrarla al terminar)."""
    temporal = None
    if origen.is_dir():
        zips = sorted(origen.glob("*.zip"), key=lambda z: z.stat().st_mtime)
        sueltas = list(origen.rglob("escena_*.mp4"))
        if zips and (not sueltas or zips[-1].stat().st_mtime > max(s.stat().st_mtime for s in sueltas)):
            origen = zips[-1]
    if origen.suffix.lower() == ".zip":
        extractor.CACHE.mkdir(parents=True, exist_ok=True)
        temporal = Path(tempfile.mkdtemp(prefix="s4_flow_", dir=extractor.CACHE))
        with zipfile.ZipFile(origen) as z:
            z.extractall(temporal)
        origen = temporal
    jsons = sorted(origen.rglob("escenas*.json"), key=lambda f: f.stat().st_mtime)
    return origen, (jsons[-1] if jsons else None), temporal


def importar(mid: str, origen: str | Path | None = None) -> dict[str, Any]:
    """Las escenas de Flow como fuente del vídeo, ya repartidas por frases. Devuelve {fuente, escenas, frases}."""
    p = montaje.cargar(mid)
    carpeta_paq, archivo_json, temporal = _paquete(Path(origen) if origen else carpeta_importar())
    try:
        return _importar(mid, p, carpeta_paq, archivo_json)
    finally:
        if temporal:
            shutil.rmtree(temporal, ignore_errors=True)


def _importar(mid: str, p: dict[str, Any], carpeta_paq: Path, archivo_json: Path | None) -> dict[str, Any]:
    archivos = sorted(carpeta_paq.rglob("escena_*.mp4"), key=lambda f: int(re.findall(r"\d+", f.stem)[-1]))
    if not archivos:
        raise ValueError(f"No encuentro escenas (escena_001.mp4…) en {carpeta_paq}. Exporta desde la herramienta de "
                         f"Flow y deja el ZIP o las escenas en esa carpeta.")
    datos = json.loads(archivo_json.read_text(encoding="utf-8")) if archivo_json else {}
    por_n = {int(e["n"]): e for e in datos.get("escenas", []) if str(e.get("n", "")).isdigit()}
    fid = f"flow_{mid}"[:110]
    extractor.CACHE.mkdir(parents=True, exist_ok=True)
    trabajo = Path(tempfile.mkdtemp(prefix="s4_flowimp_", dir=extractor.CACHE))
    try:
        # cada escena a 1920x1080 y 30 fps, sin su sonido (la voz y el fondo los pone Studio), una tras otra
        normales, planos, t = [], [], 0.0
        for k, a in enumerate(archivos, 1):
            n = int(re.findall(r"\d+", a.stem)[-1])
            salida = trabajo / f"e{k:03d}.mp4"
            medios.ffmpeg("-i", str(a), "-an", "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                          "fps=30,setsar=1", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                          str(salida))
            d = medios.duracion(salida)
            planos.append({"n": k, "ini": round(t, 3), "fin": round(t + d, 3), "pobre": False, "escena": n})
            normales.append(salida)
            t += d
        lista = trabajo / "lista.txt"
        lista.write_text("".join(f"file '{x.as_posix()}'\n" for x in normales), encoding="utf-8")
        alta, baja = extractor.CACHE / f"{fid}_1080p.mp4", extractor.CACHE / f"{fid}_360p.mp4"
        medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(alta))
        medios.ffmpeg("-i", str(alta), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", str(baja))
        miniaturas = extractor.CACHE / f"{fid}_planos"
        shutil.rmtree(miniaturas, ignore_errors=True)
        miniaturas.mkdir()
        for pl in planos:
            medios.ffmpeg("-ss", f"{pl['ini'] + min(0.5, (pl['fin'] - pl['ini']) / 2):.3f}", "-i", str(baja),
                          "-frames:v", "1", str(miniaturas / f"{pl['n']:03d}.jpg"))
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
    meta = {"id": fid, "url": "", "titulo": f"Escenas de Google Flow · {p['titulo']}", "nombre": "Escenas de Flow",
            "canal": "Google Flow (generado con IA)", "desde": 0.0, "hasta": round(t, 3), "baja": baja.name,
            "alta": alta.name, "ia": True, "importada": time.strftime("%Y-%m-%d %H:%M:%S"), "planos": planos}
    (extractor.CACHE / f"{fid}.banco.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # cada frase recibe sus escenas: por la relación guardada al exportar; si no la hay, por orden
    relacion = {e["n"]: e["frase"] for e in (p.get("escaleta") or {}).get("escenas", [])}
    plano_de = {pl["escena"]: pl["n"] for pl in planos}
    por_frase: dict[int, list[int]] = {}
    if relacion:
        for n_esc, n_frase in relacion.items():
            if n_esc in plano_de:
                por_frase.setdefault(n_frase, []).append(plano_de[n_esc])
    else:
        for f, pl in zip(p["frases"], planos):
            por_frase[f["n"]] = [pl["n"]]

    def cambio(q):
        if fid not in q["fuentes"]:
            q["fuentes"].append(fid)
        for f in q["frases"]:
            nums = sorted(por_frase.get(f["n"], []))
            if nums and not f.get("panel"):
                f["clip"] = {"fuente": fid, "plano": nums[0], **({"mas": nums[1:4]} if len(nums) > 1 else {})}
        q.update(previa="", final=None, short=None, ia=True)
    montaje.modificar(mid, cambio)
    return {"fuente": fid, "escenas": len(planos), "frases": len(por_frase), "titulo": datos.get("titulo", "")}
