"""Escenas gratis: tarjetas de diseño editorial para las escenas que no tienen clip (sin Flow y sin API de pago).

Gemini (gratis) escribe para cada escena un rótulo corto (antetítulo, titular con su palabra clave, un dato o una
cifra) y Edge, en tu PC, dibuja la tarjeta con las letras del estudio sobre un fondo de luces de neón con grano.
En el render se animan con un acercamiento lento. Todo es original: nada de capturas de juegos ni de terceros.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import config, gemini

logger = logging.getLogger("studio4.tarjetas")

EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
# Paletas nocturnas de neón (fondo 1, fondo 2, acento, segunda luz): rotan escena a escena para dar ritmo.
PALETAS = [("#120a24", "#2a0f3d", "#ff4fa3", "#ff9f43"), ("#071423", "#0d2a3f", "#29d3ff", "#a066ff"),
           ("#1a0912", "#3a0d22", "#ff5e5b", "#ffd166"), ("#081a14", "#0f3326", "#3cf0a0", "#29d3ff")]


class Tarjeta(BaseModel):
    tipo: str = Field(description="«titular» (lo normal), «cifra» (si la escena gira en torno a un número) o «cita» (una frase dicha).")
    antetitulo: str = Field(description="1 a 3 palabras en mayúsculas que sitúan (p. ej. «GTA 6», «LEONIDA»).")
    titular: str = Field(description="2 a 6 palabras que resumen lo que se ve o se dice. Sin punto final.")
    clave: str = Field(description="La palabra del titular que va resaltada (tal cual aparece en el titular).")
    dato: str = Field(default="", description="Un dato o matiz breve (máx. 14 palabras) o vacío.")
    cifra: str = Field(default="", description="Solo si tipo=cifra: el número corto (p. ej. «2026», «1.º», «90 %»).")


class Tarjetas(BaseModel):
    tarjetas: list[Tarjeta]


def disenar(escenas: list[dict[str, Any]], tema: str, produccion: str = "") -> list[dict[str, Any]]:
    """Una tarjeta por escena, en orden (una sola llamada a Gemini)."""
    lista = "\n".join(f"{e['orden']}. «{e['texto_voz']}»" for e in escenas)
    crudo = gemini.generar(
        f"Tema del vídeo: {tema}\n\nEscenas (lo que dice la voz en cada una):\n{lista}\n\n"
        "Para CADA escena, en orden, escribe la tarjeta visual que acompaña a la voz: corta, con impacto, en español. "
        "No repitas la frase de la voz: resúmela o da el dato clave. Varía el tipo (no más de 2 cifras seguidas).",
        esquema=Tarjetas, temperatura=0.5, detalle="tarjetas de escena", produccion=produccion)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    salida = [t.model_dump() for t in Tarjetas.model_validate_json(m.group(0) if m else crudo).tarjetas]
    while len(salida) < len(escenas):   # si faltara alguna, la escena lleva su propio texto como titular
        e = escenas[len(salida)]
        salida.append({"tipo": "titular", "antetitulo": "", "titular": " ".join(e["texto_voz"].split()[:6]), "clave": "", "dato": "", "cifra": ""})
    return salida[:len(escenas)]


def _uri(ruta: Path) -> str:
    return ruta.resolve().as_uri()


def html_tarjeta(t: dict[str, Any], n: int, ancho: int, alto: int) -> str:
    f1, f2, acento, luz = PALETAS[(n - 1) % len(PALETAS)]
    vertical = alto > ancho
    base = min(ancho, alto)
    esc = lambda s: html.escape(str(s or ""))  # noqa: E731
    titular = esc(t["titular"])
    clave = esc(t.get("clave", "")).strip()
    if clave and clave in titular:
        titular = titular.replace(clave, f"<em>{clave}</em>", 1)
    fuentes = config.WEB / "fuentes"
    grande = f'<div class="cifra">{esc(t["cifra"])}</div>' if t.get("tipo") == "cifra" and t.get("cifra") else ""
    comillas = '<div class="comillas">“</div>' if t.get("tipo") == "cita" else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Serif; src: url("{_uri(fuentes / 'instrument-serif-latin-normal.woff2')}"); }}
@font-face {{ font-family: Serif; font-style: italic; src: url("{_uri(fuentes / 'instrument-serif-latin-italic.woff2')}"); }}
@font-face {{ font-family: Sans; src: url("{_uri(fuentes / 'geist-latin-wght-normal.woff2')}"); font-weight: 100 900; }}
html, body {{ margin: 0; width: {ancho}px; height: {alto}px; overflow: hidden; }}
body {{ position: relative; background: radial-gradient(120% 80% at 20% 10%, {f2}, {f1} 70%); color: #f4f1ff; font-family: Sans, sans-serif; }}
.luz1, .luz2 {{ position: absolute; border-radius: 50%; filter: blur({int(base * .09)}px); opacity: .55; }}
.luz1 {{ width: {int(base * .9)}px; height: {int(base * .9)}px; left: -{int(base * .25)}px; top: {int(alto * .05)}px; background: {acento}; }}
.luz2 {{ width: {int(base * .8)}px; height: {int(base * .8)}px; right: -{int(base * .3)}px; bottom: {int(alto * .12)}px; background: {luz}; opacity: .4; }}
.rejilla {{ position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
  linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px); background-size: {int(base / 12)}px {int(base / 12)}px;
  -webkit-mask: linear-gradient(180deg, #000, transparent 75%); }}
.grano {{ position: absolute; inset: 0; opacity: .12; mix-blend-mode: overlay; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='g'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/></filter><rect width='100%' height='100%' filter='url(%23g)'/></svg>"); }}
.velo {{ position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,.55)); }}
.caja {{ position: absolute; left: {int(ancho * .12)}px; right: {int(ancho * .12)}px; top: {int(alto * (.15 if vertical else .17))}px; }}
.ante {{ display: inline-block; font: 600 {int(base * .028)}px/1 Sans; letter-spacing: .22em; text-transform: uppercase; color: {acento};
  padding: {int(base * .014)}px {int(base * .026)}px; border: 2px solid {acento}; border-radius: 999px; }}
.num {{ position: absolute; right: {int(ancho * .12)}px; top: {int(alto * .08)}px; font: italic 400 {int(base * .2)}px/1 Serif;
  color: transparent; -webkit-text-stroke: 2px rgba(255,255,255,.18); }}
.cifra {{ font: 400 {int(base * (.36 if vertical else .3))}px/.9 Serif; color: {acento}; margin-top: {int(base * .04)}px;
  text-shadow: 0 0 {int(base * .06)}px {acento}66; }}
.comillas {{ font: 400 {int(base * .3)}px/.6 Serif; color: {acento}; margin-top: {int(base * .06)}px; }}
h1 {{ font: 400 {int(base * (.12 if vertical else .1))}px/1 Serif; margin: {int(base * .035)}px 0 0; letter-spacing: -.01em; }}
h1 em {{ font-style: italic; color: {acento}; text-shadow: 0 0 {int(base * .05)}px {acento}55; }}
p {{ font: 400 {int(base * .042)}px/1.4 Sans; color: rgba(244,241,255,.82); margin: {int(base * .04)}px 0 0; max-width: 92%; }}
.marca {{ position: absolute; left: {int(ancho * .12)}px; bottom: {int(alto * .09)}px; font: 600 {int(base * .022)}px Sans;
  letter-spacing: .3em; color: rgba(255,255,255,.45); }}
</style></head><body><div class="luz1"></div><div class="luz2"></div><div class="rejilla"></div><div class="velo"></div>
<div class="num">{n:02d}</div>
<div class="caja">{f'<span class="ante">{esc(t.get("antetitulo"))}</span>' if t.get("antetitulo") else ""}{grande}{comillas}
<h1>{titular}</h1>{f"<p>{esc(t.get('dato'))}</p>" if t.get("dato") else ""}</div>
<div class="marca">FOURLEVEL</div><div class="grano"></div></body></html>"""


def html_caratula(titulo: str, subtitulo: str, marca: str, arriba: Path, abajo: Path, ancho: int, alto: int) -> str:
    """Carátula de entrada: dos imágenes del vídeo (arriba el origen, abajo el desenlace) y el título en medio."""
    _, _, acento, _ = PALETAS[0]
    base = min(ancho, alto)
    fuentes = config.WEB / "fuentes"
    esc = lambda s: html.escape(str(s or ""))  # noqa: E731
    palabras = esc(titulo).split()
    if len(palabras) > 1:   # la última palabra del título, en cursiva y con el color de acento
        palabras[-1] = f"<em>{palabras[-1]}</em>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Serif; src: url("{_uri(fuentes / 'instrument-serif-latin-normal.woff2')}"); }}
@font-face {{ font-family: Serif; font-style: italic; src: url("{_uri(fuentes / 'instrument-serif-latin-italic.woff2')}"); }}
@font-face {{ font-family: Sans; src: url("{_uri(fuentes / 'geist-latin-wght-normal.woff2')}"); font-weight: 100 900; }}
html, body {{ margin: 0; width: {ancho}px; height: {alto}px; overflow: hidden; background: #08060f; color: #f4f1ff; }}
.foto {{ position: absolute; left: 0; right: 0; height: 52%; background-size: cover; background-position: center 30%; }}
.arriba {{ top: 0; background-image: url("{_uri(arriba)}"); filter: grayscale(1) contrast(1.1);
  -webkit-mask: linear-gradient(180deg, #000 60%, transparent); }}
.abajo {{ bottom: 0; background-image: url("{_uri(abajo)}"); -webkit-mask: linear-gradient(0deg, #000 60%, transparent); }}
.velo {{ position: absolute; inset: 0; background: radial-gradient(90% 26% at 50% 50%, rgba(8,6,15,.92), rgba(8,6,15,0)); }}
.centro {{ position: absolute; left: {int(ancho * .12)}px; right: {int(ancho * .12)}px; top: 50%; transform: translateY(-50%); text-align: center; }}
.marca {{ display: inline-block; font: 600 {int(base * .026)}px/1 Sans; letter-spacing: .32em; color: {acento};
  padding: {int(base * .014)}px {int(base * .03)}px; border: 2px solid {acento}; border-radius: 999px; }}
h1 {{ font: 400 {int(base * .14)}px/.95 Serif; margin: {int(base * .035)}px 0 0; letter-spacing: -.01em; text-shadow: 0 4px 30px #000; }}
h1 em {{ color: {acento}; text-shadow: 0 0 {int(base * .05)}px {acento}66; }}
p {{ font: 400 {int(base * .036)}px/1.35 Sans; color: rgba(244,241,255,.86); margin: {int(base * .03)}px auto 0; max-width: 92%; }}
</style></head><body><div class="foto arriba"></div><div class="foto abajo"></div><div class="velo"></div>
<div class="centro"><span class="marca">{esc(marca.upper())}</span><h1>{" ".join(palabras)}</h1>{f"<p>{esc(subtitulo)}</p>" if subtitulo else ""}</div>
</body></html>"""


def dibujar_caratula(p: dict[str, Any], carpeta: Path, marca: str) -> Path:
    """La carátula de la producción, con la imagen de la primera escena y la de la última con personaje."""
    from . import medios
    fmt = config.FORMATOS[p["formato"]]

    def imagen_de(esc: dict[str, Any], nombre: str) -> Path:
        toma = esc["tomas"][esc["elegida"]]
        ruta = carpeta / (toma.get("original") or toma["archivo"])   # la foto de archivo, sin su marco
        if toma["tipo"] == "video":
            foto = carpeta / "render" / f"{nombre}.jpg"
            medios.ffmpeg("-y", "-ss", "0.5", "-i", str(ruta), "-frames:v", "1", "-q:v", "2", str(foto))
            return foto
        return ruta
    elegidas = [e for e in p["escenas"] if e.get("elegida") is not None]
    if not elegidas:
        raise RuntimeError("Sin escenas con toma no hay carátula.")
    finales = [e for e in elegidas if e["tomas"][e["elegida"]].get("origen") in ("api", "flow", "subida")] or elegidas
    titulo, _, resto = (p.get("titulo") or p["tema"]).partition(":")
    (carpeta / "render").mkdir(exist_ok=True)
    destino = carpeta / "render" / "caratula.png"
    with tempfile.TemporaryDirectory() as d:
        pagina = Path(d) / "caratula.html"
        pagina.write_text(html_caratula(titulo.strip(), resto.strip()[:1].upper() + resto.strip()[1:], marca,
                                        imagen_de(elegidas[0], "caratula_arriba"), imagen_de(finales[-1], "caratula_abajo"),
                                        fmt["ancho"], fmt["alto"]), encoding="utf-8")
        subprocess.run([_edge(), "--headless=new", f"--user-data-dir={Path(d) / 'perfil'}", "--no-first-run",
                        "--no-default-browser-check", "--disable-extensions", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={fmt['ancho']},{fmt['alto']}", "--virtual-time-budget=2500",
                        "--allow-file-access-from-files", f"--screenshot={destino}", pagina.as_uri()],
                       capture_output=True, timeout=90, check=False)
    if not destino.exists() or destino.stat().st_size < 10_000:
        raise RuntimeError("No se pudo dibujar la carátula.")
    return destino


def _edge() -> str:
    for ruta in EDGE:
        if Path(ruta).exists():
            return ruta
    raise RuntimeError("Hace falta Microsoft Edge o Google Chrome para dibujar las tarjetas.")


def dibujar(t: dict[str, Any], n: int, ancho: int, alto: int, destino: Path, marca: str = "") -> Path:
    with tempfile.TemporaryDirectory() as d:
        pagina = Path(d) / "tarjeta.html"
        pagina.write_text(html_tarjeta(t, n, ancho, alto).replace("FOURLEVEL", html.escape(marca.upper())), encoding="utf-8")
        # Perfil propio y temporal: con el de tu Edge abierto, cada dibujo esperaba a tu navegador (minutos por tarjeta).
        subprocess.run([_edge(), "--headless=new", f"--user-data-dir={Path(d) / 'perfil'}", "--no-first-run",
                        "--no-default-browser-check", "--disable-extensions", "--disable-gpu", "--hide-scrollbars", f"--window-size={ancho},{alto}",
                        "--virtual-time-budget=2500", "--allow-file-access-from-files", f"--screenshot={destino}", pagina.as_uri()],
                       capture_output=True, timeout=90, check=False)
    if not destino.exists() or destino.stat().st_size < 10_000:
        raise RuntimeError(f"No se pudo dibujar la tarjeta de la escena {n}.")
    return destino


def rellenar(p: dict[str, Any], carpeta: Path, marca: str = "", avisar=lambda *_: None, produccion: str = "") -> list[dict[str, Any]]:
    """Dibuja la tarjeta de cada escena sin clip y devuelve las tomas nuevas [{orden, toma}]."""
    fmt = config.FORMATOS[p["formato"]]
    pendientes = [e for e in p["escenas"] if e.get("elegida") is None]
    if not pendientes:
        return []
    avisar("Escribiendo los rótulos de las escenas", 10)
    disenos = disenar(pendientes, p.get("titulo") or p["tema"], produccion)
    (carpeta / "tomas").mkdir(exist_ok=True)
    nuevas = []
    for k, (e, t) in enumerate(zip(pendientes, disenos)):
        avisar(f"Dibujando la escena {e['orden']} de {len(p['escenas'])}", 20 + int(75 * k / len(pendientes)))
        tmp = carpeta / "tomas" / f"escena_{e['orden']:02d}_tarjeta.png"
        dibujar(t, e["orden"], fmt["ancho"], fmt["alto"], tmp, marca)
        sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
        nuevas.append({"orden": e["orden"], "toma": {"archivo": f"tomas/{tmp.name}", "tipo": "imagen", "origen": "tarjeta", "sha": sha}})
    return nuevas
