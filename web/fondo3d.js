// Fondo vivo del panel con Three.js: una escena distinta para cada tema, detrás de todo y sin quitar protagonismo.
// Los temas premium se mueven (despacio); los de descanso visual apenas respiran. «Menos movimiento» lo deja quieto.
import * as THREE from "three";

const lienzo = document.createElement("canvas");
lienzo.className = "fondo3d";
lienzo.setAttribute("aria-hidden", "true");
document.body.prepend(lienzo);

let render;
try {
  render = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true, alpha: true, powerPreference: "low-power" });
} catch (e) {
  lienzo.remove();   // sin WebGL: queda el fondo de CSS, que ya es bonito
  throw e;
}
render.setPixelRatio(Math.min(1.5, window.devicePixelRatio || 1));
const escena = new THREE.Scene();
const camara = new THREE.PerspectiveCamera(55, 1, 0.1, 200);
camara.position.set(0, 0, 30);
const raton = { x: 0, y: 0, vx: 0, vy: 0 };
window.addEventListener("pointermove", (ev) => { raton.x = ev.clientX / innerWidth - 0.5; raton.y = ev.clientY / innerHeight - 0.5; }, { passive: true });

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "#ffffff";
const color = (v) => new THREE.Color(css(v));
const quieto = () => document.documentElement.classList.contains("quieto") || matchMedia("(prefers-reduced-motion: reduce)").matches;

// textura de punto suave (un círculo con halo) para todas las partículas
const punto = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d"), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.25, "rgba(255,255,255,.7)"); r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
})();

// halo: una luz redonda muy difuminada (para esferas de luz, soles y burbujas: sin bordes duros)
const halo = (() => {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d"), r = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.35, "rgba(255,255,255,.45)"); r.addColorStop(0.7, "rgba(255,255,255,.1)");
  r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
})();
function luz(colorLuz, tam, opacidad, aditivo = true) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo, color: colorLuz, transparent: true, opacity: opacidad, depthWrite: false,
    blending: aditivo ? THREE.AdditiveBlending : THREE.NormalBlending }));
  s.scale.setScalar(tam);
  return s;
}

function particulas(n, repartir, { tam = 0.6, colores, opacidad = 0.8, aditivo = true } = {}) {
  const pos = new Float32Array(n * 3), col = new Float32Array(n * 3), semilla = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const [x, y, z] = repartir(i);
    pos.set([x, y, z], i * 3);
    const c = colores[i % colores.length]; col.set([c.r, c.g, c.b], i * 3);
    semilla[i] = Math.random() * 100;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  geo.userData = { base: pos.slice(), semilla };
  const mat = new THREE.PointsMaterial({ size: tam, map: punto, vertexColors: true, transparent: true, opacity: opacidad, depthWrite: false,
    blending: aditivo ? THREE.AdditiveBlending : THREE.NormalBlending, sizeAttenuation: true });
  return new THREE.Points(geo, mat);
}
const azar = (a) => (Math.random() - 0.5) * a;

// ---------- una escena por tema: crear() devuelve {objetos, mover(t, dt)} ----------
const ESCENAS = {
  cristal() {   // esferas de luz que flotan y polvo de colores
    const cs = [color("--naranja"), color("--rosa"), color("--cian"), color("--violeta")];
    const grupo = new THREE.Group();
    const esferas = cs.map((c, k) => {
      const m = luz(c, 22 + k * 5, 0.32);
      m.userData.fase = k * 1.7; grupo.add(m); return m;
    });
    const polvo = particulas(900, () => [azar(80), azar(50), azar(30) - 5], { tam: 0.35, colores: cs, opacidad: 0.7 });
    grupo.add(polvo);
    return { objetos: [grupo], mover(t) {
      esferas.forEach((m, k) => m.position.set(Math.sin(t * 0.13 + m.userData.fase) * 16, Math.cos(t * 0.11 + m.userData.fase * 1.3) * 9, -4 - k * 2));
      polvo.rotation.y = t * 0.012; polvo.rotation.x = Math.sin(t * 0.05) * 0.08;
    } };
  },
  aurora() {   // cortinas de aurora (shader con ruido) y estrellas
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { t: { value: 0 }, a: { value: color("--naranja") }, b: { value: color("--cian") } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: `uniform float t; uniform vec3 a; uniform vec3 b; varying vec2 vUv;
        float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
        float n(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
          return mix(mix(h(i), h(i+vec2(1,0)), f.x), mix(h(i+vec2(0,1)), h(i+vec2(1,1)), f.x), f.y); }
        void main(){
          float x = vUv.x * 3.0, onda = n(vec2(x * 1.3 + t * 0.05, t * 0.04)) * 0.35;
          float banda = smoothstep(0.0, 0.45, vUv.y - 0.25 - onda) * smoothstep(1.0, 0.45, vUv.y - onda);
          float rayos = 0.55 + 0.45 * n(vec2(x * 12.0, t * 0.15));
          vec3 c = mix(a, b, smoothstep(0.3, 0.9, vUv.y + onda * 0.5));
          gl_FragColor = vec4(c, banda * rayos * 0.42);
        }` });
    const cortina = new THREE.Mesh(new THREE.PlaneGeometry(110, 40, 1, 1), mat);
    cortina.position.set(0, 6, -20);
    const estrellas = particulas(500, () => [azar(140), azar(70) + 5, -40], { tam: 0.35, colores: [new THREE.Color("#ffffff")], opacidad: 0.6 });
    return { objetos: [cortina, estrellas], mover(t) { mat.uniforms.t.value = t; } };
  },
  oro() {   // polvo dorado que cae despacio, como en un archivo antiguo al sol
    const cs = [color("--naranja"), color("--cian"), new THREE.Color("#fff1c7")];
    const p = particulas(1200, () => [azar(90), azar(60), azar(40) - 5], { tam: 0.32, colores: cs, opacidad: 0.75 });
    const pos = p.geometry.attributes.position;
    return { objetos: [p], mover(t, dt) {
      const s = p.geometry.userData.semilla;
      for (let i = 0; i < pos.count; i++) {
        let y = pos.getY(i) - dt * (0.4 + (s[i] % 1) * 0.6);
        if (y < -30) y = 30;
        pos.setY(i, y); pos.setX(i, pos.getX(i) + Math.sin(t * 0.4 + s[i]) * dt * 0.25);
      }
      pos.needsUpdate = true;
    } };
  },
  oceano() {   // mar de puntos con olas lentas
    const cols = 120, filas = 60, cs = [color("--naranja"), color("--rosa"), color("--cian")];
    const p = particulas(cols * filas, (i) => [(i % cols - cols / 2) * 0.9, -10, -Math.floor(i / cols) * 0.9 + 8], { tam: 0.32, colores: cs, opacidad: 0.85 });
    const pos = p.geometry.attributes.position, base = p.geometry.userData.base;
    return { objetos: [p], mover(t) {
      for (let i = 0; i < pos.count; i++) {
        const x = base[i * 3], z = base[i * 3 + 2];
        pos.setY(i, -10 + Math.sin(x * 0.18 + t * 0.6) * 1.4 + Math.cos(z * 0.22 + t * 0.45) * 1.2);
      }
      pos.needsUpdate = true;
    } };
  },
  atardecer() {   // un sol grande que respira sobre un mar de puntos cálidos
    const sol = luz(color("--naranja"), 30, 0.55), cielo = luz(color("--rosa"), 70, 0.22);
    sol.position.set(0, 0, -30); cielo.position.set(0, 0, -32);
    const mar = ESCENAS.oceano();
    return { objetos: [cielo, sol, ...mar.objetos], mover(t, dt) { sol.scale.setScalar(30 * (1 + Math.sin(t * 0.4) * 0.04)); mar.mover(t * 0.7, dt); } };
  },
  neon() {   // cuadrícula synthwave que avanza hacia ti, con estrellas
    const paso = 4, ancho = 160, fondo = 120, v = [], c = [], a = color("--naranja"), b = color("--cian");
    for (let x = -ancho / 2; x <= ancho / 2; x += paso) { v.push(x, 0, 10, x, 0, -fondo); c.push(a.r, a.g, a.b, a.r * 0.2, a.g * 0.2, a.b * 0.2); }
    for (let z = 10; z >= -fondo; z -= paso) {
      const f = 1 + z / fondo * 0.85; v.push(-ancho / 2, 0, z, ancho / 2, 0, z); c.push(b.r * f, b.g * f, b.b * f, b.r * f, b.g * f, b.b * f);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(v, 3)); geo.setAttribute("color", new THREE.Float32BufferAttribute(c, 3));
    const rejilla = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55,
      blending: THREE.AdditiveBlending, depthWrite: false }));
    rejilla.position.y = -8;
    const sol = luz(color("--naranja"), 34, 0.5), brillo = luz(color("--rosa"), 80, 0.2);
    sol.position.set(0, 2, -100); brillo.position.set(0, 2, -102);
    const estrellas = particulas(600, () => [azar(200), Math.random() * 50 + 2, -110], { tam: 0.5, colores: [color("--naranja"), color("--cian"), new THREE.Color("#ffffff")], opacidad: 0.8 });
    return { objetos: [brillo, sol, rejilla, estrellas], mover(t) { rejilla.position.z = (t * 2.2) % paso; sol.material.opacity = 0.45 + Math.sin(t * 0.8) * 0.06; } };
  },
  grafito() {   // una forma de alambre plateada que gira, sobria
    const geo = new THREE.IcosahedronGeometry(11, 1);
    const malla = new THREE.LineSegments(new THREE.WireframeGeometry(geo),
      new THREE.LineBasicMaterial({ color: css("--naranja"), transparent: true, opacity: 0.16 }));
    const nodos = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.5, map: punto, color: css("--cian"), transparent: true, opacity: 0.7, depthWrite: false }));
    const g = new THREE.Group(); g.add(malla, nodos); g.position.set(13, -2, -6);
    return { objetos: [g], mover(t) { g.rotation.y = t * 0.06; g.rotation.x = t * 0.035; } };
  },
  perla() {   // burbujas pastel que suben, en un fondo claro (mezcla normal: lo aditivo se perdería en el blanco)
    const cs = [color("--naranja"), color("--rosa"), color("--cian")];
    const burbujas = Array.from({ length: 26 }, (_, k) => {
      const b = luz(cs[k % 3], 3 + Math.random() * 7, 0.55, false);
      b.position.set(azar(80), azar(60), azar(16) - 8); b.userData = { v: 0.5 + Math.random() * 0.8, f: Math.random() * 9 };
      return b;
    });
    return { objetos: burbujas, mover(t, dt) {
      for (const b of burbujas) {
        b.position.y += dt * b.userData.v; b.position.x += Math.sin(t * 0.3 + b.userData.f) * dt * 0.4;
        if (b.position.y > 34) b.position.y = -34;
      }
    } };
  },
  // --- descanso visual: muy lento, poco brillo ---
  papel() {   // motas de luz en el aire, como polvo en una habitación con sol
    const p = particulas(160, () => [azar(80), azar(55), azar(20) - 5], { tam: 0.5, colores: [color("--naranja"), color("--rosa")], opacidad: 0.45, aditivo: false });
    return { objetos: [p], lento: true, mover(t) { p.rotation.z = Math.sin(t * 0.02) * 0.05; p.position.y = Math.sin(t * 0.05) * 1.2; } };
  },
  bosque() {   // luciérnagas que se encienden y apagan despacio
    const n = 90, p = particulas(n, () => [azar(80), azar(30) - 6, azar(20) - 5], { tam: 0.9, colores: [new THREE.Color("#d8f59a")], opacidad: 0.9 });
    const col = p.geometry.attributes.color, s = p.geometry.userData.semilla, base = p.geometry.userData.base, pos = p.geometry.attributes.position;
    return { objetos: [p], lento: true, mover(t) {
      for (let i = 0; i < n; i++) {
        const luz = Math.max(0, Math.sin(t * 0.5 + s[i])) ** 3;
        col.setXYZ(i, 0.85 * luz, 0.96 * luz, 0.6 * luz);
        pos.setXYZ(i, base[i * 3] + Math.sin(t * 0.15 + s[i]) * 1.5, base[i * 3 + 1] + Math.cos(t * 0.12 + s[i]) * 1, base[i * 3 + 2]);
      }
      col.needsUpdate = true; pos.needsUpdate = true;
    } };
  },
  noche() {   // estrellas cálidas que titilan
    const n = 420, p = particulas(n, () => [azar(150), Math.random() * 45 - 5, -40], { tam: 0.45, colores: [new THREE.Color("#ffd9a0")], opacidad: 0.85 });
    const col = p.geometry.attributes.color, s = p.geometry.userData.semilla;
    return { objetos: [p], lento: true, mover(t) {
      for (let i = 0; i < n; i++) { const b = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * 0.8 + s[i])); col.setXYZ(i, b, b * 0.85, b * 0.63); }
      col.needsUpdate = true;
    } };
  },
};

let actual = null, temaVisto = "";
function limpiar() {
  if (!actual) return;
  actual.objetos.forEach((o) => { escena.remove(o); o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose?.(); }); });
  actual = null;
}
function montar() {
  const tema = document.documentElement.dataset.tema || "cristal";
  if (tema === temaVisto) return;
  temaVisto = tema; limpiar();
  actual = (ESCENAS[tema] || ESCENAS.cristal)();
  actual.objetos.forEach((o) => escena.add(o));
  lienzo.classList.toggle("lento", !!actual.lento);
}
function medir() {
  render.setSize(innerWidth, innerHeight, false);
  camara.aspect = innerWidth / innerHeight; camara.updateProjectionMatrix();
}
window.addEventListener("resize", medir);
// el tema cambia en <html data-tema>: se rehace la escena al momento
new MutationObserver(() => { montar(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-tema", "class"] });
medir(); montar();

let t = 0, antes = performance.now(), ultimo = 0;
function bucle(ahora) {
  requestAnimationFrame(bucle);
  if (document.hidden) { antes = ahora; return; }
  const paso = actual?.lento ? 1000 / 24 : 1000 / 45;   // los de descanso, a menos fotogramas: gastan menos y se sienten calmados
  if (ahora - ultimo < paso) return;
  ultimo = ahora;
  const dt = Math.min(0.1, (ahora - antes) / 1000); antes = ahora;
  if (!quieto()) { t += dt * (actual?.lento ? 0.6 : 1); actual?.mover(t, dt); }
  raton.vx += (raton.x - raton.vx) * 0.03; raton.vy += (raton.y - raton.vy) * 0.03;   // parallax suave con el ratón
  camara.position.x = raton.vx * 3; camara.position.y = -raton.vy * 2; camara.lookAt(0, 0, -10);
  render.render(escena, camara);
}
requestAnimationFrame(bucle);
