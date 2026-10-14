// STUDIO 4 · panel. Arriba, el asistente de guion (pregunta y ejecuta); abajo, la ejecución (Flow, Render,
// Entregas) cuando el guion está aprobado. Sondea /api/estado cada 2 s y solo repinta lo que ha cambiado.
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let estado = null;
const firmas = {};

async function api(ruta, datos, opciones = {}) {
  const r = await fetch(ruta, datos === undefined ? opciones : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos), ...opciones,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
}
function aviso(e) { alertaError(e.message || String(e)); }
function alertaError(texto) {
  const caja = estado?.produccion?.guion_aprobado ? $("t-error") : $("aviso-panel");
  caja.textContent = texto; caja.hidden = false;
  setTimeout(() => { caja.hidden = true; }, 9000);
}
function siCambia(clave, datos, pintar) {
  const f = JSON.stringify(datos);
  if (firmas[clave] === f) return;
  firmas[clave] = f;
  pintar(datos);
}
function llenarSelect(sel, opciones, valor) {
  const html = Object.entries(opciones).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("");
  if (sel.dataset.f !== html) { sel.innerHTML = html; sel.dataset.f = html; }
  if (valor !== undefined) sel.value = valor;
}
const urlMedio = (archivo, pid = estado.produccion.id) => `/media/${pid}/${archivo}`;
const miles = (n) => Number(n || 0).toLocaleString("es-ES");
const FECHA = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const fecha = (iso) => { const d = new Date(String(iso).replace(" ", "T")); return isNaN(d) ? String(iso || "").slice(0, 16) : FECHA.format(d).replace(".", ""); };   // «13 oct, 00:19»
// Un botón desactivado dice por qué, justo debajo (y al lector de pantalla).
function porQue(id, motivo) {
  const b = $(id);
  let nota = $(`${id}-porque`);
  if (!nota) {
    nota = document.createElement("small");
    nota.id = `${id}-porque`; nota.className = "por-que";
    b.insertAdjacentElement("afterend", nota);
    b.setAttribute("aria-describedby", nota.id);
  }
  nota.textContent = b.disabled ? motivo || "" : "";
}

const ESTADOS = { investigando: "investigando", escribiendo: "escribiendo guion", guion_listo: "guion por revisar",
  escenas: "creando escenas", rodando: "en Flow", renderizando: "renderizando", terminado: "terminado", error: "error" };
const VERSION = { corto: "Corto", largo: "Largo", propio: "Tu guion" };
const ESTILOS = {
  cinematografico: ["Cinematográfico", "Película realista, óptica anamórfica"],
  documental: ["Documental", "Real, cámara en mano, luz natural"],
  anime: ["Anime", "Anime de calidad, colores vivos"],
  animacion3d: ["Animación 3D", "Como una película de animación"],
  noir: ["Noir", "Contraste alto, sombras y neón"],
  scifi: ["Ciencia ficción", "Épico, luz volumétrica, futuro"],
};

// ============================================================== Ajustes: tema de color (se guarda en este navegador)
// [id, nombre, plantilla, colores de la muestra, radio de la muestra]
const TEMAS = [
  ["cristal", "Cristal", "Cristal flotante", ["#ece6fb", "#a78bfa", "#5eead4", "#f9a8d4"], 16],
  ["oceano", "Océano", "Nube sólida", ["#e3f2fb", "#7dd3fc", "#5eead4", "#a5b4fc"], 10],
  ["atardecer", "Atardecer", "Burbuja", ["#fbe9ee", "#fdba74", "#f9a8d4", "#c4b5fd"], 22],
  ["arena", "Arena", "Editorial", ["#efe8dc", "#d6c4a5", "#c9d6c2", "#e7d3b0"], 2],
  ["rosa", "Orquídea", "Pastel", ["#f5e9fb", "#f9a8d4", "#d8b4fe", "#c7d2fe"], 12],
  ["menta", "Menta", "Minimal", ["#eef6f2", "#99d8c0", "#cfe8df", "#b9e3d3"], 8],
  ["hielo", "Hielo", "Ventanas", ["#eaf0f7", "#93c5fd", "#c7d7ea", "#dbe7f5"], 6],
  ["comic", "Cómic", "Viñeta", ["#fff1b8", "#ff5a36", "#2f6bff", "#111111"], 4],
  ["grafito", "Grafito", "Estudio", ["#0a0b10", "#4f46e5", "#0d9488", "#8b5cf6"], 8],
  ["medianoche", "Medianoche", "Neón", ["#0a1026", "#3b82f6", "#6366f1", "#06b6d4"], 6],
  ["aurora", "Aurora", "Cristal oscuro", ["#2c1470", "#a855f7", "#2dd4bf", "#f472b6"], 16],
  ["bosque", "Bosque", "Terminal", ["#07120d", "#10b981", "#65a30d", "#0d9488"], 0],
  ["oro", "Carbón y oro", "Lujo", ["#0f0d09", "#f59e0b", "#b45309", "#fde68a"], 0],
  ["vino", "Vino", "Revista", ["#1a0b12", "#f43f5e", "#fbbf24", "#7f1d1d"], 4],
];
function aplicarTema(t) {
  document.documentElement.dataset.tema = t;
  try { localStorage.setItem("studio4-tema", t); } catch (_) { /* sin almacenamiento: vale solo para esta visita */ }
  document.querySelectorAll("#temas button").forEach((b) => { b.classList.toggle("si", b.dataset.tema === t); b.setAttribute("aria-pressed", b.dataset.tema === t); });
}
(() => {
  let t = "cristal";
  try { t = localStorage.getItem("studio4-tema") || t; } catch (_) { /* sin almacenamiento */ }
  $("temas").innerHTML = TEMAS.map(([id, nombre, desc, c, r]) => `
    <button type="button" data-tema="${id}">
      <span class="muestra-tema" style="background:${c[0]};border-radius:${r}px">
        <i style="inset:-20% auto auto -10%;width:70%;height:90%;background:radial-gradient(closest-side,${c[1]},transparent);filter:blur(8px)"></i>
        <i style="inset:auto -10% -25% auto;width:65%;height:90%;background:radial-gradient(closest-side,${c[2]},transparent);filter:blur(8px)"></i>
        <i style="inset:22% 14% 22% 14%;background:${["grafito", "medianoche", "aurora", "bosque", "oro", "vino"].includes(id) ? "rgb(20 22 32 / .55)" : "rgb(255 255 255 / .5)"};border:${id === "comic" ? "2px solid #111" : "1px solid rgb(255 255 255 / .5)"};border-radius:${r}px;backdrop-filter:blur(6px)"></i>
        <i style="left:22%;top:34%;width:30%;height:9px;border-radius:${Math.min(r, 5)}px;background:${c[3]}"></i>
      </span><b>${nombre}</b><small>${desc}</small></button>`).join("");
  aplicarTema(t);
})();
$("temas").addEventListener("click", (ev) => { const b = ev.target.closest("[data-tema]"); if (b) aplicarTema(b.dataset.tema); });
function cerrarAjustes() { $("ajustes").hidden = true; $("abrir-ajustes").focus(); }
$("abrir-ajustes").addEventListener("click", () => {
  $("ajustes").hidden = false;
  ($("temas").querySelector(".si") || $("cerrar-ajustes")).focus();   // el teclado entra en el panel
});
$("cerrar-ajustes").addEventListener("click", cerrarAjustes);
$("ajustes").addEventListener("click", (ev) => { if (ev.target === $("ajustes")) cerrarAjustes(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("ajustes").hidden) cerrarAjustes(); });

// Escuchar una voz antes de elegirla: frase de presentación (la primera vez se graba; después, al instante).
let botonSonando = null;
function oirVoz(boton, voz) {
  const audio = $("oir-voz");
  if (botonSonando === boton && !audio.paused) { audio.pause(); return; }
  if (botonSonando) botonSonando.classList.remove("sonando", "cargando");
  botonSonando = boton;
  boton.classList.add("cargando");
  audio.src = `/api/voz/oir?voz=${encodeURIComponent(voz)}`;
  audio.play().then(() => { boton.classList.remove("cargando"); boton.classList.add("sonando"); })
    .catch(() => { boton.classList.remove("cargando"); alertaError("No se pudo reproducir la voz."); });
}
$("oir-voz").addEventListener("ended", () => botonSonando?.classList.remove("sonando"));
$("oir-voz").addEventListener("pause", () => botonSonando?.classList.remove("sonando"));
const botonOir = (voz) => `<button type="button" class="oir" data-oir="${esc(voz)}" title="Escuchar ${esc(voz)}"><svg><use href="#i-play"/></svg></button>`;
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-oir]");
  if (!b) return;
  ev.preventDefault(); ev.stopPropagation();
  oirVoz(b, b.dataset.oir);
}, true);

// Asistente, paso 3: elegir la voz escuchándola
let vozElegida = "";
function pintarVocesAsistente(voces, porDefecto) {
  vozElegida = vozElegida || porDefecto;
  $("a-voces").innerHTML = Object.entries(voces).map(([v, d]) => `
    <label class="voz-op ${v === vozElegida ? "si" : ""}" data-voz="${esc(v)}">
      <b>${esc(v)}</b><span>${esc(d)}</span>${botonOir(v)}</label>`).join("");
}
$("a-voces").addEventListener("click", (ev) => {
  const l = ev.target.closest("[data-voz]");
  if (!l || ev.target.closest("[data-oir]")) return;
  vozElegida = l.dataset.voz;
  pintarVocesAsistente(estado.opciones.voces_gemini, estado.opciones.voz_por_defecto);
  pintarResumen();
});

// ============================================================== Barra superior: Flow, YouTube, consumo
function pintarFlow(d) {
  const b = $("flow-boton");
  b.href = "/flow/emparejar#c=" + encodeURIComponent(d.codigo);
  const conectada = d.extension.conectada;
  b.className = `pildora ${conectada ? "ok" : "aviso"}`;
  b.innerHTML = `<span class="piloto"></span><span>${conectada ? "Flow conectado" : "Flow: conectar"}</span>`;
}
$("flow-renovar").addEventListener("click", async () => {
  try {
    const d = await api("/api/flow/renovar", {});
    window.open("/flow/emparejar#c=" + encodeURIComponent(d.codigo), "_blank");
  } catch (e) { aviso(e); }
});

let canal = null;
async function cargarYoutube() {
  try { canal = await api("/api/youtube"); } catch (_) { canal = { conectado: false }; }
  const p = $("yt-pildora");
  if (canal.conectado && canal.nombre) {
    p.className = "pildora ok"; p.removeAttribute("href");
    $("yt-txt").textContent = `${canal.nombre} · ${miles(canal.suscriptores)} subs`;
    p.title = `Solo lectura. Tus más vistos: ${canal.mas_vistos.slice(0, 3).map((v) => v.titulo).join(" · ")}`;
  } else if (canal.conectado && canal.sin_canal) {
    p.className = "pildora aviso"; p.href = "#";
    $("yt-txt").textContent = "YouTube: ¿cuál es tu canal?";
    p.title = `${canal.error} La búsqueda de temas ya funciona.`;
  } else {
    p.className = "pildora"; p.href = "/youtube/conectar";
    $("yt-txt").textContent = canal.error ? "Reconectar YouTube" : "Conectar YouTube";
    p.title = canal.error || "Solo lectura: tu canal y lo que ya hay en YouTube sobre cada tema";
  }
}
$("yt-pildora").addEventListener("click", async (ev) => {
  if (!canal?.sin_canal) return;   // sin clave ni autorización, el enlace lleva a «Conectar YouTube»
  ev.preventDefault();
  const valor = prompt("Tu canal de YouTube (@usuario o enlace):");
  if (!valor) return;
  try { await api("/api/youtube/canal", { canal: valor }); await cargarYoutube(); } catch (e) { aviso(e); }
});
const params = new URLSearchParams(location.search);
if (params.get("youtube")) {
  history.replaceState(null, "", location.pathname);
  setTimeout(() => alertaError(params.get("youtube") === "ok" ? "YouTube conectado (solo lectura)." : "Conexión con YouTube cancelada."), 500);
}

// ============================================================== Asistente de guion
let paso = 1;
let empezarOtro = false;   // «Empezar otro vídeo» con una producción a medias: el asistente vuelve al paso 1
let estiloElegido = "cinematografico";
const modo = () => document.querySelector('input[name="modo"]:checked').value;
const elegido = (grupo) => document.querySelector(`.chips[data-grupo="${grupo}"] .si`)?.dataset.v || "";

function irA(n) {
  if (n === 2 && modo() === "idea" && $("a-idea").value.trim().length < 3) return alertaError("Escribe la idea del vídeo.");
  if (n === 2 && modo() === "propio" && $("a-guion").value.trim().split(/\s+/).length < 10) return alertaError("Pega tu guion (al menos unas frases).");
  if (n === 3 && modo() === "idea" && !$("a-corto").checked && !$("a-largo").checked) return alertaError("Marca corto, largo o los dos.");
  paso = n;
  pintarAsistente();
}
document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => irA(Number(b.dataset.ir))));

function pintarAsistente() {
  const p = estado?.produccion;
  // Con un guion aprobado, la caja se pliega a una línea: lo importante pasa a ser la ejecución.
  // El asistente se ve siempre completo; una línea discreta permite volver a la producción en curso.
  const enGuion = p && !p.guion_aprobado && !empezarOtro;
  const visible = enGuion ? 4 : paso;
  document.querySelectorAll(".paso").forEach((el) => { el.hidden = Number(el.dataset.paso) !== visible; });
  document.querySelectorAll("#a-pasos li").forEach((li) => {
    const n = Number(li.dataset.paso);
    li.className = n < visible ? "hecho" : n === visible ? "ahora" : "";
  });
  const propio = modo() === "propio";
  $("a-idea").hidden = propio; $("a-guion").hidden = !propio;
  document.querySelectorAll(".solo-idea").forEach((el) => { el.hidden = propio; });
  document.querySelectorAll(".solo-propio").forEach((el) => { el.hidden = !propio; });
  $("a-crear-txt").textContent = propio ? "Usar mi guion" : "Investigar y escribir";
  if (visible === 3) pintarResumen();
}
document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", pintarAsistente));
document.querySelectorAll(".chips").forEach((g) => g.addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  g.querySelectorAll("button").forEach((x) => x.classList.toggle("si", x === b));
}));
$("a-corto-s").addEventListener("input", () => { $("a-corto-v").textContent = `${$("a-corto-s").value} s`; });
$("a-largo-m").addEventListener("input", () => {
  const m = Number($("a-largo-m").value);
  $("a-largo-v").textContent = `${String(m).replace(".", ",")} min`;
  $("a-largo-nota").textContent = `≈ ${Math.round((m * 60 * 2.3) / 14)} escenas para generar en Flow`;
});
$("a-largo-m").dispatchEvent(new Event("input"));

function pintarEstilos() {
  $("a-estilos").innerHTML = Object.entries(ESTILOS).map(([k, [nombre, desc]]) =>
    `<button type="button" data-estilo="${k}" class="${k === estiloElegido ? "si" : ""}"><b>${nombre}</b><span>${desc}</span></button>`).join("");
}
$("a-estilos").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-estilo]");
  if (!b) return;
  estiloElegido = b.dataset.estilo;
  pintarEstilos();
  pintarResumen();
});
pintarEstilos();

function pintarResumen() {
  const propio = modo() === "propio";
  const formatos = propio
    ? { vertical: "vertical 9:16", horizontal: "horizontal 16:9", cuadrado: "cuadrado 1:1" }[document.querySelector('input[name="formato"]:checked').value]
    : [$("a-corto").checked && `corto de ${$("a-corto-s").value} s (Shorts y Reels)`,
       $("a-largo").checked && `largo de ${$("a-largo-m").value.replace(".", ",")} min (YouTube)`].filter(Boolean).join(" y ");
  const voz = $("a-voz").value === "gemini" && vozElegida ? `voz ${vozElegida}` : $("a-voz").selectedOptions[0]?.textContent || "";
  const partes = propio ? [formatos, ESTILOS[estiloElegido][0], voz]
    : [formatos, elegido("tono").split(",")[0], elegido("publico"), ESTILOS[estiloElegido][0], voz];
  $("a-resumen").innerHTML = partes.filter(Boolean).map((x) => `<b>${esc(x)}</b>`).join(" · ");
}
["a-voz", "a-corto", "a-largo", "a-corto-s", "a-largo-m"].forEach((id) => $(id).addEventListener("change", pintarResumen));

$("a-crear").addEventListener("click", async () => {
  const propio = modo() === "propio";
  const datos = {
    idea: $("a-idea").value, guion_propio: propio ? $("a-guion").value : "", estilo: estiloElegido, voz: $("a-voz").value,
    versiones: ["corto", "largo"].filter((v) => $(`a-${v}`).checked),
    segundos: { corto: Number($("a-corto-s").value), largo: Math.round(Number($("a-largo-m").value) * 60) },
    formato: document.querySelector('input[name="formato"]:checked').value,
    tono: elegido("tono"), publico: elegido("publico"), voz_nombre: vozElegida,
  };
  try {
    $("a-crear").disabled = true;
    await api("/api/producciones", datos);
    $("a-idea").value = ""; $("a-guion").value = "";
    empezarOtro = false; paso = 1;
    await refrescar();
  } catch (e) { aviso(e); } finally { $("a-crear").disabled = false; }
});
$("a-otro").addEventListener("click", () => { empezarOtro = true; paso = 1; pintarAsistente(); });
function nuevoVideo() {
  empezarOtro = true; paso = 1; pintarAsistente();
  $("nuevo-video").scrollIntoView({ behavior: "smooth", block: "start" });
  $("a-idea").focus({ preventScroll: true });
}
$("ir-crear").addEventListener("click", nuevoVideo);

// Pestañas: cada parte del estudio es su propia vista (#crear, #flow, #render, #entregas).
const VISTAS = ["crear", "tendencias", "flow", "render", "entregas"];
const vistaActual = () => (VISTAS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "crear");
function mostrarVista() {
  const v = vistaActual();
  const p = estado?.produccion;
  const lista = !!(p && p.guion_aprobado);
  const fuera = v === "crear" || v === "tendencias";   // vistas que no dependen de una producción
  $("crear").hidden = v !== "crear";
  $("tendencias").hidden = v !== "tendencias";
  $("prod").hidden = fuera || !lista;
  $("sin-prod").hidden = fuera || lista;
  for (const id of ["flow", "render", "entregas"]) $(`${id}-sec`).hidden = v !== id;
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("activo", a.getAttribute("href") === `#${v}`));
  document.querySelectorAll("#pasos a").forEach((a) => a.classList.toggle("abierta", a.dataset.p === v));
}
window.addEventListener("hashchange", () => { mostrarVista(); window.scrollTo({ top: 0 }); });

// Paso 4: progreso de la investigación y editor del guion
function pintarProgresoGuion(p) {
  const t = p.trabajo;
  const trabajando = t.ocupado && !p.guion_aprobado && ["investigando", "escribiendo"].includes(p.estado);
  $("a-trabajo").hidden = !trabajando;
  $("a-editor").hidden = trabajando && !p.guion;
  if (!trabajando) return;
  const fases = [["investigando", "Investigar el tema y reunir fuentes"],
    ["youtube", "Ver qué hay ya en YouTube sobre el tema"], ["escribiendo", "Escribir el guion con esos datos"]];
  const actual = p.estado === "escribiendo" ? 2 : /YouTube/.test(t.fase) ? 1 : 0;
  $("a-fases").innerHTML = fases.filter(([k]) => k !== "youtube" || canal?.conectado).map(([k, txt]) => {
    const i = fases.findIndex(([x]) => x === k);
    return `<li class="${i < actual ? "hecho" : i === actual ? "ahora" : ""}">${txt}</li>`;
  }).join("");
  $("a-barra").style.width = `${t.progreso || 5}%`;
}

function pintarGuion({ p }) {
  const ocupado = p.trabajo.ocupado;
  const palabras = p.guion ? p.guion.split(/\s+/).length : 0;
  $("g-meta").textContent = p.guion
    ? `${palabras} palabras · ~${Math.round(palabras / 2.4)} s de voz${p.version ? ` · ${VERSION[p.version] || p.version}` : ""}${p.tono ? ` · ${p.tono.split(",")[0]}` : ""}`
    : "";
  const hermanas = p.hermanas || [];
  $("g-versiones").hidden = hermanas.length < 2;
  $("g-versiones").innerHTML = hermanas.map((h) =>
    `<label><input type="radio" name="g-version" value="${esc(h.id)}" ${h.id === p.id ? "checked" : ""}>${esc(VERSION[h.version] || h.version)}</label>`).join("");
  const area = $("g-texto");
  if (document.activeElement !== area || area.dataset.pid !== p.id) area.value = p.guion || "";
  requestAnimationFrame(() => crecer(area));
  area.dataset.pid = p.id;
  area.readOnly = ocupado;
  $("g-ia").hidden = !(p.ia_detectada || []).length;
  $("g-ia").innerHTML = `<span class="ia-nota">Conviene cambiar: ${(p.ia_detectada || []).map((f) => `«${esc(f)}»`).join(", ")}</span>`;
  $("g-ganchos").hidden = !(p.ganchos || []).length;
  $("g-ganchos").innerHTML = `<span class="meta" style="width:100%">Otros comienzos</span>` +
    (p.ganchos || []).map((g) => `<button class="chip-alt" data-gancho="${esc(g)}">${esc(g)}</button>`).join("");
  $("g-aprobar").disabled = ocupado || !p.guion;
  $("g-guardar").disabled = ocupado;
  $("g-otra").hidden = !["corto", "largo"].includes(p.version);
  $("g-otra").disabled = ocupado;
}
$("g-versiones").addEventListener("change", async (ev) => {
  try { await api("/api/activar", { id: ev.target.value }); await refrescar(); } catch (e) { aviso(e); }
});
$("g-ganchos").addEventListener("click", (ev) => {
  const g = ev.target.dataset?.gancho;
  if (!g) return;
  const area = $("g-texto");
  area.value = area.value.replace(/^[\s\S]*?[.!?…](\s|$)/, `${g.replace(/\s*$/, "")} `);   // cambia la primera frase
  area.focus();
});
$("g-guardar").addEventListener("click", async () => {
  try { await api("/api/guion", { guion: $("g-texto").value }); $("g-estado").textContent = "Guardado."; await refrescar(); }
  catch (e) { aviso(e); }
});
$("g-otra").addEventListener("click", async () => {
  try { await api("/api/guion/reescribir", {}); await refrescar(); } catch (e) { aviso(e); }
});
$("g-aprobar").addEventListener("click", async () => {
  const p = estado.produccion;
  const conClips = p.escenas.some((e) => e.tomas.length);
  if (conClips && !confirm("Esta producción ya tiene clips de Flow. Aprobar el guion rehace las escenas y los descarta. ¿Seguir?")) return;
  try {
    await api("/api/guion/aprobar", { guion: $("g-texto").value, forzar: conClips });
    await refrescar();
    location.hash = "#flow";
  } catch (e) { aviso(e); }
});
$("p-reabrir").addEventListener("click", async () => {
  const conClips = estado.produccion.escenas.some((e) => e.tomas.length);
  if (conClips && !confirm("Ya hay clips de Flow. Si cambias el guion, al aprobarlo se rehacen las escenas. ¿Seguir?")) return;
  try { await api("/api/guion/reabrir", { forzar: conClips }); empezarOtro = false; await refrescar(); location.hash = "#crear"; }
  catch (e) { aviso(e); }
});

// Presentación: sello del canal, mosaico de producciones y el motor en cinco pasos.
function pintarLista(lista) {
  const activa = estado.produccion?.id;
  const canalNombre = estado.canal?.nombre || "";
  $("sello").textContent = [canalNombre, `${lista.length} ${lista.length === 1 ? "vídeo" : "vídeos"}`, "3 formatos"].filter(Boolean).join(" · ");
  $("lista").innerHTML = lista.slice(0, 7).map((p, i) => {
    const fondo = p.portada ? `style="background-image:url('${urlMedio(p.portada, p.id)}')"` : "";
    const estadoTxt = p.estado === "rodando" && p.escenas ? `${p.con_clip}/${p.escenas} clips` : ESTADOS[p.estado] || p.estado;
    return `<button type="button" data-id="${esc(p.id)}" class="pieza-mosaico m${i} ${p.portada ? "con-foto" : ""} ${p.id === activa ? "activa" : ""}" ${fondo}>
      <span class="sello">${esc(VERSION[p.version] || p.version || "Vídeo")} · ${esc(estadoTxt)}</span>
      <b class="display">${esc(p.titulo || p.tema)}</b>
      <small>${esc(fecha(p.creado))}</small></button>`;
  }).join("") + `<button type="button" class="pieza-mosaico nuevo" data-nuevo="1"><svg width="22" height="22"><use href="#i-crear"/></svg><b>Nuevo vídeo</b></button>`;
}
$("lista").addEventListener("click", async (ev) => {
  if (ev.target.closest("[data-nuevo]")) return nuevoVideo();
  const b = ev.target.closest("[data-id]");
  if (!b) return;
  try { await api("/api/activar", { id: b.dataset.id }); empezarOtro = false; await refrescar(); } catch (e) { aviso(e); }
});
const MOTOR = [
  ["idea", "i-crear", "Idea", "La escribes o eliges una tendencia"],
  ["guion", "i-guion", "Guion", "Se investiga, se escribe y lo apruebas"],
  ["flow", "i-escenas", "Flow", "Generas cada escena, vídeo o imagen"],
  ["render", "i-render", "Render", "Voz, sonido y subtítulos en tu PC"],
  ["entregas", "i-entregas", "Entregas", "Vídeo completo, Reels y Shorts"],
];
function pintarMotor(p) {
  const fase = !p ? "idea" : !p.guion_aprobado ? "guion" : pasoActual(p);
  const orden = MOTOR.map(([k]) => k);
  const listos = p ? p.escenas.filter((e) => e.elegida !== null).length : 0;
  const chip = {
    idea: p ? "Hecho" : "Empieza aquí",
    guion: !p ? "Pendiente" : p.guion_aprobado ? "Aprobado" : p.guion ? "Por revisar" : "Escribiendo",
    flow: p?.escenas.length ? `${listos}/${p.escenas.length} clips` : "Pendiente",
    render: p?.final ? "Hecho" : "Pendiente",
    entregas: p?.entregas ? `${p.entregas.piezas.length} piezas` : "3 formatos",
  };
  $("motor").innerHTML = MOTOR.map(([k, icono, titulo, txt], i) => {
    const estadoPaso = orden.indexOf(k) < orden.indexOf(fase) ? "hecho" : k === fase ? "ahora" : "";
    return `<button type="button" class="motor-paso ${estadoPaso}" data-motor="${k}">
      <span class="motor-cab"><svg width="20" height="20"><use href="#${icono}"/></svg><small>0${i + 1}</small></span>
      <b class="display">${titulo}</b><span class="motor-txt">${txt}</span><span class="sello">${esc(chip[k])}</span></button>`;
  }).join("");
}
$("motor").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-motor]");
  if (!b) return;
  const k = b.dataset.motor;
  if (k === "idea") return nuevoVideo();
  if (k === "guion") { empezarOtro = false; pintarAsistente(); return $("nuevo-video").scrollIntoView({ behavior: "smooth" }); }
  location.hash = `#${k}`;
});

// ============================================================== Ejecución (guion aprobado)
function pasoActual(p) {
  if (!p.escenas.length || !p.voz || p.escenas.some((e) => e.elegida === null)) return "flow";
  if (!p.final) return "render";
  return "entregas";
}
function pintarCabecera(p) {
  $("p-titulo").textContent = p.titulo || p.tema;
  $("p-meta").textContent = [VERSION[p.version], estado.opciones.formatos[p.formato], ESTILOS[p.estilo]?.[0] || p.estilo].filter(Boolean).join(" · ");
  $("p-guion").textContent = p.guion;
  const listas = p.escenas.filter((e) => e.elegida !== null).length;
  const hecho = { flow: p.escenas.length > 0 && listas === p.escenas.length, render: !!p.final, entregas: !!p.miniaturas };
  const ahora = pasoActual(p);
  $("est-flow").textContent = p.escenas.length ? `${listas} de ${p.escenas.length} clips` : "preparando escenas";
  $("est-render").textContent = p.final ? "vídeo listo" : hecho.flow ? "listo para montar" : "espera a los clips";
  $("est-entregas").textContent = p.miniaturas ? "miniaturas listas" : p.final ? "por hacer" : "después del render";
  document.querySelectorAll("#pasos a").forEach((a) => {
    a.classList.toggle("hecho", hecho[a.dataset.p]);
    a.classList.toggle("ahora", !hecho[a.dataset.p] && a.dataset.p === ahora);
  });
}
function pintarTrabajo(t) {
  $("en-marcha").hidden = !t.ocupado;
  $("en-marcha-txt").textContent = t.fase || "";
  $("en-marcha-pct").textContent = `${t.progreso || 0}%`;
  $("trabajo").hidden = !t.ocupado;
  $("t-fase").textContent = t.fase || "";
  $("t-pct").textContent = t.ocupado ? `${t.progreso || 0}%` : "";
  $("t-barra").style.width = `${t.progreso || 0}%`;
  for (const id of ["t-error", "aviso-panel"]) {
    if (t.error) { $(id).textContent = t.error; $(id).hidden = false; }
  }
}

function pintarExtension(ext) { $("ext-vieja").hidden = !(ext.conectada && ext.desactualizada); }
function portada(e) {
  // La toma elegida si ya hay clip; si no, negro.
  const toma = e.elegida !== null ? e.tomas[e.elegida] : null;
  if (toma) {
    return toma.tipo === "video"
      ? `<video src="${urlMedio(toma.archivo)}#t=0.5" muted preload="metadata" loop></video>`
      : `<img src="${urlMedio(toma.archivo)}" alt="">`;
  }
  return `<div class="sin-portada"></div>`;   // en negro hasta que llegue su clip
}

function pintarEscenas({ escenas, activa }) {
  const sinTipo = escenas.length && escenas.some((e) => !e.tipo_clip);
  $("pedir-tipos").hidden = !sinTipo;
  const videos = escenas.filter((e) => e.tipo_clip === "video").length;
  $("reparto").textContent = escenas.length && !sinTipo ? `${videos} en vídeo · ${escenas.length - videos} en imagen, intercaladas` : "";
  const vertical = estado.produccion.formato === "vertical";
  $("escenas").style.setProperty("--portada", vertical ? "3 / 4" : estado.produccion.formato === "cuadrado" ? "1" : "16 / 9");
  const listas = escenas.filter((e) => e.elegida !== null).length;
  $("e-cuenta").textContent = escenas.length ? `· ${listas}/${escenas.length} con clip` : "";
  $("escenas").innerHTML = escenas.map((e) => {
    const tomas = e.tomas.map((t, i) => `
      <div class="toma ${i === e.elegida ? "elegida" : ""}" data-orden="${e.orden}" data-toma="${i}">
        <button type="button" class="elegir" title="Usar esta toma" aria-label="Usar la toma ${i + 1} de la escena ${e.orden}" aria-pressed="${i === e.elegida}">
          ${t.tipo === "video" ? `<video src="${urlMedio(t.archivo)}#t=0.5" muted preload="metadata"></video>` : `<img src="${urlMedio(t.archivo)}" alt="">`}
          <span>${t.tipo === "video" ? `${String(t.duracion).replace(".", ",")} s` : "imagen"}</span></button>
        <button type="button" class="borrar" data-borrar="${i}" data-orden="${e.orden}" title="Borrar toma" aria-label="Borrar la toma ${i + 1} de la escena ${e.orden}">✕</button>
      </div>`).join("");
    const estadoTxt = e.elegida !== null ? "Clip listo" : e.orden === activa ? "Genera esta en Flow" : "Pendiente";
    const tipo = e.tipo_clip === "imagen" ? "imagen" : "video";
    return `
      <article class="escena ${e.orden === activa ? "activa" : ""} ${e.elegida !== null ? "lista-ok" : ""}">
        <div class="portada">${portada(e)}
          <span class="portada-num">Escena ${e.orden}</span><span class="portada-estado">${estadoTxt}</span></div>
        <div class="escena-cuerpo">
          ${e.tipo_clip ? `<div class="hacer-como ${tipo}"><b>Hazla en Flow como ${tipo === "imagen" ? "imagen" : "vídeo"}</b></div>` : ""}
          <p class="voz-txt">«${esc(e.texto_voz)}»</p>
          ${e.tomas.length > 1 ? `<div class="tomas">${tomas}</div>` : ""}
          <div class="acciones">
            <button class="boton" data-copiar-prompt="${e.orden}">Copiar prompt</button>
            <label class="boton">Subir clip<input type="file" accept="video/*,image/*" data-subir="${e.orden}"></label>
          </div>
        </div>
      </article>`;
  }).join("") || `<p class="meta">Gemini está convirtiendo el guion en escenas…</p>`;
}
$("escenas").addEventListener("click", async (ev) => {
  const t = ev.target;
  const p = estado.produccion;
  try {
    if (t.dataset.copiarPrompt) {
      const n = Number(t.dataset.copiarPrompt);
      await navigator.clipboard.writeText(p.escenas[n - 1].prompt_flow);
      t.textContent = "Copiado";
      setTimeout(() => { t.textContent = "Copiar prompt"; }, 1500);
      await api("/api/escena/activa", { escena: n });   // la extensión empieza a recoger para esta escena
    } else if (t.dataset.borrar !== undefined) {
      ev.stopPropagation();
      if (!confirm(`¿Borrar la toma ${Number(t.dataset.borrar) + 1} de la escena ${t.dataset.orden}? No se puede deshacer.`)) return;
      await api("/api/escena", { orden: Number(t.dataset.orden), borrar_toma: Number(t.dataset.borrar) });
    } else {
      const toma = t.closest(".toma");
      if (toma) await api("/api/escena", { orden: Number(toma.dataset.orden), elegida: Number(toma.dataset.toma) });
    }
    await refrescar();
  } catch (e) { aviso(e); }
});
$("escenas").addEventListener("change", async (ev) => {
  const input = ev.target;
  if (!input.dataset.subir || !input.files[0]) return;
  const archivo = input.files[0];
  try {
    await api(`/api/subir?escena=${input.dataset.subir}`, undefined, {
      method: "POST", headers: { "Content-Type": archivo.type || "application/octet-stream" }, body: archivo,
    });
    await refrescar();
  } catch (e) { aviso(e); }
});
$("escenas").addEventListener("mouseover", (ev) => ev.target.closest(".toma, .portada")?.querySelector("video")?.play().catch(() => {}));
$("escenas").addEventListener("mouseout", (ev) => ev.target.closest(".toma, .portada")?.querySelector("video")?.pause());
$("pedir-tipos").addEventListener("click", async () => {
  try { await api("/api/escenas/tipos", {}); await refrescar(); } catch (e) { aviso(e); }
});
$("abrir-flow").addEventListener("click", () => {
  const ancho = Math.round(screen.availWidth / 2);
  window.open("https://labs.google/fx/tools/flow", "studio4-flow",
    `popup,left=${screen.availLeft + ancho},top=${screen.availTop},width=${ancho},height=${screen.availHeight}`);
});

function pintarVoz({ voz, proveedor, opciones }) {
  llenarSelect($("v-proveedor"), opciones, proveedor);
  const audio = $("v-audio");
  if (voz) {
    const src = `${urlMedio(voz.archivo)}?v=${encodeURIComponent(voz.generada || "")}`;
    if (audio.dataset.src !== src) { audio.src = src; audio.dataset.src = src; }
  } else {
    audio.removeAttribute("src"); audio.dataset.src = "";
  }
}
// Probar voces: hasta 3 marcadas → muestras → «Usar esta voz».
const vocesMarcadas = new Set();
function pintarVoces({ voces, actual, muestras }) {
  $("v-lista").innerHTML = Object.entries(voces).map(([v, d]) => `
    <label class="voz-op ${vocesMarcadas.has(v) ? "si" : ""} ${v === actual ? "actual" : ""}">
      <input type="checkbox" value="${esc(v)}" ${vocesMarcadas.has(v) ? "checked" : ""}>
      <b>${esc(v)}${v === actual ? " · en uso" : ""}</b><span>${esc(d)}</span>${botonOir(v)}</label>`).join("");
  $("v-probar").disabled = !vocesMarcadas.size;
  $("v-cuenta").textContent = vocesMarcadas.size ? `${vocesMarcadas.size} de 3 marcadas` : "";
  $("v-muestras").innerHTML = (muestras || []).map((m) => `
    <div class="muestra ${m.voz === actual ? "actual" : ""}">
      <div><b>${esc(m.voz)}</b><span>${esc(m.descripcion)}</span></div>
      <audio controls preload="none" src="${urlMedio(m.archivo)}?v=${m.generada}"></audio>
      <button class="${m.voz === actual ? "boton" : "primario"}" data-usar-voz="${esc(m.voz)}" ${m.voz === actual ? "disabled" : ""}>
        ${m.voz === actual ? "En uso" : "Usar esta voz"}</button>
    </div>`).join("");
}
$("v-lista").addEventListener("change", (ev) => {
  const v = ev.target.value;
  if (ev.target.checked) {
    if (vocesMarcadas.size >= 3) { ev.target.checked = false; return alertaError("Como mucho 3 voces a la vez."); }
    vocesMarcadas.add(v);
  } else vocesMarcadas.delete(v);
  firmas.voces = "";
  refrescar();
});
$("v-probar").addEventListener("click", async () => {
  try { await api("/api/voz/muestras", { voces: [...vocesMarcadas] }); await refrescar(); } catch (e) { aviso(e); }
});
$("v-muestras").addEventListener("click", async (ev) => {
  const v = ev.target.dataset?.usarVoz;
  if (!v) return;
  try { await api("/api/voz/elegir", { voz: v }); await refrescar(); } catch (e) { aviso(e); }
});

$("v-rehacer").addEventListener("click", async () => {
  try { await api("/api/voz", { proveedor: $("v-proveedor").value }); await refrescar(); } catch (e) { aviso(e); }
});
// Colores de resalte de cada paleta (los mismos que usa el render, en CSS).
const COLOR_PALETA = { amarillo: "#ffe500", cian: "#00e1ff", rosa: "#ff20b0", verde: "#7fff00", blanco: "#ffffff" };
function pintarSubtitulos({ subtitulos: s, paletas }) {
  $("s-activos").checked = s.activos; $("s-gancho").checked = s.gancho;
  $("s-paletas").innerHTML = Object.entries(paletas).map(([k, nombre]) => `
    <button type="button" data-paleta="${k}" class="${k === s.paleta ? "si" : ""}" title="${esc(nombre)}">
      <span><span style="color:#fff">ASÍ SE </span><span style="color:${COLOR_PALETA[k] || "#fff"}">VEN</span></span><small>${esc(nombre)}</small></button>`).join("");
  document.querySelector(`input[name="s-pos"][value="${s.posicion}"]`).checked = true;
  document.querySelector(`input[name="s-tam"][value="${s.tamano}"]`).checked = true;
  verVista();
}
let vistaPendiente;
function verVista() {   // pide un fotograma nuevo con los ajustes guardados (agrupa cambios rápidos)
  clearTimeout(vistaPendiente);
  vistaPendiente = setTimeout(() => {
    const img = $("s-vista");
    img.classList.add("cargando");
    img.onload = img.onerror = () => img.classList.remove("cargando");
    img.src = `/api/subtitulos/vista?v=${Date.now()}`;
  }, 150);
}
async function guardarSubtitulos(cambio) {
  const s = { ...estado.produccion.subtitulos, ...cambio };
  try { await api("/api/subtitulos", s); await refrescar(); } catch (e) { aviso(e); }
}
$("s-paletas").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-paleta]");
  if (b) guardarSubtitulos({ paleta: b.dataset.paleta });
});
$("s-activos").addEventListener("change", () => guardarSubtitulos({ activos: $("s-activos").checked }));
$("s-gancho").addEventListener("change", () => guardarSubtitulos({ gancho: $("s-gancho").checked }));
$("s-posicion").addEventListener("change", (ev) => guardarSubtitulos({ posicion: ev.target.value }));
$("s-tamano").addEventListener("change", (ev) => guardarSubtitulos({ tamano: ev.target.value }));
function pintarRender({ p }) {
  const faltan = p.escenas.filter((e) => e.elegida === null).map((e) => e.orden);
  const motivos = [];
  if (!p.escenas.length) motivos.push("Esperando las escenas.");
  if (!p.voz) motivos.push("Falta la voz.");
  if (faltan.length) motivos.push(`Faltan clips de Flow en ${faltan.length === p.escenas.length ? "todas las escenas" : `las escenas ${faltan.join(", ")}`}.`);
  $("r-boton").disabled = motivos.length > 0 || p.trabajo.ocupado;
  porQue("r-boton", p.trabajo.ocupado ? "Espera a que termine lo que está en marcha." : faltan.length ? "Necesitas un clip de Flow en cada escena." : motivos[0]);
  $("r-final").hidden = !p.final;
  if (p.final) {
    const src = `${urlMedio(p.final.archivo)}?v=${encodeURIComponent(p.final.renderizado)}`;
    if ($("r-video").dataset.src !== src) { $("r-video").src = src; $("r-video").dataset.src = src; }
    $("r-descargar").href = src;
    $("r-descargar").download = nombreArchivo(p, VERSION[p.version] || "video", "mp4");
  }
}
$("r-boton").addEventListener("click", async () => {
  try { await api("/api/render", {}); await refrescar(); } catch (e) { aviso(e); }
});

// Entregas: miniaturas, descargas y textos
const PLATAFORMA_VIDEO = { youtube: "YouTube", shorts: "Shorts", reels: "Reels", feed: "Feed" };
const nombreArchivo = (p, sufijo, ext) => `${(p.titulo || "studio4").replace(/[^\p{L}\p{N}\- ]+/gu, "").trim() || "studio4"} - ${sufijo}.${ext}`;
function pintarMiniaturas({ p, plataformas }) {
  const m = p.miniaturas;
  const sinClips = !p.escenas.some((e) => e.elegida !== null);
  $("m-generar").disabled = sinClips || p.trabajo.ocupado;
  porQue("m-generar", p.trabajo.ocupado ? "Espera a que termine lo que está en marcha." : sinClips ? "Necesitas al menos un clip de Flow." : "");
  $("m-generar").firstChild.textContent = m ? "Volver a generar " : "Generar miniaturas ";
  $("m-cuerpo").hidden = !m;
  if (!m) return;
  const v = encodeURIComponent(m.version || "");
  $("m-entregas").innerHTML = Object.entries(m.salidas || {}).map(([pl, archivo]) => {
    const clase = pl === "youtube" ? "h" : pl === "feed" ? "c" : "v";
    const video = p.final ? `<a class="boton" href="${urlMedio(p.final.archivo)}" download="${esc(nombreArchivo(p, PLATAFORMA_VIDEO[pl], "mp4"))}">Vídeo MP4</a>` : "";
    return `<div class="entrega ${clase}"><b>${esc(plataformas[pl] || pl)}</b>
      <img src="${urlMedio(archivo)}?v=${v}" alt="${esc(plataformas[pl] || pl)}">
      <div class="fila"><a class="boton" href="${urlMedio(archivo)}?v=${v}" download="${esc(nombreArchivo(p, `miniatura ${PLATAFORMA_VIDEO[pl]}`, "jpg"))}">Miniatura JPG</a>${video}</div></div>`;
  }).join("") + (p.final ? "" : `<p class="meta">El vídeo aparecerá aquí para descargar cuando lo renderices.</p>`);
  if (document.activeElement !== $("m-texto")) $("m-texto").value = m.texto || "";
  if (document.activeElement !== $("m-resalte")) $("m-resalte").value = m.resalte || "";
  $("m-alternativas").innerHTML = (m.vistas_alt || []).map((a) => `
    <button type="button" class="alt-vista" data-alt="${esc(a.texto)}" data-resalte="${esc(a.resalte)}" title="Usar este texto">
      <img src="${urlMedio(a.archivo)}?v=${v}" alt="${esc(a.texto)}"><span>${esc(a.texto)}</span></button>`).join("")
    || (m.alternativas || []).map((t) => `<button class="chip-alt" data-alt="${esc(t)}">${esc(t)}</button>`).join("");
  $("m-candidatos").innerHTML = m.candidatos.map((c, i) => `
    <button type="button" class="toma ${i === m.elegido ? "elegida" : ""}" data-cand="${i}" aria-pressed="${i === m.elegido}" title="${c.escena ? `Escena ${c.escena}` : c.origen === "flow" ? "Generada en Flow" : "Subida"}">
      <img src="${urlMedio(c.archivo)}" alt="Fondo ${c.escena ? `de la escena ${c.escena}` : c.origen === "flow" ? "generado en Flow" : "subido"}" loading="lazy"><span>${c.escena ? `esc. ${c.escena}` : c.origen === "flow" ? "Flow" : "subida"}</span></button>`).join("");
}
// --- Paquete para publicar ---------------------------------------------------------------------
function pintarPaquete({ p }) {
  const pq = p.entregas;
  $("pq-preparar").disabled = !p.final || p.trabajo.ocupado;
  porQue("pq-preparar", p.trabajo.ocupado ? "Espera a que termine lo que está en marcha." : !p.final ? "Primero renderiza el vídeo en Render." : "");
  $("pq-preparar").firstChild.textContent = pq ? "Volver a preparar " : "Preparar los 3 formatos ";
  $("pq-info").textContent = p.entregas_error ? `Error: ${p.entregas_error}` : pq ? `${pq.piezas.length} piezas listas` : "";
  $("pq-carpeta").hidden = !pq;
  $("pq-piezas").innerHTML = (pq?.piezas || []).map((z) => `
    <article class="pieza ${z.clave === "completo" ? "ancha" : ""}">
      <div class="pieza-media"><video src="${urlMedio(z.video)}" poster="${urlMedio(z.portada)}" controls preload="none"></video></div>
      <div class="pieza-txt">
        <span class="paso-de">${esc(z.plataforma)} · ${String(z.duracion).replace(".", ",")} s${z.desde ? ` · escenas ${z.desde}-${z.hasta}` : ""}</span>
        <b>${esc(z.titulo)}</b>
        <p>${esc(z.descripcion)}</p>
        <p class="tags">${esc(z.hashtags.join(" "))}</p>
        <div class="fila" style="margin-top:0">
          <button class="boton" data-copiar-texto="${esc(`${z.titulo}\n\n${z.descripcion}\n\n${z.hashtags.join(" ")}`)}">Copiar texto</button>
          <a class="boton" href="${urlMedio(z.video)}" download="${esc(nombreArchivo(p, z.plataforma, "mp4"))}">Vídeo</a>
          <a class="boton" href="${urlMedio(z.portada)}" download="${esc(nombreArchivo(p, `${z.plataforma} portada`, "jpg"))}">Portada</a>
        </div>
      </div>
    </article>`).join("");
}
$("pq-preparar").addEventListener("click", async () => {
  try { await api("/api/entregas", {}); await refrescar(); } catch (e) { aviso(e); }
});
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-abrir]");
  if (b) {
    try { await api("/api/carpeta/abrir", { sub: b.dataset.abrir }); } catch (e) { aviso(e); }
    return;
  }
  const c = ev.target.closest("[data-copiar-texto]");
  if (c) {
    await navigator.clipboard.writeText(c.dataset.copiarTexto);
    c.textContent = "Copiado";
    setTimeout(() => { c.textContent = "Copiar texto"; }, 1500);
  }
});

$("m-generar").addEventListener("click", async () => {
  try { await api("/api/miniaturas/generar", {}); await refrescar(); } catch (e) { aviso(e); }
});
async function aplicarTexto() {
  try { await api("/api/miniaturas", { texto: $("m-texto").value, resalte: $("m-resalte").value }); await refrescar(); }
  catch (e) { aviso(e); }
}
$("m-aplicar").addEventListener("click", aplicarTexto);
["m-texto", "m-resalte"].forEach((id) => $(id).addEventListener("keydown", (ev) => { if (ev.key === "Enter") aplicarTexto(); }));
$("m-alternativas").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-alt]");
  if (!b) return;
  const t = b.dataset.alt;
  $("m-texto").value = t;
  $("m-resalte").value = b.dataset.resalte || t.split(/\s+/).reduce((a, x) => (x.length > a.length ? x : a), "");
  await aplicarTexto();
});
$("m-candidatos").addEventListener("click", async (ev) => {
  const c = ev.target.closest("[data-cand]");
  if (!c) return;
  try { await api("/api/miniaturas", { elegido: Number(c.dataset.cand) }); await refrescar(); } catch (e) { aviso(e); }
});
$("m-flow").addEventListener("click", async () => {
  try {
    await api("/api/miniaturas/flow", {});
    const prompt = estado.produccion.miniaturas?.prompt_flow;
    if (prompt) await navigator.clipboard.writeText(prompt);
    $("m-flow").textContent = prompt ? "Prompt copiado: genera una imagen en Flow" : "Listo: genera una imagen en Flow";
    setTimeout(() => { $("m-flow").textContent = "Generar la imagen en Flow"; }, 4000);
  } catch (e) { aviso(e); }
});
$("m-subir").addEventListener("change", async (ev) => {
  const archivo = ev.target.files[0];
  if (!archivo) return;
  try {
    await api("/api/subir?escena=0", undefined, { method: "POST", headers: { "Content-Type": archivo.type || "image/jpeg" }, body: archivo });
    await refrescar();
  } catch (e) { aviso(e); } finally { ev.target.value = ""; }
});
function pintarTextos(p) {
  $("pub-titulo").textContent = p.titulo;
  $("pub-desc").textContent = [p.descripcion, (p.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
}
document.addEventListener("click", async (ev) => {
  const id = ev.target.dataset?.copiar;
  if (!id) return;
  await navigator.clipboard.writeText($(id).textContent);
  ev.target.textContent = "Copiado";
  setTimeout(() => { ev.target.textContent = "Copiar"; }, 1500);
});

// Campos de texto que crecen con lo escrito (nunca con barra de desplazamiento).
function crecer(area) { area.style.height = "auto"; area.style.height = `${area.scrollHeight + 2}px`; }
["a-idea", "a-guion", "g-texto"].forEach((id) => $(id).addEventListener("input", () => crecer($(id))));


// ============================================================== Canales
// Cada canal ve solo sus producciones, su YouTube y su carpeta. Se cambia arriba y se edita en Ajustes.
const REDES = { youtube: ["YouTube", "@usuario"], instagram: ["Instagram", "@usuario"], tiktok: ["TikTok", "@usuario"], facebook: ["Facebook", "@página o enlace"] };
let canalActual = "";
function pintarSelectorCanal({ cs, a }) {
  $("canal").innerHTML = cs.map((c) => `<option value="${esc(c.id)}" ${c.id === a ? "selected" : ""}>${esc(c.nombre)}</option>`).join("");
  const nombre = cs.find((c) => c.id === a)?.nombre || "";
  if (canalActual && canalActual !== a) { empezarOtro = false; paso = 1; cargarYoutube(); }
  canalActual = a;
}
$("canal").addEventListener("change", async () => {
  try { await api("/api/canales/activar", { id: $("canal").value }); await refrescar(); } catch (e) { aviso(e); }
});
function fichaCanal(c, redes) {
  const id = c.id || "nuevo";
  return `<form class="canal-ficha" data-canal="${esc(c.id || "")}">
    <label><span>Nombre</span><input class="campo" name="nombre" value="${esc(c.nombre || "")}" required autocomplete="off" aria-label="Nombre del canal"></label>
    <label class="ancho"><span>Nicho (de qué trata el canal)</span><input class="campo" name="nicho" value="${esc(c.nicho || "")}" placeholder="historia y ciencia curiosa…" autocomplete="off"></label>
    ${Object.keys(redes).map((r) => `<label><span>${esc(REDES[r]?.[0] || redes[r])}</span>
      <input class="campo" name="${r}" value="${esc(c.redes?.[r] || "")}" placeholder="${esc(REDES[r]?.[1] || "@usuario")}…" autocomplete="off" spellcheck="false" id="red-${esc(id)}-${r}"></label>`).join("")}
    <div class="fila"><button class="primario" type="submit">${c.id ? "Guardar canal" : "Crear canal"}</button><span class="meta" role="status" aria-live="polite"></span></div>
  </form>`;
}
async function pintarCanalesAjustes(conNuevo = false) {
  try {
    const d = await api("/api/canales");
    $("canales-lista").innerHTML = d.canales.map((c) => fichaCanal(c, d.redes)).join("") + (conNuevo ? fichaCanal({}, d.redes) : "");
    if (conNuevo) $("canales-lista").lastElementChild.querySelector("input").focus();
  } catch (e) { aviso(e); }
}
$("canales-lista").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const datos = Object.fromEntries(new FormData(f));
  const cuerpo = { nombre: datos.nombre, nicho: datos.nicho || "", redes: Object.fromEntries(Object.keys(REDES).map((r) => [r, datos[r] || ""])) };
  if (f.dataset.canal) cuerpo.id = f.dataset.canal;
  try {
    await api("/api/canales", cuerpo);
    await pintarCanalesAjustes();
    await refrescar();
    if (f.dataset.canal === canalActual) cargarYoutube();
  } catch (e) { f.querySelector("[role=status]").textContent = e.message || String(e); }
});
$("canal-nuevo").addEventListener("click", () => pintarCanalesAjustes(true));
$("abrir-ajustes").addEventListener("click", () => pintarCanalesAjustes());

// ============================================================== Tendencias
const minSeg = (s) => (s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} min` : `${s} s`);
async function cargarTendencias() {
  let t;
  try { t = await api("/api/tendencias"); } catch (e) { return aviso(e); }
  siCambia("tendencias", { t, c: estado?.canal }, () => pintarTendencias(t));
}
function pintarTendencias(t) {
  const c = estado?.canal || {};
  $("td-canal").textContent = `Tendencias · ${c.nombre || ""}`;
  $("td-trabajo").hidden = !t.ocupado; $("td-fase").textContent = t.fase ? `${t.fase}…` : "";
  $("td-actualizar").disabled = t.ocupado;
  $("td-error").hidden = !t.error; $("td-error").textContent = t.error ? `No se pudieron actualizar: ${t.error}` : "";
  $("td-nicho").hidden = !!c.nicho;
  const d = t.datos;
  $("td-fecha").textContent = d ? fecha(d.fecha) : "";
  $("td-cuerpo").hidden = !d;
  if (!d) return;
  const m = d.metricas, i = d.informe;
  $("td-resumen").textContent = i.resumen;
  const barras = Object.entries(m.duraciones).map(([k, v]) => `<li><span>${esc(k)}</span><i style="--v:${v}%"></i><b>${v} %</b></li>`).join("");
  $("td-cifras").innerHTML = `
    <div><small>Vídeos analizados</small><b>${miles(m.total)}</b></div>
    <div><small>En HD</small><b>${m.hd} %</b></div>
    <div><small>Duración de los que más crecen</small><b>${minSeg(m.duracion_mas_rapidos)}</b></div>
    <div><small>Largo medio del título</small><b>${m.titulos.largo_medio} letras</b></div>
    <div class="td-duraciones"><small>Duración de lo más visto</small><ul>${barras}</ul></div>`;
  $("td-formato").innerHTML = [["Vídeo corto", i.duracion_corto], ["Vídeo largo", i.duracion_largo], ["Calidad", i.calidad], ["Títulos", i.titulos]]
    .map(([k, v]) => `<div><b>${k}</b><p>${esc(v)}</p></div>`).join("");
  $("td-ideas").innerHTML = i.ideas.map((x) => `
    <div class="td-idea"><small>${x.formato === "largo" ? "Largo · YouTube" : "Corto · Shorts y Reels"}</small>
      <b>${esc(x.idea)}</b>
      <button class="boton" type="button" data-idea="${esc(x.idea)}" data-formato="${x.formato === "largo" ? "largo" : "corto"}">Crear este vídeo <svg width="14" height="14"><use href="#i-flecha"/></svg></button></div>`).join("");
  $("td-nichos").innerHTML = i.nichos.map((n) => `
    <div class="td-nicho"><b>${esc(n.nombre)}</b>
      <ul>${n.ideas.map((x) => `<li><button class="enlace" type="button" data-idea="${esc(x)}" data-formato="corto">${esc(x)}</button></li>`).join("")}</ul></div>`).join("");
  $("td-consejos").innerHTML = i.consejos.map((x) => `<li>${esc(x)}</li>`).join("");
  $("td-evitar").innerHTML = i.evitar.map((x) => `<li>${esc(x)}</li>`).join("");
}
$("td-nicho").addEventListener("click", () => { $("abrir-ajustes").click(); });
$("td-actualizar").addEventListener("click", async () => {
  try { await api("/api/tendencias", {}); await cargarTendencias(); } catch (e) { aviso(e); }
});
$("tendencias").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-idea]");
  if (!b) return;
  // La idea pasa a Crear: modo idea, el formato que se recomienda y el asistente en el paso 1.
  document.querySelector('input[name="modo"][value="idea"]').checked = true;
  $("a-idea").value = b.dataset.idea; crecer($("a-idea"));
  $("a-corto").checked = b.dataset.formato === "corto"; $("a-largo").checked = b.dataset.formato === "largo";
  empezarOtro = true; paso = 1;
  location.hash = "#crear";
  pintarAsistente();
  $("a-idea").focus();
});

// ============================================================== Ciclo
async function refrescar() {
  const [d, lista] = await Promise.all([api("/api/estado"), api("/api/producciones")]);
  estado = d;
  siCambia("canales", { cs: d.canales, a: d.canal.id }, pintarSelectorCanal);
  const o = d.opciones;
  llenarSelect($("a-voz"), o.voces);
  siCambia("voces-asistente", o.voces_gemini, () => pintarVocesAsistente(o.voces_gemini, o.voz_por_defecto));
  $("aviso-salud").hidden = !o.salud.length;
  $("aviso-salud").textContent = o.salud.join(" ");
  pintarFlow(d);
  siCambia("lista", { lista, activa: d.produccion?.id, c: d.canal?.nombre }, () => pintarLista(lista));
  siCambia("motor", d.produccion && { a: d.produccion.guion_aprobado, g: !!d.produccion.guion, e: d.produccion.escenas,
    v: !!d.produccion.voz, f: !!d.produccion.final, p: d.produccion.entregas?.piezas?.length }, () => pintarMotor(d.produccion));

  const p = d.produccion;
  siCambia("asistente", { id: p?.id, aprobado: p?.guion_aprobado, empezarOtro, paso }, pintarAsistente);
  if (p) {
    siCambia("trabajo", p.trabajo, pintarTrabajo);
    siCambia("progreso-guion", { e: p.estado, t: p.trabajo, g: !!p.guion }, () => pintarProgresoGuion(p));
    siCambia("guion", { id: p.id, g: p.guion, ga: p.ganchos, ia: p.ia_detectada, o: p.trabajo.ocupado, h: p.hermanas, i: !!p.investigacion }, () => pintarGuion({ p }));
  }
  if (!firmas.vistaInicial) {   // al abrir, el navegador salta al ancla (#crear…): la vista empieza arriba
    firmas.vistaInicial = 1;
    requestAnimationFrame(() => window.scrollTo({ top: 0 }));
  }
  mostrarVista();
  if (vistaActual() === "tendencias") cargarTendencias();
  if (!p || !p.guion_aprobado) return;
  siCambia("cabecera", { p: { ...p, trabajo: null } }, () => pintarCabecera(p));
  siCambia("extension", [d.extension.conectada, d.extension.desactualizada], () => pintarExtension(d.extension));
  siCambia("escenas", { id: p.id, escenas: p.escenas, activa: p.escena_activa }, pintarEscenas);
  siCambia("voz", { id: p.id, voz: p.voz, proveedor: p.proveedor_voz, opciones: o.voces }, pintarVoz);
  siCambia("voces", { id: p.id, voces: o.voces_gemini, actual: p.voz_nombre || o.voz_por_defecto, muestras: p.muestras_voz,
    marcadas: [...vocesMarcadas] }, (x) => pintarVoces(x));
  siCambia("subtitulos", { id: p.id, subtitulos: p.subtitulos, paletas: o.paletas,
    fondo: p.escenas[0] ? [p.escenas[0].elegida, p.escenas[0].tomas.length] : null, voz: p.voz?.generada }, pintarSubtitulos);
  siCambia("render", { p }, pintarRender);
  siCambia("miniaturas", { p, plataformas: o.plataformas }, pintarMiniaturas);
  siCambia("paquete", { id: p.id, e: p.entregas, f: p.final, o: p.trabajo.ocupado, err: p.entregas_error }, () => pintarPaquete({ p }));
  siCambia("textos", { id: p.id, t: p.titulo, d: p.descripcion, h: p.hashtags }, () => pintarTextos(p));
}

refrescar().catch(aviso);
cargarYoutube();
setInterval(() => refrescar().catch(() => {}), 2000);
setInterval(cargarYoutube, 5 * 60 * 1000);
