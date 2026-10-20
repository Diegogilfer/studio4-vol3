"""Animación de «pestañas»: las imágenes del vídeo entran como tarjetas flotantes con brillo sobre un fondo negro
con rejilla en perspectiva, con rótulos («VICE CITY · 2002») y sonidos (whoosh al entrar, pop en los rótulos).

Es el estilo de los vídeos de referencia del nicho: imagen real del juego + gráficos sencillos + buena voz.
Cada fotograma es una página web que se dibuja en Edge sin ventana y se graba con FFmpeg. El tiempo lo manda
Python (`__s4(t)` coloca todo para el instante t), así que el resultado es siempre el mismo y sin saltos.
Gratis y sin dependencias nuevas (Playwright y Edge ya están). Sustituye a la intro de mo.js de Antigravity.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from . import config, medios

logger = logging.getLogger("studio4.animacion")

FUENTES = config.RAIZ / "web" / "fuentes"
COLORES = {"rosa": "#ff3ea5", "cian": "#2ee6ff", "naranja": "#ff8a3d", "violeta": "#9b6bff", "verde": "#3dffa2"}

PLANTILLA = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "S4 Sans"; src: url("geist.woff2"); font-weight: 100 900; }
html, body { margin: 0; width: __W__px; height: __H__px; overflow: hidden; background: #050508; }
body { font-family: "S4 Sans", system-ui, sans-serif; color: #fff; }
#fondo { position: absolute; inset: 0; }
#halo { position: absolute; inset: 0; background: radial-gradient(60% 40% at 50% 42%, rgba(120,80,255,.18), transparent 70%); }
.carta { position: absolute; left: 50%; border-radius: 26px; overflow: hidden; background: #111;
  transform-style: preserve-3d; will-change: transform, opacity; }
.carta img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 50% 50%; }
.carta::after { content: ""; position: absolute; inset: 0; border-radius: 26px; box-shadow: inset 0 0 0 3px rgba(255,255,255,.18); }
.rotulo { position: absolute; left: 50%; padding: 16px 36px; border-radius: 999px; font-weight: 800; font-size: 54px; z-index: 5;
  letter-spacing: .02em; white-space: nowrap; background: rgba(5,5,8,.82); border: 3px solid currentColor;
  text-shadow: 0 0 18px currentColor; will-change: transform, opacity; }
.titulo { position: absolute; left: 0; right: 0; text-align: center; font-weight: 900; font-size: 92px; line-height: 1.02;
  letter-spacing: -.01em; text-shadow: 0 6px 30px rgba(0,0,0,.8); padding: 0 60px; will-change: transform, opacity; }
</style></head><body>
<canvas id="fondo" width="__W__" height="__H__"></canvas><div id="halo"></div><div id="capa"></div>
<script>
const ESC = __ESCENAS__, W = __W__, H = __H__;
const capa = document.getElementById("capa");
const fueraDe = (a, b, x) => Math.min(1, Math.max(0, (x - a) / (b - a)));
const salida = (x) => 1 - Math.pow(1 - x, 3);
const rebote = (x) => { const c = 1.6; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
// Las piezas de cada escena se crean una vez; __s4(t) solo las coloca.
ESC.forEach((e, i) => {
  e.nodos = e.imagenes.map((im, k) => {
    const c = document.createElement("div"); c.className = "carta";
    const img = document.createElement("img"); img.src = im.src; c.appendChild(img);
    capa.appendChild(c);
    let r = null;
    if (im.etiqueta) { r = document.createElement("div"); r.className = "rotulo"; r.textContent = im.etiqueta;
      r.style.color = im.color || "#ff3ea5"; capa.appendChild(r); }
    return { c, img, r, im };
  });
  if (e.titulo) { e.t = document.createElement("div"); e.t.className = "titulo"; e.t.textContent = e.titulo; capa.appendChild(e.t); }
});
// Suelo y techo de rejilla en perspectiva, avanzando despacio hacia la cámara (como en los vídeos de referencia).
const lienzo = document.getElementById("fondo"), g = lienzo.getContext("2d");
function rejilla(t) {
  g.clearRect(0, 0, W, H);
  const fx = W / 2, horizonte = [H * 0.70, H * 0.30];
  [[1, 0.55], [-1, 0.28]].forEach(([dir, fuerza], k) => {
    const hz = horizonte[k], borde = dir > 0 ? H : 0;
    for (let i = -14; i <= 14; i++) {   // líneas hacia el punto de fuga
      g.strokeStyle = `rgba(150,130,255,${fuerza * 0.55})`; g.lineWidth = 2;
      g.beginPath(); g.moveTo(fx + i * 18, hz); g.lineTo(fx + i * W * 0.22, borde); g.stroke();
    }
    for (let j = 0; j < 14; j++) {      // líneas horizontales que se acercan
      const z = ((j + (t * 0.6) % 1) / 14);
      const y = hz + (borde - hz) * Math.pow(z, 2.2);
      g.strokeStyle = `rgba(150,130,255,${fuerza * Math.min(1, z * 1.6)})`; g.lineWidth = 1 + 2 * z;
      g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    }
  });
}
window.__s4 = (t) => {
  rejilla(t);
  ESC.forEach((e) => {
    const visible = t >= e.ini - 0.01 && t < e.fin + 0.35;
    const n = e.nodos.length, vertical = H > W;
    const ancho = W * (vertical ? 0.92 : 0.6);
    const alto = n === 1 && vertical ? ancho * 5 / 4 : ancho * 9 / 16;
    // una tarjeta grande centrada un poco arriba; dos, una sobre otra (comparación). Abajo quedan los subtítulos.
    const centros = n === 1 ? [H * (vertical ? 0.39 : 0.45)] : vertical ? [H * 0.23, H * 0.56] : [H * 0.28, H * 0.68];
    e.nodos.forEach((nd, k) => {
      if (!visible) { nd.c.style.opacity = 0; if (nd.r) nd.r.style.opacity = 0; return; }
      const u = t - e.ini - k * 0.22, dur = e.fin - e.ini;
      const ent = salida(fueraDe(0, 0.5, u)), sal = fueraDe(dur - 0.05, dur + 0.3, t - e.ini);
      const lado = k % 2 ? -1 : 1;
      const x = (1 - ent) * W * 0.9 * lado - sal * W * 0.9 * lado;
      const giro = (1 - ent) * -38 * lado + sal * 30 * lado;
      const flota = Math.sin((t + k) * 1.3) * 10;
      nd.c.style.width = ancho + "px"; nd.c.style.height = alto + "px";
      nd.c.style.top = (centros[k] - alto / 2) + "px";
      nd.c.style.transform = `translate(calc(-50% + ${x}px), ${flota}px) perspective(1400px) rotateY(${giro}deg) rotateZ(${Math.sin(t * 0.7 + k) * 0.8}deg)`;
      nd.c.style.opacity = Math.min(ent, 1 - sal);
      const color = nd.im.color || "#ff3ea5";
      nd.c.style.boxShadow = `0 0 ${40 + 18 * Math.sin(t * 2 + k)}px ${color}88, 0 30px 80px rgba(0,0,0,.7)`;
      // dentro de la tarjeta, la imagen se acerca despacio: nunca está quieta
      nd.img.style.transform = `scale(${1.04 + 0.08 * fueraDe(0, dur, t - e.ini)})`;
      if (nd.r) {
        const p = fueraDe(0.45, 0.8, u);
        nd.r.style.opacity = Math.min(p * 3, 1 - sal);
        nd.r.style.top = (centros[k] + alto / 2 - 46) + "px";
        nd.r.style.transform = `translateX(-50%) scale(${p > 0 ? rebote(p) : 0})`;
      }
    });
    if (e.t) {
      const u = t - e.ini, p = salida(fueraDe(0.1, 0.55, u)), sal = fueraDe(e.fin - e.ini - 0.05, e.fin - e.ini + 0.3, u);
      e.t.style.opacity = visible ? Math.min(p, 1 - sal) : 0;
      e.t.style.top = (n === 0 ? H * 0.36 : H * 0.055) + "px";
      e.t.style.transform = `translateY(${(1 - p) * 60}px) scale(${0.92 + 0.08 * p})`;
    }
  });
};
window.__s4(0);
</script></body></html>"""


def _html(escenas: list[dict[str, Any]], ancho: int, alto: int) -> str:
    limpias = [{"ini": round(e["ini"], 3), "fin": round(e["fin"], 3), "titulo": e.get("titulo", ""),
                "imagenes": [{"src": i["src"], "etiqueta": i.get("etiqueta", ""), "color": COLORES.get(i.get("color", ""), i.get("color", ""))}
                             for i in e.get("imagenes", [])]} for e in escenas]
    return (PLANTILLA.replace("__ESCENAS__", json.dumps(limpias, ensure_ascii=False))
            .replace("__W__", str(ancho)).replace("__H__", str(alto)))


def sonidos_de(escenas: list[dict[str, Any]]) -> list[tuple[float, str]]:
    """Dónde va cada efecto: whoosh al entrar cada tarjeta y pop cuando salta su rótulo."""
    marcas: list[tuple[float, str]] = []
    for e in escenas:
        for k, im in enumerate(e.get("imagenes", [])):
            marcas.append((max(0.0, e["ini"] + k * 0.22 - 0.05), "whoosh"))
            if im.get("etiqueta"):
                marcas.append((e["ini"] + k * 0.22 + 0.5, "pop"))
        if e.get("titulo") and not e.get("imagenes"):
            marcas.append((e["ini"] + 0.1, "whoosh"))
    return marcas


def efectos(carpeta: Path) -> dict[str, Path]:
    """Los sonidos, generados con FFmpeg (ruido filtrado y un tono corto): nuestros, sin derechos de nadie."""
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = {"whoosh": carpeta / "whoosh.wav", "pop": carpeta / "pop.wav"}
    if not salida["whoosh"].exists():
        medios.ffmpeg("-f", "lavfi", "-i", "anoisesrc=d=0.55:c=pink:a=0.9", "-af",
                      "highpass=f=300,lowpass=f=5000,afade=t=in:d=0.22,afade=t=out:st=0.25:d=0.3,volume=0.9",
                      "-ar", "48000", "-ac", "2", str(salida["whoosh"]))
    if not salida["pop"].exists():
        medios.ffmpeg("-f", "lavfi", "-i", "sine=f=880:d=0.12", "-af",
                      "afade=t=out:st=0.02:d=0.1,volume=0.55", "-ar", "48000", "-ac", "2", str(salida["pop"]))
    return salida


def pista_de_efectos(escenas: list[dict[str, Any]], total: float, destino: Path) -> Path:
    """Una pista de audio con todos los efectos en su sitio (para mezclar bajo la voz)."""
    fx = efectos(destino.parent / "_fx")
    marcas = [m for m in sonidos_de(escenas) if m[0] < total]
    if not marcas:
        medios.ffmpeg("-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", f"{total:.3f}", str(destino))
        return destino
    entradas, filtros = [], []
    for k, (t, tipo) in enumerate(marcas):
        entradas += ["-i", str(fx[tipo])]
        filtros.append(f"[{k}:a]adelay={int(t * 1000)}:all=1[f{k}]")
    filtros.append("".join(f"[f{k}]" for k in range(len(marcas))) +
                   f"amix=inputs={len(marcas)}:normalize=0,apad,atrim=0:{total:.3f}[a]")
    medios.ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[a]", "-ar", "48000", str(destino))
    return destino


def renderizar(escenas: list[dict[str, Any]], total: float, destino: Path, ancho: int = 1080, alto: int = 1920,
               fps: int = config.FPS, avisar: Callable[[str, int], None] = lambda *_: None) -> Path:
    """El vídeo de la animación, sin audio. `escenas`: [{ini, fin, titulo?, imagenes: [{archivo, etiqueta?, color?}]}]."""
    from playwright.sync_api import sync_playwright
    trabajo = Path(tempfile.mkdtemp(prefix="s4_anim_", dir=config.PRODUCCIONES))
    try:
        shutil.copy(FUENTES / "geist-latin-wght-normal.woff2", trabajo / "geist.woff2")
        propias = []
        for k, e in enumerate(escenas):   # las imágenes van junto a la página: Edge no lee rutas sueltas del disco
            ims = []
            for j, im in enumerate(e.get("imagenes", [])):
                nombre = f"i{k:02d}_{j}{Path(im['archivo']).suffix.lower()}"
                shutil.copy(im["archivo"], trabajo / nombre)
                ims.append({**im, "src": nombre})
            propias.append({**e, "imagenes": ims})
        pagina = trabajo / "anim.html"
        pagina.write_text(_html(propias, ancho, alto), encoding="utf-8")
        cuadros = int(math.ceil(total * fps))
        destino.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                                   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                                   "-movflags", "+faststart", str(destino)], stdin=subprocess.PIPE)
        try:
            with sync_playwright() as pw:
                nav = pw.chromium.launch(channel="msedge", headless=True)
                pag = nav.new_page(viewport={"width": ancho, "height": alto})
                pag.goto(pagina.as_uri())
                pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
                for n in range(cuadros):
                    pag.evaluate(f"window.__s4({n / fps:.5f})")
                    ffmpeg.stdin.write(pag.screenshot(type="jpeg", quality=93))
                    if n % (fps * 2) == 0:
                        avisar(f"Animando {n // fps} s de {int(total)} s", int(100 * n / cuadros))
                nav.close()
        finally:
            ffmpeg.stdin.close()
            if ffmpeg.wait() != 0:
                raise RuntimeError("FFmpeg no pudo grabar la animación.")
        return destino
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
