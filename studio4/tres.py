"""Escenas 3D de verdad con Three.js (WebGL): las mismas maquetas del estilo isométrico, pero con volumen real, luces
que proyectan sombras, materiales con brillo, niebla, resplandor (bloom) en luces y ventanas y una cámara 3D que se
mueve. Todo con formas geométricas originales (sin personajes ni logotipos).

El navegador del PC dibuja cada fotograma cuando se le pide (`dibujar(t)`): así la animación es exacta, sin tirones,
aunque el PC no tenga tarjeta gráfica (se dibuja con el procesador). Three.js va en web/vendor/three (licencia MIT).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from . import config, isometrico

VENDOR = config.RAIZ / "web" / "vendor" / "three"
CAMARAS = ("orbita", "acercar", "grua", "paneo", "alejar")

JS = r"""
import * as THREE from 'three';
import { EffectComposer } from './jsm/postprocessing/EffectComposer.js';
import { RenderPass } from './jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from './jsm/postprocessing/UnrealBloomPass.js';

const col = (c) => new THREE.Color(c).convertSRGBToLinear();
const E = window.ESCENA, CAM = window.CAMARA, DUR = window.SEGUNDOS, W = window.ANCHO, H = window.ALTO;
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setSize(W, H); renderer.setPixelRatio(1);
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputEncoding = THREE.sRGBEncoding; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.9;
document.body.appendChild(renderer.domElement);

const escena = new THREE.Scene();
escena.background = col(E.fondo);
escena.fog = new THREE.Fog(col(E.fondo), 30, 80);
const camara = new THREE.PerspectiveCamera(32, W / H, 0.1, 200);

// luz: ambiente suave + una luz principal que proyecta sombras + un relleno del color de acento
escena.add(new THREE.HemisphereLight(0x8090c0, 0x100c08, 0.35));
const sol = new THREE.DirectionalLight(0xfff1dc, 0.9);
sol.position.set(-8, 16, 10); sol.castShadow = true;
sol.shadow.mapSize.set(2048, 2048);
Object.assign(sol.shadow.camera, { left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 60 });
escena.add(sol);
const relleno = new THREE.PointLight(col(E.acento), 0.5, 40); relleno.position.set(10, 6, -6); escena.add(relleno);

// la maqueta: x, y en el suelo (en Three.js, x y z) y z hacia arriba (en Three.js, y)
const objetos = E.objetos, cx = window.CENTRO[0], cz = window.CENTRO[1];
const piezas = [];
const azar = (() => { let s = window.SEMILLA; return () => (s = (s * 16807) % 2147483647) / 2147483647; })();
const material = (c, brillo) => new THREE.MeshStandardMaterial({ color: col(c), roughness: brillo ? 0.35 : 0.75, metalness: brillo ? 0.2 : 0.05 });

// el suelo: una losa que recibe las sombras
const suelo = new THREE.Mesh(new THREE.BoxGeometry(window.SUELO[0], 0.4, window.SUELO[1]), material(E.suelo));
suelo.position.set(0, -0.2, 0); suelo.receiveShadow = true; escena.add(suelo);

objetos.forEach((o, k) => {
  const g = new THREE.Group();
  let malla;
  if (o.tipo === 'caja' || o.tipo === 'plataforma') {
    malla = new THREE.Mesh(new THREE.BoxGeometry(o.w, o.h, o.d), material(o.color));
    malla.position.y = o.h / 2;
    if (o.ventanas && o.h >= 0.8) {   // ventanas encendidas: emiten luz (y el bloom las hace brillar)
      const cols = Math.max(1, Math.floor(o.w / 0.45)), pisos = Math.max(1, Math.floor(o.h / 0.5));
      const vmat = new THREE.MeshStandardMaterial({ color: 0x000000, emissive: col(E.acento), emissiveIntensity: 3.0 });
      for (let i = 0; i < cols; i++) for (let j = 0; j < pisos; j++) {
        if (azar() < 0.4) continue;
        const v = new THREE.Mesh(new THREE.PlaneGeometry(o.w / cols * 0.45, o.h / pisos * 0.4), vmat);
        v.position.set(-o.w / 2 + (i + 0.5) * o.w / cols, (j + 0.55) * o.h / pisos, o.d / 2 + 0.01);
        g.add(v);
      }
    }
  } else if (o.tipo === 'piramide') {
    malla = new THREE.Mesh(new THREE.ConeGeometry(Math.max(o.w, o.d) / Math.SQRT2, o.h, 4), material(o.color));
    malla.rotation.y = Math.PI / 4; malla.position.y = o.h / 2;
  } else if (o.tipo === 'cilindro') {
    malla = new THREE.Mesh(new THREE.CylinderGeometry(o.w / 2, o.w / 2, o.h, 32), material(o.color, true));
    malla.position.y = o.h / 2;
  } else if (o.tipo === 'esfera') {
    malla = new THREE.Mesh(new THREE.SphereGeometry(o.w / 2, 32, 24), material(o.color, true));
    malla.position.y = o.w / 2;
  } else {   // luz: una bombilla que emite y una luz puntual que ilumina lo de alrededor
    malla = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.15, o.w * 0.25), 24, 16),
      new THREE.MeshStandardMaterial({ color: 0x000000, emissive: col(o.color || E.acento), emissiveIntensity: 4 }));
    const p = new THREE.PointLight(col(o.color || E.acento), 1.6, 10, 1.6); g.add(p); g.userData.luz = p;
  }
  malla.castShadow = o.tipo !== 'luz'; malla.receiveShadow = true;
  g.add(malla);
  const w = o.tipo === 'luz' ? 0 : o.w, d = o.tipo === 'luz' ? 0 : (o.d || o.w);
  g.position.set(o.x + w / 2 - cx, o.z, o.y + d / 2 - cz);
  g.userData.base = g.position.y; g.userData.k = k; g.userData.luzBase = g.userData.luz ? g.userData.luz.intensity : 0;
  escena.add(g); piezas.push(g);
});

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(escena, camara));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), 0.75, 0.5, 0.88));

const R = window.RADIO;
const suave = (x) => x * x * (3 - 2 * x);
window.dibujar = (t) => {
  const p = Math.min(1, t / DUR), s = suave(p);
  // las piezas caen desde arriba una tras otra (la maqueta se construye) y las luces laten
  piezas.forEach((g) => {
    const inicio = Math.min(1.2, g.userData.k * 0.06), e = Math.min(1, Math.max(0, (t - inicio) / 0.7));
    const rebote = 1 - Math.pow(1 - e, 3);
    g.position.y = g.userData.base + (1 - rebote) * 6;
    g.scale.setScalar(0.001 + 0.999 * rebote);
    if (g.userData.luz) g.userData.luz.intensity = g.userData.luzBase * (0.75 + 0.25 * Math.sin(t * 3.4 + g.userData.k));
  });
  // la cámara: cada tipo, un movimiento distinto a lo largo de toda la escena
  let ang = 0.75, alto = R * 1.05, dist = R * 2.3;
  if (CAM === 'orbita') ang = 0.35 + 0.9 * s;
  if (CAM === 'acercar') { dist = R * (2.7 - 0.9 * s); ang = 0.7 + 0.15 * s; }
  if (CAM === 'alejar') { dist = R * (1.7 + 0.9 * s); ang = 0.9 - 0.15 * s; }
  if (CAM === 'grua') { alto = R * (0.4 + 1.1 * s); ang = 0.6 + 0.3 * s; }
  if (CAM === 'paneo') { ang = 1.15 - 0.7 * s; dist = R * 2.2; }
  camara.position.set(Math.sin(ang) * dist, alto, Math.cos(ang) * dist);
  camara.lookAt(0, R * 0.18, 0);
  composer.render();
};
window.dibujar(0);
window.listo = true;
"""


def _encuadre(escena: dict[str, Any]) -> tuple[list[float], list[float], float]:
    objs = escena["objetos"]
    if not objs:
        return [0.0, 0.0], [10.0, 10.0], 8.0
    x0 = min(o["x"] for o in objs) - 1.5
    y0 = min(o["y"] for o in objs) - 1.5
    x1 = max(o["x"] + o["w"] for o in objs) + 1.5
    y1 = max(o["y"] + o["d"] for o in objs) + 1.5
    alto = max(o["z"] + o["h"] for o in objs)
    radio = max(x1 - x0, y1 - y0, alto * 1.6) * 0.75
    return [(x0 + x1) / 2, (y0 + y1) / 2], [x1 - x0, y1 - y0], radio


def html(escena: dict[str, Any], camara: str, segundos: float, ancho: int, alto: int, semilla: int = 7) -> str:
    e = isometrico.validar(escena)
    centro, suelo, radio = _encuadre(e)
    datos = {"ESCENA": e, "CAMARA": camara if camara in CAMARAS else "orbita", "SEGUNDOS": max(0.5, segundos),
             "ANCHO": ancho, "ALTO": alto, "CENTRO": centro, "SUELO": suelo, "RADIO": radio, "SEMILLA": max(1, semilla % 2147483646)}
    previas = "".join(f"window.{k} = {json.dumps(v, ensure_ascii=False)};" for k, v in datos.items())
    return (f'<!doctype html><meta charset="utf-8"><style>body{{margin:0;background:#000;overflow:hidden}}</style>'
            f'<script type="importmap">{{"imports": {{"three": "./three.module.js"}}}}</script>'
            f"<script>{previas}</script><script type=\"module\">{JS}</script>")


def animar(escena: dict[str, Any], destino: Path, segundos: float, camara: str = "orbita", ancho: int = 1920,
           alto: int = 1080, semilla: int = 7, fps: int = 30) -> Path:
    """La escena 3D a MP4, fotograma a fotograma (exacto). Se dibuja a 1280×720 y se escala: en un PC sin tarjeta
    gráfica, el 3D con sombras y resplandor a 1080p sería demasiado lento."""
    from playwright.sync_api import sync_playwright
    destino.parent.mkdir(parents=True, exist_ok=True)
    w, h = (1280, 720) if ancho >= 1280 else (ancho, alto)
    pagina = VENDOR / f"_escena_{destino.stem}.html"   # junto a three.module.js: así lo encuentra el importmap
    pagina.write_text(html(escena, camara, segundos, w, h, semilla), encoding="utf-8")
    cuadros = max(2, round(segundos * fps))
    ff = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
                           "-i", "-", "-vf", f"scale={ancho}:{alto}:flags=lanczos", "-c:v", "libx264", "-preset", "medium",
                           "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), str(destino)], stdin=subprocess.PIPE)
    try:
        with sync_playwright() as pw:
            nav = pw.chromium.launch(channel="msedge", headless=True,
                                     args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
            pag = nav.new_page(viewport={"width": w, "height": h})
            errores: list[str] = []
            pag.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
            pag.on("pageerror", lambda e: errores.append(str(e)))

            def servir(ruta):   # los módulos no cargan desde file://: se sirven desde una dirección interna
                archivo = VENDOR / ruta.request.url.split("http://studio4.local/", 1)[1].split("?")[0]
                if archivo.is_file() and VENDOR in archivo.resolve().parents:
                    tipo = "text/html" if archivo.suffix == ".html" else "text/javascript"
                    ruta.fulfill(status=200, body=archivo.read_bytes(), headers={"Content-Type": tipo})
                else:
                    ruta.fulfill(status=404, body=b"")
            pag.route("http://studio4.local/**", servir)
            pag.goto(f"http://studio4.local/{pagina.name}")
            try:
                pag.wait_for_function("window.listo === true", timeout=90000)
            except Exception as e:
                raise RuntimeError(f"La escena 3D no arrancó: {'; '.join(errores[:3]) or e}") from e
            lienzo = pag.locator("canvas")
            for i in range(cuadros):
                pag.evaluate(f"window.dibujar({i / fps})")
                ff.stdin.write(lienzo.screenshot(type="jpeg", quality=92))
            nav.close()
    finally:
        ff.stdin.close()
        ff.wait()
        pagina.unlink(missing_ok=True)
    if ff.returncode != 0 or not destino.exists():
        raise RuntimeError("No se pudo animar la escena 3D.")
    return destino
