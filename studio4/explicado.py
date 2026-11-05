"""«Explicado animado»: gráficos hechos con código para cada frase, al estilo de los canales que explican con
infografías en movimiento (reloj, deslizador, contador, multitud, mapa, camino, comparación, línea de tiempo,
chips y edificios). La IA solo elige el gráfico y sus datos; el dibujo y el movimiento los hace esta página.

Dos temas: «neon» (FourLevel: oscuro con rosa, cian y oro, todo entra rápido) y «archivo» (ARIGAB: papel oscuro,
dorado y crema, letra de documento, todo más despacio). La página se graba fotograma a fotograma como las demás
animaciones de Studio 4, a la duración exacta de la frase.
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

from . import config

logger = logging.getLogger("studio4.explicado")
VERSION = 3
TIPOS = {
    "contador": "una cifra que cuenta hasta su valor, con su unidad (para números, récords, precios, tamaños)",
    "reloj": "una esfera que gira entre dos extremos (día/noche, antes/después, horas, duración)",
    "deslizador": "un control de ajuste que se mueve (más/menos realismo, dificultad, tamaño, velocidad)",
    "personas": "una multitud de muñecos planos (peatones, jugadores, habitantes, tripulación)",
    "mapa": "un mapa visto desde arriba con puntos que se marcan (lugares, rutas, zonas)",
    "camino": "una decisión con dos caminos (elegir, dilema, o esto o aquello)",
    "comparacion": "dos barras que se comparan (antes contra ahora, un juego contra otro)",
    "linea": "una línea de tiempo con fechas (historia, lanzamientos, sucesos en orden)",
    "chips": "una idea clave en grande con 2-4 etiquetas (resumen, características, lista corta)",
    "edificios": "edificios de líneas que crecen con un contador (ciudad, construcción, tamaño del mapa)",
}
TEMAS = {"neon": {"ritmo": 1.0}, "archivo": {"ritmo": 1.7}}

PLANTILLA = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: S4; src: url(geist.woff2); font-weight: 100 900; }
:root { --fondo: #06060c; --tinta: #f4f6fb; --tenue: rgba(244,246,251,.55); --a: #ff3ea5; --b: #2ee6ff; --c: #ffc85a;
  --caja: rgba(255,255,255,.06); --borde: rgba(255,255,255,.14); --letra: S4, "Segoe UI", sans-serif; --titulo: S4, "Segoe UI", sans-serif; }
body.archivo { --fondo: #110d08; --tinta: #efe6d2; --tenue: rgba(239,230,210,.6); --a: #c8a45a; --b: #e9e1cf; --c: #d98c4a;
  --caja: rgba(200,164,90,.08); --borde: rgba(200,164,90,.35); --titulo: Georgia, "Times New Roman", serif; }
html, body { margin: 0; width: __W__px; height: __H__px; overflow: hidden; background: var(--fondo); color: var(--tinta);
  font-family: var(--letra); zoom: __ZOOM__; }
#fondo { position: absolute; inset: 0; }
#escena { position: absolute; inset: 0; }
.abs { position: absolute; }
.chip { position: absolute; display: flex; align-items: center; gap: 14px; padding: 12px 26px; border-radius: 999px; font-size: 30px;
  font-weight: 800; letter-spacing: .14em; text-transform: uppercase; background: rgba(0,0,0,.45); border: 2px solid var(--borde);
  white-space: nowrap; transform-origin: center; }
.chip i { width: 14px; height: 14px; border-radius: 50%; background: var(--a); box-shadow: 0 0 14px var(--a); }
.caja { position: absolute; border-radius: 28px; background: var(--caja); border: 2px solid var(--borde); backdrop-filter: blur(6px); }
.num { font-weight: 900; letter-spacing: -.03em; line-height: .9; font-variant-numeric: tabular-nums; }
body.archivo .num, body.archivo .grande { font-family: var(--titulo); font-weight: 700; }
.peq { font-size: 26px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; color: var(--tenue); }
svg { position: absolute; overflow: visible; }
#foto { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; filter: brightness(.34) saturate(1.15) blur(7px); transform-origin: 50% 45%; }
#foto.nitida { filter: brightness(.5) saturate(1.05); }
body.archivo #foto.nitida { filter: brightness(.48) sepia(.3); }
.tarjeta-foto { position: absolute; border-radius: 26px; overflow: hidden; border: 3px solid var(--borde); background: rgba(255,255,255,.92);
  box-shadow: 0 20px 60px rgba(0,0,0,.5); }
.tarjeta-foto img { width: 100%; height: 100%; object-fit: contain; display: block; }
#velo { position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 45%, rgba(0,0,0,.05), rgba(0,0,0,.6) 75%); }
body.archivo #foto { filter: brightness(.32) sepia(.45) saturate(.9) blur(7px); }
#grano { position: absolute; inset: 0; pointer-events: none; opacity: 0; background-image: radial-gradient(rgba(255,255,255,.05) 1px, transparent 1px);
  background-size: 5px 5px; }
body.archivo #grano { opacity: 1; }
</style></head><body class="__TEMA__">__FOTO__<canvas id="fondo" width="__W__" height="__H__"></canvas><div id="escena"></div><div id="grano"></div>
<script>
const G = __G__, W = __W__, H = __H__, R = __RITMO__, DUR = __DUR__, V = H > W;
const M = Math.min(W, H), cx = W / 2, cy = H / 2;
const css = getComputedStyle(document.body), C = { a: css.getPropertyValue("--a").trim(), b: css.getPropertyValue("--b").trim(), c: css.getPropertyValue("--c").trim(), t: css.getPropertyValue("--tinta").trim() };
const esc = document.getElementById("escena");
const cl = (x) => Math.max(0, Math.min(1, x)), tramo = (t, a, b) => cl((t - a) / (b - a));
const sal = (x) => 1 - Math.pow(1 - x, 3), reb = (x) => x <= 0 ? 0 : 1 + 2.4 * Math.pow(x - 1, 3) + 1.4 * Math.pow(x - 1, 2);
const mz = (a, b, p) => a + (b - a) * p;
const div = (cls, html, padre) => { const d = document.createElement("div"); d.className = cls; if (html !== undefined) d.innerHTML = html; (padre || esc).appendChild(d); return d; };
const SVG = (w, h, x, y) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("width", w); s.setAttribute("height", h);
  s.setAttribute("viewBox", `0 0 ${w} ${h}`); s.style.left = x + "px"; s.style.top = y + "px"; esc.appendChild(s); return s; };
const el = (s, tag, at) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in at) e.setAttribute(k, at[k]); s.appendChild(e); return e; };
const fmt = (v, d) => (d ? v.toFixed(d) : Math.round(v).toString()).replace(/\B(?=(\d{3})+(?!\d))/g, ".").replace(/\.(\d)$/, ",$1");
const azar = (s) => { const x = Math.sin(s * 127.1) * 43758.5453; return x - Math.floor(x); };
const ponerChip = (texto, x, y) => { const c = div("chip", `<i></i><span></span>`); c.querySelector("span").textContent = texto; c.style.left = x + "px"; c.style.top = y + "px"; return c; };
const aparece = (n, p, dy) => { n.style.opacity = cl(p * 1.6); n.style.transform = `translate(-50%,${(1 - sal(p)) * (dy ?? 40)}px) scale(${mz(.85, 1, sal(p))})`; };

// fondo: rejilla tenue que avanza despacio y motas de luz
const lz = document.getElementById("fondo").getContext("2d");
const FOTO = document.getElementById("foto");
function fondo(t) {
  if (FOTO) {   // imagen del juego de fondo: zoom lento y solo las motas de luz encima (sin rejilla)
    FOTO.style.transform = `scale(${1.06 + .06 * t / DUR})`;
    lz.clearRect(0, 0, W, H);
    for (let i = 0; i < 28; i++) {
      const x = azar(i) * W, y = (azar(i + 9) * H - t * (10 + 25 * azar(i + 3)) / R + H) % H;
      lz.fillStyle = `rgba(255,255,255,${(.12 + .25 * azar(i + 5)) * (.5 + .5 * Math.sin(t * 2 + i))})`; lz.beginPath(); lz.arc(x, y, 1.5 + 2 * azar(i + 7), 0, 7); lz.fill();
    }
    return;
  }
  const g = lz.createRadialGradient(cx, cy * .9, 10, cx, cy, Math.max(W, H) * .75);
  g.addColorStop(0, document.body.classList.contains("archivo") ? "#2a2014" : "#141433"); g.addColorStop(1, getComputedStyle(document.body).getPropertyValue("--fondo"));
  lz.fillStyle = g; lz.fillRect(0, 0, W, H);
  lz.strokeStyle = document.body.classList.contains("archivo") ? "rgba(200,164,90,.07)" : "rgba(46,230,255,.06)"; lz.lineWidth = 1.5;
  const paso = M / 9, d = (t * 18 / R) % paso;
  for (let x = -paso + d; x < W + paso; x += paso) { lz.beginPath(); lz.moveTo(x, 0); lz.lineTo(x, H); lz.stroke(); }
  for (let y = -paso + d; y < H + paso; y += paso) { lz.beginPath(); lz.moveTo(0, y); lz.lineTo(W, y); lz.stroke(); }
  for (let i = 0; i < 40; i++) {
    const x = azar(i) * W, y = (azar(i + 9) * H - t * (12 + 30 * azar(i + 3)) / R + H) % H, a = .15 + .35 * azar(i + 5);
    lz.fillStyle = `rgba(255,255,255,${a * (.5 + .5 * Math.sin(t * 2 + i))})`; lz.beginPath(); lz.arc(x, y, 1.5 + 2 * azar(i + 7), 0, 7); lz.fill();
  }
}

const P = {};   // un constructor por tipo: devuelve la función que lo coloca en el instante t
P.contador = (g) => {
  const n = div("abs num grande", ""), u = div("abs peq", ""), barra = div("abs", ""), relleno = div("abs", "", barra);
  const tam = V ? 260 : 230;
  n.style.fontSize = tam + "px"; n.style.color = C.c; n.style.textShadow = `0 0 40px ${C.c}55`;
  u.textContent = g.unidad || ""; u.style.fontSize = (V ? 40 : 34) + "px"; u.style.color = C.t;
  Object.assign(barra.style, { width: M * .62 + "px", height: "10px", borderRadius: "10px", background: "rgba(255,255,255,.1)" });
  Object.assign(relleno.style, { left: 0, top: 0, height: "10px", borderRadius: "10px", background: `linear-gradient(90deg, ${C.a}, ${C.c})` });
  const chip = g.etiqueta ? ponerChip(g.etiqueta, cx, cy - tam * 1.15) : null;
  const desde = g.desde ?? (g.valor >= 1500 && g.valor <= 2100 && g.valor % 1 === 0 && !g.unidad ? g.valor - 40 : 0);
  return (t) => {
    const p = tramo(t, .1 * R, 1.1 * R), v = mz(desde, g.valor, sal(p));
    n.textContent = (g.prefijo || "") + fmt(p >= 1 ? g.valor : v, g.decimales || 0) + (g.sufijo || "");
    n.style.left = cx + "px"; n.style.top = cy - tam * .55 + "px"; aparece(n, tramo(t, 0, .35 * R), 30);
    u.style.left = cx + "px"; u.style.top = cy + tam * .5 + "px"; aparece(u, tramo(t, .3 * R, .7 * R));
    barra.style.left = cx - M * .31 + "px"; barra.style.top = cy + tam * .5 + 80 + "px"; barra.style.opacity = tramo(t, .2 * R, .5 * R);
    relleno.style.width = M * .62 * sal(p) + "px";
    if (chip) aparece(chip, tramo(t, .15 * R, .55 * R));
  };
};
P.reloj = (g) => {
  const r = M * (V ? .34 : .3), s = SVG(r * 2 + 80, r * 2 + 80, cx - r - 40, cy - r - 40 - (V ? 60 : 30)), o = r + 40;
  const arcos = [[C.c, -150, -40], [C.a, -30, 60], [C.b, 70, 170]].map(([col, a1, a2]) => {
    const p = (a) => [o + r * Math.cos((a - 90) * Math.PI / 180), o + r * Math.sin((a - 90) * Math.PI / 180)];
    const [x1, y1] = p(a1), [x2, y2] = p(a2);
    return el(s, "path", { d: `M${x1} ${y1} A${r} ${r} 0 0 1 ${x2} ${y2}`, stroke: col, "stroke-width": 26, fill: "none", "stroke-linecap": "round", "stroke-dasharray": 2000, "stroke-dashoffset": 2000 });
  });
  for (let k = 0; k < 24; k++) { const a = k * 15 * Math.PI / 180; el(s, "line", { x1: o + (r - 46) * Math.cos(a), y1: o + (r - 46) * Math.sin(a), x2: o + (r - (k % 6 ? 36 : 26)) * Math.cos(a), y2: o + (r - (k % 6 ? 36 : 26)) * Math.sin(a), stroke: "rgba(255,255,255,.25)", "stroke-width": 3 }); }
  const aguja = el(s, "line", { x1: o, y1: o, x2: o, y2: o - r + 70, stroke: C.t, "stroke-width": 8, "stroke-linecap": "round" });
  el(s, "circle", { cx: o, cy: o, r: 16, fill: C.t });
  const sol = el(s, "circle", { cx: o, cy: o - r - 2, r: 20, fill: C.c }), luna = el(s, "circle", { cx: o, cy: o + r + 2, r: 16, fill: "none", stroke: C.t, "stroke-width": 4 });
  const centro = div("abs grande", ""); centro.textContent = g.centro || ""; Object.assign(centro.style, { fontSize: (V ? 80 : 70) + "px", fontWeight: 900, color: C.t,
    padding: "6px 22px", borderRadius: "18px", background: "rgba(0,0,0,.55)", zIndex: 3 });   // por encima de la aguja
  const pie = div("abs peq", ""); pie.textContent = `${g.izquierda || "DÍA"}  ·  ${g.derecha || "NOCHE"}`;
  return (t) => {
    arcos.forEach((a, k) => a.setAttribute("stroke-dashoffset", 2000 * (1 - sal(tramo(t, (.15 + k * .15) * R, (.6 + k * .15) * R)))));
    const giro = mz(-120, 120 * (g.vueltas || 1), sal(tramo(t, .4 * R, DUR - .2)));
    aguja.setAttribute("transform", `rotate(${giro} ${o} ${o})`);
    sol.setAttribute("opacity", tramo(t, .3 * R, .6 * R)); luna.setAttribute("opacity", tramo(t, .45 * R, .75 * R));
    s.style.opacity = tramo(t, 0, .3 * R); s.style.transform = `scale(${mz(.8, 1, sal(tramo(t, 0, .5 * R)))})`;
    centro.style.left = cx + "px"; centro.style.top = cy - (V ? 60 : 30) + r * .32 + "px"; aparece(centro, tramo(t, .35 * R, .8 * R), 20);
    pie.style.left = cx + "px"; pie.style.top = cy + r + (V ? 40 : 30) + "px"; aparece(pie, tramo(t, .5 * R, .9 * R));
  };
};
P.deslizador = (g) => {
  const w = M * (V ? .78 : .5), h = 300, caja = div("caja", ""); Object.assign(caja.style, { width: w + "px", height: h + "px" });
  const tit = div("abs peq", "", caja); tit.textContent = g.titulo || "AJUSTE"; Object.assign(tit.style, { left: "44px", top: "40px", color: C.t });
  const pista = div("abs", "", caja), lleno = div("abs", "", caja), bola = div("abs", "", caja), valor = div("abs peq", "", caja);
  Object.assign(pista.style, { left: "44px", top: "150px", width: w - 88 + "px", height: "14px", borderRadius: "14px", background: "rgba(255,255,255,.12)" });
  Object.assign(lleno.style, { left: "44px", top: "150px", height: "14px", borderRadius: "14px", background: `linear-gradient(90deg, ${C.b}, ${C.a})` });
  Object.assign(bola.style, { top: "135px", width: "44px", height: "44px", borderRadius: "50%", background: C.t, boxShadow: `0 0 24px ${C.a}` });
  Object.assign(valor.style, { left: "44px", top: "215px", color: C.c });
  const chip = g.etiqueta ? ponerChip(g.etiqueta, cx, cy - h / 2 - 110) : null;
  const a = g.desde ?? .25, b = g.hasta ?? .85;
  return (t) => {
    caja.style.left = cx - w / 2 + "px"; caja.style.top = cy - h / 2 + "px";
    caja.style.opacity = tramo(t, 0, .3 * R); caja.style.transform = `translateY(${(1 - sal(tramo(t, 0, .45 * R))) * 60}px)`;
    const p = mz(a, b, sal(tramo(t, .5 * R, 1.4 * R)) - .03 * Math.sin(tramo(t, 1.4 * R, 1.8 * R) * Math.PI));
    lleno.style.width = (w - 88) * p + "px"; bola.style.left = 44 + (w - 88) * p - 22 + "px";
    valor.textContent = p >= b - .01 ? (g.etiqueta_fin || g.hasta_texto || "MÁS") : (g.etiqueta_ini || g.desde_texto || "MENOS");
    if (chip) aparece(chip, tramo(t, .2 * R, .6 * R));
  };
};
P.personas = (g) => {
  const n = Math.max(4, Math.min(42, g.n || 18)), cols = V ? 6 : 9, filas = Math.ceil(n / cols), paso = (V ? W * .8 : W * .62) / cols;
  const cols3 = document.body.classList.contains("archivo") ? [C.a, C.b, C.c, "#8a6a3c", "#b9a27a"] : [C.a, C.b, C.c, "#f6c7d9", "#9fe8f4"];
  const gente = Array.from({ length: n }, (_, i) => {
    const s = SVG(paso * .8, paso * 1.3, 0, 0), col = cols3[Math.floor(azar(i + 1) * cols3.length)];
    el(s, "circle", { cx: paso * .4, cy: paso * .28, r: paso * .2, fill: "#f3dfc8" });
    el(s, "rect", { x: paso * .18, y: paso * .5, width: paso * .44, height: paso * .5, rx: paso * .18, fill: col });
    el(s, "rect", { x: paso * .22, y: paso * .92, width: paso * .13, height: paso * .32, rx: 6, fill: col });
    el(s, "rect", { x: paso * .45, y: paso * .92, width: paso * .13, height: paso * .32, rx: 6, fill: col });
    return { s, x: cx - cols * paso / 2 + (i % cols) * paso + (Math.floor(i / cols) % 2) * paso * .3, y: cy - filas * paso * .7 + Math.floor(i / cols) * paso * 1.35 };
  });
  const chip = g.etiqueta ? ponerChip(g.etiqueta, cx, cy - filas * paso * .7 - 120) : null;
  return (t) => gente.forEach((p, i) => {
    const q = tramo(t, (.05 + i * .025) * R, (.35 + i * .025) * R), bob = Math.sin(t * 5 / R + i) * 6 * q;
    p.s.style.left = p.x + "px"; p.s.style.top = p.y + (1 - sal(q)) * 50 + bob + "px"; p.s.style.opacity = cl(q * 1.5);
    p.s.style.transform = `scale(${reb(q) || 0})`; if (chip) aparece(chip, tramo(t, .1 * R, .5 * R));
  });
};
P.mapa = (g) => {
  const plano = div("abs", ""); const ww = V ? W * 1.1 : W * .9, hh = V ? H * .5 : H * .9;
  Object.assign(plano.style, { width: ww + "px", height: hh + "px", left: cx - ww / 2 + "px", top: cy - hh / 2 + "px",
    backgroundImage: `linear-gradient(${C.b}22 2px, transparent 2px), linear-gradient(90deg, ${C.b}22 2px, transparent 2px)`,
    backgroundSize: "90px 90px", borderRadius: "30px", transform: "perspective(1400px) rotateX(52deg)", border: `2px solid ${C.b}33` });
  const puntos = (g.puntos || ["A", "B", "C"]).slice(0, 5).map((tx, i) => {
    const x = cx + (azar(i * 3 + 2) - .5) * ww * .62, y = cy + (azar(i * 7 + 1) - .5) * hh * .42;
    const aro = div("abs", ""); Object.assign(aro.style, { width: "90px", height: "90px", borderRadius: "50%", border: `8px solid ${C.c}`, left: x - 45 + "px", top: y - 45 + "px" });
    const lab = div("chip", `<i></i><span></span>`); lab.querySelector("span").textContent = tx; lab.style.left = x + "px"; lab.style.top = y - 120 + "px";
    return { aro, lab, x, y };
  });
  const ruta = SVG(W, H, 0, 0), linea = el(ruta, "polyline", { points: puntos.map((p) => `${p.x},${p.y}`).join(" "), fill: "none", stroke: C.a, "stroke-width": 6, "stroke-dasharray": 4000, "stroke-dashoffset": 4000 });
  return (t) => {
    plano.style.opacity = tramo(t, 0, .4 * R);
    linea.setAttribute("stroke-dashoffset", 4000 * (1 - sal(tramo(t, .5 * R, (.5 + puntos.length * .35) * R))));
    puntos.forEach((p, i) => {
      const q = tramo(t, (.3 + i * .35) * R, (.6 + i * .35) * R), pul = 1 + .12 * Math.sin(t * 6 / R + i);
      p.aro.style.opacity = cl(q * 2); p.aro.style.transform = `scale(${(reb(q) || 0) * pul})`; aparece(p.lab, tramo(t, (.4 + i * .35) * R, (.75 + i * .35) * R));
    });
  };
};
P.camino = (g) => {
  const s = SVG(W, H, 0, 0), arriba = cy - (V ? 380 : 260), y2 = cy + (V ? 260 : 160), dx = V ? W * .26 : W * .22;
  const yo = div("abs", ""); Object.assign(yo.style, { width: "120px", height: "120px", borderRadius: "50%", background: C.a, boxShadow: `0 0 40px ${C.a}`, left: cx - 60 + "px", top: arriba - 60 + "px" });
  const ramas = [-1, 1].map((sg) => el(s, "path", { d: `M${cx} ${arriba + 60} C ${cx} ${(arriba + y2) / 2}, ${cx + sg * dx} ${(arriba + y2) / 2}, ${cx + sg * dx} ${y2 - 80}`,
    stroke: sg < 0 ? C.b : C.c, "stroke-width": 7, fill: "none", "stroke-dasharray": 3000, "stroke-dashoffset": 3000 }));
  const cajas = [g.a || "A", g.b || "B"].map((tx, i) => { const c = div("chip", `<i></i><span></span>`); c.querySelector("span").textContent = tx;
    c.style.left = cx + (i ? dx : -dx) + "px"; c.style.top = y2 - 40 + "px"; c.style.fontSize = (V ? 34 : 30) + "px"; return c; });
  const pre = g.pregunta ? ponerChip(g.pregunta, cx, arriba - 200) : null;
  return (t) => {
    yo.style.opacity = tramo(t, 0, .3 * R); yo.style.transform = `scale(${reb(tramo(t, 0, .5 * R)) || 0})`;
    ramas.forEach((r, i) => r.setAttribute("stroke-dashoffset", 3000 * (1 - sal(tramo(t, (.4 + i * .15) * R, (1.1 + i * .15) * R)))));
    cajas.forEach((c, i) => aparece(c, tramo(t, (1 + i * .2) * R, (1.4 + i * .2) * R)));
    if (pre) aparece(pre, tramo(t, .15 * R, .55 * R));
  };
};
P.comparacion = (g) => {
  const a = g.a || { nombre: "A", valor: 1 }, b = g.b || { nombre: "B", valor: 2 }, max = Math.max(a.valor, b.valor) || 1;
  const conFotos = !!(G.fotos_src && (G.fotos_src.a || G.fotos_src.b));
  const alto = conFotos ? H * .14 : (V ? H * .38 : H * .52), base = conFotos ? H * .9 : cy + alto / 2, sep = V ? W * .22 : W * .17;
  const ladoFoto = V ? W * .4 : H * .5, topeFoto = V ? H * .16 : H * .12;
  const piezas = [[a, C.b, -1], [b, C.a, 1]].map(([d, col, sg]) => {
    const barra = div("abs", ""); Object.assign(barra.style, { width: (V ? 190 : 170) + "px", borderRadius: "24px 24px 6px 6px", background: `linear-gradient(180deg, ${col}, ${col}55)`, boxShadow: `0 0 40px ${col}44` });
    const num = div("abs num", ""); num.style.fontSize = (V ? 90 : 80) + "px"; num.style.color = C.t;
    const nom = div("abs peq", ""); nom.textContent = d.nombre; nom.style.color = C.t;
    let foto = null;
    const src = G.fotos_src?.[sg < 0 ? "a" : "b"];
    if (src) { foto = div("tarjeta-foto", `<img src="${src}">`); }
    return { barra, num, nom, d, x: cx + sg * sep, foto };
  });
  const chip = g.etiqueta ? ponerChip(g.etiqueta, cx, conFotos ? topeFoto - 90 : cy - alto / 2 - 190) : null;
  return (t) => piezas.forEach((p, i) => {
    const q = sal(tramo(t, (.3 + i * .3) * R, (1.2 + i * .3) * R)), h = alto * (p.d.valor / max) * q, w = parseFloat(p.barra.style.width);
    Object.assign(p.barra.style, { left: p.x - w / 2 + "px", top: base - h + "px", height: h + "px", opacity: tramo(t, 0, .3 * R) });
    p.num.textContent = fmt(p.d.valor * q, p.d.decimales || 0) + (g.unidad ? " " + g.unidad : ""); p.num.style.left = p.x + "px";
    p.num.style.top = (conFotos ? topeFoto + ladoFoto + 24 : base - h - 110) + "px";
    aparece(p.num, tramo(t, (.3 + i * .3) * R, (.6 + i * .3) * R), 10);
    p.nom.style.left = p.x + "px"; p.nom.style.top = base + 26 + "px"; aparece(p.nom, tramo(t, .2 * R, .5 * R));
    if (p.foto) {   // la foto real de cada lado, encima de su barra
      const lado = ladoFoto, q2 = tramo(t, (.1 + i * .2) * R, (.5 + i * .2) * R);
      Object.assign(p.foto.style, { width: lado + "px", height: lado + "px", left: p.x - lado / 2 + "px", top: topeFoto + "px",
        opacity: cl(q2 * 1.5), transform: `translateY(${(1 - sal(q2)) * 40}px) scale(${mz(.85, 1, sal(q2))})` });
    }
    if (chip) aparece(chip, tramo(t, .1 * R, .5 * R));
  });
};
P.linea = (g) => {
  const hitos = (g.hitos || []).slice(0, 5), s = SVG(W, H, 0, 0), x0 = W * (V ? .12 : .1), x1 = W * (V ? .88 : .9);
  const raya = el(s, "line", { x1: x0, y1: cy, x2: x0, y2: cy, stroke: C.c, "stroke-width": 6, "stroke-linecap": "round" });
  const piezas = hitos.map((h, i) => {
    const x = hitos.length > 1 ? mz(x0 + 40, x1 - 40, i / (hitos.length - 1)) : cx, arriba = i % 2 === 0;
    const punto = el(s, "circle", { cx: x, cy: cy, r: 0, fill: C.a });
    const f = div("abs num", ""); f.textContent = h.fecha || ""; f.style.fontSize = (V ? 62 : 56) + "px"; f.style.color = C.c;
    const tx = div("abs peq", ""); tx.textContent = h.texto || ""; Object.assign(tx.style, { color: C.t, width: (V ? 240 : 300) + "px", textAlign: "center", whiteSpace: "normal", lineHeight: 1.25, fontSize: "24px" });
    return { punto, f, tx, x, arriba };
  });
  return (t) => {
    raya.setAttribute("x2", mz(x0, x1, sal(tramo(t, .1 * R, (.4 + hitos.length * .4) * R))));
    piezas.forEach((p, i) => {
      const q = tramo(t, (.35 + i * .4) * R, (.7 + i * .4) * R);
      p.punto.setAttribute("r", 16 * (reb(q) || 0));
      p.f.style.left = p.x + "px"; p.f.style.top = cy + (p.arriba ? -150 : 40) + "px"; aparece(p.f, q, p.arriba ? 30 : -30);
      p.tx.style.left = p.x + "px"; p.tx.style.top = cy + (p.arriba ? -80 : 110) + "px"; aparece(p.tx, tramo(t, (.5 + i * .4) * R, (.85 + i * .4) * R), 10);
    });
  };
};
P.chips = (g) => {
  const tit = div("abs grande", ""); tit.textContent = g.titulo || ""; Object.assign(tit.style, { fontSize: (V ? 120 : 110) + "px", fontWeight: 900, color: C.t, textAlign: "center",
    width: W * .86 + "px", lineHeight: 1, textShadow: `0 0 50px ${C.a}66` });
  const chips = (g.chips || []).slice(0, 4).map((tx, i) => ponerChip(tx, 0, 0));
  return (t) => {
    tit.style.left = cx + "px"; tit.style.top = cy - (V ? 260 : 170) + "px"; aparece(tit, tramo(t, 0, .45 * R), 50);
    chips.forEach((c, i) => {
      const col = V ? 1 : 2, x = V ? cx : cx + (i % 2 ? 1 : -1) * W * .17, y = cy + (V ? 40 + i * 120 : 20 + Math.floor(i / 2) * 120);
      c.style.left = x + "px"; c.style.top = y + "px"; aparece(c, tramo(t, (.4 + i * .22) * R, (.7 + i * .22) * R));
    });
  };
};
P.edificios = (g) => {
  const s = SVG(W, H, 0, 0), n = V ? 7 : 11, ancho = (V ? W * .8 : W * .7) / n, suelo = cy + (V ? 360 : 240);
  const bloques = Array.from({ length: n }, (_, i) => {
    const alto = (V ? 260 : 180) + azar(i + 4) * (V ? 520 : 360), x = cx - n * ancho / 2 + i * ancho;
    const cara = el(s, "rect", { x: x + 6, y: suelo, width: ancho - 12, height: 0, fill: "rgba(255,255,255,.03)", stroke: C.b, "stroke-width": 3 });
    const techo = el(s, "polygon", { points: "", fill: "none", stroke: C.b, "stroke-width": 3 });
    const vent = Array.from({ length: 6 }, (_, k) => el(s, "rect", { x: x + 18, y: 0, width: ancho - 36, height: 8, fill: C.t, opacity: 0 }));
    return { cara, techo, vent, alto, x };
  });
  const cont = div("abs num", ""); cont.style.fontSize = (V ? 150 : 130) + "px"; cont.style.color = C.c;
  const lab = g.etiqueta ? div("abs peq", "") : null; if (lab) { lab.textContent = g.etiqueta; lab.style.color = C.t; }
  return (t) => {
    bloques.forEach((b, i) => {
      const q = sal(tramo(t, (.1 + i * .08) * R, (.8 + i * .08) * R)), h = b.alto * q, top = suelo - h;
      b.cara.setAttribute("y", top); b.cara.setAttribute("height", h);
      b.techo.setAttribute("points", `${b.x + 6},${top} ${b.x + 26},${top - 20} ${b.x + ancho + 14},${top - 20} ${b.x + ancho - 6},${top}`);
      b.vent.forEach((v, k) => { v.setAttribute("y", top + 30 + k * 46); v.setAttribute("opacity", h > 60 + k * 46 ? .55 * (.6 + .4 * azar(i * 9 + k)) : 0); });
    });
    const p = tramo(t, .4 * R, 1.4 * R);
    cont.textContent = (g.valor != null ? "+" + fmt(g.valor * sal(p), 0) : ""); cont.style.left = cx + "px"; cont.style.top = (V ? H * .16 : H * .1) + "px"; aparece(cont, tramo(t, .3 * R, .7 * R));
    if (lab) { lab.style.left = cx + "px"; lab.style.top = (V ? H * .16 : H * .1) + (V ? 170 : 150) + "px"; aparece(lab, tramo(t, .5 * R, .9 * R)); }
  };
};
const colocar = (P[G.tipo] || P.chips)(G);
// salida: todo se aleja un poco y se apaga en los últimos 0,25 s (el corte con lo siguiente queda limpio)
window.__s4 = (t) => {
  fondo(t); colocar(t);
  const fin = tramo(t, DUR - .25 * R, DUR);
  esc.style.opacity = 1 - fin; esc.style.transform = `scale(${1 + .04 * fin + .015 * Math.sin(t / R)})`;
};
</script></body></html>"""


def tema_de(canal: dict[str, Any] | None) -> str:
    from . import canales
    return "neon" if canal is None or canales.es_de_juegos(canal) else "archivo"


def _base(ancho: int, alto: int) -> tuple[int, int]:
    return (1080, 1920) if alto > ancho else (1920, 1080)


def html(grafico: dict[str, Any], dur: float, ancho: int, alto: int, tema: str = "neon", foto: str = "", nitida: bool = False) -> str:
    bw, bh = _base(ancho, alto)
    clase = ' class="nitida"' if nitida else ""
    return (PLANTILLA.replace("__FOTO__", f'<img id="foto"{clase} src="{foto}"><div id="velo"></div>' if foto else "")
            .replace("__G__", json.dumps(grafico, ensure_ascii=False)).replace("__W__", str(bw)).replace("__H__", str(bh))
            .replace("__ZOOM__", f"{ancho / bw:.4f}").replace("__TEMA__", tema if tema in TEMAS else "neon")
            .replace("__RITMO__", str(TEMAS.get(tema, TEMAS["neon"])["ritmo"])).replace("__DUR__", f"{dur:.3f}"))


def renderizar(grafico: dict[str, Any], dur: float, destino: Path, ancho: int = 1920, alto: int = 1080, tema: str = "neon",
               fps: int = config.FPS, avisar: Callable[[str, int], None] = lambda *_: None, fondo: Path | None = None,
               nitida: bool = False, fotos: dict[str, Path] | None = None) -> Path:
    """El vídeo del gráfico, sin audio, a la duración exacta de la frase. `fondo`: una imagen del juego que va detrás
    (oscurecida, con zoom lento); sin ella, la rejilla."""
    from playwright.sync_api import sync_playwright
    from . import animacion
    trabajo = Path(tempfile.mkdtemp(prefix="s4_expl_", dir=config.PRODUCCIONES))
    try:
        shutil.copy(animacion.FUENTES / "geist-latin-wght-normal.woff2", trabajo / "geist.woff2")
        foto = ""
        if fondo and Path(fondo).exists():
            foto = f"fondo{Path(fondo).suffix.lower()}"
            shutil.copy(fondo, trabajo / foto)
        grafico = dict(grafico)
        for lado, ruta in (fotos or {}).items():   # las fotos reales de la comparación, junto a la página
            if ruta and Path(ruta).exists():
                shutil.copy(ruta, trabajo / f"lado_{lado}{Path(ruta).suffix.lower()}")
                grafico.setdefault("fotos_src", {})[lado] = f"lado_{lado}{Path(ruta).suffix.lower()}"
        pagina = trabajo / "g.html"
        pagina.write_text(html(grafico, dur, ancho, alto, tema, foto, nitida), encoding="utf-8")
        cuadros = max(1, int(math.ceil(dur * fps)))
        destino.parent.mkdir(parents=True, exist_ok=True)
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                               "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                               str(destino)], stdin=subprocess.PIPE)
        try:
            with sync_playwright() as pw:
                nav = pw.chromium.launch(channel="msedge", headless=True)
                pag = nav.new_page(viewport={"width": ancho, "height": alto})
                pag.goto(pagina.as_uri())
                pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
                for n in range(cuadros):
                    pag.evaluate(f"window.__s4({n / fps:.5f})")
                    ff.stdin.write(pag.screenshot(type="jpeg", quality=93))
                nav.close()
        except Exception:
            ff.stdin.close()
            ff.wait()
            raise   # el error de verdad (página, navegador), no el de FFmpeg que se queda sin fotogramas
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("FFmpeg no pudo grabar el gráfico.")
        return destino
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)


SISTEMA = """Eres el grafista de un canal de YouTube que explica con infografías animadas (como los mejores canales de
curiosidades). Para cada frase del guion decide si va un GRÁFICO o el material real (vídeo/imagen). Tipos de gráfico:
__TIPOS__
Reglas: usa un gráfico solo donde ayuda a entender o impacta (cifras, comparaciones, decisiones, multitudes, lugares,
cambios); __PROPORCION__ No repitas el mismo tipo dos frases seguidas. Textos de los gráficos CORTOS y en
mayúsculas (máx. 3 palabras por etiqueta), datos SOLO del guion (nunca inventes cifras). Sin logos ni personajes reales.
FOTO REAL: si la frase habla de algo real y concreto que se pueda fotografiar (un producto como una consola, un
lugar real, un objeto), añade en "datos" "foto": búsqueda corta en INGLÉS con su nombre exacto (p. ej. "PlayStation 5",
"Xbox Series X"); en una comparación de dos cosas reales, "foto_a" y "foto_b". Nunca para personajes de videojuegos.
Devuelve JSON: {"frases": [{"n": 1, "tipo": "ninguno|contador|reloj|...", "datos": {...}}]} con estos datos por tipo:
contador {"valor": 212, "unidad": "GB", "etiqueta": "TAMAÑO", "decimales": 0}; reloj {"centro": "GTA VI", "izquierda": "DÍA",
"derecha": "NOCHE"}; deslizador {"titulo": "REALISMO", "etiqueta": "AJUSTE", "desde": 0.2, "hasta": 0.9, "etiqueta_ini": "MENOS",
"etiqueta_fin": "MÁS"}; personas {"n": 24, "etiqueta": "PEATONES"}; mapa {"puntos": ["AEROPUERTO", "PUERTO"]};
camino {"pregunta": "¿QUÉ HARÍAS?", "a": "DISTRACCIÓN", "b": "MISIONES"}; comparacion {"a": {"nombre": "GTA V", "valor": 1},
"b": {"nombre": "GTA VI", "valor": 2.5}, "unidad": "", "etiqueta": "TAMAÑO DEL MAPA"}; linea {"hitos": [{"fecha": "2013",
"texto": "GTA V"}]}; chips {"titulo": "TAN REAL", "chips": ["CALLES", "PEATONES"]}; edificios {"valor": 16, "etiqueta": "EDIFICIOS MÁS"}."""


def proponer(frases: list[dict[str, Any]], titulo: str, tema: str = "neon", produccion: str = "") -> dict[int, dict[str, Any]]:
    """Qué gráfico lleva cada frase: {n: {"tipo", ...datos}}. FourLevel (neón) ~60 % de frases; ARIGAB (archivo) ~30 %."""
    from . import deepseek, gemini, jsonia
    proporcion = ("en un Short rápido de videojuegos, más o menos 6 de cada 10 frases llevan gráfico." if tema == "neon"
                  else "en una historia larga y pausada, solo 3 de cada 10 frases llevan gráfico (el resto, imágenes reales).")
    sistema = SISTEMA.replace("__TIPOS__", "\n".join(f"- {k}: {v}" for k, v in TIPOS.items())).replace("__PROPORCION__", proporcion)
    texto = f"TÍTULO: {titulo}\n\n" + "\n".join(f"{f['n']}. {f['texto']}" for f in frases)
    try:
        d = deepseek.generar_json(sistema, texto, temperatura=0.4, detalle="gráficos animados", produccion=produccion) \
            if deepseek.disponible() else jsonia.leer(gemini.generar(texto, sistema=sistema, temperatura=0.4, detalle="gráficos animados", produccion=produccion))
    except Exception as e:  # noqa: BLE001 - sin IA no hay gráficos (el vídeo sigue con su material)
        logger.warning("Gráficos animados: %s", e)
        return {}
    salida: dict[int, dict[str, Any]] = {}
    anterior = ""
    for x in d.get("frases") or []:
        tipo = str(x.get("tipo", ""))
        if tipo not in TIPOS or tipo == anterior:
            anterior = ""
            continue
        datos = x.get("datos") if isinstance(x.get("datos"), dict) else {}
        try:
            salida[int(x["n"])] = {"tipo": tipo, **datos}
            anterior = tipo
        except (KeyError, TypeError, ValueError):
            continue
    return salida
