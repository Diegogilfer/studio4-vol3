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
const urlMedio = (archivo) => `/media/${estado.produccion.id}/${archivo}`;
const miles = (n) => Number(n || 0).toLocaleString("es-ES");

const ESTADOS = { investigando: "investigando", escribiendo: "escribiendo guion", guion_listo: "guion por revisar",
  escenas: "creando escenas", rodando: "en Flow", renderizando: "renderizando", terminado: "terminado", error: "error" };
const VERSION = { corto: "Corto", largo: "Largo", propio: "Tu guion" };
const TONO = { narrativo: "narrativo", intrigante: "intrigante", tenso: "tenso", emocionante: "emocionante",
  cinematografico: "cinematográfico", intimo: "íntimo", solemne: "solemne", asombro: "asombro", triunfal: "triunfal" };
const ESTILOS = {
  cinematografico: ["Cinematográfico", "Película realista, óptica anamórfica"],
  documental: ["Documental", "Real, cámara en mano, luz natural"],
  anime: ["Anime", "Anime de calidad, colores vivos"],
  animacion3d: ["Animación 3D", "Como una película de animación"],
  noir: ["Noir", "Contraste alto, sombras y neón"],
  scifi: ["Ciencia ficción", "Épico, luz volumétrica, futuro"],
};

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
  $("a-yt-nota").textContent = canal.conectado
    ? "Con tu canal conectado, el guion tendrá en cuenta el tono de tus vídeos más vistos y buscará un ángulo que no esté ya en YouTube."
    : "";
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
  const plegada = !!(p && p.guion_aprobado && !empezarOtro);
  $("crear").classList.toggle("plegada", plegada);
  if (plegada) $("a-compacta-txt").textContent = `Trabajando en «${p.titulo || p.tema}». Su guion ya está aprobado.`;
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
  const voz = $("a-voz").selectedOptions[0]?.textContent || "";
  $("a-resumen").innerHTML = propio
    ? `Tu guion se usa <b>tal cual</b> para un vídeo <b>${esc(formatos)}</b>, estilo <b>${esc(ESTILOS[estiloElegido][0])}</b>, <b>${esc(voz)}</b>. Lo revisas y lo apruebas en el paso 4.`
    : `Se <b>investiga</b> el tema${canal?.conectado ? " y lo que ya hay en <b>YouTube</b>" : ""} y se escribe un guion <b>${esc(formatos)}</b> en tono <b>${esc(elegido("tono").split(",")[0])}</b> para <b>${esc(elegido("publico"))}</b>. Estilo <b>${esc(ESTILOS[estiloElegido][0])}</b>, <b>${esc(voz)}</b>. Lo revisas antes de crear escenas.`;
}
["a-voz", "a-corto", "a-largo", "a-corto-s", "a-largo-m"].forEach((id) => $(id).addEventListener("change", pintarResumen));

$("a-crear").addEventListener("click", async () => {
  const propio = modo() === "propio";
  const datos = {
    idea: $("a-idea").value, guion_propio: propio ? $("a-guion").value : "", estilo: estiloElegido, voz: $("a-voz").value,
    versiones: ["corto", "largo"].filter((v) => $(`a-${v}`).checked),
    segundos: { corto: Number($("a-corto-s").value), largo: Math.round(Number($("a-largo-m").value) * 60) },
    formato: document.querySelector('input[name="formato"]:checked').value,
    tono: elegido("tono"), publico: elegido("publico"),
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
$("a-nuevo").addEventListener("click", () => { empezarOtro = true; paso = 1; pintarAsistente(); $("a-idea").focus(); });

// Pestañas: cada parte del estudio es su propia vista (#crear, #flow, #render, #entregas).
const VISTAS = ["crear", "flow", "render", "entregas"];
const vistaActual = () => (VISTAS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "crear");
function mostrarVista() {
  const v = vistaActual();
  const p = estado?.produccion;
  const lista = !!(p && p.guion_aprobado);
  $("crear").hidden = v !== "crear";
  $("prod").hidden = v === "crear" || !lista;
  $("sin-prod").hidden = v === "crear" || lista;
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
  $("g-ganchos").innerHTML = `<span class="meta" style="width:100%">Otras primeras frases (clic para usarla):</span>` +
    (p.ganchos || []).map((g) => `<button class="chip-alt" data-gancho="${esc(g)}">${esc(g)}</button>`).join("");
  $("g-aprobar").disabled = ocupado || !p.guion;
  $("g-guardar").disabled = ocupado;
  $("g-otra").hidden = !["corto", "largo"].includes(p.version);
  $("g-otra").disabled = ocupado;
  const inv = p.investigacion;
  $("g-investigacion").hidden = !inv;
  if (inv) {
    $("g-dossier").textContent = inv.dossier;
    $("g-fuentes-n").textContent = `· ${inv.metodo || "Google"} · ${inv.fuentes.length} fuentes`;
    $("g-fuentes").innerHTML = inv.fuentes.map((f) => `<li><a href="${esc(f.url)}" target="_blank" rel="noreferrer">${esc(f.titulo)}</a></li>`).join("");
  }
  const yt = inv?.youtube?.competencia || [];
  $("g-youtube").hidden = !yt.length;
  $("g-yt-n").textContent = `· ${yt.length} vídeos`;
  $("g-yt").innerHTML = yt.map((v) => `<li><a href="${esc(v.url)}" target="_blank" rel="noreferrer">${esc(v.titulo)}</a> · ${esc(v.canal)} · ${miles(v.vistas)} vistas</li>`).join("");
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

function pintarLista(lista) {
  const activa = estado.produccion?.id;
  $("lista").innerHTML = lista.length ? lista.map((p) => `
    <button type="button" data-id="${esc(p.id)}" class="${p.id === activa ? "activa" : ""}">
      <b>${esc(p.titulo || p.tema)}</b><small>${p.version ? `${esc(VERSION[p.version] || p.version)} · ` : ""}${esc(p.creado.slice(0, 16))} · ${esc(ESTADOS[p.estado] || p.estado)}</small>
    </button>`).join("") : `<span class="meta faint">Todavía no hay ninguna.</span>`;
}
$("lista").addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-id]");
  if (!b) return;
  try { await api("/api/activar", { id: b.dataset.id }); empezarOtro = false; await refrescar(); } catch (e) { aviso(e); }
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

function pintarRegistroFlow(ext) {
  $("ext-vieja").hidden = !ext.desactualizada;
  const ev = ext.eventos || [];
  $("ext-resumen").textContent = ext.conectada
    ? `· conectada${ext.version ? ` (v${ext.version})` : ""}${ev.length ? ` · último: ${ev[0].tipo} ${ev[0].t}` : ""}`
    : "· sin conexión: abre Google Flow con la extensión cargada";
  $("ext-eventos").innerHTML = ev.length
    ? ev.map((e) => `<li class="${esc(e.tipo)}"><span>${esc(e.t)}</span><b>${esc(e.tipo)}</b><span>${esc(e.detalle)}</span></li>`).join("")
    : `<li><span></span><b></b><span>Aún nada. En Flow pulsa «Copiar prompt», pega y genera.</span></li>`;
  if (ev.some((e) => e.tipo === "error" || e.tipo === "rechazada")) $("ext-registro").open = true;
}
function pintarAvisos(avisos) {
  $("avisos").hidden = !avisos.length;
  $("avisos").innerHTML = avisos.map((a) =>
    `<div><b>Difícil de filmar:</b> «${esc(a.frase)}» — ${esc(a.problema)}<br><span class="meta">Sugerencia: ${esc(a.sugerencia)}</span></div>`).join("");
}
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
  const vertical = estado.produccion.formato === "vertical";
  $("escenas").style.setProperty("--portada", vertical ? "3 / 4" : estado.produccion.formato === "cuadrado" ? "1" : "16 / 9");
  const listas = escenas.filter((e) => e.elegida !== null).length;
  $("e-cuenta").textContent = escenas.length ? `· ${listas}/${escenas.length} con clip` : "";
  $("escenas").innerHTML = escenas.map((e) => {
    const tomas = e.tomas.map((t, i) => `
      <div class="toma ${i === e.elegida ? "elegida" : ""}" data-orden="${e.orden}" data-toma="${i}" title="Usar esta toma">
        ${t.tipo === "video" ? `<video src="${urlMedio(t.archivo)}#t=0.5" muted preload="metadata"></video>` : `<img src="${urlMedio(t.archivo)}" alt="">`}
        <span>${t.tipo === "video" ? `${String(t.duracion).replace(".", ",")} s` : "imagen"}</span>
        <button class="borrar" data-borrar="${i}" data-orden="${e.orden}" title="Borrar toma">✕</button>
      </div>`).join("");
    const estadoTxt = e.elegida !== null ? "Clip listo" : e.orden === activa ? "Genera esta en Flow" : "Pendiente";
    const tono = e.tono_voz ? `Voz ${TONO[e.tono_voz] || e.tono_voz}${e.ritmo_voz && e.ritmo_voz !== "normal" ? `, ${e.ritmo_voz === "rapido" ? "rápida" : "lenta"}` : ""}` : "";
    return `
      <article class="escena ${e.orden === activa ? "activa" : ""} ${e.elegida !== null ? "lista-ok" : ""}">
        <div class="portada">${portada(e)}
          <span class="portada-num">Escena ${e.orden}</span><span class="portada-estado">${estadoTxt}</span></div>
        <div class="escena-cuerpo">
          <p class="voz-txt">«${esc(e.texto_voz)}»</p>
          ${tono ? `<span class="tono-voz">${esc(tono)}</span>` : ""}
          <details class="prompt-plegado"><summary>Prompt para Flow</summary><pre class="prompt">${esc(e.prompt_flow)}</pre></details>
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
    $("v-info").textContent = `· ${voz.duracion.toFixed(1)} s · ${opciones[voz.proveedor] || voz.proveedor}${voz.dirigida ? " · interpretada escena a escena" : ""}`;
  } else {
    audio.removeAttribute("src"); audio.dataset.src = "";
    $("v-info").textContent = "· se graba sola al crear las escenas";
  }
}
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
  $("r-falta").textContent = motivos.join(" ") || (p.final ? `Renderizado ${p.final.renderizado}. Vuelve a renderizar si cambias tomas o subtítulos.` : "Todo listo para montar.");
  $("r-boton").disabled = motivos.length > 0 || p.trabajo.ocupado;
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
  $("m-generar").firstChild.textContent = m ? "Volver a generar " : "Generar miniaturas ";
  $("m-info").textContent = sinClips
    ? "Las miniaturas salen de tus clips: cuando tengas tomas de Flow, Gemini elige el mejor fotograma y escribe el texto."
    : "Miniaturas, vídeo y textos listos para cada plataforma.";
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
    <div class="toma ${i === m.elegido ? "elegida" : ""}" data-cand="${i}" title="${c.escena ? `Escena ${c.escena}` : c.origen === "flow" ? "Generada en Flow" : "Subida"}">
      <img src="${urlMedio(c.archivo)}" alt="" loading="lazy"><span>${c.escena ? `esc. ${c.escena}` : c.origen === "flow" ? "Flow" : "subida"}</span></div>`).join("");
}
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
  const b = p.biblia || {};
  $("pub-biblia").innerHTML = b.escenario_en ? `
    <p><b>Escenario:</b> ${esc(b.escenario_en)}</p><p><b>Luz:</b> ${esc(b.luz_en)}</p><p><b>Paleta:</b> ${esc(b.paleta_en)}</p>
    ${(b.personajes || []).map((x) => `<p><b>${esc(x.nombre)}:</b> ${esc(x.aspecto_en)}</p>`).join("")}` : "";
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

// ============================================================== Ciclo
async function refrescar() {
  const [d, lista] = await Promise.all([api("/api/estado"), api("/api/producciones")]);
  estado = d;
  const o = d.opciones;
  llenarSelect($("a-voz"), o.voces);
  $("aviso-salud").hidden = !o.salud.length;
  $("aviso-salud").textContent = o.salud.join(" ");
  pintarFlow(d);
  siCambia("lista", { lista, activa: d.produccion?.id }, () => pintarLista(lista));

  const p = d.produccion;
  siCambia("asistente", { id: p?.id, aprobado: p?.guion_aprobado, empezarOtro, paso }, pintarAsistente);
  if (p) {
    siCambia("trabajo", p.trabajo, pintarTrabajo);
    siCambia("progreso-guion", { e: p.estado, t: p.trabajo, g: !!p.guion }, () => pintarProgresoGuion(p));
    siCambia("guion", { id: p.id, g: p.guion, ga: p.ganchos, ia: p.ia_detectada, o: p.trabajo.ocupado, h: p.hermanas, i: !!p.investigacion }, () => pintarGuion({ p }));
  }
  if (!firmas.vistaInicial) {   // al abrir el panel con una producción en marcha, se va directo a su paso
    firmas.vistaInicial = 1;
    if (!location.hash && p?.guion_aprobado) history.replaceState(null, "", `#${pasoActual(p)}`);
  }
  mostrarVista();
  if (!p || !p.guion_aprobado) return;
  siCambia("cabecera", { p: { ...p, trabajo: null } }, () => pintarCabecera(p));
  siCambia("registro-flow", d.extension, pintarRegistroFlow);
  siCambia("avisos", p.avisos || [], pintarAvisos);
  siCambia("escenas", { id: p.id, escenas: p.escenas, activa: p.escena_activa }, pintarEscenas);
  siCambia("voz", { id: p.id, voz: p.voz, proveedor: p.proveedor_voz, opciones: o.voces }, pintarVoz);
  siCambia("subtitulos", { id: p.id, subtitulos: p.subtitulos, paletas: o.paletas,
    fondo: p.escenas[0] ? [p.escenas[0].elegida, p.escenas[0].tomas.length] : null, voz: p.voz?.generada }, pintarSubtitulos);
  siCambia("render", { p }, pintarRender);
  siCambia("miniaturas", { p, plataformas: o.plataformas }, pintarMiniaturas);
  siCambia("textos", { id: p.id, t: p.titulo, d: p.descripcion, b: p.biblia }, () => pintarTextos(p));
}

refrescar().catch(aviso);
cargarYoutube();
setInterval(() => refrescar().catch(() => {}), 2000);
setInterval(cargarYoutube, 5 * 60 * 1000);
