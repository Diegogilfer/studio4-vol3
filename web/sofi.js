// Sofi · la asistente de voz de Studio 4. Un orbe de partículas en 3D (Three.js) que reacciona a la voz; escucha
// «Oye Sofi» (reconocimiento de voz del navegador, en español), hace lo que pides con el mismo chat de Inicio
// (nichos, ideas, tendencias, crear vídeos, estado de los montajes) y te contesta en voz alta.
import * as THREE from "three";
import { EffectComposer } from "/web/vendor/three/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "/web/vendor/three/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "/web/vendor/three/jsm/postprocessing/UnrealBloomPass.js";

const $ = (id) => document.getElementById(id);
const COLORES = { espera: 0x3fe0ff, escuchando: 0xff3ea5, pensando: 0x9a7bff, hablando: 0xc8a45a };
let estado = "espera", nivel = 0;

// ---------- el orbe: una esfera de partículas, dos anillos finos y un núcleo que respira ----------
const lienzo = $("lienzo");
const render = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true });
render.setPixelRatio(Math.min(2, window.devicePixelRatio));
const escena = new THREE.Scene();
const camara = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
camara.position.set(0, 0, 9);

const N = 2600, pos = new Float32Array(N * 3), base = new Float32Array(N * 3);
for (let i = 0; i < N; i++) {   // reparto uniforme en la esfera (espiral de Fibonacci)
  const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), a = i * 2.39996;
  base.set([Math.cos(a) * r * 2.2, y * 2.2, Math.sin(a) * r * 2.2], i * 3);
}
pos.set(base);
const geo = new THREE.BufferGeometry();
geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
const matPuntos = new THREE.PointsMaterial({ size: 0.035, color: COLORES.espera, transparent: true, opacity: 0.9 });
const orbe = new THREE.Points(geo, matPuntos);
escena.add(orbe);

const anillo = (radio, grosor, color) => new THREE.Mesh(new THREE.TorusGeometry(radio, grosor, 16, 220),
  new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85 }));
const anilloA = anillo(3.0, 0.012, 0xc8a45a), anilloB = anillo(3.35, 0.008, COLORES.espera);
anilloA.rotation.x = 1.2; anilloB.rotation.x = 1.9; anilloB.rotation.y = 0.4;
escena.add(anilloA, anilloB);
const nucleo = new THREE.Mesh(new THREE.SphereGeometry(0.55, 48, 32), new THREE.MeshBasicMaterial({ color: COLORES.espera }));
escena.add(nucleo);

// polvo de fondo, muy tenue
const polvo = new THREE.BufferGeometry(), pp = new Float32Array(1500 * 3);
for (let i = 0; i < pp.length; i++) pp[i] = (Math.random() - 0.5) * 40;
polvo.setAttribute("position", new THREE.BufferAttribute(pp, 3));
escena.add(new THREE.Points(polvo, new THREE.PointsMaterial({ size: 0.02, color: 0x3fe0ff, transparent: true, opacity: 0.35 })));

const composer = new EffectComposer(render);
composer.addPass(new RenderPass(escena, camara));
const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 1.1, 0.6, 0.1);
composer.addPass(bloom);

function medir() {
  const w = window.innerWidth, h = window.innerHeight;
  render.setSize(w, h, false); composer.setSize(w, h); camara.aspect = w / h; camara.updateProjectionMatrix();
}
window.addEventListener("resize", medir); medir();

const color = new THREE.Color(COLORES.espera), destinoColor = new THREE.Color();
function cuadro(ms) {
  const t = ms / 1000;
  destinoColor.set(COLORES[estado]); color.lerp(destinoColor, 0.06);
  matPuntos.color.copy(color); nucleo.material.color.copy(color); anilloB.material.color.copy(color);
  const fuerza = estado === "hablando" ? 0.18 + 0.12 * Math.sin(t * 9) : estado === "pensando" ? 0.08 : nivel * 0.9;
  for (let i = 0; i < N; i++) {   // las partículas respiran y se agitan con la voz
    const k = i * 3, ola = 1 + fuerza * Math.sin(t * 3 + i * 0.13) + 0.025 * Math.sin(t * 1.3 + i);
    pos[k] = base[k] * ola; pos[k + 1] = base[k + 1] * ola; pos[k + 2] = base[k + 2] * ola;
  }
  geo.attributes.position.needsUpdate = true;
  orbe.rotation.y = t * 0.12; orbe.rotation.x = Math.sin(t * 0.2) * 0.2;
  anilloA.rotation.z = t * 0.25; anilloB.rotation.z = -t * 0.18;
  nucleo.scale.setScalar(1 + fuerza * 1.4 + 0.04 * Math.sin(t * 2));
  bloom.strength = 1.0 + fuerza * 2;
  composer.render();
  requestAnimationFrame(cuadro);
}
requestAnimationFrame(cuadro);

// ---------- estado, lo que se dice y las tarjetas ----------
const TEXTOS = { espera: "En espera · di «Oye Sofi»", escuchando: "Te escucho…", pensando: "Pensando…", hablando: "Sofi habla" };
function poner(e) {
  estado = e;
  $("estado").style.color = "#" + COLORES[e].toString(16).padStart(6, "0");
  $("estado").querySelector("span").textContent = TEXTOS[e];
}
function decir(tu, ella) {
  $("dicho").innerHTML = (tu ? `<span class="tu">Tú: ${tu.replace(/</g, "&lt;")}</span>` : "") + (ella || "").replace(/</g, "&lt;");
}
async function tarjetas() {
  try {
    const p = await (await fetch("/api/panel")).json();
    const a = p.canales.find((c) => c.canal.id === p.activo);
    const y = a?.youtube;
    const fmt = (n) => n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? (n / 1e3).toFixed(1) + " K" : String(n);
    $("tarjetas").innerHTML = y ? `<div class="tarjeta"><small>${a.canal.nombre} · suscriptores</small><b>${fmt(y.suscriptores)}</b></div>
      <div class="tarjeta"><small>vistas totales</small><b>${fmt(y.vistas)}</b></div><div class="tarjeta"><small>vídeos</small><b>${y.videos}</b></div>`
      : `<div class="tarjeta"><small>Canal</small><b>${a?.canal.nombre || "—"}</b></div>`;
  } catch (_) { /* sin YouTube, sin tarjetas */ }
}
tarjetas();

// ---------- la voz de Sofi (la del navegador, en español; gratis e inmediata) ----------
let vozEs = null;
function elegirVoz() {
  const voces = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("es"));
  vozEs = voces.find((v) => /sabina|dalia|helena|elvira|laura|paloma|sofia|female|mujer/i.test(v.name)) || voces[0] || null;
}
speechSynthesis.onvoiceschanged = elegirVoz; elegirVoz();
function hablar(texto) {
  return new Promise((listo) => {
    if (!texto) return listo();
    parar();
    const u = new SpeechSynthesisUtterance(texto);
    if (vozEs) u.voice = vozEs;
    u.lang = vozEs?.lang || "es-ES"; u.rate = 1.03;
    u.onend = u.onerror = () => { poner("espera"); arrancar(); listo(); };
    poner("hablando"); speechSynthesis.speak(u);
  });
}

// ---------- lo que pides: va al mismo chat de Inicio (sus acciones son las del estudio) ----------
function resumen(r) {
  const x = r?.resultado || {};
  if (x.tipo === "ideas" && x.ideas?.length) return ` Te dejo ${x.ideas.length} ideas en Inicio.`;
  if (x.tipo === "nicho" && x.nichos?.length) return " " + x.nichos.map((n) => `${n.tema}: ${n.veredicto}`).join(". ") + ".";
  if (x.tipo === "video") return " El vídeo ya se está escribiendo; lo tienes en Vídeos.";
  if (x.tipo === "estado") {
    const curso = (x.en_curso || []).map((v) => `${v.titulo}: ${v.fase}, al ${v.progreso} por ciento`).join(". ");
    return " " + (curso ? "Ahora se monta: " + curso + "." : "Ahora mismo no se está montando nada.")
      + ((x.terminados || []).length ? " Los últimos terminados: " + x.terminados.join(", ") + "." : "");
  }
  if (x.tipo === "estilo") return " Elige el estilo en la pantalla de Inicio o dímelo, por ejemplo: en collage documental.";
  return "";
}
async function pedir(texto) {
  texto = texto.trim();
  if (!texto) return;
  poner("pensando"); decir(texto, "");
  try {
    const r = await (await fetch("/api/m/inicio-chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto }) })).json();
    if (r.error && !r.respuesta) throw new Error(r.error);
    const dicho = (r.respuesta || "Hecho.") + (r.error ? " Ojo: " + r.error : "") + resumen(r);
    decir(texto, dicho); await hablar(dicho);
  } catch (e) {
    const fallo = "No he podido hacerlo: " + (e.message || e);
    decir(texto, fallo); await hablar(fallo);
  }
}
$("form").onsubmit = (ev) => { ev.preventDefault(); const t = $("texto").value; $("texto").value = ""; pedir(t); };

// ---------- escuchar: micrófono, nivel de voz para el orbe y «Oye Sofi» ----------
const Reconocer = window.SpeechRecognition || window.webkitSpeechRecognition;
let oido = null, micro = false, esperandoPedido = false, plazo = null;
const PALABRA = /\b(?:oye\s+)?(?:sof[ií]a?|so\s?fi)\b[\s,.:]*/i;

async function nivelDeVoz() {
  try {
    const flujo = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new AudioContext(), an = ctx.createAnalyser(); an.fftSize = 512;
    ctx.createMediaStreamSource(flujo).connect(an);
    const datos = new Uint8Array(an.fftSize);
    const leer = () => { an.getByteTimeDomainData(datos); let s = 0; for (const v of datos) s += ((v - 128) / 128) ** 2;
      nivel = micro ? Math.min(0.5, Math.sqrt(s / datos.length) * 3) : 0; requestAnimationFrame(leer); };
    leer();
  } catch (_) { /* sin permiso de micro: el orbe no reacciona, pero se puede escribir */ }
}
function arrancar() { if (micro && oido && estado !== "hablando") { try { oido.start(); } catch (_) { /* ya escuchaba */ } } }
function parar() { if (oido) { try { oido.abort(); } catch (_) { /* nada */ } } }

if (Reconocer) {
  oido = new Reconocer();
  oido.lang = "es-ES"; oido.continuous = true; oido.interimResults = false;
  oido.onresult = (ev) => {
    const frase = ev.results[ev.results.length - 1][0].transcript.trim();
    if (esperandoPedido) { esperandoPedido = false; clearTimeout(plazo); pedir(frase); return; }
    const m = frase.match(PALABRA);
    if (!m) return;
    const resto = frase.slice(m.index + m[0].length).trim();
    if (resto.length > 2) { pedir(resto); return; }
    esperandoPedido = true; poner("escuchando"); decir("", "Dime.");
    clearTimeout(plazo); plazo = setTimeout(() => { esperandoPedido = false; poner("espera"); }, 9000);
  };
  oido.onend = () => arrancar();
} else {
  $("estado").querySelector("span").textContent = "Este navegador no reconoce voz: usa Edge o Chrome, o escribe abajo";
}
$("mic").onclick = async () => {
  micro = !micro;
  $("mic").textContent = micro ? "Micro: encendido" : "Micro: apagado";
  $("mic").classList.toggle("activo", micro);
  if (micro) { await nivelDeVoz(); arrancar(); } else { parar(); poner("espera"); }
};
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT") return;
  if (ev.key === "Escape") { speechSynthesis.cancel(); poner("espera"); arrancar(); }
  if (ev.code === "Space" && micro) { ev.preventDefault(); esperandoPedido = true; poner("escuchando"); decir("", "Dime."); }
});
