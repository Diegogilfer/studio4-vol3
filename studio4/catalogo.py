"""El plano perfecto para cada frase: Studio 4 MIRA el material antes de montarlo.

1. Catalogar: Gemini (gratis con la clave de Google) ve la miniatura de cada plano de una fuente y apunta en una frase
   qué se ve (personaje, vehículo, lugar, acción) y si sirve (un menú, un logo, texto o negro no sirven). Se guarda en
   el banco: cada fuente se cataloga una vez y vale para todos los vídeos.
2. Emparejar: con las frases del guion y lo que se ve en cada plano, se elige para cada frase el plano que MEJOR
   enseña lo que dice, sin repetir y sin planos que no sirven. Si nada encaja, la frase queda sin plano (mejor eso que
   un plano que no tiene nada que ver): el panel la marca para elegir a mano, ponerle una imagen o un panel.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from . import extractor, gemini

logger = logging.getLogger("studio4.catalogo")
LOTE = 16   # miniaturas por petición a Gemini

SISTEMA_VER = """Eres documentalista de vídeo. Te doy miniaturas numeradas de planos de un vídeo («{titulo}»). Para cada
una di en UNA frase corta en español qué se ve: personaje o persona, vehículo, lugar, acción y momento (día/noche).
Sé concreto («Trevor pilota un caza sobre el desierto de noche»), no interpretes. Marca util=false si es un menú,
una pantalla de carga, un logo, texto a pantalla completa, negro o algo borroso. Devuelve solo JSON:
{{"planos": [{{"i": 1, "ve": "…", "util": true}}]}}"""

SISTEMA_EMPAREJAR = """Eres montador de vídeo. Te doy las frases de un guion y los planos disponibles, cada uno con su id y
lo que se ve. Para cada frase elige el plano que MEJOR enseña lo que dice la frase (mismo personaje, vehículo, lugar
o acción). Reglas: un plano solo una vez; no pongas el mismo tipo de imagen en dos frases seguidas si hay otra que
encaje; si NINGÚN plano tiene que ver con la frase, no la pongas (es mejor dejarla vacía que poner algo sin relación).
Devuelve solo JSON: {"asignaciones": [{"n": 1, "plano": "fuente:12", "por_que": "muy corto"}]}"""


def _miniatura(fid: str, n: int) -> bytes | None:
    f = extractor.CACHE / f"{fid}_planos" / f"{n:03d}.jpg"
    return f.read_bytes() if f.exists() else None


def catalogar(fid: str, avisar: Callable[[str], None] = lambda _t: None) -> int:
    """Apunta qué se ve en cada plano de la fuente que aún no lo tenga. Devuelve cuántos planos describió."""
    from . import montaje
    ruta = extractor.CACHE / f"{fid}.banco.json"
    meta = montaje.fuente(fid)
    pendientes = [pl for pl in meta["planos"] if "ve" not in pl and _miniatura(fid, pl["n"])]
    hechos = 0
    for k in range(0, len(pendientes), LOTE):
        lote = pendientes[k:k + LOTE]
        avisar(f"Mirando los planos de «{meta.get('nombre') or meta['titulo'][:40]}» ({k + len(lote)} de {len(pendientes)})")
        try:
            crudo = gemini.generar("Describe cada miniatura en orden. Responde solo con el JSON.",
                                   sistema=SISTEMA_VER.format(titulo=meta["titulo"][:90]), temperatura=0.2,
                                   detalle="catalogar planos", imagenes=[_miniatura(fid, pl["n"]) for pl in lote])
            m = re.search(r"\{.*\}", crudo, re.DOTALL)
            vistos = {int(x["i"]): x for x in json.loads(m.group(0) if m else crudo).get("planos") or [] if str(x.get("i", "")).isdigit()}
        except Exception as e:  # noqa: BLE001 - un lote que falla no frena el resto; se reintenta otro día
            logger.warning("Catalogar %s: %s", fid, e)
            continue
        for i, pl in enumerate(lote, 1):
            x = vistos.get(i)
            if x and str(x.get("ve", "")).strip():
                pl["ve"] = str(x["ve"]).strip()[:160]
                pl["util"] = x.get("util") is not False
                hechos += 1
        ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return hechos


def emparejar(mid: str, todas: bool = False, avisar: Callable[[str], None] = lambda _t: None) -> dict[str, int]:
    """Cada frase sin imagen (o todas) recibe el plano que mejor enseña lo que dice. Devuelve {puestas, sin_plano}."""
    from . import montaje
    p = montaje.cargar(mid)
    if not p["fuentes"]:
        raise ValueError("Primero añade material (paso 2).")
    for fid in p["fuentes"]:
        catalogar(fid, avisar)
    p = montaje.cargar(mid)
    usados = set() if todas else {f"{f['clip']['fuente']}:{f['clip']['plano']}" for f in p["frases"] if f.get("clip")}
    planos = {}
    for fid in p["fuentes"]:
        for pl in montaje.fuente(fid)["planos"]:
            pid = f"{fid}:{pl['n']}"
            if pl.get("ve") and pl.get("util", True) and not pl.get("pobre") and pid not in usados:
                planos[pid] = pl["ve"]
    frases = [f for f in p["frases"] if todas or not montaje.con_imagen(f)]
    if not frases or not planos:
        if frases and not any(pl.get("ve") for fid in p["fuentes"] for pl in montaje.fuente(fid)["planos"]):
            raise RuntimeError("No se pudo mirar ningún plano (Gemini no respondió).")
        return {"puestas": 0, "sin_plano": len(frases)}
    avisar("Eligiendo el plano de cada frase")
    alias = {f"P{k}": pid for k, pid in enumerate(planos, 1)}   # ids cortos: el modelo se equivoca menos
    lista_planos = "\n".join(f"{a} — {planos[pid]}" for a, pid in alias.items())
    lista_frases = "\n".join(f"{f['n']}. {f['texto']}" for f in frases)
    crudo = gemini.generar(f"FRASES:\n{lista_frases}\n\nPLANOS:\n{lista_planos}\n\nUsa los ids de plano tal cual (P1, P2…). Responde solo con el JSON.",
                           sistema=SISTEMA_EMPAREJAR, temperatura=0.2, detalle="emparejar planos", produccion=mid)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    asignaciones = json.loads(m.group(0) if m else crudo).get("asignaciones") or []
    elegidos: dict[int, str] = {}
    tomados: set[str] = set()
    for a in asignaciones:
        pid = alias.get(str(a.get("plano", "")).strip())
        n = int(a["n"]) if str(a.get("n", "")).isdigit() else 0
        if pid and pid not in tomados and n in {f["n"] for f in frases}:
            elegidos[n] = pid
            tomados.add(pid)

    def cambio(q):
        for f in q["frases"]:
            if f["n"] in elegidos:
                fid, n = elegidos[f["n"]].rsplit(":", 1)
                f["clip"] = {"fuente": fid, "plano": int(n), "elegido_por": "catalogo"}
            elif todas and f["n"] in {x["n"] for x in frases} and (f.get("clip") or {}).get("elegido_por") != "autor":
                f.pop("clip", None)
        q.update(previa="", final=None, short=None)
    montaje.modificar(mid, cambio)
    return {"puestas": len(elegidos), "sin_plano": len(frases) - len(elegidos)}
