"""Las entregas finales, listas para publicar: vídeo completo (YouTube), Reels (el mejor momento) y Shorts
(los mejores recortes), todos subtitulados, cada uno con su portada y su texto para publicar.

Gemini (gratis) lee la línea de tiempo del vídeo y elige los momentos que se sostienen solos: empiezan con
gancho, se entienden sin el resto y terminan en algo que deja con ganas. Siempre en límites de escena.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from . import carpetas, config, gemini, medios, miniaturas, render

logger = logging.getLogger("studio4.entregas")


class Texto(BaseModel):
    titulo: str = Field(description="Título para la plataforma (máx. 70 caracteres para YouTube, 50 para vertical).")
    descripcion: str = Field(description="Descripción lista para pegar: gancho, 2-3 frases y llamada a la acción breve.")
    hashtags: list[str] = Field(description="4 a 8 hashtags con #.")


class Momento(Texto):
    desde: int = Field(description="Primera escena del recorte (número).")
    hasta: int = Field(description="Última escena del recorte (número, incluida).")
    gancho: str = Field(description="2 a 5 palabras para el rótulo del arranque del recorte.")


class Paquete(BaseModel):
    youtube: Texto
    reels: Momento
    shorts: list[Momento]


SISTEMA = """Eres editor de redes de un canal de divulgación. Te doy la línea de tiempo de un vídeo, escena a escena,
con sus segundos. Elige:
- REELS: el MEJOR momento único, de 15 a 45 segundos: arranca con algo que engancha y se entiende solo.
- SHORTS: 1 o 2 recortes de 20 a 58 segundos cada uno (distintos del de Reels si se puede), igual de autosuficientes.
Los recortes son escenas consecutivas (desde-hasta). Para cada pieza escribe título, descripción y hashtags
pensados para ESA plataforma (YouTube largo: SEO y curiosidad; Shorts y Reels: directo y emocional).
Español neutro, sin clickbait engañoso, sin emojis en exceso."""


def _duracion(p: dict, desde: int, hasta: int) -> float:
    t = p["voz"]["escenas"]
    return t[hasta - 1]["fin"] - t[desde - 1]["ini"]


def _ajustar(p: dict, m: dict, minimo: float, maximo: float) -> dict:
    """Corrige el rango si se sale de los límites de duración, ampliando o recortando por escenas."""
    n = len(p["escenas"])
    desde, hasta = max(1, int(m["desde"])), min(n, int(m["hasta"]))
    if hasta < desde:
        desde, hasta = hasta, desde
    while _duracion(p, desde, hasta) > maximo and hasta > desde:
        hasta -= 1
    while _duracion(p, desde, hasta) < minimo and hasta < n:
        hasta += 1
    return {**m, "desde": desde, "hasta": hasta, "duracion": round(_duracion(p, desde, hasta), 1)}


def elegir(p: dict[str, Any]) -> dict[str, Any]:
    linea = "\n".join(f"Escena {e['orden']} ({t['ini']:.1f}-{t['fin']:.1f} s): {e['texto_voz']}"
                      for e, t in zip(p["escenas"], p["voz"]["escenas"]))
    crudo = gemini.generar(f"Título del vídeo: {p.get('titulo') or p['tema']}\nDuración total: {p['voz']['duracion']:.0f} s\n\n{linea}",
                           sistema=SISTEMA, esquema=Paquete, temperatura=0.5, detalle="momentos para Reels y Shorts",
                           produccion=p["id"])
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    d = Paquete.model_validate_json(m.group(0) if m else crudo).model_dump()
    d["reels"] = _ajustar(p, d["reels"], 15, 45)
    shorts = [_ajustar(p, s, 20, 58) for s in d["shorts"][:2]]
    # Un Short no repite el tramo del Reels ni el de otro Short (si todos coinciden, queda uno).
    vistos = {(d["reels"]["desde"], d["reels"]["hasta"])}
    distintos = []
    for s in shorts:
        if (s["desde"], s["hasta"]) not in vistos:
            distintos.append(s)
            vistos.add((s["desde"], s["hasta"]))
    d["shorts"] = distintos or shorts[:1] or [_ajustar(p, d["reels"], 20, 58)]
    return d


def _portada(fuente: Path, destino: Path, plataforma: str, texto: str, foco: tuple[float, float] = (0.5, 0.5)) -> Path:
    resalte = max(texto.split(), key=len) if texto.split() else ""
    return miniaturas.componer(fuente, destino, plataforma, texto, resalte, *foco)


def preparar(p: dict[str, Any], base: Path, avisar: Callable[[str, int], None] = lambda *_: None) -> dict[str, Any]:
    if not p.get("final"):
        raise RuntimeError("Primero renderiza el vídeo completo (pestaña Render).")
    avisar("Gemini elige los mejores momentos y escribe los textos", 5)
    plan = elegir(p)
    salida = base / "entregas"
    salida.mkdir(exist_ok=True)
    completo = base / p["final"]["archivo"]
    vertical = p["formato"] == "vertical"

    # Fondo de las portadas: la imagen elegida en Miniaturas o, si no hay, un fotograma del vídeo.
    m = p.get("miniaturas") or {}
    if m.get("candidatos"):
        fondo = base / m["candidatos"][m["elegido"]]["archivo"]
        foco = (m.get("foco_x", 0.5), m.get("foco_y", 0.5))
    else:
        fondo = salida / "fondo.jpg"
        momento = min(p["voz"]["duracion"] * 0.3, max(0.0, medios.duracion(completo) - 0.5))   # siempre dentro del vídeo
        medios.ffmpeg("-ss", f"{momento:.2f}", "-i", str(completo), "-frames:v", "1", "-q:v", "2", str(fondo))
        foco = (0.5, 0.5)

    piezas: list[dict[str, Any]] = []
    # 1 · Vídeo completo
    plataforma_completo = "shorts" if vertical else "youtube"
    pref = re.sub(r"[^a-z0-9]+", "-", (p.get("titulo") or p["tema"]).lower()).strip("-")[:40] or "video"   # nombre del vídeo
    _portada(fondo, salida / f"{pref}_portada_completo.jpg", plataforma_completo, m.get("texto") or plan["reels"]["gancho"], foco)
    piezas.append({"clave": "completo", "plataforma": "Vídeo completo · YouTube" if not vertical else "Vídeo completo",
                   "video": p["final"]["archivo"], "portada": f"entregas/{pref}_portada_completo.jpg", **plan["youtube"],
                   "duracion": round(p["voz"]["duracion"], 1)})
    # 2 · Reels y 3 · Shorts (recortes verticales)
    recortes = [("reels", "Reels", plan["reels"])] + [(f"short_{i}", f"Short {i}", s) for i, s in enumerate(plan["shorts"], 1)]
    for k, (clave, nombre, mom) in enumerate(recortes):
        avisar(f"Montando {nombre} (escenas {mom['desde']}-{mom['hasta']})", 15 + int(75 * k / len(recortes)))
        destino = salida / f"{pref}_{clave}.mp4"
        render.recorte(p, base, mom["desde"], mom["hasta"], destino, 1080, 1920, gancho=mom["gancho"])
        _portada(fondo, salida / f"{pref}_portada_{clave}.jpg", "reels" if clave == "reels" else "shorts", mom["gancho"], foco)
        piezas.append({"clave": clave, "plataforma": nombre, "video": f"entregas/{pref}_{clave}.mp4",
                       "portada": f"entregas/{pref}_portada_{clave}.jpg",
                       "titulo": mom["titulo"], "descripcion": mom["descripcion"], "hashtags": mom["hashtags"],
                       "desde": mom["desde"], "hasta": mom["hasta"], "duracion": mom["duracion"]})

    # Copia ordenada a la carpeta de la producción, con las descripciones listas para pegar
    avisar("Guardando en tu carpeta de la producción", 95)
    archivos, textos = [], []
    for pz in piezas:
        archivos += [(base / pz["video"], f"{pz['plataforma']}.mp4"), (base / pz["portada"], f"{pz['plataforma']} - portada.jpg")]
        textos += [f"===== {pz['plataforma'].upper()} ({pz['duracion']} s) =====", f"Título: {pz['titulo']}", "",
                   pz["descripcion"], "", " ".join(pz["hashtags"]), "", ""]
    destino = carpetas.exportar(p, archivos, "\n".join(textos))
    return {"piezas": piezas, "carpeta": str(destino)}
