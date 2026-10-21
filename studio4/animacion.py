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
ACENTO = "#39ff88"   # el neón de los paneles, la rejilla y las partículas
ICONOS_NOMBRES = ('idea', 'guion', 'video', 'voz', 'imagen', 'mapa', 'calendario', 'persona', 'pareja', 'auto', 'dinero', 'estrella', 'escudo', 'mando', 'herramienta', 'check')   # los iconos de trazo que sabe dibujar la página

PLANTILLA = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "S4 Sans"; src: url("geist.woff2"); font-weight: 100 900; }
:root { --ac: __ACENTO__; }
html, body { margin: 0; width: __W__px; height: __H__px; overflow: hidden; background: #040607; }
body { font-family: "S4 Sans", system-ui, sans-serif; color: #fff; zoom: __ZOOM__; }
#fondo { position: absolute; inset: 0; }
/* ambiente: el propio vídeo, desenfocado y oscuro, detrás de todo (nada de fondo plano) */
#ambiente { position: absolute; inset: -6%; width: 112%; height: 112%; object-fit: cover; opacity: 0;
  filter: blur(34px) brightness(.42) saturate(1.35); will-change: transform, opacity; }
#rayos { position: absolute; inset: 0; opacity: 0; mix-blend-mode: screen;
  background: conic-gradient(from 200deg at 50% -10%, transparent 0deg, color-mix(in srgb, var(--ac) 22%, transparent) 8deg, transparent 18deg,
  transparent 30deg, color-mix(in srgb, var(--ac) 14%, transparent) 37deg, transparent 46deg, transparent 60deg,
  color-mix(in srgb, var(--ac) 18%, transparent) 66deg, transparent 76deg); }
#halo { position: absolute; inset: 0; background: radial-gradient(55% 45% at 50% 48%, color-mix(in srgb, var(--ac) 16%, transparent), transparent 72%),
  radial-gradient(120% 90% at 50% 50%, transparent 55%, rgba(0,0,0,.75)); }
.carta { position: absolute; left: 50%; border-radius: 26px; overflow: hidden; background: #111;
  transform-style: preserve-3d; will-change: transform, opacity; }
.carta img, .puente img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: 50% 50%; }
.carta::after { content: ""; position: absolute; inset: 0; border-radius: 26px; box-shadow: inset 0 0 0 3px rgba(255,255,255,.18); }
/* una imagen del vídeo que sale de la pantalla completa (o vuelve a ella): mismo encuadre, sin salto */
.puente { position: absolute; overflow: hidden; background: #000; will-change: transform, opacity; transform-origin: 50% 50%; }
.puente::after { content: ""; position: absolute; inset: 0; border-radius: inherit; box-shadow: inset 0 0 0 var(--borde, 0px) color-mix(in srgb, var(--ac) 70%, white); }
.rotulo { position: absolute; left: 50%; padding: 16px 36px; border-radius: 999px; font-weight: 800; font-size: 54px; z-index: 5;
  letter-spacing: .02em; white-space: nowrap; background: rgba(5,5,8,.82); border: 3px solid currentColor;
  text-shadow: 0 0 18px currentColor; will-change: transform, opacity; }
#logo { position: absolute; top: 46px; right: 46px; width: 150px; height: 150px; border-radius: 50%; opacity: .5;
  filter: blur(.4px) drop-shadow(0 0 18px rgba(150,120,255,.55)); z-index: 9; }
/* panel de cristal con borde de neón y un brillo que lo recorre */
.panel { position: absolute; padding: 46px 50px 40px; border-radius: 34px; box-sizing: border-box; overflow: hidden;
  background: linear-gradient(160deg, rgba(22,34,30,.78), rgba(6,10,10,.86)); backdrop-filter: blur(14px);
  border: 2px solid color-mix(in srgb, var(--ac) 70%, transparent); will-change: transform, opacity; z-index: 4; }
.panel::before { content: ""; position: absolute; inset: -40% -60%; pointer-events: none;
  background: linear-gradient(105deg, transparent 42%, rgba(255,255,255,.16) 50%, transparent 58%); transform: translateX(var(--brillo, -120%)); }
.panel h2 { margin: 0 0 30px; font-size: 70px; font-weight: 900; letter-spacing: -.01em; }
.panel .item { display: flex; gap: 24px; align-items: center; font-size: 52px; font-weight: 700; margin: 16px 0; padding: 14px 18px;
  border-radius: 20px; background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.08); will-change: transform, opacity; }
.panel .item b { flex: none; display: grid; place-items: center; width: 72px; height: 72px; border-radius: 20px; font-size: 36px;
  color: var(--ac); background: color-mix(in srgb, var(--ac) 14%, transparent); border: 2px solid color-mix(in srgb, var(--ac) 75%, transparent);
  box-shadow: 0 0 22px color-mix(in srgb, var(--ac) 45%, transparent); }
.panel .item b svg { width: 40px; height: 40px; }
.panel .nota { margin-top: 22px; font-size: 28px; color: rgba(255,255,255,.55); font-weight: 600; letter-spacing: .04em; }
.titulo { position: absolute; left: 0; right: 0; text-align: center; font-weight: 900; font-size: 92px; line-height: 1.02;
  letter-spacing: -.01em; text-shadow: 0 6px 30px rgba(0,0,0,.8); padding: 0 60px; will-change: transform, opacity; }
</style></head><body>
<img id="ambiente"><canvas id="fondo" width="__W__" height="__H__"></canvas><div id="rayos"></div><div id="halo"></div><div id="capa"></div>__LOGO__
<script>
const ESC = __ESCENAS__, W = __W__, H = __H__, FPS = __FPS__, VERTICAL = H > W;
const capa = document.getElementById("capa"), halo = document.getElementById("halo");
const ambiente = document.getElementById("ambiente"), rayos = document.getElementById("rayos");
const conAmbiente = ESC.find((e) => e.entra || e.sale);
if (conAmbiente) ambiente.src = conAmbiente.entra || conAmbiente.sale;
const fueraDe = (a, b, x) => Math.min(1, Math.max(0, (x - a) / (b - a)));
const salida = (x) => 1 - Math.pow(1 - x, 3);
const suave = (x) => x * x * (3 - 2 * x);
const rebote = (x) => { const c = 1.6; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
const mezcla = (a, b, p) => a + (b - a) * p;
// Iconos de trazo para los puntos del panel (sin dibujos de personajes: solo símbolos limpios)
const ICONOS = {
  idea: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
  guion: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
  video: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9l5 3-5 3z"/>',
  voz: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  imagen: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="16" cy="9" r="1.6"/>',
  mapa: '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
  calendario: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  persona: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  pareja: '<circle cx="8" cy="8" r="3.2"/><circle cx="16.5" cy="9" r="2.8"/><path d="M2.5 20c1-3.5 3-5 5.5-5s4.5 1.5 5.5 5M14 15.5c2.6-.6 5.6.5 7 4.5"/>',
  auto: '<path d="M4 16v-4l2-5h12l2 5v4z"/><circle cx="7.5" cy="16.5" r="1.8"/><circle cx="16.5" cy="16.5" r="1.8"/><path d="M4 12h16"/>',
  dinero: '<circle cx="12" cy="12" r="9"/><path d="M15 8.5c-.8-.9-2-1.3-3.2-1.3-1.8 0-3 .9-3 2.3 0 3.2 6.4 1.8 6.4 5 0 1.4-1.3 2.4-3.3 2.4-1.3 0-2.6-.5-3.4-1.4M12 5v2.2M12 17v2"/>',
  estrella: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
  escudo: '<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z"/>',
  mando: '<path d="M7 8h10a5 5 0 0 1 4.6 7l-.6 1.6a2.4 2.4 0 0 1-4 .7L15 15H9l-2 2.3a2.4 2.4 0 0 1-4-.7L2.4 15A5 5 0 0 1 7 8z"/><path d="M7 11v3M5.5 12.5h3M16 12h.01M18 13.5h.01"/>',
  herramienta: '<path d="M14.5 6.5a4 4 0 0 0 5 5L12 19l-3 1 1-3 7.5-7.5"/><path d="M4 4l6 6"/>',
  check: '<path d="M4 12.5l5 5L20 6.5"/>',
};
const icono = (n) => ICONOS[n] ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONOS[n]}</svg>` : n;
const fotograma = (pref, i) => pref + String(i).padStart(5, "0") + ".jpg";
const poner = (img, src) => { if (!img.src.endsWith(src)) img.src = src; };
const nuevoPuente = (src) => { const c = document.createElement("div"); c.className = "puente";
  const img = document.createElement("img"); img.src = src; c.appendChild(img); capa.appendChild(c); return c; };
// Las piezas de cada escena se crean una vez; __s4(t) solo las coloca.
ESC.forEach((e, i) => {
  e.nodos = e.imagenes.map((im, k) => {
    const c = document.createElement("div"); c.className = "carta";
    const img = document.createElement("img"); img.src = im.frames ? im.pref + "00001.jpg" : im.src; c.appendChild(img);
    capa.appendChild(c);
    let r = null;
    if (im.etiqueta) { r = document.createElement("div"); r.className = "rotulo"; r.textContent = im.etiqueta;
      r.style.color = im.color || "#ff3ea5"; capa.appendChild(r); }
    return { c, img, r, im };
  });
  if (e.titulo) { e.t = document.createElement("div"); e.t.className = "titulo"; e.t.textContent = e.titulo; capa.appendChild(e.t); }
  if (e.panel) {
    const pn = document.createElement("div"); pn.className = "panel";
    if (e.panel.titulo) { const h = document.createElement("h2"); h.textContent = e.panel.titulo; pn.appendChild(h); }
    e.items = (e.panel.items || []).map((tx, k) => {
      const it = document.createElement("div"); it.className = "item";
      it.innerHTML = `<b>${icono(e.panel.iconos?.[k] || String(k + 1))}</b><span></span>`; it.querySelector("span").textContent = tx;
      pn.appendChild(it); return it;
    });
    if (e.panel.nota) { const n = document.createElement("div"); n.className = "nota"; n.textContent = e.panel.nota; pn.appendChild(n); }
    capa.appendChild(pn); e.pn = pn;
  }
  e.pEntra = e.entra ? nuevoPuente(e.entra) : null;
  e.pSale = e.sale ? nuevoPuente(e.sale) : null;
  if (e.pSale) e.pSale.style.zIndex = 8;
  if (e.sale && e.etiqueta) { e.rs = document.createElement("div"); e.rs.className = "rotulo"; e.rs.textContent = e.etiqueta;
    e.rs.style.color = e.color || "var(--ac)"; e.rs.style.zIndex = 9; capa.appendChild(e.rs); }
});
// Rejilla en perspectiva (suelo y techo) que avanza hacia la cámara, con partículas de luz que suben despacio.
const lienzo = document.getElementById("fondo"), g = lienzo.getContext("2d");
const AC = getComputedStyle(document.documentElement).getPropertyValue("--ac").trim() || "#39ff88";
const rgb = ((h) => { const n = parseInt(h.replace("#", ""), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; })(AC);
const col = (a) => `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;
const azar = (s) => { const x = Math.sin(s * 127.1) * 43758.5453; return x - Math.floor(x); };
function rejilla(t, fuerza) {
  g.clearRect(0, 0, W, H);
  if (fuerza <= 0) return;
  g.globalAlpha = fuerza;
  const fx = W / 2, horizonte = [H * 0.70, H * 0.30];
  const tenue = conAmbiente ? 0.45 : 1;   // sobre el vídeo desenfocado la rejilla es solo un rastro de luz
  [[1, 0.55 * tenue], [-1, 0.22 * tenue]].forEach(([dir, f], k) => {
    const hz = horizonte[k], borde = dir > 0 ? H : 0;
    for (let i = -14; i <= 14; i++) {
      g.strokeStyle = col(f * 0.5); g.lineWidth = 2;
      g.beginPath(); g.moveTo(fx + i * 18, hz); g.lineTo(fx + i * W * 0.22, borde); g.stroke();
    }
    for (let j = 0; j < 14; j++) {
      const z = ((j + (t * 0.6) % 1) / 14);
      const y = hz + (borde - hz) * Math.pow(z, 2.2);
      g.strokeStyle = col(f * Math.min(1, z * 1.6)); g.lineWidth = 1 + 2 * z;
      g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    }
  });
  // un destello que recorre el horizonte de vez en cuando
  const barrido = ((t * 0.35) % 1) * W * 1.6 - W * 0.3;
  const gr = g.createLinearGradient(barrido - 260, 0, barrido + 260, 0);
  gr.addColorStop(0, col(0)); gr.addColorStop(0.5, col(0.55)); gr.addColorStop(1, col(0));
  g.fillStyle = gr; g.fillRect(0, H * 0.70 - 2, W, 4); g.fillRect(0, H * 0.30 - 2, W, 4);
  for (let k = 0; k < 46; k++) {
    const x = azar(k + 1) * W, v = 0.02 + azar(k + 7) * 0.05;
    const y = H - ((azar(k + 3) + t * v) % 1) * H * 1.1;
    const r = 1.5 + azar(k + 5) * 3.5, a = 0.25 + 0.5 * Math.abs(Math.sin(t * 1.7 + k));
    g.fillStyle = col(a); g.shadowColor = col(0.9); g.shadowBlur = 12;
    g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
  }
  g.shadowBlur = 0; g.globalAlpha = 1;
}
// Una tarjeta de vídeo (siempre en 16:9 o el formato del vídeo, para que el encuadre sea el mismo) en un hueco.
const hueco = (cx, cy, w, giro) => ({ x: cx - w / 2, y: cy - w * H / W / 2, w, h: w * H / W, giro });
const PANTALLA = { x: 0, y: 0, w: W, h: H, giro: 0 };
function colocar(nodo, a, b, p, flota, brillo) {
  const x = mezcla(a.x, b.x, p), y = mezcla(a.y, b.y, p) + flota, w = mezcla(a.w, b.w, p), h = mezcla(a.h, b.h, p);
  const lejos = Math.max(fueraDe(0, 0.15, Math.abs(1 - w / W)), 0);   // a pantalla completa: sin bordes ni giro
  nodo.style.left = x + "px"; nodo.style.top = y + "px"; nodo.style.width = w + "px"; nodo.style.height = h + "px";
  nodo.style.borderRadius = 26 * lejos + "px";
  nodo.style.transform = `perspective(1600px) rotateY(${mezcla(a.giro, b.giro, p)}deg)`;
  nodo.style.setProperty("--borde", 2 * lejos + "px");
  nodo.style.boxShadow = lejos ? `0 0 ${(30 + 16 * brillo) * lejos}px ${col(0.45 * lejos)}, 0 30px 80px rgba(0,0,0,${0.7 * lejos})` : "none";
}
window.__s4 = (t) => {
  let fondo = 0;
  ESC.forEach((e) => {
    const visible = t >= e.ini - 0.01 && t < e.fin + 0.35;
    const u = t - e.ini, dur = e.fin - e.ini;
    // entrada: el último fotograma del vídeo se encoge; salida: el primero del siguiente crece a pantalla completa
    const pin = e.pEntra ? salida(fueraDe(0, 0.6, u)) : 1;
    const pout = e.pSale ? suave(fueraDe(dur - 0.62, dur - 1 / FPS, u)) : 0;
    if (visible) fondo = Math.max(fondo, Math.min(e.pEntra ? fueraDe(0, 0.35, u) : salida(fueraDe(0, 0.3, u)), 1 - pout));
    const conPanel = !!e.pn;
    const sitioA = VERTICAL ? hueco(W * 0.5, H * 0.16, W * 0.62, 0)
      : conPanel ? hueco(W * 0.25, H * 0.33, W * 0.36, 14) : hueco(W * 0.27, H * 0.44, W * 0.36, 16);
    const sitioB = VERTICAL ? hueco(W * 0.5, H * 0.66, W * 0.62, 0)
      : conPanel ? hueco(W * 0.31, H * 0.66, W * 0.30, 10) : hueco(W * 0.63, H * 0.46, W * 0.5, -10);
    if (e.pEntra) {
      e.pEntra.style.opacity = visible ? 1 - pout : 0;
      e.pEntra.style.zIndex = pin < 1 ? 7 : 2;
      colocar(e.pEntra, PANTALLA, sitioA, pin, Math.sin(t * 1.2) * 8 * pin, Math.sin(t * 2));
      e.pEntra.firstChild.style.transform = `scale(${1 + 0.05 * pin})`;
      if (e.entra_n) {   // sigue el plano anterior; si se acaba, va y vuelve despacio (nunca se queda quieto)
        const n = e.entra_n, ciclo = Math.max(1, 2 * (n - 1)), atras = e.entra_modo === "atras";
        // «atras»: empieza en su último fotograma (el que se veía a pantalla completa) y retrocede a media velocidad
        let j = Math.floor(Math.max(0, u) * FPS * (atras ? 0.5 : 1)) % ciclo; if (j >= n) j = ciclo - j;
        poner(e.pEntra.firstChild, fotograma(e.entra_pref, Math.min(n, (atras ? n - 1 - j : j) + 1)));
      }
      e.pEntra.firstChild.style.filter = `brightness(${1 - 0.25 * pin})`;
    }
    if (e.pSale) {
      // aparece desde la derecha, flota en su sitio y al final crece hasta ser el vídeo siguiente
      const llega = salida(fueraDe(conPanel ? 0.9 : 0.25, conPanel ? 1.45 : 0.85, u));
      const desde = conPanel ? { ...sitioB, y: sitioB.y + H * 0.55, giro: sitioB.giro + 25 }
        : { ...sitioB, x: sitioB.x + W * 0.7, giro: sitioB.giro - 40 };
      const enSitio = { ...sitioB, x: mezcla(desde.x, sitioB.x, llega), y: mezcla(desde.y, sitioB.y, llega),
        giro: mezcla(desde.giro, sitioB.giro, llega) };
      e.pSale.style.opacity = visible ? Math.max(llega, pout) : 0;
      colocar(e.pSale, enSitio, PANTALLA, pout, Math.sin(t * 1.4 + 1) * 8 * (1 - pout), Math.sin(t * 2 + 1));
      e.pSale.firstChild.style.transform = `scale(${1.04 - 0.04 * pout})`;
      if (e.sale_n) {
        const n = e.sale_n, falta = Math.max(0, Math.round((dur - 1 / FPS - u) * FPS));
        let i;
        if (e.sale_modo === "hacia") {   // va y vuelve despacio y acaba en su primer fotograma, donde sigue el vídeo
          const ciclo = Math.max(1, 2 * (n - 1));
          let j = Math.floor(falta * 0.5) % ciclo; if (j >= n) j = ciclo - j;
          i = j + 1;
        } else {   // el arranque del plano siguiente: su último fotograma llega justo a pantalla completa
          i = Math.max(1, n - falta);
        }
        poner(e.pSale.firstChild, fotograma(e.sale_pref, Math.min(n, i)));
      }
      if (e.rs) {
        const q = fueraDe(0.45, 0.8, u - (conPanel ? 0.65 : 0.2));
        e.rs.style.opacity = visible ? Math.min(q * 3, 1 - fueraDe(0, 0.35, pout)) : 0;
        e.rs.style.left = (sitioB.x + sitioB.w / 2) + "px"; e.rs.style.top = (sitioB.y + sitioB.h - 40) + "px";
        e.rs.style.transform = `translateX(-50%) scale(${q > 0 ? rebote(q) : 0})`;
      }
    }
    const n = e.nodos.length;
    const ancho = W * (VERTICAL ? 0.92 : 0.6);
    const alto = n === 1 && VERTICAL ? ancho * 5 / 4 : ancho * 9 / 16;
    const centros = n === 1 ? [H * (VERTICAL ? 0.39 : 0.45)] : VERTICAL ? [H * 0.23, H * 0.56] : [H * 0.28, H * 0.68];
    e.nodos.forEach((nd, k) => {
      if (!visible) { nd.c.style.opacity = 0; if (nd.r) nd.r.style.opacity = 0; return; }
      const v = u - k * 0.22;
      const ent = salida(fueraDe(0, 0.5, v)), sal = fueraDe(dur - 0.05, dur + 0.3, u);
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
      nd.img.style.transform = `scale(${1.04 + 0.08 * fueraDe(0, dur, u)})`;
      if (nd.im.frames) {
        const nf = nd.im.frames, necesarios = (dur + 0.3) * FPS;
        const vel = Math.max(0.5, Math.min(1, nf / necesarios));
        let j = Math.floor(Math.max(0, u) * FPS * vel);
        const ciclo = Math.max(1, 2 * (nf - 1));
        j = j % ciclo; if (j >= nf) j = ciclo - j;
        const i = Math.min(nf, Math.max(1, j + 1));
        const src = nd.im.pref + String(i).padStart(5, "0") + ".jpg";
        if (!nd.img.src.endsWith(src)) nd.img.src = src;
      }
      if (nd.r) {
        const p = fueraDe(0.45, 0.8, v);
        nd.r.style.opacity = Math.min(p * 3, 1 - sal);
        nd.r.style.top = (centros[k] + alto / 2 - 46) + "px";
        nd.r.style.transform = `translateX(-50%) scale(${p > 0 ? rebote(p) : 0})`;
      }
    });
    if (e.pn) {
      const p = salida(fueraDe(e.pEntra ? 0.25 : 0, e.pEntra ? 0.75 : 0.45, u));
      const sal = e.pSale ? fueraDe(0, 0.6, pout) : fueraDe(dur - 0.05, dur + 0.3, u);
      e.pn.style.opacity = visible ? Math.min(p, 1 - sal) : 0;
      const ancho = VERTICAL ? W * 0.86 : W * 0.44;
      e.pn.style.width = ancho + "px";
      e.pn.style.left = (VERTICAL ? W * 0.07 : W * 0.525) + "px";
      e.pn.style.top = (VERTICAL ? H * 0.38 : H * 0.45) + "px";
      const flota = Math.sin(t * 1.1) * 6;
      e.pn.style.transform = `translateY(calc(-50% + ${(1 - p) * 70 + flota}px)) perspective(1600px) rotateX(${(1 - p) * 22}deg) rotateY(${VERTICAL ? 0 : -6 * p}deg) scale(${(0.92 + 0.08 * p) * (1 + 0.06 * sal)})`;
      e.pn.style.filter = sal ? `blur(${sal * 8}px)` : "none";
      const pulso = 0.5 + 0.5 * Math.sin(t * 2.2);
      e.pn.style.boxShadow = `0 0 ${50 + 30 * pulso}px ${col(0.28 + 0.12 * pulso)}, inset 0 0 40px ${col(0.08)}, 0 30px 90px rgba(0,0,0,.75)`;
      const vuelta = u < 0.7 ? 0 : ((u - 0.7) % 4.5) / 0.9;   // el brillo cruza el panel al llegar y cada 4,5 s
      e.pn.style.setProperty("--brillo", mezcla(-120, 160, Math.min(1, vuelta)) + "%");
      const base = e.pEntra ? 0.75 : 0.45;
      e.items.forEach((it, k) => {
        const q = fueraDe(base + k * 0.42, base + 0.32 + k * 0.42, u);
        it.style.opacity = q; it.style.transform = `translateX(${(1 - salida(q)) * 90}px) scale(${0.96 + 0.04 * salida(q)})`;
      });
    }
    if (e.t) {
      const p = salida(fueraDe(0.1, 0.55, u)), sal = fueraDe(dur - 0.05, dur + 0.3, u);
      e.t.style.opacity = visible ? Math.min(p, 1 - sal) : 0;
      e.t.style.top = (n === 0 ? H * 0.36 : H * 0.055) + "px";
      e.t.style.transform = `translateY(${(1 - p) * 60}px) scale(${0.92 + 0.08 * p})`;
    }
  });
  const puentes = ESC.some((e) => e.pEntra || e.pSale);
  rejilla(t, puentes ? fondo : 1);
  halo.style.opacity = puentes ? fondo : 1;
  ambiente.style.opacity = puentes ? fondo : 0;
  ambiente.style.transform = `scale(${1.02 + 0.04 * Math.sin(t * 0.25)}) translateX(${Math.sin(t * 0.2) * 12}px)`;
  rayos.style.opacity = puentes ? fondo * (0.75 + 0.25 * Math.sin(t * 1.3)) : 0;
  rayos.style.transform = `rotate(${Math.sin(t * 0.3) * 4}deg)`;
};
window.__s4(0);
</script></body></html>"""


ICONOS_AUTO = [   # (icono, pistas en el texto del punto): el primero que encaje; si ninguno, va su número
    ("calendario", r"\b(19|20)\d\d\b|\d{1,2}[-/]\d{1,2}|\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|"
                   r"octubre|noviembre|diciembre|año|años|fecha|sale|lanzamiento)\b"),
    ("pareja", r"^\w+ (y|e) \w+$|\b(pareja|dúo|equipo|pandilla|amigos|cooperativo)\b"),
    ("mapa", r"\b(city|ciudad|leonida|mapa|isla|barrio|nueva york|coney|miami|estado|zona)\b"),
    ("auto", r"\b(auto|autos|coche|carro|vehículo|moto|estéreo|desguace)\b"),
    ("dinero", r"\$|\b(dinero|precio|pago|robo|robar|asalto|tienda|pagar)\b"),
    ("escudo", r"\b(policía|rastreador|alarma|seguridad|inmovilizador)\b"),
    ("mando", r"\b(jugar|juego|jugable|mecánica|minijuego|misión|consola)\b"),
    ("herramienta", r"\b(herramienta|barra|clonador|tornillos?|palanca|romper)\b"),
    ("persona", r"\b(jason|lucía|lucia|protagonista|personaje)\b"),
]


def icono_para(texto: str) -> str:
    """El icono de un punto del panel según lo que dice («Sale el 19-11-2026» → calendario)."""
    import re
    t = texto.lower().strip()
    return next((nombre for nombre, pista in ICONOS_AUTO if re.search(pista, t)), "")


def _base(ancho: int, alto: int) -> tuple[int, int]:
    """El tamaño en el que se diseña la página (los textos y paneles están medidos para él). Una previa más pequeña
    se dibuja igual y se reduce con zoom: se ve idéntica al final, solo con menos píxeles."""
    return (1080, 1920) if alto > ancho else (1920, 1080)


def _html(escenas: list[dict[str, Any]], ancho: int, alto: int, fps: int = config.FPS, logo: str = "") -> str:
    base_w, base_h = _base(ancho, alto)
    def con_iconos(panel: dict[str, Any] | None) -> dict[str, Any] | None:
        if not panel:
            return panel
        dados = list(panel.get("iconos") or [])
        items = panel.get("items", [])
        return {**panel, "iconos": [dados[k] if k < len(dados) and dados[k] else icono_para(tx) or str(k + 1)
                                    for k, tx in enumerate(items)]}
    limpias = [{"ini": round(e["ini"], 3), "fin": round(e["fin"], 3), "titulo": e.get("titulo", ""),
                "panel": con_iconos(e.get("panel")),
                "entra": e.get("entra", ""), "sale": e.get("sale", ""), "etiqueta": e.get("etiqueta", ""),
                "entra_pref": e.get("entra_pref", ""), "entra_n": e.get("entra_n", 0),
                "sale_pref": e.get("sale_pref", ""), "sale_n": e.get("sale_n", 0),
                "entra_modo": e.get("entra_modo", ""), "sale_modo": e.get("sale_modo", ""),
                "color": COLORES.get(e.get("color", ""), e.get("color", "")),
                "imagenes": [{"src": i.get("src", ""), "frames": i.get("frames", 0), "pref": i.get("pref", ""),
                              "etiqueta": i.get("etiqueta", ""), "color": COLORES.get(i.get("color", ""), i.get("color", ""))}
                             for i in e.get("imagenes", [])]} for e in escenas]
    return (PLANTILLA.replace("__ESCENAS__", json.dumps(limpias, ensure_ascii=False))
            .replace("__LOGO__", f'<img id="logo" src="{logo}">' if logo else "")
            .replace("__ACENTO__", ACENTO).replace("__ZOOM__", f"{ancho / base_w:.4f}")
            .replace("__FPS__", str(fps)).replace("__W__", str(base_w)).replace("__H__", str(base_h)))


def sonidos_de(escenas: list[dict[str, Any]]) -> list[tuple[float, str]]:
    """Dónde va cada efecto: whoosh al entrar cada tarjeta y pop cuando salta su rótulo."""
    marcas: list[tuple[float, str]] = []
    for e in escenas:
        for k, im in enumerate(e.get("imagenes", [])):
            marcas.append((max(0.0, e["ini"] + k * 0.22 - 0.05), "whoosh"))
            if im.get("etiqueta"):
                marcas.append((e["ini"] + k * 0.22 + 0.5, "pop"))
        if (e.get("titulo") or e.get("panel")) and not e.get("imagenes"):
            marcas.append((e["ini"] + 0.05, "whoosh"))
        for k, _ in enumerate((e.get("panel") or {}).get("items", [])):
            marcas.append((e["ini"] + 0.45 + k * 0.45, "pop"))
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
               fps: int = config.FPS, avisar: Callable[[str, int], None] = lambda *_: None, logo: Path | None = None) -> Path:
    """El vídeo de la animación, sin audio. `escenas`: [{ini, fin, titulo?, panel?, imagenes: [...]}], donde cada
    imagen es {archivo} (foto) o {video, desde} (un clip que avanza dentro de la tarjeta), con etiqueta y color.
    Puentes con el vídeo (sin corte brusco): `entra` es el último fotograma del plano anterior, que empieza a pantalla
    completa y se encoge a tarjeta; `sale`, el primero del siguiente, que crece hasta la pantalla completa al final
    (con `etiqueta` y `color` opcionales). El fondo es entonces ese mismo vídeo, desenfocado.
    `logo`: la marca del canal, discreta en una esquina de todas las escenas."""
    from playwright.sync_api import sync_playwright
    trabajo = Path(tempfile.mkdtemp(prefix="s4_anim_", dir=config.PRODUCCIONES))
    try:
        shutil.copy(FUENTES / "geist-latin-wght-normal.woff2", trabajo / "geist.woff2")
        propias = []
        for k, e in enumerate(escenas):   # las imágenes van junto a la página: Edge no lee rutas sueltas del disco
            ims = []
            for j, im in enumerate(e.get("imagenes", [])):
                if im.get("video"):   # el clip, en fotogramas JPG del ancho de la tarjeta: se avanza uno por cuadro
                    carpeta_f = trabajo / f"c{k:02d}_{j}"
                    carpeta_f.mkdir()
                    # solo el plano elegido [desde, hasta]: nunca se cuela el plano siguiente del vídeo de origen
                    largo = (float(im["hasta"]) - float(im.get("desde", 0))) if im.get("hasta") else e["fin"] - e["ini"] + 0.5
                    medios.ffmpeg("-ss", f"{float(im.get('desde', 0)):.3f}", "-i", str(im["video"]),
                                  "-t", f"{max(0.3, largo - 0.05):.3f}", "-an", "-vf", f"fps={fps},scale=1000:-2",
                                  "-q:v", "3", str(carpeta_f / "f%05d.jpg"))
                    ims.append({**im, "frames": len(list(carpeta_f.glob("f*.jpg"))), "pref": f"c{k:02d}_{j}/f"})
                    continue
                nombre = f"i{k:02d}_{j}{Path(im['archivo']).suffix.lower()}"
                shutil.copy(im["archivo"], trabajo / nombre)
                ims.append({**im, "src": nombre})
            puentes = {}
            for clave in ("entra", "sale"):
                if e.get(clave):
                    nombre = f"{clave}{k:02d}{Path(e[clave]).suffix.lower()}"
                    shutil.copy(e[clave], trabajo / nombre)
                    puentes[clave] = nombre
                if e.get(f"{clave}_video"):   # la tarjeta en movimiento: sus fotogramas a calidad casi sin pérdida
                    carpeta_f = trabajo / f"{clave}{k:02d}"
                    carpeta_f.mkdir()
                    medios.ffmpeg("-i", str(e[f"{clave}_video"]), "-an", "-vf", f"fps={fps}", "-q:v", "2",
                                  str(carpeta_f / "f%05d.jpg"))
                    puentes[f"{clave}_pref"] = f"{clave}{k:02d}/f"
                    puentes[f"{clave}_n"] = len(list(carpeta_f.glob("f*.jpg")))
            propias.append({**e, **puentes, "imagenes": ims})
        pagina = trabajo / "anim.html"
        if logo:
            shutil.copy(logo, trabajo / f"logo{Path(logo).suffix.lower()}")
        pagina.write_text(_html(propias, ancho, alto, fps, f"logo{Path(logo).suffix.lower()}" if logo else ""),
                          encoding="utf-8")
        cuadros = int(math.ceil(total * fps))
        destino.parent.mkdir(parents=True, exist_ok=True)
        alta = ancho * alto >= 1920 * 1080   # en el final, cada cuadro sin pérdida (PNG); en la previa basta JPG
        ffmpeg = subprocess.Popen(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
                                   "-c:v", "libx264", "-preset", "medium", "-crf", "16" if alta else "20", "-pix_fmt", "yuv420p",
                                   "-movflags", "+faststart", str(destino)], stdin=subprocess.PIPE)
        try:
            with sync_playwright() as pw:
                nav = pw.chromium.launch(channel="msedge", headless=True)
                pag = nav.new_page(viewport={"width": ancho, "height": alto})
                pag.goto(pagina.as_uri())
                pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
                for n in range(cuadros):
                    pag.evaluate(f"window.__s4({n / fps:.5f})")
                    pag.wait_for_function("[...document.images].every(i => i.complete)")   # el fotograma del clip
                    ffmpeg.stdin.write(pag.screenshot(type="png") if alta else pag.screenshot(type="jpeg", quality=92))
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
