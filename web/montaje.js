// Studio 4 · panel: siete pantallas (Inicio, Vídeos, Biblioteca, Tendencias, Música, Canal, Herramientas) y, dentro de cada
// vídeo, un paso por pantalla (guion → material → montaje → previa → final) con su línea de tiempo por pistas.
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(ruta, datos) {
  const r = await fetch(ruta, datos === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
}
const seguro = async (ruta) => { try { return await api(ruta); } catch (_) { return null; } };

// ============================================================ Subir vídeos de tu PC (Examinar o arrastrar)
function subirVideo(archivo, id, alAvanzar, ruta = "/api/m/subir") {
  return new Promise((ok, mal) => {
    const x = new XMLHttpRequest();   // XHR y no fetch: da el progreso de la subida (vídeos de varios GB)
    x.open("POST", ruta + (id ? `?id=${encodeURIComponent(id)}` : ""));
    x.setRequestHeader("X-Nombre", encodeURIComponent(archivo.name));
    x.upload.onprogress = (e) => { if (e.lengthComputable && alAvanzar) alAvanzar(Math.round((100 * e.loaded) / e.total)); };
    x.onload = () => {
      let d = {};
      try { d = JSON.parse(x.responseText); } catch (_) { /* respuesta vacía */ }
      if (x.status < 300) ok(d); else mal(new Error(d.error || `Error ${x.status}`));
    };
    x.onerror = () => mal(new Error("No se pudo subir: se cortó la conexión con el estudio."));
    x.send(archivo);
  });
}
async function traerArchivo(archivo) {
  const enVideo = location.hash.match(/^#v=([\w-]+)/);   // dentro de un vídeo: se añade a ese; fuera: vídeo nuevo
  const estado = (t) => { if ($("subida-estado")) $("subida-estado").textContent = t; else if (t) aviso(t); };
  estado(`Subiendo «${archivo.name}»… 0 %`);
  try {
    const r = await subirVideo(archivo, enVideo ? enVideo[1] : "", (pc) => estado(`Subiendo «${archivo.name}»… ${pc} %`));
    estado("Subido. Preparando el material…");
    if (enVideo && enVideo[1] === r.id) cargarVideo(r.id);
    location.hash = `v=${r.id}/2`;
  } catch (e) { estado(""); aviso(e); }
}
// soltar un vídeo en cualquier parte del panel (salvo en los campos de imagen de cada frase, que tienen lo suyo)
const esCampoPropio = (ev) => ev.target.closest?.("input[type=file]:not(#archivo-input)");
document.addEventListener("dragover", (ev) => {
  if (esCampoPropio(ev) || ![...(ev.dataTransfer?.types || [])].includes("Files")) return;
  ev.preventDefault();
  document.body.classList.add("soltando");
});
document.addEventListener("dragleave", (ev) => { if (!ev.relatedTarget) document.body.classList.remove("soltando"); });
document.addEventListener("drop", (ev) => {
  document.body.classList.remove("soltando");
  const f = ev.dataTransfer?.files?.[0];
  if (!f || esCampoPropio(ev)) return;
  ev.preventDefault();
  if (!f.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name)) { aviso("Suelta un vídeo (MP4, MOV, MKV o WEBM)."); return; }
  traerArchivo(f);
});
function aviso(e) {
  $("aviso").textContent = e.message || String(e);
  $("aviso").hidden = false;
  clearTimeout(aviso.t); aviso.t = setTimeout(() => { $("aviso").hidden = true; }, 7000);
}
// «2:34:12», «154:55» o «90» → segundos
function segundos(t) {
  const s = String(t || "").trim();
  if (!s) return null;
  return s.split(":").reduce((a, x) => a * 60 + Number(x || 0), 0);
}
const reloj = (s) => { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const pad3 = (n) => String(n).padStart(3, "0");
const num = (n) => Number(n || 0).toLocaleString("es");
const corto = (n) => n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(".", ",")} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1).replace(".", ",")} K` : String(n || 0);
const mb = (b) => b > 1e9 ? `${(b / 1e9).toFixed(1).replace(".", ",")} GB` : `${Math.round(b / 1e6)} MB`;
const cabecera = (titulo, sub) => `<div class="seccion-cab"><h1>${titulo}</h1>${sub ? `<p class="meta">${sub}</p>` : ""}</div>`;
const tarjetaVideo = (v) => `
  <article class="tarjeta" data-abrir="${esc(v.id)}">
    <b>${esc(v.titulo)}</b>
    <div class="puntos">${[1, 2, 3, 4, 5].map((n) => `<i class="${n < v.paso || v.final ? "si" : ""}"></i>`).join("")}</div>
    <small>${v.terminado ? "Terminado ✓" : v.final ? "Montado · falta cerrar" : `Paso ${v.paso} de 5`} · ${v.con_clip}/${v.frases} frases con imagen · ${esc(v.creado)}</small>
    ${v.final ? "" : `<button class="archivar" type="button" data-archivar="${esc(v.id)}" title="No lo voy a terminar: sacarlo de la lista">Archivar</button>`}
  </article>`;

let datos = null;          // el vídeo abierto: {video, paso, fuentes}
let firma = "";            // para no repintar si nada cambió (y no borrar lo que estás escribiendo)
let pasoVisto = 0;         // el paso que se está mirando dentro del vídeo
let fraseEligiendo = 0, fuenteViendo = "";

// ============================================================ Inicio
async function vistaInicio() {
  // se pinta enseguida con tus vídeos; el canal (YouTube tarda) y las ideas se rellenan al llegar
  const m = await api("/api/m");
  $("vista").innerHTML = `
    <section class="carrusel" id="carrusel" aria-label="Presentación"><div class="carrusel-pista" id="carrusel-pista"></div></section>
    <div id="i-canal"><section class="canal-hero cargando"><div class="canal-logo"></div><div class="canal-datos"><h1>${esc(m.canal?.nombre || "")}</h1>
      <p class="meta">Leyendo tu canal en YouTube…</p></div></section></div>
    <section class="inicio-chat" id="inicio-chat"><div class="cargando-chat meta">Cargando el chat…</div></section>
    <section class="url-magica pegar-guion">
      <div><span class="etiqueta">¿Ya tienes guion?</span><h2>Pega tu <em>guion</em></h2>
        <p class="meta">Quita marcas de tiempo, acotaciones y muletillas, y lo parte en escenas listo para empezar.</p></div>
      <form class="pegar-form" id="pegar-form">
        <textarea class="campo" id="pegar-texto" rows="5" placeholder="Pega aquí tu guion o una transcripción (con o sin tiempos)…" required></textarea>
        <div class="fila"><input class="campo" id="pegar-titulo" placeholder="Título (opcional: si no, lo propone Studio 4)">
          <button class="primario" type="submit">Preparar guion</button></div>
      </form>
    </section>
    <section class="url-magica">
      <div><span class="etiqueta">Trae tu vídeo</span><h2>Pega un <em>enlace</em> o suelta un <em>archivo</em></h2>
        <p class="meta">Entra como material y lo editas: planos, 3 formatos, subtítulos.</p></div>
      <form class="fila" id="url-form">
        <input class="campo" id="url-input" placeholder="https://…  (enlace de un vídeo)" required>
        <button class="primario" type="submit">Traer vídeo</button>
      </form>
      <label class="soltar" id="soltar">
        <input type="file" id="archivo-input" accept="video/*" hidden>
        <b>Arrastra aquí tu vídeo</b><span class="meta">o pulsa para <u>examinar</u> · MP4, MOV, MKV, WEBM</span>
        <small class="meta" id="subida-estado"></small>
      </label>
    </section>
    <div id="i-ideas"></div>
    <div id="i-radar"></div>
    <section class="bloque-inicio">
      <div class="seccion-cab fila-entre"><h2>Sigue con <em>tus vídeos</em></h2><a class="boton" href="#videos">Ver todos</a></div>
      <div class="videos">
        <article class="tarjeta nuevo" data-al-chat><span>+</span><b>Nuevo vídeo</b><small>Cuéntaselo al chat: sin guion</small></article>
        ${m.videos.slice(0, 5).map(tarjetaVideo).join("")}
      </div>
    </section>`;
  $("archivo-input").onchange = (ev) => ev.target.files[0] && traerArchivo(ev.target.files[0]);
  pintarInicioChat();
  $("pegar-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const b = ev.target.querySelector("button"); b.disabled = true; b.textContent = "Limpiando y puliendo…";
    try { location.hash = `v=${(await api("/api/m/desde-guion", { guion: $("pegar-texto").value, titulo: $("pegar-titulo").value })).id}/1`; }
    catch (e) { aviso(e); b.disabled = false; b.textContent = "Preparar guion"; }
  };
  $("url-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const b = ev.target.querySelector("button"); b.disabled = true; b.textContent = "Trayendo…";
    try { location.hash = `v=${(await api("/api/m/desde-url", { url: $("url-input").value })).id}/2`; }
    catch (e) { aviso(e); b.disabled = false; b.textContent = "Traer vídeo"; }
  };
  seguro("/api/m/presentacion").then((d) => pintarCarrusel(d?.diapos || []));
  seguro("/api/ideas/diarias").then((d) => { if ($("i-ideas")) { $("i-ideas").innerHTML = pintarIdeas(d); enlazarIdeas(); } });
  seguro("/api/m/radar").then((r) => { if ($("i-radar")) $("i-radar").innerHTML = pintarRadar(r); });
  seguro("/api/panel").then((panel) => {
    if (!$("i-canal")) return;
    const activo = panel?.canales.find((c) => c.canal.id === panel.activo) || null;
    $("i-canal").innerHTML = pintarCanalHero(activo, panel);
    enlazarCanal();
  });
}

function pintarCanalHero(c, panel) {
  if (!c) return "";
  const yt = c.youtube || {};
  const otros = (panel.canales || []).filter((x) => x.canal.id !== c.canal.id);
  return `<section class="canal-hero">
    <img class="canal-logo" src="/canal/${esc(c.canal.id)}/logo.png" alt="" onerror="this.style.visibility='hidden'">
    <div class="canal-datos">
      <div class="fila"><h1>${esc(c.canal.nombre)}</h1>
        ${otros.length ? `<select class="campo canal-cambiar" id="cambiar-canal"><option value="">Cambiar de canal…</option>
          ${otros.map((o) => `<option value="${esc(o.canal.id)}">${esc(o.canal.nombre)}</option>`).join("")}</select>` : ""}</div>
      <p class="meta">${esc(c.canal.nicho || "")}${c.canal.redes?.youtube ? ` · ${esc(c.canal.redes.youtube)}` : ""}</p>
      <div class="cifras">
        <div><b>${corto(yt.suscriptores)}</b><small>suscriptores</small></div>
        <div><b>${corto(yt.vistas)}</b><small>vistas</small></div>
        <div><b>${num(yt.videos)}</b><small>vídeos publicados</small></div>
        <div><b>${num(c.producciones?.terminadas)}</b><small>terminados en Studio</small></div>
      </div>
      ${c.error ? `<p class="meta">YouTube: ${esc(c.error)}</p>` : ""}
    </div></section>`;
}
function enlazarCanal() {
  if ($("cambiar-canal")) $("cambiar-canal").onchange = async (ev) => {
    if (!ev.target.value) return;
    try { await api("/api/canales/activar", { id: ev.target.value }); ir(); } catch (e) { aviso(e); }
  };
}

// ============================================================ Chat de Inicio: se empieza hablando, nunca con un guion
const SUGERENCIAS_INICIO = ["Prepárame la campaña de Black Friday de mi producto", "Busca un nicho poco saturado para mi canal", "Dame 5 ideas de Shorts para esta semana",
  "¿Qué es tendencia hoy en mi nicho?", "Hazme un Short de 1 minuto sobre algo que esté sonando"];
function nichoHTML(n) {
  const color = n.veredicto.startsWith("Hueco") ? "ok" : n.veredicto.startsWith("Saturado") || n.veredicto.startsWith("Poca") ? "bajo" : "medio";
  return `<div class="nicho-fila"><b>${esc(n.tema)}</b><span class="nota-titulo ${color}">${esc(n.veredicto)}</span>
    ${n.videos ? `<small class="meta">${corto(n.mediana_vistas)} vistas medianas · ${n.grandes_1M} canales de +1M · el top 3 se lleva el ${Math.round(n.top3_cuota * 100)} % · ${n.pequenos_que_explotan} canales pequeños que explotan</small>` : ""}
    ${n.ejemplo ? `<small class="meta">Ejemplo: ${esc(n.ejemplo)}</small>` : ""}
    ${(n.historias || []).length ? `<div class="historias-nicho"><span class="etiqueta">Historias reales para empezar</span>
      ${n.historias.map((h) => `<div class="historia"><b>${esc(h.titulo)}</b><small class="meta">${esc(h.resumen)}</small>
        <div class="fila"><a class="chip" href="${esc(h.fuente)}" target="_blank" rel="noopener">Fuente</a>
        <button class="chip" type="button" data-preguntar="Dame guiones sobre esta historia real: ${esc(h.titulo)}">Guiones de esta historia</button></div></div>`).join("")}</div>` : ""}
    <button class="chip" type="button" data-preguntar="Dame ideas de guiones sobre ${esc(n.tema)}">Ideas de este nicho</button></div>`;
}
function resultadoHTML(r) {
  if (!r) return "";
  if (r.tipo === "nicho") return `<div class="nichos">${r.nichos.map(nichoHTML).join("")}</div>`;
  if (r.tipo === "ideas") return `<div class="ideas-rejilla">${r.ideas.map((i) => ideaHTML(i, false)).join("")}</div>`;
  if (r.tipo === "tendencias") return `<div class="chips">${r.senales.map((s) => `<button type="button" class="chip-radar" data-preguntar="Dame ideas de guiones sobre ${esc(s.tema)} (${esc((s.titulares || [])[0] || "")})">${esc(s.tema)} <b>${s.n_fuentes}</b></button>`).join("") || `<span class="meta">El radar aún no tiene señales de hoy.</span>`}</div>`;
  if (r.tipo === "estilo") return `<div class="estilos-ia chips-ia">${r.estilos.map((e) => `<button type="button" class="chip-ia${e.hecho_por === "claude" ? " por-claude" : ""}" title="${esc(e.para)} · ${esc(e.imagen)}" data-preguntar="Hazlo en estilo ${esc(e.nombre)} (${esc(e.id)})">${esc(e.nombre)}</button>`).join("")}</div>
    <p class="meta">✦ = lo hace Claude con código, gratis. El resto necesita un modelo de imagen o vídeo.</p>`;
  if (r.tipo === "campana") return campanaHTML(r.kit);
  if (r.tipo === "propuesta") return `<div class="propuesta${r.lanzada ? " lanzada" : ""}"><span class="etiqueta">${r.lanzada ? "Lanzado ✓" : "Listo para lanzar"}</span>
    <p>${esc(r.plan)}</p>${r.lanzada ? "" : `<div class="fila"><button class="primario" type="button" data-lanzar-inicio>Lanzar</button>
    <span class="meta">o escribe «lánzalo». Si quieres cambiar algo, dímelo antes.</span></div>`}</div>`;
  if (r.tipo === "video") return `<div class="fila"><a class="primario" href="#v=${esc(r.id)}/1">Abrir el vídeo (${esc(r.estilo)})</a><span class="meta">Se está investigando y escribiendo solo.</span></div>`;
  return "";
}
async function pintarInicioChat() {
  const caja = $("inicio-chat");
  if (!caja) return;
  const d = await seguro("/api/m/inicio-chat");
  const chat = d?.chat || [];
  const plegado = estadoChat("s4-chat-inicio") === "minimizado";
  caja.classList.toggle("plegado", plegado);
  caja.innerHTML = `<div class="seccion-cab fila-entre"><h2>¿Qué vídeo <em>hacemos</em> hoy?</h2>
      <div class="fila">${chat.length && !plegado ? `<button class="boton" type="button" id="inicio-limpiar">Empezar de nuevo</button>` : ""}
        <button class="boton icono" type="button" id="inicio-plegar" title="${plegado ? "Abrir el chat" : "Minimizar el chat"}" aria-label="${plegado ? "Abrir el chat" : "Minimizar el chat"}">${plegado ? "▾" : "—"}</button></div></div>
    ${plegado ? "" : `
    <form class="chat-form" id="inicio-form"><textarea class="campo" id="inicio-texto" rows="2" placeholder="Pregúntame lo que quieras o pídeme un vídeo: te digo qué haría y lo lanzas cuando quieras"></textarea>
      <button class="primario" type="submit">Enviar</button></form>
    <div class="chips-ia sugerencias">${SUGERENCIAS_INICIO.map((t) => `<button type="button" class="chip-ia" data-preguntar="${esc(t)}">${esc(t)}</button>`).join("")}</div>
    <div class="chat-msgs inicio-msgs" id="inicio-msgs">${pares(chat).map((x) => x.quien === "tú"
      ? `<div class="msg mio"><p>${esc(x.texto)}</p></div>`
      : `<div class="msg ia"><p>${esc(x.texto)}</p>${x.error ? `<small class="fallo">✕ ${esc(x.error)}</small>` : ""}${resultadoHTML(x.resultado)}</div>`).join("")
      || `<p class="meta">Pregúntame lo que quieras: un nicho, ideas, lo que es tendencia o un vídeo. Primero te digo qué haría; nada largo arranca hasta que digas «lánzalo».</p>`}</div>`}`;
  $("inicio-plegar").onclick = () => { estadoChat("s4-chat-inicio", plegado ? "abierto" : "minimizado"); pintarInicioChat(); };
  if (plegado) return;
  if ($("inicio-texto") && sessionStorage.getItem("s4-al-chat")) { sessionStorage.removeItem("s4-al-chat"); $("inicio-texto").focus(); }
  caja.querySelectorAll("[data-lanzar-inicio]").forEach((b) => {
    b.onclick = async () => {
      b.disabled = true; b.textContent = "Lanzando…";
      try {
        const r = await api("/api/m/inicio-chat/lanzar", {});
        if (r.resultado?.tipo === "video") { location.hash = `v=${r.resultado.id}/1`; return; }
        await pintarInicioChat();
      } catch (e) { aviso(e); b.disabled = false; b.textContent = "Lanzar"; }
    };
  });
  const enviarInicio = async (texto) => {
    if (!texto.trim()) return;
    const b = $("inicio-form").querySelector("button");
    b.disabled = true; b.textContent = "Pensando…";
    try {
      const r = await api("/api/m/inicio-chat", { mensaje: texto });
      if (r.resultado?.tipo === "video") { location.hash = `v=${r.resultado.id}/1`; return; }
      await pintarInicioChat();
    } catch (e) { aviso(e); b.disabled = false; b.textContent = "Enviar"; }
  };
  $("inicio-form").onsubmit = (ev) => { ev.preventDefault(); enviarInicio($("inicio-texto").value); };
  $("inicio-texto").onkeydown = (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); enviarInicio(ev.target.value); } };
  caja.querySelectorAll("[data-preguntar]").forEach((x) => { x.onclick = () => enviarInicio(x.dataset.preguntar); });
  if ($("inicio-limpiar")) $("inicio-limpiar").onclick = async () => { await api("/api/m/inicio-chat/limpiar", {}); pintarInicioChat(); };
  // las propuestas de guion: crear el vídeo o guardarlas, igual que en la Biblioteca
  caja.querySelectorAll("[data-idea-crear]").forEach((x) => { x.onclick = async () => {
    x.disabled = true; x.textContent = "Creando…";
    try { location.hash = `v=${(await api("/api/m/biblioteca/crear", { idea: x.dataset.ideaCrear })).id}/1`; } catch (e) { aviso(e); x.disabled = false; x.textContent = "Crear vídeo"; }
  }; });
  caja.querySelectorAll("[data-idea-guardar]").forEach((x) => { x.onclick = async () => {
    try { await api("/api/m/biblioteca/guardar", { idea: x.dataset.ideaGuardar }); x.textContent = "Guardada"; x.disabled = true; } catch (e) { aviso(e); }
  }; });
  if (sessionStorage.getItem("s4-al-chat")) { sessionStorage.removeItem("s4-al-chat"); $("inicio-texto").focus(); caja.scrollIntoView({ behavior: "smooth" }); }
}
document.addEventListener("click", (ev) => {   // «Nuevo vídeo» = ir al chat de inicio
  if (!ev.target.closest("[data-al-chat]")) return;
  sessionStorage.setItem("s4-al-chat", "1");
  estadoChat("s4-chat-inicio", "abierto");   // si estaba plegado, se abre
  if (location.hash === "#inicio" || location.hash === "") { pintarInicioChat(); } else { location.hash = "inicio"; }
});

// ============================================================ Presentación en carrusel (cristal sobre imagen)
let carruselTimer = 0;
function pintarCarrusel(diapos) {
  const caja = $("carrusel"), pista = $("carrusel-pista");
  if (!caja || !diapos.length) { if (caja) caja.hidden = true; return; }
  pista.innerHTML = diapos.map((d, k) => `
    <article class="diapo" style="${d.imagen ? `--img:url('${esc(d.imagen)}')` : ""}" aria-label="${k + 1} de ${diapos.length}">
      <div class="diapo-fondo"></div>${d.orbe ? `<div class="diapo-orbe"></div>` : ""}
      <div class="diapo-cristal"><span class="etiqueta">${esc(d.etiqueta)}</span><h2>${esc(d.titulo)}</h2><p>${esc(d.texto)}</p>
        ${d.chat ? `<button class="primario" type="button" data-al-chat>${esc(d.accion)} →</button>`
        : `<a class="primario" href="${esc(d.href)}">${esc(d.accion)} →</a>`}</div>
      ${(d.abanico || []).length > 1 ? `<div class="diapo-abanico">${d.abanico.map((im) => `<img src="${esc(im)}" alt="" loading="lazy">`).join("")}</div>`
        : d.imagen && !d.orbe ? `<img class="diapo-mini" src="${esc(d.imagen)}" alt="" loading="lazy">` : ""}
    </article>`).join("");
  caja.insertAdjacentHTML("beforeend", `<button class="carrusel-flecha izq" type="button" aria-label="Anterior">‹</button>
    <button class="carrusel-flecha der" type="button" aria-label="Siguiente">›</button>
    <div class="carrusel-puntos">${diapos.map((_, k) => `<button type="button" data-ir="${k}" aria-label="Diapositiva ${k + 1}"></button>`).join("")}</div>`);
  const actual = () => Math.round(pista.scrollLeft / pista.clientWidth);
  const ir = (k) => pista.scrollTo({ left: ((k + diapos.length) % diapos.length) * pista.clientWidth, behavior: "smooth" });
  const marcar = () => caja.querySelectorAll("[data-ir]").forEach((b, k) => b.classList.toggle("activo", k === actual()));
  caja.querySelector(".izq").onclick = () => ir(actual() - 1);
  caja.querySelector(".der").onclick = () => ir(actual() + 1);
  caja.querySelectorAll("[data-ir]").forEach((b) => { b.onclick = () => ir(Number(b.dataset.ir)); });
  pista.addEventListener("scroll", () => requestAnimationFrame(marcar), { passive: true });
  marcar();
  // pasa sola cada 6 s; se para mientras el ratón o el dedo están encima
  let quieto = false;
  caja.onmouseenter = caja.ontouchstart = () => { quieto = true; };
  caja.onmouseleave = caja.ontouchend = () => { quieto = false; };
  clearInterval(carruselTimer);
  carruselTimer = setInterval(() => {
    if (!$("carrusel")) { clearInterval(carruselTimer); return; }
    if (!quieto && !document.hidden) ir(actual() + 1);
  }, 6000);
}

// ============================================================ Temas del panel (cada uno con su paleta y su fondo)
const TEMAS = [
  { id: "cristal", nombre: "Cristal", nota: "El de siempre", colores: ["#ff8a3d", "#ff3ea5", "#2ee6ff"], fondo: "#07070c" },
  { id: "aurora", nombre: "Aurora boreal", nota: "Verdes y violetas del norte", colores: ["#3dffb4", "#22d3c5", "#8b6bff"], fondo: "#050b14" },
  { id: "oro", nombre: "Oro negro", nota: "Negro y dorado, de archivo", colores: ["#f3d58a", "#d4a64a", "#8a6a2c"], fondo: "#0a0907" },
  { id: "oceano", nombre: "Océano profundo", nota: "Azules y aguamarina", colores: ["#5eead4", "#38bdf8", "#6366f1"], fondo: "#040a18" },
  { id: "atardecer", nombre: "Atardecer", nota: "Naranja, coral y ciruela", colores: ["#ffb35c", "#ff6b6b", "#c04cfd"], fondo: "#120712" },
  { id: "neon", nombre: "Neón Tokio", nota: "Magenta y cian eléctricos", colores: ["#ff2bd6", "#7a5cff", "#00f0ff"], fondo: "#05030a" },
  { id: "grafito", nombre: "Grafito", nota: "Negro y plata, sobrio", colores: ["#e5e7eb", "#9ca3af", "#4b5563"], fondo: "#09090b" },
  { id: "perla", nombre: "Perla", nota: "Claro, suave y luminoso", colores: ["#ffb4a2", "#c7b8ff", "#9be7d8"], fondo: "#f6f3f1" },
  // descanso visual: poco contraste, sin brillos ni movimiento, colores cálidos y una ilustración tranquila de fondo
  { id: "papel", nombre: "Papel", nota: "Cálido y claro, como leer en papel", colores: ["#e8d5b5", "#c9a77c", "#a3b18a"], fondo: "#f3ecdf", calma: true },
  { id: "bosque", nombre: "Bosque", nota: "Verdes apagados, oscuro suave", colores: ["#3f6b5c", "#6f9a7f", "#2a4a40"], fondo: "#0f1a17", calma: true },
  { id: "noche", nombre: "Noche cálida", nota: "Sin luz azul, para la noche", colores: ["#ffcf8a", "#d08b4a", "#5a3a22"], fondo: "#140d08", calma: true },
];
function ponerTema(id, animar = true) {
  const raiz = document.documentElement;
  if (animar) { raiz.classList.add("cambiando-tema"); setTimeout(() => raiz.classList.remove("cambiando-tema"), 700); }
  raiz.dataset.tema = id;
  raiz.classList.toggle("calma", !!TEMAS.find((t) => t.id === id)?.calma);
  try { localStorage.setItem("s4-tema", id); } catch (e) { /* sin almacenamiento: el tema dura esta visita */ }
  document.querySelectorAll("[data-tema-elegir]").forEach((b) => b.classList.toggle("activo", b.dataset.temaElegir === id));
}
function montarTemas() {
  const caja = $("temas"), boton = $("tema-boton");
  if (!caja || !boton) return;
  const op = (t) => `<button type="button" class="tema-op" data-tema-elegir="${t.id}"
      style="--m1:${t.colores[0]};--m2:${t.colores[1]};--m3:${t.colores[2]};--mf:${t.fondo}">
      <span class="tema-muestra"><i></i><i></i><i></i></span><b>${esc(t.nombre)}</b><small>${esc(t.nota)}</small></button>`;
  $("temas-rejilla").innerHTML = TEMAS.filter((t) => !t.calma).map(op).join("")
    + `<span class="etiqueta temas-grupo">Descanso visual</span>` + TEMAS.filter((t) => t.calma).map(op).join("")
    + `<div class="temas-opciones">
        <label><input type="checkbox" id="op-quieto"> Menos movimiento</label>
        <label><input type="checkbox" id="op-pausas"> Recordarme descansar la vista (cada 20 min)</label></div>`;
  const leer = (k) => { try { return localStorage.getItem(k) === "1"; } catch (e) { return false; } };
  const guardar = (k, v) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch (e) { /* solo esta visita */ } };
  $("op-quieto").checked = leer("s4-quieto"); document.documentElement.classList.toggle("quieto", $("op-quieto").checked);
  $("op-quieto").onchange = (ev) => { guardar("s4-quieto", ev.target.checked); document.documentElement.classList.toggle("quieto", ev.target.checked); };
  $("op-pausas").checked = leer("s4-pausas"); pausasVista($("op-pausas").checked);
  $("op-pausas").onchange = (ev) => { guardar("s4-pausas", ev.target.checked); pausasVista(ev.target.checked); };
  boton.onclick = (ev) => { ev.stopPropagation(); caja.hidden = !caja.hidden; };
  caja.onclick = (ev) => { const b = ev.target.closest("[data-tema-elegir]"); if (b) ponerTema(b.dataset.temaElegir); };
  document.addEventListener("click", (ev) => { if (!caja.hidden && !caja.contains(ev.target) && ev.target !== boton) caja.hidden = true; });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") caja.hidden = true; });
  ponerTema(document.documentElement.dataset.tema || "cristal", false);
}
// regla 20-20-20: cada 20 min mirando la pantalla, 20 s mirando algo lejano (a unos 6 metros)
let pausaTimer = 0, pausaActivo = 0;
function pausasVista(si) {
  clearInterval(pausaTimer); pausaActivo = 0;
  if (!si) return;
  pausaTimer = setInterval(() => {   // solo cuenta el tiempo con el panel a la vista
    if (document.hidden || $("pausa-vista")) return;
    pausaActivo += 30;
    if (pausaActivo >= 20 * 60) { pausaActivo = 0; mostrarPausa(); }
  }, 30000);
}
function mostrarPausa() {
  document.body.insertAdjacentHTML("beforeend", `<div class="pausa-vista" id="pausa-vista" role="dialog" aria-label="Descanso visual">
    <div class="pausa-caja"><span class="etiqueta">Descanso visual</span><h2>Mira algo lejano</h2>
      <p>Aparta la vista de la pantalla y mira algo a unos 6 metros. Parpadea despacio.</p>
      <b class="pausa-cuenta" id="pausa-cuenta">20</b><button class="boton" type="button" id="pausa-saltar">Seguir ahora</button></div></div>`);
  let n = 20;
  const cerrar = () => { clearInterval(t); $("pausa-vista")?.classList.add("saliendo"); setTimeout(() => $("pausa-vista")?.remove(), 400); };
  const t = setInterval(() => { n -= 1; if ($("pausa-cuenta")) $("pausa-cuenta").textContent = n; if (n <= 0) cerrar(); }, 1000);
  $("pausa-saltar").onclick = cerrar;
}
montarTemas();

// los chats con la barra arriba: cada pregunta con su respuesta, lo más nuevo primero
function pares(mensajes) {
  const grupos = [];
  mensajes.forEach((m) => { if (m.quien === "tú" || !grupos.length) grupos.push([m]); else grupos[grupos.length - 1].push(m); });
  return grupos.reverse().flat();
}

// el kit de campaña: anuncios (cada uno se convierte en vídeo), publicaciones, correos y calendario
function campanaHTML(k) {
  const copiar = (t) => `<button type="button" class="chip" data-copiar="${esc(t)}">Copiar</button>`;
  return `<div class="campana"><span class="etiqueta">${esc(k.temporada)} · ${esc(k.titulo)}</span>
    ${k.mensaje ? `<p class="gancho">«${esc(k.mensaje)}»</p>` : ""}
    <div class="campana-anuncios">${k.anuncios.map((a, n) => `<div class="historia"><b>Anuncio ${a.duracion} s · ${esc(a.titulo)}</b>
      <small class="meta">${esc(a.guion)}</small><div class="fila"><button class="primario" type="button" data-anuncio="${n}" data-kit="${esc(k.id)}">Hacer este anuncio</button>${copiar(a.guion)}</div></div>`).join("")}</div>
    <details><summary>Publicaciones para redes (${k.publicaciones.length})</summary>${k.publicaciones.map((p) => `<div class="historia"><b>${esc(p.cuando)} · ${esc(p.red)}</b>
      <small>${esc(p.texto)} ${esc((p.hashtags || []).join(" "))}</small>${copiar(`${p.texto}\n\n${(p.hashtags || []).join(" ")}`)}</div>`).join("")}</details>
    <details><summary>Correos (${k.correos.length})</summary>${k.correos.map((c) => `<div class="historia"><b>${esc(c.cuando)} · ${esc(c.asunto)}</b>
      <small>${esc(c.cuerpo)}</small>${copiar(`${c.asunto}\n\n${c.cuerpo}`)}</div>`).join("")}</details>
    <details><summary>Calendario</summary><ul>${k.calendario.map((c) => `<li><b>${esc(c.cuando)}</b> · ${esc(c.que)}</li>`).join("")}</ul></details></div>`;
}
document.addEventListener("click", async (ev) => {
  const c = ev.target.closest("[data-copiar]");
  if (c) { try { await navigator.clipboard.writeText(c.dataset.copiar); c.textContent = "Copiado ✓"; } catch (e) { aviso("No pude copiar: selecciónalo a mano."); } return; }
  const a = ev.target.closest("[data-anuncio]");
  if (a) {
    a.disabled = true; a.textContent = "Creando…";
    try { location.hash = `v=${(await api("/api/m/campana/video", { kit: a.dataset.kit, n: Number(a.dataset.anuncio) })).id}/1`; }
    catch (e) { aviso(e); a.disabled = false; a.textContent = "Hacer este anuncio"; }
  }
});

// el panel de chat se puede minimizar (burbuja flotante) o cerrar (botón «Chat» arriba); se recuerda
const estadoChat = (clave, valor) => {
  try { if (valor) localStorage.setItem(clave, valor); return localStorage.getItem(clave) || "abierto"; } catch (e) { return valor || "abierto"; }
};

function pintarRadar(r) {
  const s = r?.senales || [];
  if (!s.length) return r?.actualizando ? `<section class="bloque-inicio"><div class="seccion-cab"><h2>En <em>tendencia</em> ahora</h2>
    <p class="meta">Buscando las tendencias de este canal…</p></div></section>` : "";
  // pulsar una tendencia = pedir guiones sobre ella en la Biblioteca (no crea ningún vídeo a medias)
  return `<section class="bloque-inicio">
    <div class="seccion-cab"><h2>En <em>tendencia</em> ahora</h2><p class="meta">${esc(r.descripcion || "")} Pulsa una para ver guiones posibles.</p></div>
    <div class="chips">${s.map((x) => `<button type="button" class="chip-radar${x.caliente ? " caliente" : ""}" data-tendencia="${esc(x.tema)}" data-titulares="${esc((x.titulares || []).slice(0, 2).join(" · "))}" title="${esc((x.titulares || []).join(" · "))}">${esc(x.tema)} <b>${x.n_fuentes}</b></button>`).join("")}</div>
  </section>`;
}
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-tendencia]");
  if (t) {
    sessionStorage.setItem("s4-buscar", `Guiones sobre «${t.dataset.tendencia}», que está en tendencia ahora (${t.dataset.titulares})`);
    location.hash = "biblioteca";
    return;
  }
  const a = ev.target.closest("[data-archivar]");
  if (a) {
    ev.stopPropagation();
    if (!confirm("¿Archivar este vídeo? Sale de la lista (se guarda en la papelera, no se borra).")) return;
    try { await api("/api/m/archivar", { id: a.dataset.archivar }); ir(); } catch (e) { aviso(e); }
  }
}, true);

function pintarIdeas(d) {
  const ideas = d?.ideas || [];
  if (!ideas.length) return d?.ocupado ? `<section class="bloque-inicio"><div class="seccion-cab"><h2>Ideas para <em>hoy</em></h2>
    <p class="meta">${esc(d.fase || "Preparando las 3 ideas de hoy…")}</p></div></section>` : "";
  return `<section class="bloque-inicio">
    <div class="seccion-cab"><h2>Ideas para <em>hoy</em></h2><p class="meta">Lo que más crece en tu nicho, convertido en idea propia.</p></div>
    <div class="ideas">${ideas.map((x, i) => `
      <article class="idea">
        ${x.miniatura ? `<img src="${esc(x.miniatura)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : `<div class="idea-sin"></div>`}
        <div class="idea-cuerpo"><small>${x.formato === "largo" ? "Largo" : "Corto"} · ${corto(x.fuente?.vistas_hora || 0)} vistas/hora</small>
          <b>${esc(x.idea)}</b>
          <details><summary>Por qué funciona</summary><p class="meta">${esc(x.por_que || "")}</p></details>
          <button class="primario" type="button" data-idea="${i}">Escribir guion y crear</button></div>
      </article>`).join("")}</div></section>`;
}
function enlazarIdeas() {
  document.querySelectorAll("[data-idea]").forEach((b) => { b.onclick = async () => {
    b.disabled = true; b.textContent = "Investigando…";
    try { location.hash = `v=${(await api("/api/m/desde-idea", { n: Number(b.dataset.idea) })).id}`; } catch (e) { aviso(e); b.disabled = false; }
  }; });
}

// ============================================================ Vídeos
async function vistaVideos() {
  const m = await api("/api/m");
  $("vista").innerHTML = `
    ${cabecera("Tus <em>vídeos</em>", "En 16:9 con material real, cinco pasos. De ahí salen el Short, los textos y la miniatura.")}
    <form class="nuevo-form" id="nuevo-form" hidden>
      <h2>Vídeo <em>nuevo</em></h2>
      <input class="campo" id="n-titulo" placeholder="Título de trabajo" required>
      <textarea class="campo" id="n-guion" placeholder="Pega aquí el guion: solo lo que dirá la voz. Deja una línea en blanco entre bloques: ahí irá la transición."></textarea>
      <div class="fila"><button class="primario" type="submit">Crear vídeo</button><button class="boton" type="button" id="n-cancelar">Cancelar</button></div>
    </form>
    <div class="videos">
      <article class="tarjeta nuevo" data-al-chat><span>+</span><b>Nuevo vídeo</b><small>Cuéntaselo al chat: sin guion</small></article>
      ${m.videos.map(tarjetaVideo).join("")}
    </div>
    <p class="meta">¿Ya tienes el guion escrito? <a href="#" data-nuevo>Pégalo aquí</a>.</p>
    <div hidden>
    </div>`;
  $("n-cancelar").onclick = () => { $("nuevo-form").hidden = true; };
  $("nuevo-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try { location.hash = `v=${(await api("/api/m/desde-guion", { titulo: $("n-titulo").value, guion: $("n-guion").value })).id}/1`; } catch (e) { aviso(e); }
  };
  if (sessionStorage.getItem("s4-nuevo")) { sessionStorage.removeItem("s4-nuevo"); abrirNuevo(); }
}
function abrirNuevo() {
  if (!$("nuevo-form")) { sessionStorage.setItem("s4-nuevo", "1"); location.hash = "videos"; return; }
  $("nuevo-form").hidden = false; $("n-titulo").focus();
}

// ============================================================ Biblioteca
// una propuesta de guion del chat de la Biblioteca: título, gancho, ángulo y sus fuentes reales
function ideaHTML(i, guardada) {
  const dominio = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (_) { return u; } };
  return `<article class="idea-guion">
    <div class="idea-cab"><span class="chip">${i.formato === "largo" ? "Vídeo largo" : "Short"}</span><b>${esc(i.titulo)}</b></div>
    <p class="gancho">«${esc(i.gancho)}»</p>
    ${i.angulo ? `<small class="meta">${esc(i.angulo)}</small>` : ""}
    <div class="idea-fuentes">${i.fuentes.map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(dominio(u))}</a>`).join("")}</div>
    <div class="fila"><button class="primario" type="button" data-idea-crear="${esc(i.id)}">Crear vídeo</button>
      ${guardada ? `<button class="boton" type="button" data-idea-quitar="${esc(i.id)}">Quitar</button>`
        : `<button class="boton" type="button" data-idea-guardar="${esc(i.id)}">Guardar idea</button>`}</div>
  </article>`;
}

async function vistaBiblioteca() {
  const [m, d, bc] = await Promise.all([api("/api/m"), seguro("/api/biblioteca"), seguro("/api/m/biblioteca-chat")]);
  const chat = bc?.chat || [];
  const guardadas = bc?.guardadas || [];
  const bases = bc?.bases || { canal: [], abiertas: [] };
  const mios = new Set(m.videos.map((v) => v.id));
  const guiones = d?.guiones || [];
  const temas = new Map();
  guiones.forEach((g) => { if (!temas.has(g.codigo)) temas.set(g.codigo, []); temas.get(g.codigo).push(g); });
  $("vista").innerHTML = `
    ${cabecera("Biblioteca de <em>guiones</em>", `Pide guiones por chat: se buscan en las bases de ${esc(bc?.canal || "tu canal")} y en bases abiertas, con sus fuentes.`)}
    <a class="chatgpt-logo" href="https://chatgpt.com/auth/login?next=%2Fg%2Fg-IgKhQ7IgB" target="_blank" rel="noopener" title="Abrir tu GPT en ChatGPT" aria-label="Abrir tu GPT en ChatGPT">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"/></svg><span>ChatGPT</span></a>
    <section class="bases">
      <span class="etiqueta">Bases de donde salen los guiones</span>
      <div class="bases-lista">${bases.canal.map((u) => `<span class="chip base-canal" title="Fuente de confianza del canal">${esc(u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}<button type="button" data-quitar-base="${esc(u)}" aria-label="Quitar">×</button></span>`).join("")}
        ${bases.abiertas.map((b) => `<span class="chip base-abierta" title="${esc(b.para)}">${esc(b.nombre)}</span>`).join("")}</div>
      <form class="fila" id="base-form"><input class="campo" id="base-url" placeholder="Añadir una web de confianza (https://…)"><button class="boton" type="submit">Añadir base</button></form>
    </section>
    <section class="bib-chat">
      <div class="chat-msgs bib-msgs" id="bib-msgs">${chat.length ? chat.map((x) => x.quien === "tú"
        ? `<div class="msg mio"><p>${esc(x.texto)}</p></div>`
        : `<div class="msg ia"><p>${esc(x.texto)}</p>${x.referencia ? `<small class="meta">Vídeo de referencia: <a href="${esc(x.referencia.url)}" target="_blank" rel="noopener">${esc(x.referencia.titulo)}</a></small>` : ""}${(x.bases || []).length ? `<small class="meta">Buscado en: ${esc(x.bases.join(", "))}</small>` : ""}
            ${(x.opciones || []).length ? `<div class="chips-ia">${x.opciones.map((o) => `<button type="button" class="chip-ia" data-bib-opcion="${esc(o)}">${esc(o)}</button>`).join("")}</div>` : ""}
            <div class="ideas-rejilla">${(x.ideas || []).map((i) => ideaHTML(i, guardadas.some((g) => g.id === i.id))).join("")}</div></div>`).join("")
        : `<p class="meta">Escribe qué guiones buscas: «misterios del mar sin resolver», «mitos nórdicos poco contados», «5 Shorts de enigmas arqueológicos»…</p>`}</div>
      <form class="chat-form" id="bib-form"><textarea class="campo" id="bib-texto" rows="2" placeholder="Escribe la idea con tus palabras o pega el enlace de un vídeo de referencia…"></textarea>
        <button class="primario" type="submit">Buscar</button></form>
    </section>
    ${guardadas.length ? `<section><span class="etiqueta">Ideas guardadas (${guardadas.length})</span>
      <div class="ideas-rejilla">${guardadas.map((i) => ideaHTML(i, true)).join("")}</div></section>` : ""}
    <details class="bib-antiguos"><summary class="etiqueta">Guiones ya escritos (${temas.size} temas · ${guiones.length} guiones)</summary>
    ${!temas.size ? `<p class="meta">Aún no hay guiones escritos.</p>` : ""}
    <div class="temas">${[...temas].map(([codigo, gs]) => {
      const largo = gs.find((g) => g.tipo === "largo") || gs[0];
      const cortos = gs.filter((g) => g !== largo);
      const repe = gs.some((g) => g.parecido_a?.length);
      return `<details class="tema-caja ${mios.has(largo.producido) ? "hecho" : ""}">
        <summary class="tema">
          <span class="tema-cod">${esc(codigo)}</span>
          <div><b>${esc(largo.titulo || largo.guion.slice(0, 70))}</b>
            <small>${largo.palabras} palabras · ${cortos.length} cortos${largo.producido && !mios.has(largo.producido) ? " · ya empezado" : ""}${repe ? ` · <span class="repe">algún corto se parece a otro tema</span>` : ""}</small></div>
          ${mios.has(largo.producido) ? `<button class="boton" type="button" data-abrir="${esc(largo.producido)}">Abrir</button>`
            : `<button class="primario" type="button" data-bib="${esc(largo.id)}">Crear en 16:9</button>`}
        </summary>
        <div class="tema-cuerpo">
          <p class="guion-previo">${esc(largo.guion.slice(0, 420))}${largo.guion.length > 420 ? "…" : ""}</p>
          ${cortos.length ? `<span class="etiqueta">Cortos de este tema</span>
            ${cortos.map((g) => `<div class="corto-item"><b>${esc(g.etiqueta)}</b><span>${esc(g.titulo || g.guion.slice(0, 80))}</span>
              ${g.parecido_a?.length ? `<small class="repe">se parece a ${esc(g.parecido_a.join(", "))}</small>` : ""}</div>`).join("")}` : ""}
        </div>
      </details>`; }).join("")}</div></details>`;
  const caja = $("bib-msgs");
  if (caja) caja.scrollTop = caja.scrollHeight;
  const pendiente = sessionStorage.getItem("s4-buscar");   // viene de pulsar una tendencia
  if (pendiente) { sessionStorage.removeItem("s4-buscar"); $("bib-texto").value = pendiente; setTimeout(() => buscar(), 0); }
  const buscar = async () => {
    const texto = $("bib-texto").value.trim();
    if (!texto) return;
    const b = $("bib-form").querySelector("button");
    b.disabled = true; b.textContent = "Buscando en las bases…";
    try { await api("/api/m/biblioteca/chat", { mensaje: texto }); await vistaBiblioteca(); }
    catch (e) { aviso(e); b.disabled = false; b.textContent = "Buscar"; }
  };
  $("bib-form").onsubmit = (ev) => { ev.preventDefault(); buscar(); };
  document.querySelectorAll("[data-bib-opcion]").forEach((b) => { b.onclick = () => { $("bib-texto").value = b.dataset.bibOpcion; buscar(); }; });
  $("bib-texto").onkeydown = (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); buscar(); } };
  $("base-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("/api/m/biblioteca/bases", { fuentes: [...bases.canal, $("base-url").value.trim()] }); await vistaBiblioteca(); } catch (e) { aviso(e); }
  };
  document.querySelectorAll("[data-quitar-base]").forEach((b) => { b.onclick = async () => {
    try { await api("/api/m/biblioteca/bases", { fuentes: bases.canal.filter((u) => u !== b.dataset.quitarBase) }); await vistaBiblioteca(); } catch (e) { aviso(e); }
  }; });
  document.querySelectorAll("[data-idea-guardar]").forEach((b) => { b.onclick = async () => {
    try { await api("/api/m/biblioteca/guardar", { idea: b.dataset.ideaGuardar }); await vistaBiblioteca(); } catch (e) { aviso(e); }
  }; });
  document.querySelectorAll("[data-idea-quitar]").forEach((b) => { b.onclick = async () => {
    try { await api("/api/m/biblioteca/quitar", { idea: b.dataset.ideaQuitar }); await vistaBiblioteca(); } catch (e) { aviso(e); }
  }; });
  document.querySelectorAll("[data-idea-crear]").forEach((b) => { b.onclick = async () => {
    b.disabled = true; b.textContent = "Creando…";
    try { location.hash = `v=${(await api("/api/m/biblioteca/crear", { idea: b.dataset.ideaCrear })).id}`; } catch (e) { aviso(e); b.disabled = false; b.textContent = "Crear vídeo"; }
  }; });
  document.querySelectorAll("[data-bib]").forEach((b) => { b.onclick = async (ev) => {
    ev.preventDefault(); b.disabled = true;
    try { location.hash = `v=${(await api("/api/m/desde-biblioteca", { item: b.dataset.bib })).id}`; } catch (e) { aviso(e); b.disabled = false; }
  }; });
}

// ============================================================ Tendencias
async function vistaTendencias() {
  const t = await seguro("/api/tendencias");
  const i = t?.datos?.informe;
  $("vista").innerHTML = `
    ${cabecera("<em>Tendencias</em> de tu nicho", t?.datos ? `Informe del ${esc(t.datos.fecha.slice(0, 10))}${t.caducado ? " · ya es viejo" : ""}` : "Aún no hay informe.")}
    <div class="fila"><button class="primario" type="button" id="act-tendencias" ${t?.ocupado ? "disabled" : ""}>${t?.ocupado ? esc(t.fase || "Analizando…") : "Actualizar tendencias"}</button>
      <button class="boton" type="button" id="ver-vivo">Lo que más crece esta semana</button></div>
    <div id="vivo"></div>
    ${i ? `<div class="tendencias">
      <p class="resumen">${esc(i.resumen)}</p>
      <div class="tend-col"><span class="etiqueta">Nichos que crecen</span>
        ${(i.nichos || []).map((n) => `<div class="tend-item"><b>${esc(n.nombre)}</b><small>${esc(n.por_que || "")}</small></div>`).join("")}</div>
      <div class="tend-col"><span class="etiqueta">Consejos de hoy</span>
        ${(i.consejos || []).map((c) => `<div class="tend-item"><small>${esc(c)}</small></div>`).join("")}
        <span class="etiqueta">Títulos que funcionan</span><div class="tend-item"><small>${esc(i.titulos || "")}</small></div>
        <span class="etiqueta">Evita</span>${(i.evitar || []).map((c) => `<div class="tend-item"><small>${esc(c)}</small></div>`).join("")}</div>
    </div>` : ""}`;
  $("act-tendencias").onclick = async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Analizando tu nicho…";
    try { await api("/api/tendencias", {}); setTimeout(ir, 5000); } catch (e) { aviso(e); }
  };
  $("ver-vivo").onclick = async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Buscando…";
    try {
      const d = await api("/api/ideas/vivo");
      $("vivo").innerHTML = `<div class="vivo">${d.videos.map((v) => `<a class="vivo-item" href="${esc(v.url)}" target="_blank" rel="noopener">
        <b>${esc(v.titulo)}</b><small>${esc(v.canal)} · ${corto(v.vistas_hora)} vistas/hora · ${corto(v.vistas)} vistas</small></a>`).join("")}</div>`;
    } catch (e) { aviso(e); }
    ev.target.disabled = false; ev.target.textContent = "Lo que más crece esta semana";
  };
}

// ============================================================ Canal
async function vistaCanal() {
  const panel = await seguro("/api/panel");
  const canales = panel?.canales || [];
  $("vista").innerHTML = `
    ${cabecera("Tus <em>canales</em>", "Estadísticas públicas de YouTube y lo hecho en Studio.")}
    ${canales.map((c) => {
      const yt = c.youtube || {};
      const lista = (t, vs) => vs?.length ? `<div class="tend-col"><span class="etiqueta">${t}</span>${vs.slice(0, 5).map((v) =>
        `<div class="tend-item"><b>${esc(v.titulo)}</b><small>${corto(v.vistas)} vistas</small></div>`).join("")}</div>` : "";
      return `<section class="canal-caja ${c.canal.id === panel.activo ? "activo" : ""}">
        <div class="canal-fila">
          <img class="canal-logo chico" src="/canal/${esc(c.canal.id)}/logo.png" alt="" onerror="this.style.visibility='hidden'">
          <div><h2>${esc(c.canal.nombre)}</h2><p class="meta">${esc(c.canal.nicho || "")}</p>
            <div class="redes">${Object.entries(c.canal.redes || {}).map(([r, u]) => `<span class="chip">${esc(r)}: ${esc(u)}</span>`).join("")}</div></div>
          ${c.canal.id === panel.activo ? `<span class="voz">Activo</span>` : `<button class="boton" type="button" data-activar="${esc(c.canal.id)}">Trabajar con este</button>`}
        </div>
        <div class="cifras">
          <div><b>${corto(yt.suscriptores)}</b><small>suscriptores</small></div>
          <div><b>${corto(yt.vistas)}</b><small>vistas</small></div>
          <div><b>${num(yt.videos)}</b><small>vídeos publicados</small></div>
          <div><b>${num(c.producciones?.total)}</b><small>producciones en Studio</small></div>
        </div>
        ${c.error ? `<p class="meta">YouTube: ${esc(c.error)}</p>` : ""}
        <div class="tendencias">${lista("Lo más visto", yt.mas_vistos)}${lista("Lo más reciente", yt.recientes)}</div>
      </section>`; }).join("")}`;
  document.querySelectorAll("[data-activar]").forEach((b) => { b.onclick = async () => {
    try { await api("/api/canales/activar", { id: b.dataset.activar }); ir(); } catch (e) { aviso(e); }
  }; });
}

// ============================================================ Herramientas
async function vistaHerramientas() {
  $("vista").innerHTML = `
    ${cabecera("<em>Herramientas</em>", "Accesos rápidos y el mantenimiento del estudio.")}
    <div class="herramientas">
      <a class="herramienta" href="#inicio"><svg><use href="#i-enlace"/></svg><b>Desde URL</b><small>Pega un enlace en el inicio → vídeo listo para editar</small></a>
      <a class="herramienta" href="/youtube" target="_blank"><svg><use href="#i-yt"/></svg><b>Vista YouTube</b><small>Tus vídeos y miniaturas como se verán publicados</small></a>
      <a class="herramienta" data-nuevo><svg><use href="#i-crear"/></svg><b>Pegar un guion</b><small>Vídeo nuevo pegando el texto de la voz</small></a>
    </div>
    <section class="mantenimiento"><span class="etiqueta">Tu herramienta de Google Flow</span>
      <p class="meta">Pega aquí el enlace de compartir de tu herramienta «Studio 4 · Guion a vídeo»: así la abres con un clic
        desde cada vídeo (paso Material).</p>
      <div class="fila"><input class="campo" id="flow-enlace" placeholder="https://labs.google/fx/…">
        <button class="boton" type="button" id="flow-guardar">Guardar</button><a class="boton" id="flow-abrir" target="_blank" rel="noopener" hidden>Abrir</a></div>
    </section>
    <div id="conexiones"></div>
    <div id="mantenimiento"></div>`;
  seguro("/api/m/flow").then((r) => {
    if (!r || !$("flow-enlace")) return;
    $("flow-enlace").value = r.enlace || "";
    if (r.enlace) { $("flow-abrir").href = r.enlace; $("flow-abrir").hidden = false; }
  });
  $("flow-guardar").onclick = async () => {
    try {
      const r = await api("/api/m/flow/enlace", { enlace: $("flow-enlace").value });
      $("flow-abrir").href = r.enlace; $("flow-abrir").hidden = !r.enlace; $("flow-guardar").textContent = "Guardado";
    } catch (e) { aviso(e); }
  };
  seguro("/api/m/conexiones").then((c) => {
    if (!c || !$("conexiones")) return;
    $("conexiones").innerHTML = `<section class="mantenimiento"><span class="etiqueta">Conexiones (las mismas claves del proyecto anterior)</span>
      <div class="conexiones">${c.conexiones.map((x) => `<div class="conexion ${x.conectada ? "si" : ""}">
        <i></i><div><b>${esc(x.api)}</b><small>${esc(x.uso)}</small></div><span>${x.conectada ? (x.pago ? "Conectada · de pago" : "Conectada · gratis") : "Sin conectar"}</span></div>`).join("")}</div></section>`;
  });
  try {
    const m = await api("/api/m/mantenimiento");
    $("mantenimiento").innerHTML = `<section class="mantenimiento"><span class="etiqueta">Mantenimiento</span>
      <div class="fila"><span class="meta">Vídeos ${mb(m.espacio.montajes)} · banco de clips ${mb(m.espacio.banco)}${m.espacio.papelera ? ` · papelera ${mb(m.espacio.papelera)}` : ""}</span>
        ${m.espacio.liberable > 50e6 ? `<button class="boton" id="liberar">Liberar ${mb(m.espacio.liberable)} de temporales</button>` : ""}</div>
      <div class="fila"><span class="meta">Descargador ${esc(m.descargador.version)}${m.descargador.viejo ? ` · tiene ${m.descargador.dias} días: conviene actualizarlo` : " · al día"}</span>
        ${m.descargador.viejo ? `<button class="boton" id="actualizar-dl">Actualizar descargador</button>` : ""}</div></section>`;
    if ($("liberar")) $("liberar").onclick = async (ev) => {
      if (!confirm("Se borran solo los trozos temporales de los montajes. Los vídeos, previas, Shorts y voces se quedan. ¿Seguir?")) return;
      ev.target.disabled = true;
      try { const r = await api("/api/m/liberar", {}); ev.target.textContent = `Liberados ${mb(r.liberado)}`; } catch (e) { aviso(e); }
    };
    if ($("actualizar-dl")) $("actualizar-dl").onclick = async (ev) => {
      ev.target.disabled = true; ev.target.textContent = "Actualizando…";
      try { const r = await api("/api/m/actualizar-descargador", {}); ev.target.textContent = `Listo (${r.version}): reinicia Studio 4`; }
      catch (e) { aviso(e); ev.target.disabled = false; ev.target.textContent = "Actualizar descargador"; }
    };
  } catch (_) { /* es un extra */ }
}

// ============================================================ Música (Biblioteca de audio de YouTube)
async function vistaMusica() {
  $("vista").innerHTML = `
    ${cabecera("<em>Música</em>", "Tus pistas de la Biblioteca de audio de YouTube: seguras para monetizar. Nada de YouTube Music (Content ID).")}
    <section class="mantenimiento musica-pasos">
      <span class="etiqueta">Cómo añadir pistas</span>
      <ol>
        <li>Abre <a href="https://studio.youtube.com/" target="_blank" rel="noopener">YouTube Studio</a> → <b>Biblioteca de audio</b>.</li>
        <li>Filtra por género o ánimo, escucha y pulsa <b>Descargar</b>.</li>
        <li>Guarda el archivo en tu carpeta de música (botón de abajo): Studio lo cataloga solo y le iguala el volumen.</li>
        <li>Si la pista pide <b>atribución</b>, copia ese texto en su casilla: irá en la descripción y en los créditos.</li>
      </ol>
      <div class="fila"><button class="boton" type="button" id="abrir-musica">Abrir carpeta de música</button><span class="meta" id="carpeta-musica"></span></div>
    </section>
    <div id="pistas" class="pistas"><p class="meta">Catalogando tu música…</p></div>`;
  $("abrir-musica").onclick = () => api("/api/m/musica/carpeta", {}).catch(aviso);
  const m = await api("/api/m/musica");
  $("carpeta-musica").textContent = m.carpeta;
  pintarPistas(m);
}

function pintarPistas(m) {
  if (!m.pistas.length) {
    $("pistas").innerHTML = `<p class="meta">Aún no hay pistas. Mientras tanto, los vídeos llevan el fondo suave del Studio.</p>`;
    return;
  }
  $("pistas").innerHTML = m.pistas.map((p) => `
    <article class="pista" data-archivo="${esc(p.archivo)}">
      <div class="pista-cab">
        <div><b>${esc(p.titulo)}</b><small>${esc(p.artista || "Sin artista")} · ${reloj(p.duracion)} · ${p.usos.length ? `usada en ${p.usos.length} vídeo${p.usos.length > 1 ? "s" : ""}` : "sin usar"}</small></div>
        <audio controls preload="none" src="/musica/${encodeURIComponent(p.archivo)}"></audio>
      </div>
      <div class="chips">${m.animos.map((a) => `<button class="chip ${p.animo.includes(a) ? "activo" : ""}" type="button" data-animo="${esc(a)}">${esc(a)}</button>`).join("")}</div>
      <input class="campo" data-atribucion placeholder="Atribución (solo si la pista la pide)" value="${esc(p.atribucion)}">
    </article>`).join("");
  $("pistas").querySelectorAll(".pista").forEach((el) => {
    const archivo = el.dataset.archivo;
    el.querySelectorAll("[data-animo]").forEach((b) => {
      b.onclick = async () => {
        b.classList.toggle("activo");
        const animo = [...el.querySelectorAll("[data-animo].activo")].map((x) => x.dataset.animo);
        try { await api("/api/m/musica/etiquetar", { archivo, animo }); } catch (e) { aviso(e); }
      };
    });
    const at = el.querySelector("[data-atribucion]");
    at.onchange = () => api("/api/m/musica/etiquetar", { archivo, atribucion: at.value }).catch(aviso);
  });
}

// ============================================================ Un vídeo, paso a paso
async function cargarVideo(id) {
  datos = await api(`/api/m/ver?id=${encodeURIComponent(id)}`);
  // cada aviso de progreso cambia «actualizado»: si contara, el panel se redibujaba entero (imágenes y
  // reproductores) cada 1,5 s mientras trabaja. Se redibuja solo si cambia algo de verdad o al acabar el trabajo.
  const { trabajo, actualizado, ...resto } = datos.video;
  const nueva = JSON.stringify([resto, Object.keys(datos.fuentes), pasoVisto, !!trabajo?.ocupado]);
  pintarTrabajo(trabajo);
  const escribiendo = document.activeElement && $("vista").contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (nueva !== firma && !(escribiendo && firma)) { firma = nueva; pintarVideo(); }
}

function miniaturaDe(f) {
  if (f.panel) return `<span>Panel: ${esc(f.panel.titulo || "texto")}</span>`;
  if (f.imagen) return `<img src="/m/${esc(datos.video.id)}/imagenes/${esc(f.imagen.archivo)}" alt="" loading="lazy"><em>Imagen${f.imagen.credito ? ` · ${esc(f.imagen.credito)}` : ""}</em>`;
  if (!f.clip) return `<span>Elegir plano</span>`;
  const fu = datos.fuentes[f.clip.fuente];
  const pl = fu?.planos[f.clip.plano - 1];
  return `<img src="/fv/${esc(f.clip.fuente)}/${pad3(f.clip.plano)}.jpg" alt="" loading="lazy"><em>${esc(fu?.nombre || "")} · ${pl ? (pl.fin - pl.ini).toFixed(1) : "?"} s</em>`;
}

const NOMBRES = ["Guion", "Material", "Montaje", "Previa", "Final"];
// ============================================================ Chat del vídeo (DeepSeek ejecuta acciones del estudio)
const SUGERENCIAS = ["Escribe el guion con IA", "Pon un plano en cada frase", "Subtítulos estilo cine arriba",
  "Cambia la voz a Charon", "Haz la previa", "Hazlo todo: los 3 formatos"];
function chatHTML(v) {
  const msgs = v.chat || [];
  const form = `<form class="chat-form" id="chat-form"><textarea class="campo" id="chat-texto" rows="2" placeholder="Pregunta o pide un cambio; lo largo te lo propongo y lo lanzas tú…"></textarea>
      <label class="boton clip" title="Adjuntar imagen, vídeo o guion">📎<input type="file" id="chat-adjunto" accept="image/*,video/*,.txt,.md" hidden></label>
      <button class="primario" type="submit">Enviar</button></form>`;
  return `<aside class="chat-lado"><div class="chat-cab"><b>Chat</b><small class="meta">Conversa; lo largo lo lanzas tú</small>
      <span class="chat-ventana"><button type="button" class="boton icono" data-chat="minimizado" title="Minimizar" aria-label="Minimizar el chat">—</button>
      <button type="button" class="boton icono" data-chat="cerrado" title="Cerrar" aria-label="Cerrar el chat">×</button></span></div>
    ${form}<span class="meta" id="chat-estado"></span>
    <div class="chips-ia sugerencias">${SUGERENCIAS.map((t) => `<button type="button" class="chip-ia" data-sugerencia="${esc(t)}">${esc(t)}</button>`).join("")}</div>
    <div class="chat-msgs" id="chat-msgs">${msgs.length ? pares(msgs).map((m) => `
      <div class="msg ${m.quien === "tú" ? "mio" : "ia"}"><p>${esc(m.texto)}</p>
        ${(m.hechas || []).map((h) => `<small class="hecho">✓ ${esc(h)}</small>`).join("")}
        ${(m.errores || []).map((h) => `<small class="fallo">✕ ${esc(h)}</small>`).join("")}
        ${m.pendiente ? `<div class="propuesta${m.pendiente.lanzada ? " lanzada" : ""}"><span class="etiqueta">${m.pendiente.lanzada ? "Lanzado ✓" : "Listo para lanzar"}</span>
          <p>${esc(m.pendiente.plan)}</p>${m.pendiente.lanzada ? "" : `<button class="primario" type="button" data-lanzar-video>Lanzar</button>`}</div>` : ""}</div>`).join("")
      : `<p class="meta">Pregúntame por el vídeo o pide cambios: «¿qué le falta?», «pon subtítulos estilo cine», «escribe un guion de 1 minuto»…</p>`}</div>
    ${(v.adjuntos || []).length ? `<div class="adjuntos">${v.adjuntos.map((a) => `<img src="/m/${esc(v.id)}/adjuntos/${esc(a.archivo)}" alt="${esc(a.nombre)}" title="${esc(a.nombre)} · pídele: «ponla en la miniatura» o «ponla en la frase 3»">`).join("")}</div>` : ""}
    </aside>`;
}
function enlazarChat(v) {
  const caja = $("chat-msgs");
  if (caja) caja.scrollTop = 0;   // lo nuevo va arriba, junto a la barra
  document.querySelectorAll("[data-lanzar-video]").forEach((b) => {
    b.onclick = async () => {
      b.disabled = true; b.textContent = "Lanzando…";
      try { await api("/api/m/chat/lanzar", { id: v.id }); } catch (e) { aviso(e); }
      firma = ""; await cargarVideo(v.id);
    };
  });
  const enviarChat = async (texto) => {
    if (!texto.trim()) return;
    const b = $("chat-form").querySelector("button");
    b.disabled = true; b.textContent = "Pensando…";
    try { await api("/api/m/chat", { id: v.id, mensaje: texto }); $("chat-texto").value = ""; }
    catch (e) { aviso(e); }
    finally { b.disabled = false; b.textContent = "Enviar"; firma = ""; await cargarVideo(v.id); }
  };
  $("chat-form").onsubmit = (ev) => { ev.preventDefault(); enviarChat($("chat-texto").value); };
  $("chat-texto").onkeydown = (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); enviarChat(ev.target.value); } };
  document.querySelectorAll("[data-sugerencia]").forEach((b) => { b.onclick = () => enviarChat(b.dataset.sugerencia); });
  // adjuntos: imagen → queda en el vídeo para la miniatura o una frase; vídeo → material; .txt → guion
  const adjuntar = async (f) => {
    const estado = (t) => { $("chat-estado").textContent = t; };
    try {
      if (/\.(txt|md)$/i.test(f.name) || f.type.startsWith("text/")) {
        const texto = await f.text();
        if (!confirm(`¿Usar «${f.name}» como guion de este vídeo? (${texto.split(/\s+/).length} palabras)`)) return;
        await api("/api/m/guion", { id: v.id, guion: texto });
      } else if (f.type.startsWith("image/") || /\.(jpe?g|png|webp)$/i.test(f.name)) {
        await subirVideo(f, v.id, (pc) => estado(`Adjuntando «${f.name}»… ${pc} %`), "/api/m/adjuntar");
      } else if (f.type.startsWith("video/") || /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name)) {
        await subirVideo(f, v.id, (pc) => estado(`Subiendo «${f.name}»… ${pc} %`));
      } else { aviso("Adjunta una imagen, un vídeo o un guion en .txt."); return; }
      estado(""); firma = ""; await cargarVideo(v.id);
    } catch (e) { estado(""); aviso(e); }
  };
  $("chat-adjunto").onchange = (ev) => { if (ev.target.files[0]) adjuntar(ev.target.files[0]); };
  const lado = document.querySelector(".chat-lado");
  lado.addEventListener("dragover", (ev) => { ev.preventDefault(); ev.stopPropagation(); lado.classList.add("soltando-chat"); });
  lado.addEventListener("dragleave", () => lado.classList.remove("soltando-chat"));
  lado.addEventListener("drop", (ev) => {
    ev.preventDefault(); ev.stopPropagation(); lado.classList.remove("soltando-chat");
    const f = ev.dataTransfer?.files?.[0];
    if (f) adjuntar(f);
  });
}

// Tarjeta «Resumen» y guion gráfico (escenas con su tiempo y su plano), como el lienzo de CapCut
function resumenIAHTML(v) {
  const r = v.resumen_ia;
  if (!r) return "";
  const fila = (k, val) => (val ? `<div><small class="meta">${k}</small><b>${esc(String(val))}</b></div>` : "");
  return `<section class="resumen-ia"><span class="etiqueta">Resumen del vídeo</span>
    ${r.gancho ? `<p class="gancho">«${esc(r.gancho)}»</p>` : ""}
    <div class="resumen-rejilla">${fila("Duración", reloj(r.duracion))}${fila("Formato", r.formato)}${fila("Tono", r.tono)}
      ${fila("Modo", r.modo === "inventar" ? "Historia" : "Investigación oficial")}${fila("Voz", v.voz_nombre)}${fila("Música", r.musica)}
      ${fila("Subtítulos", (v.subtitulos?.estilo || "viral") + " · " + (v.subtitulos?.posicion || "abajo"))}${fila("Material", `${v.fuentes.length} vídeo(s)`)}${fila("Plataforma", r.plataforma)}</div></section>`;
}
function guionGraficoHTML(v) {
  if (!v.frases.length) return "";
  const tiempos = v.voz?.tiempos;
  let t = 0;
  const filas = v.frases.map((f, k) => {
    const ini = tiempos?.[k] ? tiempos[k][0] : t;
    t += f.texto.split(/\s+/).length / 2.25;
    return `<div class="gg-fila"><small class="gg-t">${reloj(ini)}</small><p>${esc(f.texto)}</p>
      <button class="gg-mini" type="button" data-elegir="${f.n}" title="Elegir el plano">${miniaturaDe(f)}</button></div>`;
  }).join("");
  return `<section class="guion-grafico"><span class="etiqueta">Guion gráfico · ${v.frases.length} escenas</span>${filas}</section>`;
}

// el vídeo terminado: la edición se cierra y se invita a hacer el siguiente
function cierreHTML(v) {
  const t = v.textos || {};
  return `<section class="paso cierre"><span class="etiqueta">Edición terminada${v.terminado?.hecho ? ` · ${esc(v.terminado.hecho)}` : ""}</span>
    <h2>¡Tu vídeo está listo!</h2>
    <p class="meta">«${esc((t.titulos || [])[0] || v.titulo)}» ya está en su carpeta, con los 3 formatos, miniaturas, subtítulos, textos para publicar y el LÉEME que dice dónde va cada cosa.</p>
    <video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/final_16x9.mp4?v=${encodeURIComponent(v.final?.hecho || "")}"></video>
    <div class="fila">${v.paquete ? `<a class="boton" href="/m/${esc(v.id)}/paquete.zip?v=${encodeURIComponent(v.paquete.hecho)}" download="${esc(v.titulo)} (proyecto).zip">Descargar proyecto (.zip)</a>
      <button class="boton" type="button" id="abrir-paquete">Abrir carpeta</button>` : ""}
      <button class="boton" type="button" id="reabrir">Seguir editando</button></div>
    <div class="cierre-nuevo"><div><b>¿Hacemos el siguiente?</b><p class="meta">Cuéntale al chat de inicio una idea o pídele temas en tendencia.</p></div>
      <a class="primario grande" href="#inicio" id="nuevo-tras-cierre">Hacer un nuevo vídeo →</a></div></section>`;
}

function pintarVideo() {
  const v = datos.video, paso = datos.paso;
  if (v.terminado && v.final) {
    $("vista").innerHTML = `<div class="lienzo solo"><div class="lienzo-main"><a class="volver" href="#videos">← Tus vídeos</a>
      <div class="cabeza"><h1>${esc(v.titulo)}</h1></div>${cierreHTML(v)}</div></div>`;
    if ($("abrir-paquete")) $("abrir-paquete").onclick = () => enviar("/api/m/paquete/abrir");
    $("reabrir").onclick = () => { pasoVisto = 5; enviar("/api/m/reabrir"); };
    return;
  }
  const p = pasoVisto || paso;
  const estado = (n) => (n < paso || (n === 5 && v.final) ? "hecho" : n === paso ? "toca" : "");
  const conClip = v.frases.filter((f) => f.clip || f.panel || f.imagen).length;
  const chatVista = estadoChat("s4-chat-video");
  const pendiente = (v.chat || []).some((m) => m.pendiente && !m.pendiente.lanzada);
  $("vista").innerHTML = `
    <div class="lienzo ${chatVista !== "abierto" ? "sin-chat" : ""}"><div class="lienzo-main">
    <a class="volver" href="#videos">← Tus vídeos</a>
    <div class="cabeza"><h1>${esc(v.titulo)}</h1>
      <div class="fila"><button class="boton" type="button" id="abrir-carpeta">Abrir carpeta</button>
      ${chatVista === "cerrado" ? `<button class="boton" type="button" data-chat="abierto">Chat</button>` : ""}</div></div>
    <nav class="pasos">${NOMBRES.map((n, k) => `<a href="#v=${esc(v.id)}/${k + 1}" class="${estado(k + 1)} ${p === k + 1 ? "visto" : ""}">
      <b>${estado(k + 1) === "hecho" ? "✓" : k + 1}</b><span>${n}</span></a>`).join("")}</nav>
    ${[pasoGuion, pasoMaterial, pasoMontaje, pasoPrevia, pasoFinal][p - 1](v, conClip)}
    <div class="navegar">
      ${p > 1 ? `<a class="boton" href="#v=${esc(v.id)}/${p - 1}">← ${NOMBRES[p - 2]}</a>` : "<span></span>"}
      ${p < 5 ? `<a class="primario" href="#v=${esc(v.id)}/${p + 1}">${NOMBRES[p]} →</a>` : ""}
    </div>
    </div>${chatVista === "abierto" ? chatHTML(v) : ""}</div>
    ${chatVista === "minimizado" ? `<button class="chat-burbuja${pendiente ? " aviso" : ""}" type="button" data-chat="abierto" aria-label="Abrir el chat">
      <span>Chat</span>${pendiente ? "<i></i>" : ""}</button>` : ""}`;
  document.querySelectorAll("[data-chat]").forEach((b) => { b.onclick = () => { estadoChat("s4-chat-video", b.dataset.chat); firma = ""; pintarVideo(); }; });
  enlazarVideo(p);
  if (chatVista === "abierto") enlazarChat(v);
}

const pasoCab = (n, titulo, texto) => `<div class="paso-cab"><span class="num">${n}</span><div><h2>${titulo}</h2><p>${texto}</p></div></div>`;
// El resumen del guion: duración, capítulos (bloques) y escenas (frases)
const resumenHTML = (r) => !r || !r.frases ? "" : `<div class="resumen">
  <div><b>${reloj(r.duracion)}</b><small>${r.estimada ? "duración estimada" : "duración con la voz"}</small></div>
  <div><b>${r.capitulos}</b><small>capítulos</small></div>
  <div><b>${r.frases}</b><small>escenas</small></div>
  <div><b>${r.paneles}</b><small>paneles</small></div>
  <div><b>${r.con_imagen}/${r.frases}</b><small>con imagen</small></div></div>`;
// La revisión de calidad que se hace sola al terminar la previa o el final
function calidadHTML(c) {
  if (!c) return "";
  if (c.ok) return `<div class="calidad ok"><b>Revisión de calidad: lista para ver</b><small>Sin congelados, huecos de sonido ni subtítulos sueltos · ${String(c.lufs.toFixed(1)).replace(".", ",")} LUFS · ${c.hecha}</small>
    ${c.avisos.length ? `<small>${c.avisos.map(esc).join(" · ")}</small>` : ""}</div>`;
  return `<div class="calidad mal"><b>Revisión de calidad: ${c.fallos.length} cosa${c.fallos.length > 1 ? "s" : ""} por arreglar</b>
    ${c.fallos.map((f) => `<small>✗ ${esc(f)}</small>`).join("")}</div>`;
}

// Opciones de «Crea con IA»: duración, formato, modo (investigación oficial o historia) y tono
const DURACIONES_IA = [[15, "15 s"], [30, "30 s"], [60, "1 min"], [180, "3 min"], [300, "5 min"], [600, "10 min"]];
let ESTILOS_IA = { estilos: [], canal: "", composicion: null, canal_composicion: {} };   // studio4/estilos.py y composicion.py
seguro("/api/m/estilos").then((r) => { if (r) ESTILOS_IA = r; });
function recomendacion(id) {
  const e = ESTILOS_IA.estilos.find((x) => x.id === id);
  if (!e) return "";
  return `${e.hecho_por === "claude" ? "<b>Lo hace Claude · gratis.</b>" : `<b>Necesita modelo · coste ${esc(e.coste)}.</b>`} ${esc(e.para)}.
    Imagen: ${esc(e.imagen)}. Vídeo: ${esc(e.video)}.${e.animar ? ` Como mucho ${e.animar} escenas animadas.` : ""}`;
}
function opcionesIA(o = {}) {
  const d = Number(o.duracion || 60), f = o.formato || "16:9", m = o.modo || "buscar", es = o.estilo || ESTILOS_IA.canal || "documental";
  const chip = (grupo, valor, texto, activo) => `<button type="button" class="chip-ia${activo ? " activo" : ""}" data-valor="${esc(valor)}">${texto}</button>`;
  return `<div class="ia-opciones">
    <div class="chips-ia" data-grupo="duracion">${DURACIONES_IA.map(([sg, t]) => chip("duracion", sg, t, sg === d)).join("")}</div>
    <div class="chips-ia" data-grupo="formato">${chip("formato", "16:9", "▭ 16:9", f === "16:9")}${chip("formato", "9:16", "▯ 9:16", f === "9:16")}</div>
    <div class="chips-ia" data-grupo="modo">${chip("modo", "buscar", "Investigación oficial", m === "buscar")}${chip("modo", "inventar", "Historia inventada", m === "inventar")}</div>
    ${ESTILOS_IA.estilos.length ? `<div class="chips-ia estilos-ia" data-grupo="estilo">${ESTILOS_IA.estilos.map((e) =>
      `<button type="button" class="chip-ia${e.id === es ? " activo" : ""}${e.hecho_por === "claude" ? " por-claude" : ""}" data-valor="${esc(e.id)}" title="${esc(e.para)}">${esc(e.nombre)}</button>`).join("")}</div>
    <p class="meta recomendacion" data-recomendacion>${recomendacion(es)}</p>` : ""}
    ${composicionHTML(o)}
    <input class="campo" data-tono placeholder="Tono (opcional): misterio, épico, humor…" value="${esc(o.tono || "")}">
  </div>`;
}
// la composición: gancho + ritmo + leyenda (el estilo va arriba); cada fila con su ejemplo
function composicionHTML(o = {}) {
  const c = ESTILOS_IA.composicion;
  if (!c) return "";
  const def = ESTILOS_IA.canal_composicion || {};
  const fila = (grupo, titulo) => `<div class="comp-fila"><span class="meta">${titulo}</span>
    <div class="chips-ia" data-grupo="${grupo}">${c[grupo].map((x) => `<button type="button" class="chip-ia${x.id === (o[grupo] || def[grupo]) ? " activo" : ""}${grupo === "leyenda" ? ` leyenda-${esc(x.paleta)}` : ""}" data-valor="${esc(x.id)}" title="${esc(x.detalle)}">${esc(x.nombre)}</button>`).join("")}</div></div>`;
  return `<div class="composicion"><span class="etiqueta">Composición</span>${fila("gancho", "Gancho")}${fila("ritmo", "Ritmo")}${fila("leyenda", "Subtítulos")}</div>`;
}
function leerOpcionesIA(raiz) {
  const o = { tono: raiz.querySelector("[data-tono]")?.value || "" };
  raiz.querySelectorAll(".chips-ia").forEach((g) => { const a = g.querySelector(".activo"); if (a) o[g.dataset.grupo] = a.dataset.valor; });
  return o;
}
document.addEventListener("click", (ev) => {   // un solo chip activo por grupo
  const c = ev.target.closest(".chip-ia");
  if (c) c.parentElement.querySelectorAll(".chip-ia").forEach((x) => x.classList.toggle("activo", x === c));
  if (c && c.parentElement.dataset.grupo === "estilo") {   // al elegir estilo, su recomendación de modelos y coste
    const r = c.closest(".ia-opciones")?.querySelector("[data-recomendacion]");
    if (r) r.innerHTML = recomendacion(c.dataset.valor);
  }
});

function pasoGuion(v) {
  return `<section class="paso">
    ${pasoCab(1, "Guion", `${v.frases.length} frases en ${new Set(v.frases.map((f) => f.bloque)).size} bloques. Una línea en blanco separa los bloques: ahí entra la rejilla.`)}
    ${resumenIAHTML(v)}
    ${resumenHTML(datos.resumen)}
    ${guionGraficoHTML(v)}
    ${v.avisos?.length ? `<div class="avisos">${v.avisos.map((a) => `<p>${esc(a)}</p>`).join("")}</div>` : ""}
    ${!v.frases.length && v.trabajo?.ocupado ? `<p class="meta">Studio está investigando y escribiendo el guion: aparecerá aquí al terminar.</p>` : ""}
    <div class="ia-caja" id="guion-ia">
      <span class="etiqueta">Generar guion con IA</span>
      <p class="meta">Investiga el tema en fuentes oficiales, mira el material real y escribe el guion. Después lo revisas abajo.</p>
      ${opcionesIA(v.ia_opciones)}
      <div class="fila"><button class="primario" type="button" id="generar-guion" ${v.trabajo?.ocupado ? "disabled" : ""}>${v.frases.length ? "Rehacer el guion con IA" : "Generar guion con IA"}</button></div>
    </div>
    <details class="a-mano" ${v.frases.length ? "open" : ""}><summary>${v.frases.length ? "Revisar y editar el guion" : "…o pégalo a mano"}</summary>
      <textarea class="campo guion" id="guion">${esc(v.guion)}</textarea>
      <div class="fila"><button class="boton" type="button" id="guardar-guion">Guardar cambios del guion</button></div>
    </details>
  </section>`;
}

function pasoMaterial(v) {
  return `<section class="paso">
    ${pasoCab(2, "Material", "Tráilers oficiales y gameplay sin comentario. Se baja en baja calidad solo para ver los planos; en alta, solo lo que uses.")}
    <form class="material-form" id="material-form">
      <input class="campo" id="m-url" placeholder="Enlace del vídeo (YouTube…)" required>
      <input class="campo" id="m-desde" placeholder="Desde (2:33:55)">
      <input class="campo" id="m-hasta" placeholder="Hasta (2:50:33)">
      <button class="primario" type="submit">Añadir</button>
    </form>
    <label class="boton subir-material"><input type="file" accept="video/*" hidden data-subir-material>Subir vídeo de tu PC</label>
    <p class="meta">En un gameplay de horas, pon desde y hasta (el capítulo de la misión): así solo se baja ese tramo.</p>
    ${sugeridoHTML(v)}
    <div class="flow-caja">
      <span class="etiqueta">Escenas con IA · tu herramienta de Google Flow</span>
      <p class="meta">1) Saca la escaleta y pégala en tu herramienta «Studio 4 · Guion a vídeo». 2) En Flow, genera y pulsa
        «Exportar para Studio 4». 3) Deja el ZIP (o las escenas) en la carpeta de importar y pulsa «Importar de Flow».</p>
      <div class="fila">
        <a class="boton" id="abrir-flow" target="_blank" rel="noopener" hidden>Abrir mi herramienta</a>
        <button class="boton" type="button" id="escaleta-flow">Escaleta para Flow</button>
        <button class="boton" type="button" id="carpeta-flow">Abrir carpeta de importar</button>
        <button class="primario" type="button" id="importar-flow">Importar de Flow</button>
      </div>
      <div id="escaleta-caja" hidden>
        <textarea class="campo" id="escaleta-json" readonly style="min-height:180px;font-family:monospace;font-size:12px"></textarea>
        <div class="fila"><button class="boton" type="button" id="copiar-escaleta">Copiar escaleta</button><span class="meta" id="escaleta-info"></span></div>
      </div>
    </div>
    <div class="fuentes">${v.fuentes.map((fid) => { const f = datos.fuentes[fid]; return `
      <div class="fuente"><img src="/fv/${esc(fid)}/${pad3((f.planos.find((x) => !x.pobre) || f.planos[0]).n)}.jpg" alt="" loading="lazy"><div><b>${esc(f.nombre)}</b>
        <small class="meta">${f.planos.length} planos · ${esc(f.canal || "")}${datos.escenas?.[fid] ? ` · ${datos.escenas[fid]} escenas (GTA Wiki)` : ""}</small></div></div>`; }).join("")}</div>
    <div id="banco"></div>
  </section>`;
}

function sugeridoHTML(v) {
  const usadas = new Set(v.fuentes.map((fid) => datos.fuentes[fid]?.url).filter(Boolean));
  const escenas = (v.material_sugerido || []).map((e) => `
    <div class="sugerida"><b>${esc([e.juego, e.que].filter(Boolean).join(" · "))}</b>
      ${e.videos.length ? e.videos.map((x) => `
        <div class="sugerido"><img src="https://i.ytimg.com/vi/${esc(x.id)}/mqdefault.jpg" alt="" loading="lazy">
          <div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.titulo)}</a>
            <small class="meta">${esc(x.canal)} · ${reloj(x.duracion)}</small></div>
          ${usadas.has(x.url) ? `<span class="meta">Añadido</span>`
            : `<button class="boton" type="button" data-sugerido="${esc(x.url)}">Añadir</button>`}</div>`).join("")
        : `<p class="meta">No hay material de esto: mejor quitarlo del guion o contarlo en un panel.</p>`}
    </div>`).join("");
  return `<div class="sugerido-caja">
    <span class="etiqueta">Material real del tema</span>
    <p class="meta">Tráilers oficiales y gameplay sin comentario de los juegos de los que habla el guion. Nada de vídeos
      de análisis o reacciones de otros canales. Si algo del guion no tiene material, no se cuenta.</p>
    ${escenas}
    <div class="fila"><button class="boton" type="button" id="buscar-material">${v.material_sugerido ? "Buscar otra vez" : "Buscar material del tema"}</button></div>
  </div>`;
}

function pasoMontaje(v, conClip) {
  let bloque = -1;
  const frases = v.frases.map((f) => {
    const sep = f.bloque !== bloque ? `<div class="bloque-sep">Bloque ${f.bloque + 1}${f.bloque > 0 ? " · entra con la rejilla" : ""}</div>` : "";
    bloque = f.bloque;
    return `${sep}<div class="frase" id="frase-${f.n}">
      <button class="miniatura" type="button" data-elegir="${f.n}" title="Elegir el plano de esta frase">${miniaturaDe(f)}</button>
      <div class="cuerpo"><small>FRASE ${f.n}</small><p>${esc(f.texto)}</p>
        <div class="fila">
          <input class="campo rotulo" data-rotulo="${f.n}" value="${esc(f.rotulo || "")}" placeholder="Rótulo (opcional): THE WARRIORS · 2005">
          <button class="boton" type="button" data-panel="${f.n}">${f.panel ? "Editar panel" : "Panel de texto"}</button>
          <button class="boton" type="button" data-imagen="${f.n}">${f.imagen ? "Cambiar imagen" : "Imagen"}</button>
          <button class="boton icono" type="button" data-subir="${f.n}" title="Subir esta escena">▲</button>
          <button class="boton icono" type="button" data-bajar="${f.n}" title="Bajar esta escena">▼</button>
          ${f.clip ? `<button class="boton icono" type="button" data-quitar-clip="${f.n}" title="Quitar el clip (la frase se queda sin plano)">✕</button>` : ""}
        </div>
        <div class="panel-txt" data-imagen-form="${f.n}" hidden>
          <span class="etiqueta">Imagen para esta frase (arte oficial, captura, producto…)</span>
          <div class="fila"><input class="campo" data-iurl="${f.n}" placeholder="Pega el enlace de una imagen (https://…)">
            <button class="primario" type="button" data-poner-url="${f.n}">Poner</button></div>
          <div class="fila"><input class="campo" type="file" accept="image/*" data-ifile="${f.n}">
            <input class="campo" data-icred="${f.n}" placeholder="De dónde es (crédito)" value="${esc(f.imagen?.credito || "")}"></div>
          <div class="fila"><input class="campo" data-ibuscar="${f.n}" placeholder="Buscar en tus fuentes: Rockstar Toronto, Vespa mods 1964…">
            <button class="boton" type="button" data-buscar-img="${f.n}">Buscar</button>
            ${f.imagen ? `<button class="boton" type="button" data-quitar-imagen="${f.n}">Quitar imagen</button>` : ""}</div>
          <div class="resultados-img" data-iresultados="${f.n}"></div>
        </div>
        <div class="panel-txt" data-panel-form="${f.n}" hidden>
          <input class="campo" data-pt="${f.n}" placeholder="Título del panel" value="${esc(f.panel?.titulo || "")}">
          <textarea class="campo" data-pi="${f.n}" style="min-height:110px" placeholder="Una línea por punto (máx. 5)">${esc((f.panel?.items || []).join("\n"))}</textarea>
          <input class="campo" data-pn="${f.n}" placeholder="Nota pequeña (p. ej. Según avances de prensa · recreación)" value="${esc(f.panel?.nota || "")}">
          <div class="fila"><button class="primario" type="button" data-guardar-panel="${f.n}">Guardar panel</button>
            ${f.panel ? `<button class="boton" type="button" data-quitar-panel="${f.n}">Quitar panel</button>` : ""}</div>
        </div>
      </div></div>`;
  }).join("");
  return `<section class="paso">
    ${pasoCab(3, "Montaje", `${conClip} de ${v.frases.length} frases con imagen. Toca un clip de la línea de tiempo o una imagen para cambiar el plano.`)}
    <div class="fila"><button class="primario" type="button" id="proponer" ${v.fuentes.length ? "" : "disabled"}>Proponer planos para las frases vacías</button>
      ${Object.values(datos.escenas || {}).some((n) => n) ? `<button class="boton" type="button" id="planos-escenas"
        title="Cada frase con el plano del tráiler donde ocurre lo que dice (índice de escenas de GTA Wiki)">Planos por escenas</button>
        <label class="meta"><input type="checkbox" id="escenas-todas"> también las que ya tienen plano</label>` : ""}
      <button class="boton" type="button" id="ver-storyboard" ${conClip ? "" : "disabled"}>Ver storyboard</button>
      <button class="boton" type="button" id="automatico" ${conClip === v.frases.length && v.frases.length ? "" : "disabled"}
        title="Vídeo final con voz, subtítulos y música, Short, textos, miniatura y revisión, sin pararse">Hacerlo todo</button></div>
    ${datos.resumen?.cobertura?.length ? `<div class="avisos">${datos.resumen.cobertura.map((c) => `<p>Frase ${c.n}: su plano da ${String(c.hay).replace(".", ",")} s y necesita ${String(c.necesita).replace(".", ",")} s · ${c.congela ? "se quedaría quieto: añade otro plano o cámbialo" : "irá algo más lento"}</p>`).join("")}</div>` : ""}
    <div class="linea" id="linea"><p class="meta">Cargando la línea de tiempo…</p></div>
    ${frases}
  </section>`;
}

function pasoPrevia(v, conClip) {
  return `<section class="paso">
    ${pasoCab(4, "Previa", "En silencio, con los efectos y las transiciones. Gratis: revísala antes de la voz.")}
    ${v.previa ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/previa.mp4?v=${encodeURIComponent(v.actualizado)}"></video>` : `<div class="pantalla vacia">Aún no hay previa</div>`}
    ${v.previa ? calidadHTML(v.calidad?.previa) : ""}
    <div class="fila"><button class="primario" type="button" id="hacer-previa" ${conClip === v.frases.length && v.frases.length ? "" : "disabled"}>${v.previa ? "Rehacer previa" : "Hacer previa"}</button>
      ${conClip < v.frases.length ? `<span class="meta">Faltan ${v.frases.length - conClip} frases por elegir (paso 3).</span>` : ""}</div>
  </section>`;
}

// una tarjeta de sonido: ▶ para escucharlo antes de elegir, su nombre y «Usar»
function tarjetaSonido({ oir = "", pago = false, nombre, detalle = "", usar, elegida }) {
  return `<div class="op-audio${elegida ? " activa" : ""}">
    ${oir ? `<button class="oir" type="button" data-oir="${esc(oir)}" ${pago ? 'data-pago="1"' : ""} aria-label="Escuchar ${esc(nombre)}">▶</button>` : `<span class="oir mudo">·</span>`}
    <div class="op-texto"><b>${esc(nombre)}</b>${detalle ? `<small>${esc(detalle)}</small>` : ""}</div>
    <button class="chip${elegida ? " activo" : ""}" type="button" ${usar}>${elegida ? "Elegida" : "Usar"}</button>
  </div>`;
}

function vozMusicaHTML(v) {
  const prov = v.voz_proveedor || "gemini";
  const voces = Object.entries(datos.voces).filter(([, o]) => o.disponible).flatMap(([pv, o]) => Object.entries(o.voces).map(([n, d]) =>
    tarjetaSonido({ oir: `/api/voz/oir?voz=${pv === "fal" ? "fal:" : ""}${encodeURIComponent(n)}`, pago: pv === "fal", nombre: n,
      detalle: pv === "fal" ? `${d} · de pago` : d, usar: `data-usar-voz="${esc(pv)}|${esc(n)}"`, elegida: prov === pv && n === v.voz_nombre })));
  // tus voces subidas, guardadas para todos los vídeos
  const guardadas = (datos.voces_guardadas || []).map((x) => tarjetaSonido({ oir: `/api/m/voces-guardadas/${x.id}.wav`, nombre: x.nombre,
    detalle: `Tu voz · ${Math.round(x.duracion)} s`, usar: `data-voz-guardada="${esc(x.id)}"`,
    elegida: prov === "propia" && v.voz_propia?.huella === x.id }));
  const vel = v.voz_velocidad || 1;
  const velocidades = [0.9, 1, 1.1, 1.2, 1.3].map((x) =>
    `<button class="chip${Math.abs(x - vel) < 0.01 ? " activo" : ""}" type="button" data-velocidad="${x}">${String(x).replace(".", ",")}×</button>`).join("");
  const m = datos.musica;
  const musicas = [
    tarjetaSonido({ nombre: "Automática", detalle: m.modo === "auto" && m.elegida ? `ahora: ${m.elegida}` : "por el ánimo del guion", usar: 'data-usar-musica="auto"', elegida: m.modo === "auto" }),
    tarjetaSonido({ oir: "/api/m/musica/cama", nombre: "Fondo suave", detalle: "del Studio, sin canción", usar: 'data-usar-musica="cama"', elegida: m.modo === "cama" }),
    tarjetaSonido({ nombre: "Sin fondo", detalle: "la pongo después", usar: 'data-usar-musica="nada"', elegida: m.modo === "nada" }),
    ...m.pistas.map((x) => tarjetaSonido({ oir: `/musica/${encodeURIComponent(x.archivo)}`, nombre: x.titulo, detalle: x.animo.join(", ") || x.artista || "",
      usar: `data-usar-musica="${esc(x.archivo)}"`, elegida: m.modo === x.archivo })),
  ];
  return `<div class="voz-elegir">
      <div class="fila"><span class="etiqueta">Voz</span>
        <span class="${datos.coste_voz ? "coste" : "voz"}">${datos.coste_voz ? `De pago: ≈${datos.coste_voz.toFixed(2).replace(".", ",")} $ este guion` : "Gratis"}</span></div>
      <div class="fila chips-vel"><span class="meta">Velocidad</span>${velocidades}</div>
      <div class="rejilla-audio">${guardadas.join("")}${voces.join("")}</div>
      <label class="boton examinar">Examinar… subir tu voz<input type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac,.aac" id="subir-voz" hidden></label>
      <span class="meta" id="estado-voz"></span>
    </div>
    <div class="voz-elegir">
      <div class="fila"><span class="etiqueta">Música</span></div>
      <div class="rejilla-audio">${musicas.join("")}</div>
      <label class="boton examinar">Examinar… subir música<input type="file" accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac,.aac" id="subir-musica" hidden></label>
      <span class="meta" id="estado-musica"></span>
    </div>`;
}

// un solo reproductor para todas las muestras: ▶ suena, ■ para; al pulsar otra, cambia
const sonando = new Audio();
let botonSonando = null;
function oir(boton) {
  const parar = () => { sonando.pause(); if (botonSonando) { botonSonando.textContent = "▶"; botonSonando.classList.remove("sonando"); } botonSonando = null; };
  if (botonSonando === boton) { parar(); return; }
  if (boton.dataset.pago && !confirm("Escuchar una voz de pago graba una muestra (≈0,01 $) la primera vez. ¿Seguir?")) return;
  parar();
  botonSonando = boton; boton.textContent = "…"; boton.classList.add("sonando");
  sonando.src = boton.dataset.oir;
  // las voces se oyen a la velocidad elegida (sin cambiar el tono), igual que en el montaje
  sonando.playbackRate = boton.closest(".voz-elegir")?.querySelector("[data-velocidad].activo") ? Number(datos.video.voz_velocidad || 1) : 1;
  sonando.preservesPitch = true;
  sonando.onplaying = () => { if (botonSonando === boton) boton.textContent = "■"; };
  sonando.onended = parar;
  sonando.onerror = () => { parar(); aviso("No se pudo escuchar esa muestra."); };
  sonando.play().catch(() => {});
}

// subtítulos del vídeo ya montado: se eligen VIENDO un fotograma y se aplican sin volver a montar
function subsRapidosHTML(v) {
  const s = { activos: true, estilo: "viral", posicion: "abajo", tamano: "normal", ...(v.subtitulos || {}) };
  const grupo = (clave, opciones) => opciones.map(([val, txt]) =>
    `<button class="chip${String(s[clave]) === String(val) ? " activo" : ""}" type="button" data-subs="${clave}" data-valor="${val}">${txt}</button>`).join("");
  return `<div class="textos subs-rapidos"><span class="etiqueta">Subtítulos</span>
    <div class="fila">${grupo("activos", [[true, "Con subtítulos"], [false, "Sin"]])}</div>
    <div class="fila">${grupo("estilo", [["viral", "Viral"], ["cine", "Cine"]])}${grupo("posicion", [["abajo", "Abajo"], ["centro", "Centro"], ["arriba", "Arriba"]])}${grupo("tamano", [["pequeno", "Pequeño"], ["normal", "Normal"], ["grande", "Grande"]])}</div>
    <div class="dos vistas-subs"><img id="vista-subs" alt="Vista previa 16:9"><img id="vista-subs-v" class="vertical-mini" alt="Vista previa 9:16"></div>
    <div class="fila"><button class="primario" type="button" id="aplicar-subs">Aplicar a los 3 formatos</button><span class="meta">Solo rehace los subtítulos: segundos, no el vídeo entero.</span></div>
    <div class="fila"><input class="campo corto-t" id="sub-de" placeholder="Palabra mal"><span>→</span><input class="campo corto-t" id="sub-a" placeholder="Corregida">
      <button class="boton" type="button" id="corregir-sub">Corregir en los subtítulos</button></div>
  </div>`;
}

function pasoFinal(v) {
  const t = v.textos;
  const fotosMini = v.frases.filter((f) => f.clip);
  const descripcion = t ? [t.descripcion, "", ...(t.capitulos || []), "", t.creditos, "", (t.hashtags || []).join(" ")].join("\n") : "";
  return `<section class="paso">
    ${pasoCab(5, "Final", "Voz, planos en alta calidad, subtítulos, logo y música. Luego el Short, los textos y la miniatura.")}
    ${vozMusicaHTML(v)}
    <div class="fila">
      <button class="primario" type="button" id="montar-final" ${v.previa ? "" : "disabled"}>${v.final ? "Volver a montar" : "Montar vídeo final"}</button>
      ${!v.previa ? `<span class="meta">Primero haz la previa (paso 4).</span>` : ""}</div>
    ${v.final ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/final_16x9.mp4?v=${encodeURIComponent(v.final.hecho)}"></video>
    ${calidadHTML(v.calidad?.final)}
    ${v.ia ? `<div class="avisos"><p>Este vídeo lleva escenas generadas con IA: al subirlo a YouTube marca «Contenido alterado o sintético» (lo pide YouTube).</p></div>` : ""}
    ${subsRapidosHTML(v)}
    <div class="fila"><a class="boton" href="/m/${esc(v.id)}/subtitulos.srt" download="${esc(v.titulo)}.srt">Subtítulos .srt para YouTube</a>
      <a class="boton" href="/m/${esc(v.id)}/final_16x9.mp4" download="${esc(v.titulo)}.mp4">Descargar vídeo</a></div>
    <div class="textos"><span class="etiqueta">Proyecto completo</span>
      <p class="meta">Una carpeta ordenada con los 3 vídeos, miniaturas, subtítulos, textos para publicar, guion y voz, y un LÉEME que dice dónde va cada cosa.${v.paquete ? ` Hecha el ${esc(v.paquete.hecho)} · ${esc(v.paquete.carpeta)}` : ""}</p>
      <div class="fila">${v.paquete ? `<a class="boton primario" href="/m/${esc(v.id)}/paquete.zip?v=${encodeURIComponent(v.paquete.hecho)}" download="${esc(v.titulo)} (proyecto).zip">Descargar proyecto (.zip)</a>
        <button class="boton" type="button" id="abrir-paquete">Abrir carpeta</button>` : ""}
        <button class="boton" type="button" id="hacer-paquete">${v.paquete ? "Rehacer carpeta" : "Preparar carpeta del proyecto"}</button>
        <button class="primario" type="button" id="terminar-edicion">Terminar edición ✓</button></div></div>
    <div class="dos">
      <div class="textos"><span class="etiqueta">Short vertical</span>
        <div class="fila"><input class="campo corto-t" id="s-desde" value="${reloj(v.short?.desde ?? 0)}">
          <input class="campo corto-t" id="s-hasta" value="${reloj(v.short?.hasta ?? Math.min(45, v.voz?.duracion || 45))}">
          <button class="boton" type="button" id="hacer-short">${v.short ? "Rehacer Short" : "Sacar Short"}</button></div>
        ${v.short ? `<video class="vertical" controls preload="metadata" src="/m/${esc(v.id)}/short_9x16.mp4?v=${encodeURIComponent(v.actualizado)}"></video>` : `<p class="meta">Elige de qué segundo a qué segundo (máx. 60).</p>`}
      </div>
      <div class="textos"><span class="etiqueta">Miniatura</span>
        <div class="fila"><button class="primario" type="button" id="ver-minis">${(v.miniatura_candidatos || []).length ? "Otras opciones" : "Ver opciones para elegir"}</button></div>
        ${(v.miniatura_candidatos || []).length ? `<div class="minis">${v.miniatura_candidatos.map((c) => `
          <figure class="mini-op"><img src="/m/${esc(v.id)}/${esc(c.archivo)}?v=${encodeURIComponent(v.actualizado)}" alt="${esc(c.texto)}">
            <button class="chip" type="button" data-mini="${esc(c.archivo)}">Usar esta</button></figure>`).join("")}</div>` : ""}
        <details><summary class="meta">Hacerla a mano</summary>
        <input class="campo" id="mini-texto" value="${esc(t?.texto_miniatura || "")}" placeholder="Texto grande: ¿LO COPIÓ?">
        <div class="fila"><select class="campo" id="mini-a" style="flex:1">${fotosMini.map((f) => `<option value="${f.n}">Frase ${f.n}</option>`).join("")}</select>
          <select class="campo" id="mini-b" style="flex:1"><option value="">Una sola imagen</option>${fotosMini.map((f, k) => `<option value="${f.n}" ${k === fotosMini.length - 1 ? "selected" : ""}>Frase ${f.n}</option>`).join("")}</select></div>
        <button class="boton" type="button" id="hacer-mini">${v.miniatura ? "Rehacer miniatura" : "Hacer miniatura"}</button>
        </details>
        ${v.miniatura ? `<span class="meta">La elegida</span><img class="miniatura-hecha" src="/m/${esc(v.id)}/miniatura.jpg?v=${encodeURIComponent(v.actualizado)}" alt="Miniatura">` : ""}
      </div>
    </div>
    <div class="textos"><span class="etiqueta">Textos para publicar</span>
      ${t ? `${t.titulos.map((x, k) => { const r = t.revision?.titulos?.[k]; return `<div class="copiable"><p>${esc(x)}
          ${r ? `<small class="nota-titulo ${r.nota >= 80 ? "ok" : r.nota >= 60 ? "medio" : "bajo"}">${r.nota}/100${t.revision.mejor === k ? " · el mejor" : ""}</small>${r.mal.length ? `<small class="meta">${r.mal.map(esc).join(" · ")}</small>` : ""}` : ""}</p>
          <button class="boton" data-copiar="${esc(x)}">Copiar</button></div>`; }).join("")}
      ${t.revision?.gancho?.mal?.length ? `<p class="meta">Gancho (primera frase): ${t.revision.gancho.mal.map(esc).join(" · ")}</p>` : ""}
      ${t.revision?.aviso_capitulos ? `<p class="meta">${esc(t.revision.aviso_capitulos)}</p>` : ""}
        <div class="copiable"><p>${esc(descripcion)}</p><button class="boton" data-copiar="${esc(descripcion)}">Copiar</button></div>`
        : `<p class="meta">Se escriben solos al montar el vídeo final.</p>`}
      <div class="fila"><button class="boton" type="button" id="rehacer-textos">${t ? "Rehacer textos" : "Escribir textos"}</button></div>
    </div>` : ""}
  </section>`;
}

// La línea de tiempo por pistas (la misma que se guarda junto al vídeo final)
async function pintarLinea() {
  if (!$("linea")) return;
  try {
    const { linea, errores } = await api(`/api/m/linea?id=${encodeURIComponent(datos.video.id)}`);
    const total = linea.duration || 1;
    const nombres = { "video-1": "Vídeo", "graficos-1": "Gráficos", "rotulos-1": "Rótulos", voz: "Voz", musica: "Música" };
    const marcas = Array.from({ length: Math.floor(total / 5) + 1 }, (_, k) => `<i style="left:${(k * 5 / total) * 100}%">${reloj(k * 5)}</i>`).join("");
    $("linea").innerHTML = `
      <div class="linea-cab"><span class="etiqueta">Línea de tiempo · ${reloj(total)}${datos.video.voz ? "" : " (estimada: aún sin voz)"}</span>
        ${errores.length ? `<span class="repe">${errores.length} aviso(s): ${esc(errores[0])}</span>` : ""}</div>
      <div class="regla">${marcas}</div>
      ${linea.tracks.map((t) => `<div class="pista"><span class="pista-nombre">${esc(nombres[t.id] || t.id)}</span><div class="carril">
        ${t.clips.map((c) => {
          const izq = (c.start / total) * 100, ancho = Math.max(0.6, ((c.end - c.start) / total) * 100);
          if (t.type === "video") {
            const [fid, pl] = c.source.split("#");
            // las frases con imagen van como «imagen:<archivo>»: su miniatura es la propia imagen, no un plano
            const fondo = fid.startsWith("imagen:") ? `/m/${esc(datos.video.id)}/imagenes/${esc(fid.slice(7))}` : `/fv/${esc(fid)}/${pad3(pl)}.jpg`;
            return `<button class="clip clip-video ${c.transitionIn ? "con-entrada" : ""}" style="left:${izq}%;width:${ancho}%;background-image:url('${fondo}')"
              data-elegir="${c.id.split("-")[1]}" title="${esc(c.label)} · ${c.in}–${c.out} s"></button>`;
          }
          return `<span class="clip clip-${t.type}" style="left:${izq}%;width:${ancho}%" title="${esc(c.content || c.source || "")}">${esc(c.content || "")}</span>`;
        }).join("")}</div></div>`).join("")}`;
  } catch (e) { $("linea").innerHTML = `<p class="meta">${esc(e.message)}</p>`; }
}

async function pintarBanco() {
  if (!$("banco")) return;
  try {
    const d = await api("/api/m");
    const libres = d.banco.filter((f) => !datos.video.fuentes.includes(f.id));
    $("banco").innerHTML = libres.length ? `<span class="etiqueta">Del banco de clips</span>
      <div class="chips">${libres.map((f) => `<button class="chip" type="button" data-usar="${esc(f.id)}">+ ${esc(f.nombre)} · ${f.planos} planos</button>`).join("")}</div>` : "";
  } catch (_) { /* el banco es un extra */ }
}

const enviar = async (ruta, extra = {}) => {
  try { await api(ruta, { id: datos.video.id, ...extra }); await cargarVideo(datos.video.id); } catch (e) { aviso(e); }
};

function enlazarVideo(p) {
  const v = datos.video;
  $("abrir-carpeta").onclick = () => enviar("/api/m/carpeta");
  if (p === 1) {
    $("guardar-guion").onclick = () => enviar("/api/m/guion", { guion: $("guion").value });
    $("generar-guion").onclick = () => {
      if (v.frases.length && !confirm("Esto reemplaza el guion actual por uno nuevo. ¿Seguir?")) return;
      enviar("/api/m/guion-ia", { opciones: leerOpcionesIA($("guion-ia")) });
    };
  }
  if (p === 2) {
    $("material-form").onsubmit = (ev) => {
      ev.preventDefault();
      enviar("/api/m/fuente", { url: $("m-url").value, desde: segundos($("m-desde").value), hasta: segundos($("m-hasta").value) });
    };
    pintarBanco();
    $("buscar-material").onclick = () => enviar("/api/m/material/buscar");
    document.querySelectorAll("[data-sugerido]").forEach((b) => {
      b.onclick = () => { b.disabled = true; b.textContent = "Añadiendo…"; enviar("/api/m/fuente", { url: b.dataset.sugerido }); };
    });
  }
  if (p === 2) {
    $("escaleta-flow").onclick = async (ev) => {
      ev.target.disabled = true; ev.target.textContent = "Preparando la escaleta…";
      try {
        const r = await api("/api/m/escaleta", { id: datos.video.id });
        $("escaleta-caja").hidden = false;
        $("escaleta-json").value = JSON.stringify(r.escaleta, null, 1);
        const seg = r.escaleta.escenas.reduce((s, e) => s + e.duracion, 0);
        $("escaleta-info").textContent = `${r.escaleta.escenas.length} escenas · ${reloj(seg)} · ${r.escaleta.personajes.length} personajes · ${r.escaleta.ambientes.length} ambientes`;
      } catch (e) { aviso(e); }
      ev.target.disabled = false; ev.target.textContent = "Escaleta para Flow";
    };
    $("copiar-escaleta").onclick = () => navigator.clipboard.writeText($("escaleta-json").value).then(() => { $("copiar-escaleta").textContent = "Copiada"; });
    $("carpeta-flow").onclick = () => api("/api/m/flow/carpeta", {}).catch(aviso);
    seguro("/api/m/flow").then((r) => { if (r?.enlace && $("abrir-flow")) { $("abrir-flow").href = r.enlace; $("abrir-flow").hidden = false; } });
    $("importar-flow").onclick = async (ev) => {
      ev.target.disabled = true; ev.target.textContent = "Importando…";
      try {
        const r = await api("/api/m/importar-flow", { id: datos.video.id });
        aviso(new Error(`Importadas ${r.escenas} escenas de Flow en ${r.frases} frases.`));
        await cargarVideo(datos.video.id);
      } catch (e) { aviso(e); ev.target.disabled = false; ev.target.textContent = "Importar de Flow"; }
    };
  }
  if (p === 3) {
    $("proponer").onclick = () => enviar("/api/m/proponer");
    if ($("planos-escenas")) $("planos-escenas").onclick = () => enviar("/api/m/planos-escenas", { todas: $("escenas-todas").checked });
    $("ver-storyboard").onclick = async () => {
      const w = window.open("about:blank", "_blank");
      try { const r = await api("/api/m/storyboard", { id: datos.video.id }); w.location = `${r.url}?v=${Date.now()}`; }
      catch (e) { w.close(); aviso(e); }
    };
    $("automatico").onclick = () => {
      const coste = datos.coste_voz;
      const pregunta = coste
        ? `La voz ${datos.video.voz_nombre} es de pago: ≈${coste.toFixed(2)} $. ¿Hacerlo todo (vídeo final, Short, textos y miniatura)?`
        : "Se hace todo seguido: vídeo final con voz, subtítulos y música, Short, textos, miniatura y revisión. ¿Seguir?";
      if (confirm(pregunta)) enviar("/api/m/automatico", { pago_ok: !!coste });
    };
    pintarLinea();
  }
  if (p === 4) $("hacer-previa").onclick = () => enviar("/api/m/previa");
  if (p === 5) {
    document.querySelectorAll("[data-oir]").forEach((b) => { b.onclick = () => oir(b); });
    document.querySelectorAll("[data-usar-voz]").forEach((b) => { b.onclick = () => { const [proveedor, nombre] = b.dataset.usarVoz.split("|"); enviar("/api/m/voz", { proveedor, nombre }); }; });
    document.querySelectorAll("[data-voz-guardada]").forEach((b) => { b.onclick = () => enviar("/api/m/voz-guardada", { voz: b.dataset.vozGuardada }); });
    document.querySelectorAll("[data-velocidad]").forEach((b) => { b.onclick = () => {
      // se oye al instante la voz que suena a la nueva velocidad, y queda guardada para el montaje
      datos.video.voz_velocidad = Number(b.dataset.velocidad);
      document.querySelectorAll("[data-velocidad]").forEach((x) => x.classList.toggle("activo", x === b));
      if (botonSonando?.closest(".voz-elegir")) sonando.playbackRate = datos.video.voz_velocidad;
      api("/api/m/velocidad", { id: v.id, velocidad: datos.video.voz_velocidad }).catch(aviso);
    }; });
    document.querySelectorAll("[data-usar-musica]").forEach((b) => { b.onclick = () => enviar("/api/m/musica/elegir", { musica: b.dataset.usarMusica }); });
    const subirAudio = (input, ruta, estado) => {
      input.onchange = async () => {
        const f = input.files[0];
        if (!f) return;
        try {
          await subirVideo(f, v.id, (pc) => { $(estado).textContent = `Subiendo «${f.name}»… ${pc} %`; }, ruta);
          $(estado).textContent = "";
          await cargarVideo(v.id);
        } catch (e) { $(estado).textContent = ""; aviso(e); }
      };
    };
    subirAudio($("subir-voz"), "/api/m/subir-voz", "estado-voz");
    subirAudio($("subir-musica"), "/api/m/subir-musica", "estado-musica");
    $("montar-final").onclick = () => {
      // lo de pago, solo con un sí explícito y el importe delante
      if (datos.coste_voz && !confirm(`La voz ${datos.video.voz_nombre} es de pago: ≈${datos.coste_voz.toFixed(2)} $ por este guion. ¿Montar?`)) return;
      enviar("/api/m/final");
    };
    // subtítulos: la vista previa cambia al pulsar cada opción; «Aplicar» rehace solo los subtítulos
    if ($("vista-subs")) {
      const elegido = { ...(v.subtitulos || {}) };
      const vista = () => {
        const q = new URLSearchParams({ id: v.id, ...Object.fromEntries(Object.entries(elegido).map(([k, x]) => [k, String(x)])) });
        $("vista-subs").src = `/api/m/subs-vista?${q}&formato=16x9`;
        $("vista-subs-v").src = `/api/m/subs-vista?${q}&formato=9x16`;
      };
      document.querySelectorAll("[data-subs]").forEach((b) => { b.onclick = () => {
        elegido[b.dataset.subs] = b.dataset.subs === "activos" ? b.dataset.valor === "true" : b.dataset.valor;
        document.querySelectorAll(`[data-subs="${b.dataset.subs}"]`).forEach((x) => x.classList.toggle("activo", x === b));
        vista();
      }; });
      $("vista-subs").onerror = () => { $("vista-subs").hidden = true; $("vista-subs-v").hidden = true; };
      vista();
      $("aplicar-subs").onclick = () => enviar("/api/m/subtitulos-rapido", { cambios: elegido });
      $("corregir-sub").onclick = () => enviar("/api/m/corregir-subtitulo", { de: $("sub-de").value, a: $("sub-a").value });
    }
    if ($("hacer-paquete")) $("hacer-paquete").onclick = () => enviar("/api/m/paquete");
    if ($("terminar-edicion")) $("terminar-edicion").onclick = () => enviar("/api/m/terminar");
    if ($("abrir-paquete")) $("abrir-paquete").onclick = () => enviar("/api/m/paquete/abrir");
    if ($("ver-minis")) $("ver-minis").onclick = () => enviar("/api/m/miniaturas", { texto: $("mini-texto")?.value || "" });
    document.querySelectorAll("[data-mini]").forEach((b) => { b.onclick = () => enviar("/api/m/miniatura/elegir", { archivo: b.dataset.mini }); });
    if ($("hacer-short")) $("hacer-short").onclick = () => enviar("/api/m/short", { desde: segundos($("s-desde").value), hasta: segundos($("s-hasta").value) });
    if ($("rehacer-textos")) $("rehacer-textos").onclick = () => enviar("/api/m/textos");
    if ($("hacer-mini")) $("hacer-mini").onclick = () => {
      const clip = (n) => v.frases.find((f) => f.n === Number(n))?.clip;
      const fotos = [clip($("mini-a").value), $("mini-b").value ? clip($("mini-b").value) : null].filter(Boolean);
      enviar("/api/m/miniatura", { texto: $("mini-texto").value, fotos });
    };
  }
}

// delegación: lo que se repite por frase, el banco, abrir y nuevo
$("vista").addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-elegir],[data-panel],[data-guardar-panel],[data-quitar-panel],[data-usar],[data-copiar],[data-abrir],[data-nuevo],"
    + "[data-imagen],[data-poner-url],[data-buscar-img],[data-quitar-imagen],[data-elegir-img]");
  if (!el) return;
  // imágenes por frase: enlace, archivo de tu PC o búsqueda en las fuentes del canal
  if (el.dataset.imagen) { const f = document.querySelector(`[data-imagen-form="${el.dataset.imagen}"]`); f.hidden = !f.hidden; return; }
  const credito = (n) => document.querySelector(`[data-icred="${n}"]`)?.value || "";
  if (el.dataset.ponerUrl) {
    const n = Number(el.dataset.ponerUrl);
    return enviar("/api/m/imagen", { n, url: document.querySelector(`[data-iurl="${n}"]`).value, credito: credito(n) });
  }
  if (el.dataset.quitarImagen) return enviar("/api/m/imagen/quitar", { n: Number(el.dataset.quitarImagen) });
  if (el.dataset.elegirImg) {
    const n = Number(el.dataset.n);
    return enviar("/api/m/imagen", { n, url: el.dataset.elegirImg, credito: credito(n) || el.dataset.pagina || "" });
  }
  if (el.dataset.buscarImg) {
    const n = el.dataset.buscarImg, caja = document.querySelector(`[data-iresultados="${n}"]`);
    caja.innerHTML = `<p class="meta">Buscando en tus fuentes…</p>`;
    api("/api/m/imagenes/buscar", { id: datos.video.id, consulta: document.querySelector(`[data-ibuscar="${n}"]`).value })
      .then((r) => {
        caja.innerHTML = r.imagenes.length ? r.imagenes.map((i) => `<button type="button" class="resultado-img" data-n="${n}"
          data-elegir-img="${esc(i.url)}" data-pagina="${esc(i.pagina ? new URL(i.pagina).hostname : "")}" title="${esc(i.descripcion)}">
          <img src="${esc(i.miniatura)}" alt="" loading="lazy"></button>`).join("") : `<p class="meta">No encontré imágenes con eso. Prueba otras palabras o pega un enlace.</p>`;
      }).catch((e) => { caja.innerHTML = ""; aviso(e); });
    return;
  }
  if (el.dataset.nuevo !== undefined) return abrirNuevo();
  if (el.dataset.abrir) { ev.preventDefault(); location.hash = `v=${el.dataset.abrir}`; return; }
  if (el.dataset.elegir) return abrirSelector(Number(el.dataset.elegir));
  if (el.dataset.subir) return enviar("/api/m/mover", { n: Number(el.dataset.subir), direccion: -1 });
  if (el.dataset.bajar) return enviar("/api/m/mover", { n: Number(el.dataset.bajar), direccion: 1 });
  if (el.dataset.quitarClip) return enviar("/api/m/quitar-clip", { n: Number(el.dataset.quitarClip) });
  if (el.dataset.usar) return enviar("/api/m/usar-fuente", { fuente: el.dataset.usar });
  if (el.dataset.copiar !== undefined) {
    navigator.clipboard.writeText(el.dataset.copiar).then(() => { el.textContent = "Copiado"; setTimeout(() => { el.textContent = "Copiar"; }, 1500); });
    return;
  }
  if (el.dataset.panel) { const f = document.querySelector(`[data-panel-form="${el.dataset.panel}"]`); f.hidden = !f.hidden; return; }
  const n = Number(el.dataset.guardarPanel || el.dataset.quitarPanel);
  const panel = el.dataset.quitarPanel ? {} : {
    titulo: document.querySelector(`[data-pt="${n}"]`).value,
    items: document.querySelector(`[data-pi="${n}"]`).value.split("\n").map((x) => x.trim()).filter(Boolean),
    nota: document.querySelector(`[data-pn="${n}"]`).value,
  };
  enviar("/api/m/asignar", { n, panel });
});
$("vista").addEventListener("change", (ev) => {
  const material = ev.target.closest("[data-subir-material]");
  if (material && material.files[0]) { traerArchivo(material.files[0]); return; }
  const archivo = ev.target.closest("[data-ifile]");
  if (archivo && archivo.files[0]) {   // una imagen de tu PC: se manda como texto (base64)
    const n = Number(archivo.dataset.ifile), lector = new FileReader();
    lector.onload = () => enviar("/api/m/imagen", { n, datos: lector.result, credito: document.querySelector(`[data-icred="${n}"]`)?.value || "" });
    lector.readAsDataURL(archivo.files[0]);
    return;
  }
  const r = ev.target.closest("[data-rotulo]");
  if (r) enviar("/api/m/asignar", { n: Number(r.dataset.rotulo), rotulo: r.value });
});

// ============================================================ Elegir plano
function abrirSelector(n) {
  if (!datos) return;
  fraseEligiendo = n;
  const f = datos.video.frases.find((x) => x.n === n);
  if (!datos.video.fuentes.length) return aviso(new Error("Primero añade material en el paso 2."));
  fuenteViendo = f.clip?.fuente || datos.video.fuentes[0];
  $("sel-frase-n").textContent = `FRASE ${n}`;
  $("sel-frase").textContent = f.texto;
  pintarSelector();
  $("selector").hidden = false;
}
function pintarSelector() {
  const usados = new Set(datos.video.frases.filter((f) => f.clip).map((f) => `${f.clip.fuente}#${f.clip.plano}`));
  const actual = datos.video.frases.find((x) => x.n === fraseEligiendo)?.clip;
  $("sel-fuentes").innerHTML = datos.video.fuentes.map((fid) =>
    `<button type="button" class="${fid === fuenteViendo ? "si" : ""}" data-ver-fuente="${esc(fid)}">${esc(datos.fuentes[fid].nombre)}</button>`).join("");
  $("sel-planos").innerHTML = datos.fuentes[fuenteViendo].planos.map((pl) => {
    const clave = `${fuenteViendo}#${pl.n}`, si = actual && `${actual.fuente}#${actual.plano}` === clave;
    return `<button type="button" class="${si ? "si" : usados.has(clave) || pl.pobre ? "usado" : ""}" data-plano="${pl.n}" title="${pl.pobre ? "Oscuro, liso o muy corto" : ""}">
      <img src="/fv/${esc(fuenteViendo)}/${pad3(pl.n)}.jpg" alt="" loading="lazy"><em>${pl.n} · ${(pl.fin - pl.ini).toFixed(1)} s</em></button>`;
  }).join("");
}
$("selector").addEventListener("click", async (ev) => {
  if (ev.target === $("selector") || ev.target.closest("[data-cerrar]")) { $("selector").hidden = true; return; }
  const fu = ev.target.closest("[data-ver-fuente]");
  if (fu) { fuenteViendo = fu.dataset.verFuente; return pintarSelector(); }
  const pl = ev.target.closest("[data-plano]");
  if (pl) {
    $("selector").hidden = true;
    await enviar("/api/m/asignar", { n: fraseEligiendo, fuente: fuenteViendo, plano: Number(pl.dataset.plano) });
  }
});
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") $("selector").hidden = true; });

// ============================================================ Trabajo en marcha
function pintarTrabajo(t) {
  const caja = $("trabajo");
  if (!t || (!t.ocupado && !t.error)) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.classList.toggle("error", !!t.error);
  $("trabajo-fase").textContent = t.error || t.fase || t.nombre || "";
  $("trabajo-pct").textContent = t.ocupado ? `${t.progreso || 0} %` : "";
  $("trabajo-barra").style.width = `${t.ocupado ? t.progreso || 0 : 100}%`;
}

// ============================================================ Rutas
// Planes de suscripción (producto). Precios de ejemplo: Diego los ajusta. Aún sin cobro real (eso llega con el hosting).
async function vistaPlanes() {
  const datosPlanes = await seguro("/api/m/planes");   // calculados en studio4/planes.py desde los costes
  const PLANES = datosPlanes?.planes || [], PRUEBA = datosPlanes?.prueba;
  $("vista").innerHTML = `
    ${cabecera("<em>Planes</em>", "Elige el que te cuadre. Cambias o cancelas cuando quieras.")}
    ${PRUEBA ? `<section class="prueba-plan"><b>Prueba ${PRUEBA.dias} días el plan ${esc(PRUEBA.plan)}, potenciado</b>
      <span class="meta">${PRUEBA.puntos.map(esc).join(" · ")}</span></section>` : ""}
    <div class="planes">
      ${PLANES.map((p) => `
        <article class="plan${p.destacado ? " destacado" : ""}">
          ${p.destacado ? `<span class="plan-cinta">${esc(p.gancho)}</span>` : `<small class="meta">${esc(p.gancho)}</small>`}
          <h2>${esc(p.nombre)}</h2>
          <div class="plan-precio">${esc(p.precio)}</div>
          <ul>${p.puntos.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          <button class="${p.destacado ? "primario" : "boton"}" type="button" data-plan="${esc(p.id)}">Elegir ${esc(p.nombre)}</button>
        </article>`).join("")}
    </div>
    <section class="mantenimiento">
      <span class="etiqueta">Más información · contacto</span>
      <p class="meta">¿Dudas o quieres una demo? Escríbenos.</p>
      <div class="fila"><a class="boton" href="mailto:hola@studio4.app">Escribir un correo</a></div>
    </section>`;
  document.querySelectorAll("[data-plan]").forEach((b) => {
    b.onclick = () => aviso("Los pagos se activan con la versión en internet. De momento esto es una vista previa.");
  });
}

const VISTAS = { inicio: vistaInicio, videos: vistaVideos, biblioteca: vistaBiblioteca, tendencias: vistaTendencias,
  musica: vistaMusica, canal: vistaCanal, herramientas: vistaHerramientas, planes: vistaPlanes };
async function ir() {
  $("trabajo").hidden = true;
  $("selector").hidden = true;
  const m = location.hash.match(/^#v=([\w-]+)(?:\/(\d))?/);
  const vista = m ? "videos" : (location.hash.slice(1) || "inicio");
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("activo", a.dataset.vista === vista));
  seguro("/api/m").then((d) => { $("canal").textContent = d?.canal?.nombre || ""; });
  try {
    if (m) {
      const nuevoVideo = !datos || datos.video.id !== m[1];
      pasoVisto = m[2] ? Number(m[2]) : 0;
      firma = "";
      await cargarVideo(m[1]);
      if (nuevoVideo && !m[2]) { pasoVisto = datos.paso; firma = ""; pintarVideo(); }
    } else {
      datos = null; firma = "";
      await (VISTAS[vista] || vistaInicio)();
    }
    window.scrollTo({ top: 0 });
  } catch (e) { aviso(e); if (m) location.hash = "videos"; }
  const carga = $("carga");
  if (carga) { carga.style.opacity = 0; setTimeout(() => carga.remove(), 300); }
}
window.addEventListener("hashchange", ir);
ir();
// mientras trabaja, se mira cada segundo y medio; si no, cada 6 s (por si terminó algo en otra ventana)
setInterval(() => { if (datos && datos.video.trabajo?.ocupado) cargarVideo(datos.video.id).catch(() => {}); }, 1500);
setInterval(() => { if (datos && !datos.video.trabajo?.ocupado) cargarVideo(datos.video.id).catch(() => {}); }, 6000);
