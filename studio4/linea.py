"""Línea de tiempo por pistas (el formato de cualquier editor de vídeo), corregida a partir del modelo del autor:

    {"tracks": [{"id", "type": "video", "clips": [{"start", "end", "source", "transform"}]},
                {"id", "type": "text",  "clips": [{"start", "end", "content", "animation"}]}]}

Correcciones (versión 1):
- Datos generales: versión, fps, ancho, alto y duración total.
- Cada clip lleva su `id`; los de vídeo y audio, el trozo del archivo que usan (`in`/`out`, en segundos) y su
  velocidad: `start`/`end` solo dicen dónde van en el vídeo, no qué parte de la fuente se ve.
- `transform` con unidades claras: x e y en proporción de la pantalla (0–1, centro = 0,5), escala, giro, opacidad
  y ancla.
- Texto con estilo (fuente, tamaño en px a 1080p, color, posición) y animación como objeto: entrada, salida y
  duración.
- Pistas de audio: voz, música (que se atenúa sola bajo la voz: `ducking`) y efectos.
- Transiciones de entrada por clip (la rejilla entre bloques).
- `validar` impide clips que se pisan en una misma pista, tiempos al revés o fuera del vídeo.

Studio genera la línea de tiempo de cada vídeo desde su montaje; el panel la dibuja y se guarda junto al vídeo.
"""

from __future__ import annotations

from typing import Any

from . import config

VERSION = 1
TIPOS = {"video", "text", "audio"}


def desde_montaje(p: dict[str, Any], fuentes: dict[str, dict[str, Any]], tiempos: list[tuple[float, float]] | None = None,
                  ancho: int = 1920, alto: int = 1080) -> dict[str, Any]:
    """La línea de tiempo de un vídeo del panel de montaje. Sin voz grabada, con tiempos estimados por palabras."""
    from . import montaje
    if tiempos is None:
        voz_ = p.get("voz") or {}
        tiempos = [tuple(x) for x in (voz_.get("pausas") or voz_).get("tiempos") or montaje._tiempos_estimados(p)]
    tramos = [(0.0 if k == 0 else a, tiempos[k + 1][0] if k + 1 < len(tiempos) else b + 1.2) for k, (a, b) in enumerate(tiempos)]
    video, texto, graficos = [], [], []
    for k, (f, (a, b)) in enumerate(zip(p["frases"], tramos)):
        nuevo_bloque = k > 0 and f["bloque"] != p["frases"][k - 1]["bloque"]
        if f.get("panel"):
            graficos.append({"id": f"panel-{f['n']}", "start": round(a, 3), "end": round(b, 3), "content": f["panel"].get("titulo", ""),
                             "items": f["panel"].get("items", []), "style": {"kind": "panel", "position": "center"},
                             "animation": {"in": "rise", "out": "fade", "duration": 0.45}})
        elif f.get("clip"):
            meta = fuentes.get(f["clip"]["fuente"]) or {}
            pl = (meta.get("planos") or [{}] * f["clip"]["plano"])[f["clip"]["plano"] - 1] or {}
            largo = max(0.3, float(pl.get("fin", 0)) - float(pl.get("ini", 0)))
            d = b - a
            video.append({"id": f"frase-{f['n']}", "start": round(a, 3), "end": round(b, 3),
                          "source": f"{f['clip']['fuente']}#{f['clip']['plano']}", "label": meta.get("nombre", ""),
                          "in": round(float(meta.get("desde", 0)) + float(pl.get("ini", 0)), 3),
                          "out": round(float(meta.get("desde", 0)) + float(pl.get("fin", 0)), 3),
                          "speed": round(max(0.5, min(1.0, largo / d)) if d > 0 else 1.0, 3),
                          "transform": {"x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0, "opacity": 1.0, "anchor": "center"},
                          **({"transitionIn": {"type": "grid", "duration": montaje.TRANSICION}} if nuevo_bloque else {})})
        elif f.get("imagen"):
            video.append({"id": f"frase-{f['n']}", "start": round(a, 3), "end": round(b, 3),
                          "source": f"imagen:{f['imagen']['archivo']}", "label": f["imagen"].get("credito", "Imagen"),
                          "in": 0.0, "out": round(b - a, 3), "speed": 1.0,
                          "transform": {"x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0, "opacity": 1.0, "anchor": "center"}})
        if f.get("rotulo"):
            texto.append({"id": f"rotulo-{f['n']}", "start": round(a + 0.2, 3), "end": round(min(b, a + 3.5), 3), "content": f["rotulo"],
                          "style": {"font": "Arial Bold", "size": 46, "color": "#ff3ea5", "position": "bottom-left"},
                          "animation": {"in": "fade", "out": "fade", "duration": 0.3}})
    total = round(tramos[-1][1], 3) if tramos else 0.0
    pistas = [{"id": "video-1", "type": "video", "clips": video},
              {"id": "graficos-1", "type": "text", "clips": graficos},
              {"id": "rotulos-1", "type": "text", "clips": texto}]
    if p.get("voz"):
        pistas.append({"id": "voz", "type": "audio", "clips": [{"id": "voz-1", "start": montaje.ENTRADA,
                       "end": round(montaje.ENTRADA + p["voz"]["duracion"], 3), "source": "voz.wav", "in": 0.0,
                       "out": round(p["voz"]["duracion"], 3), "gain": 1.0}]})
        musica = montaje._musica(p)
        if musica:   # solo si hay pistas en tu carpeta de música
            pistas.append({"id": "musica", "type": "audio", "ducking": "voz", "clips": [{"id": "musica-1", "start": 0.0, "end": total,
                           "source": musica.name, "in": 0.0, "out": total, "gain": config.VOLUMEN_MUSICA, "loop": True}]})
    return {"version": VERSION, "fps": config.FPS, "width": ancho, "height": alto, "duration": total, "tracks": pistas}


def validar(tl: dict[str, Any]) -> list[str]:
    """Los errores de una línea de tiempo (vacía si está bien)."""
    errores = []
    for k in ("version", "fps", "width", "height", "duration", "tracks"):
        if k not in tl:
            errores.append(f"Falta «{k}».")
    total = float(tl.get("duration") or 0)
    ids = set()
    for t in tl.get("tracks", []):
        if t.get("type") not in TIPOS:
            errores.append(f"Pista {t.get('id')}: tipo «{t.get('type')}» desconocido.")
        anterior = None
        for c in sorted(t.get("clips", []), key=lambda c: c.get("start", 0)):
            cid = c.get("id")
            if not cid or cid in ids:
                errores.append(f"Pista {t.get('id')}: clip sin id o repetido ({cid}).")
            ids.add(cid)
            a, b = float(c.get("start", -1)), float(c.get("end", -1))
            if not 0 <= a < b:
                errores.append(f"{cid}: empieza en {a} y acaba en {b}.")
            if total and b > total + 0.05:
                errores.append(f"{cid}: acaba en {b}, después del final del vídeo ({total}).")
            if anterior and a < anterior[1] - 1e-6:
                errores.append(f"{cid}: se pisa con {anterior[0]} en la pista {t.get('id')}.")
            if t.get("type") in ("video", "audio") and not (0 <= float(c.get("in", 0)) < float(c.get("out", 0))):
                errores.append(f"{cid}: el trozo de la fuente (in/out) está mal.")
            anterior = (cid, b)
    return errores
