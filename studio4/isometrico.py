"""Ilustraciones isométricas 3D hechas con CÓDIGO (sin modelo de imagen, gratis): maquetas de bloques, edificios,
pirámides, columnas, torres y luces, con ventanas que brillan, caras sombreadas y viñeta. La IA del estudio solo
describe la escena (qué objetos y dónde, en JSON); el dibujo lo hace este módulo en SVG y el navegador lo pasa a PNG.

Proyección isométrica: x pantalla = (x − y)·cos30, y pantalla = (x + y)·sin30 − z. Se dibuja de atrás adelante.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from pathlib import Path
from typing import Any

COS, SIN = math.cos(math.radians(30)), math.sin(math.radians(30))
TIPOS = ("caja", "piramide", "cilindro", "esfera", "plataforma", "luz")
MAX_OBJETOS = 30
PALETAS = {   # fondo, suelo, cuerpo, acento (luces y ventanas)
    "noche": ("#07080d", "#11131c", "#1d2233", "#ffb547"),
    "neon": ("#06040f", "#120d24", "#22183f", "#ff3ea5"),
    "desierto": ("#120c07", "#2a1d10", "#6b4a2b", "#ffd27a"),
    "hielo": ("#05090f", "#0e1824", "#1f3346", "#6fe7ff"),
    "bosque": ("#050b07", "#0f1d13", "#1f3a26", "#c9ff7a"),
}


def _hex(c: str, defecto: str) -> str:
    return c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else defecto


def _mezcla(c: str, f: float) -> str:
    """Aclara (f > 1) u oscurece (f < 1) un color: así cada cara tiene su luz."""
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v * f))) for v in (r, g, b)))


def validar(escena: dict[str, Any]) -> dict[str, Any]:
    """La escena que llega de la IA, saneada: tipos conocidos, números acotados, colores válidos, como mucho 30 objetos."""
    paleta = escena.get("paleta") if escena.get("paleta") in PALETAS else "noche"
    fondo, suelo, cuerpo, acento = PALETAS[paleta]
    objetos = []
    for o in (escena.get("objetos") or [])[:MAX_OBJETOS]:
        if not isinstance(o, dict) or o.get("tipo") not in TIPOS:
            continue
        num = lambda k, d, lo, hi: max(lo, min(hi, float(o.get(k, d)) if isinstance(o.get(k, d), (int, float)) else d))  # noqa: E731
        objetos.append({"tipo": o["tipo"], "x": num("x", 0, -2, 14), "y": num("y", 0, -2, 14), "z": num("z", 0, 0, 10),
                        "w": num("w", 1, 0.2, 8), "d": num("d", 1, 0.2, 8), "h": num("h", 1, 0.1, 12),
                        "color": _hex(o.get("color"), cuerpo), "ventanas": bool(o.get("ventanas"))})
    return {"paleta": paleta, "fondo": fondo, "suelo": suelo, "acento": _hex(escena.get("acento"), acento), "objetos": objetos}


def _p(x: float, y: float, z: float) -> tuple[float, float]:
    return (x - y) * COS, (x + y) * SIN - z


def _poligono(puntos: list[tuple[float, float]], relleno: str, extra: str = "") -> str:
    return f'<polygon points="{" ".join(f"{a:.3f},{b:.3f}" for a, b in puntos)}" fill="{relleno}" {extra}/>'


def _caja(o: dict[str, Any], acento: str, azar: random.Random) -> str:
    x, y, z, w, d, h, c = o["x"], o["y"], o["z"], o["w"], o["d"], o["h"], o["color"]
    arriba = [_p(x, y, z + h), _p(x + w, y, z + h), _p(x + w, y + d, z + h), _p(x, y + d, z + h)]
    derecha = [_p(x + w, y, z), _p(x + w, y + d, z), _p(x + w, y + d, z + h), _p(x + w, y, z + h)]
    izquierda = [_p(x, y + d, z), _p(x + w, y + d, z), _p(x + w, y + d, z + h), _p(x, y + d, z + h)]
    trazo = 'stroke="#000" stroke-opacity=".25" stroke-width=".02"'
    s = _poligono(izquierda, _mezcla(c, 0.75), trazo) + _poligono(derecha, _mezcla(c, 0.55), trazo) + _poligono(arriba, _mezcla(c, 1.35), trazo)
    if o["ventanas"] and h >= 0.8:
        pisos = max(1, int(h / 0.45))
        for cara, largo, punto in ((derecha, d, lambda u, v: _p(x + w, y + u, z + v)), (izquierda, w, lambda u, v: _p(x + u, y + d, z + v))):
            cols = max(1, int(largo / 0.4))
            for i in range(cols):
                for j in range(pisos):
                    if azar.random() < 0.45:
                        continue
                    u0, v0 = (i + 0.25) * largo / cols, (j + 0.3) * h / pisos
                    du, dv = 0.5 * largo / cols, 0.4 * h / pisos
                    luz = acento if azar.random() < 0.7 else _mezcla(acento, 0.6)
                    s += _poligono([punto(u0, v0), punto(u0 + du, v0), punto(u0 + du, v0 + dv), punto(u0, v0 + dv)],
                                   luz, 'filter="url(#brillo)"')
    return s


def _piramide(o: dict[str, Any]) -> str:
    x, y, z, w, d, h, c = o["x"], o["y"], o["z"], o["w"], o["d"], o["h"], o["color"]
    cima = _p(x + w / 2, y + d / 2, z + h)
    return (_poligono([_p(x, y + d, z), _p(x + w, y + d, z), cima], _mezcla(c, 0.8))
            + _poligono([_p(x + w, y, z), _p(x + w, y + d, z), cima], _mezcla(c, 0.55)))


def _cilindro(o: dict[str, Any]) -> str:
    x, y, z, w, h, c = o["x"], o["y"], o["z"], o["w"], o["h"], o["color"]
    cx, cy = _p(x + w / 2, y + w / 2, z)
    _, cy_arriba = _p(x + w / 2, y + w / 2, z + h)
    rx, ry = w / 2 * 2 * COS * 0.82, w / 2 * 2 * SIN * 0.82
    return (f'<path d="M{cx - rx:.3f},{cy:.3f} L{cx - rx:.3f},{cy_arriba:.3f} L{cx + rx:.3f},{cy_arriba:.3f} '
            f'L{cx + rx:.3f},{cy:.3f} A{rx:.3f},{ry:.3f} 0 0 1 {cx - rx:.3f},{cy:.3f} Z" fill="{_mezcla(c, 0.7)}"/>'
            f'<ellipse cx="{cx:.3f}" cy="{cy_arriba:.3f}" rx="{rx:.3f}" ry="{ry:.3f}" fill="{_mezcla(c, 1.3)}"/>')


def _esfera(o: dict[str, Any]) -> str:
    cx, cy = _p(o["x"] + o["w"] / 2, o["y"] + o["w"] / 2, o["z"] + o["w"] / 2)
    return (f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{o["w"] / 2 * 1.1:.3f}" fill="url(#esfera)" '
            f'style="color:{o["color"]}"/><circle cx="{cx:.3f}" cy="{cy:.3f}" r="{o["w"] / 2 * 1.1:.3f}" fill="{o["color"]}" opacity=".55"/>')


def _luz(o: dict[str, Any], acento: str) -> str:
    cx, cy = _p(o["x"], o["y"], o["z"])
    r = max(0.3, o["w"])
    return f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" fill="{_hex(o["color"], acento)}" opacity=".9" filter="url(#halo)"/>'


def svg(escena: dict[str, Any], ancho: int = 1920, alto: int = 1080, semilla: str = "") -> str:
    """La escena (ya validada) en SVG, encuadrada y centrada en el lienzo."""
    e = validar(escena)
    azar = random.Random(hashlib.sha1((semilla or str(e)).encode()).hexdigest())
    # primero lo que está más abajo (el suelo elevado antes que lo que lleva encima), luego de atrás adelante
    objs = sorted(e["objetos"], key=lambda o: (o["z"], (o["x"] + o["w"] / 2) + (o["y"] + o["d"] / 2)))
    # el suelo: una losa bajo todo lo que hay
    if objs:
        x0 = min(o["x"] for o in objs) - 1.5
        y0 = min(o["y"] for o in objs) - 1.5
        x1 = max(o["x"] + o["w"] for o in objs) + 1.5
        y1 = max(o["y"] + o["d"] for o in objs) + 1.5
    else:
        x0 = y0 = 0
        x1 = y1 = 8
    suelo = {"tipo": "plataforma", "x": x0, "y": y0, "z": -0.4, "w": x1 - x0, "d": y1 - y0, "h": 0.4, "color": e["suelo"], "ventanas": False}
    cuerpo = _caja(suelo, e["acento"], azar)
    for i in range(int(x1 - x0) + 1):   # rejilla tenue sobre el suelo
        a, b = _p(x0 + i, y0, 0), _p(x0 + i, y1, 0)
        cuerpo += f'<line x1="{a[0]:.3f}" y1="{a[1]:.3f}" x2="{b[0]:.3f}" y2="{b[1]:.3f}" stroke="{e["acento"]}" stroke-opacity=".08" stroke-width=".02"/>'
    for i in range(int(y1 - y0) + 1):
        a, b = _p(x0, y0 + i, 0), _p(x1, y0 + i, 0)
        cuerpo += f'<line x1="{a[0]:.3f}" y1="{a[1]:.3f}" x2="{b[0]:.3f}" y2="{b[1]:.3f}" stroke="{e["acento"]}" stroke-opacity=".08" stroke-width=".02"/>'
    for o in objs:
        if o["tipo"] in ("caja", "plataforma"):
            cuerpo += _caja(o, e["acento"], azar)
        elif o["tipo"] == "piramide":
            cuerpo += _piramide(o)
        elif o["tipo"] == "cilindro":
            cuerpo += _cilindro(o)
        elif o["tipo"] == "esfera":
            cuerpo += _esfera(o)
        elif o["tipo"] == "luz":
            cuerpo += _luz(o, e["acento"])
    # encuadre: todos los puntos proyectados caben con margen
    pts = [_p(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (-0.4,)]
    pts += [_p(o["x"] + dx, o["y"] + dy, o["z"] + o["h"]) for o in objs for dx in (0, o["w"]) for dy in (0, o["d"])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    escala = min(ancho * 0.8 / max(w, 0.1), alto * 0.8 / max(h, 0.1))
    tx = ancho / 2 - (min(xs) + w / 2) * escala
    ty = alto / 2 - (min(ys) + h / 2) * escala
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}">
<defs>
  <filter id="brillo" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation=".05" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="halo" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation=".35"/></filter>
  <radialGradient id="esfera" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="currentColor"/></radialGradient>
  <radialGradient id="vineta" cx="50%" cy="50%" r="75%"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".75"/></radialGradient>
  <radialGradient id="fondo" cx="50%" cy="40%" r="80%"><stop offset="0" stop-color="{_mezcla(e['fondo'], 2.4)}"/><stop offset="1" stop-color="{e['fondo']}"/></radialGradient>
</defs>
<rect width="100%" height="100%" fill="url(#fondo)"/>
<g transform="translate({tx:.2f},{ty:.2f}) scale({escala:.3f})">{cuerpo}</g>
<rect width="100%" height="100%" fill="url(#vineta)"/>
</svg>"""


def dibujar(escena: dict[str, Any], destino: Path, ancho: int = 1920, alto: int = 1080, semilla: str = "") -> Path:
    """La escena a PNG con el navegador del PC (como las miniaturas)."""
    from playwright.sync_api import sync_playwright
    destino.parent.mkdir(parents=True, exist_ok=True)
    html = destino.with_suffix(".html")
    html.write_text(f'<!doctype html><body style="margin:0;background:#000">{svg(escena, ancho, alto, semilla)}</body>', encoding="utf-8")
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ancho, "height": alto})
        pag.goto(html.as_uri())
        pag.screenshot(path=str(destino), type="png")
        nav.close()
    html.unlink(missing_ok=True)
    return destino


def escena_de_reserva(texto: str) -> dict[str, Any]:
    """Sin IA: una maqueta de ciudad nocturna distinta para cada frase (por su huella)."""
    azar = random.Random(hashlib.sha1(texto.encode("utf-8")).hexdigest())
    objetos = []
    for i in range(4):
        for j in range(4):
            if azar.random() < 0.25:
                continue
            h = azar.choice([1.2, 2, 3, 4.5, 6])
            objetos.append({"tipo": "caja", "x": i * 2.2, "y": j * 2.2, "z": 0, "w": 1.6, "d": 1.6, "h": h, "ventanas": h > 1.5})
    objetos.append({"tipo": "luz", "x": 4, "y": 4, "z": 7, "w": 1.2})
    return {"paleta": azar.choice(list(PALETAS)), "objetos": objetos}


SISTEMA = """Diseñas maquetas isométricas 3D minimalistas (estilo diorama de bloques con luces) que ilustran una frase
de un vídeo. Usa SOLO estos objetos: caja (edificios, muros, mesas, cofres), piramide, cilindro (torres, columnas,
árboles), esfera (planetas, cúpulas, cabezas), plataforma (suelos, islas, escalones), luz (brillos, faroles, soles).
Coordenadas en una rejilla de 0 a 12 (x, y en el suelo; z hacia arriba); tamaños w, d, h entre 0.2 y 8. Entre 6 y 25
objetos, bien apoyados (z = altura de lo que tienen debajo). Nada de texto, logos ni personajes reales.
Paletas: noche, neon, desierto, hielo, bosque. Devuelve solo JSON:
{"paleta": "...", "objetos": [{"tipo": "caja", "x": 0, "y": 0, "z": 0, "w": 2, "d": 2, "h": 4, "color": "#2a3550", "ventanas": true}]}"""


def escena_para(frase: str, contexto: str = "", produccion: str = "") -> dict[str, Any]:
    """La escena de una frase, diseñada por la IA del estudio; si no hay IA o falla, la de reserva."""
    from . import deepseek
    if deepseek.disponible():
        try:
            d = deepseek.generar_json(SISTEMA, f"VÍDEO: {contexto[:300]}\nFRASE: {frase}", temperatura=0.6,
                                      detalle="escena isométrica", produccion=produccion)
            if validar(d)["objetos"]:
                return d
        except (RuntimeError, ValueError):
            pass
    return escena_de_reserva(frase)
