// STUDIO 4 · panel. Sondea /api/estado cada 2 s y solo repinta lo que ha cambiado
// (así un vídeo que estás viendo no se reinicia cuando llega una toma nueva).
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
  // Sin producción abierta, el aviso va bajo la caja de inicio; con producción, en su tarjeta.
  const caja = estado?.produccion ? $("t-error") : $("aviso-panel");
  caja.textContent = texto; caja.hidden = false;
  setTimeout(() => { caja.hidden = true; }, 9000);
}

// Repinta un bloque solo si sus datos cambiaron.
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

// --- Flow: botón de vinculación ---------------------------------------------------------------
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

function pintarFlow(d) {
  const b = $("flow-boton");
  b.href = "/flow/emparejar#c=" + encodeURIComponent(d.codigo);
  const conectada = d.extension.conectada;
  b.className = `pildora ${conectada ? "ok" : "aviso"}`;
  b.innerHTML = `<span class="piloto"></span><span>${conectada ? "Flow conectado" : "Flow: conectar"}</span>`;
  b.title = conectada ? "La extensión está enviando lo que generas en Flow" : "Abre la página de vinculación con la extensión";
}
$("flow-renovar").addEventListener("click", async () => {
  try {
    const d = await api("/api/flow/renovar", {});
    window.open("/flow/emparejar#c=" + encodeURIComponent(d.codigo), "_blank");
  } catch (e) { aviso(e); }
});

// --- Nueva producción --------------------------------------------------------------------------
const form = $("nuevo");
form.segundos.addEventListener("input", () => { $("seg-valor").textContent = `${form.segundos.value} s`; });
form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const datos = Object.fromEntries(new FormData(form));
  datos.segundos = Number(datos.segundos);
  try {
    form.querySelector("button").disabled = true;
    await api("/api/producciones", datos);
    form.tema.value = "";
    await refrescar();
  } catch (e) { aviso(e); } finally { form.querySelector("button").disabled = false; }
});

function pintarLista(lista) {
  const activa = estado.produccion?.id;
  $("lista").innerHTML = lista.length ? lista.map((p) => `
    <button type="button" data-id="${esc(p.id)}" class="${p.id === activa ? "activa" : ""}">
      <b>${esc(p.titulo || p.tema)}</b><small>${esc(p.creado.slice(0, 16))} · ${esc(p.formato)} · ${esc(p.estado)}</small>
    </button>`).join("") : `<span class="meta faint">Todavía no hay ninguna: escribe un tema arriba.</span>`;
}
$("lista").addEventListener("click", async (ev) => {
  const li = ev.target.closest("[data-id]");
  if (!li) return;
  try { await api("/api/activar", { id: li.dataset.id }); await refrescar(); } catch (e) { aviso(e); }
});

function pintarConsumo(c) {
  const flow = c.consumo["Google Flow"]?.total || 0;
  $("consumo-txt").textContent = `${flow} tomas Flow · 0 $`;
  $("consumo").title = [...Object.entries(c.consumo).map(([k, v]) => `${k}: ${v.total} ${v.unidad}`),
    `ElevenLabs disponible: ${c.restantes} créditos`].join("\n");
}

// --- Producción activa -------------------------------------------------------------------------
function pasoActual(p) {
  if (!p.guion) return "guion";
  if (!p.escenas.length) return "escenas";
  if (!p.voz) return "voz";
  if (p.escenas.some((e) => e.elegida === null)) return "flow";
  return "render";
}

function pintarCabecera(p) {
  $("p-titulo").textContent = p.titulo || p.tema;
  $("p-meta").textContent = `${p.tema} · ${estado.opciones.formatos[p.formato] || p.formato} · ${p.estilo} · ${p.segundos}s`;
  const orden = ["guion", "escenas", "voz", "flow", "render"];
  const ahora = p.estado === "terminado" ? "fin" : pasoActual(p);
  document.querySelectorAll("#pasos li").forEach((li) => {
    const i = orden.indexOf(li.dataset.p);
    const hechoVoz = li.dataset.p === "voz" && p.voz;
    li.className = ahora === "fin" || hechoVoz || i < orden.indexOf(ahora) ? "hecho" : li.dataset.p === ahora ? "ahora" : "";
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
  $("t-error").hidden = !t.error;
  $("t-error").textContent = t.error || "";
}

function urlMedio(archivo) { return `/media/${estado.produccion.id}/${archivo}`; }

function pintarEscenas(datos) {
  const { escenas, activa } = datos;
  const listas = escenas.filter((e) => e.elegida !== null).length;
  $("e-cuenta").textContent = escenas.length ? `· ${listas}/${escenas.length} con clip` : "";
  $("escenas").innerHTML = escenas.map((e) => {
    const tomas = e.tomas.map((t, i) => `
      <div class="toma ${i === e.elegida ? "elegida" : ""}" data-orden="${e.orden}" data-toma="${i}" title="Usar esta toma">
        ${t.tipo === "video"
          ? `<video src="${urlMedio(t.archivo)}#t=0.5" muted preload="metadata"></video>`
          : `<img src="${urlMedio(t.archivo)}" alt="">`}
        <span>${t.tipo === "video" ? `▶ ${t.duracion}s` : "img"}</span>
        <button class="borrar" data-borrar="${i}" data-orden="${e.orden}" title="Borrar toma">✕</button>
      </div>`).join("");
    const etiqueta = e.elegida !== null ? `<span class="etiqueta ok">✓ clip listo</span>`
      : e.orden === activa ? `<span class="etiqueta ahora">genera esta en Flow</span>` : `<span class="etiqueta">pendiente</span>`;
    return `
      <article class="escena ${e.orden === activa ? "activa" : ""} ${e.elegida !== null ? "lista-ok" : ""}">
        <div class="escena-cab"><span class="escena-num">Escena ${e.orden}</span>${etiqueta}</div>
        <p class="voz-txt">«${esc(e.texto_voz)}»</p>
        <pre class="prompt">${esc(e.prompt_flow)}</pre>
        ${tomas ? `<div class="tomas">${tomas}</div>` : ""}
        <div class="acciones">
          <button class="boton" data-copiar-prompt="${e.orden}">Copiar prompt</button>
          ${e.orden !== activa ? `<button class="boton" data-activar="${e.orden}">Generar esta ahora</button>` : ""}
          <label class="boton">Subir clip<input type="file" accept="video/*,image/*" data-subir="${e.orden}"></label>
        </div>
      </article>`;
  }).join("");
}

$("escenas").addEventListener("click", async (ev) => {
  const t = ev.target;
  const p = estado.produccion;
  try {
    if (t.dataset.copiarPrompt) {
      const n = Number(t.dataset.copiarPrompt);
      await navigator.clipboard.writeText(p.escenas[n - 1].prompt_flow);
      t.textContent = "Copiado ✓";
      setTimeout(() => { t.textContent = "Copiar prompt"; }, 1500);
      await api("/api/escena/activa", { escena: n });   // la extensión empieza a recoger para esta escena
    } else if (t.dataset.activar) {
      await api("/api/escena/activa", { escena: Number(t.dataset.activar) });
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

// Previsualización: pasar el ratón por una toma la reproduce.
$("escenas").addEventListener("mouseover", (ev) => ev.target.closest(".toma")?.querySelector("video")?.play().catch(() => {}));
$("escenas").addEventListener("mouseout", (ev) => ev.target.closest(".toma")?.querySelector("video")?.pause());

function pintarVoz(d) {
  const { voz, proveedor, opciones } = d;
  llenarSelect($("v-proveedor"), opciones, proveedor);
  const audio = $("v-audio");
  if (voz) {
    const src = `${urlMedio(voz.archivo)}?v=${encodeURIComponent(voz.generada || "")}`;
    if (audio.dataset.src !== src) { audio.src = src; audio.dataset.src = src; }
    $("v-info").textContent = `${voz.duracion.toFixed(1)} s · ${opciones[voz.proveedor] || voz.proveedor} · ${voz.escenas.length} cortes de escena`;
  } else {
    audio.removeAttribute("src"); audio.dataset.src = "";
    $("v-info").textContent = "Aún sin voz: se genera sola al terminar el plan de escenas.";
  }
}
$("v-rehacer").addEventListener("click", async () => {
  try { await api("/api/voz", { proveedor: $("v-proveedor").value }); await refrescar(); } catch (e) { aviso(e); }
});

function pintarSubtitulos(d) {
  const s = d.subtitulos;
  llenarSelect($("s-paleta"), d.paletas, s.paleta);
  $("s-activos").checked = s.activos; $("s-gancho").checked = s.gancho;
  $("s-posicion").value = s.posicion; $("s-tamano").value = s.tamano;
}
["s-activos", "s-gancho", "s-paleta", "s-posicion", "s-tamano"].forEach((id) => $(id).addEventListener("change", async () => {
  try {
    await api("/api/subtitulos", {
      activos: $("s-activos").checked, gancho: $("s-gancho").checked,
      paleta: $("s-paleta").value, posicion: $("s-posicion").value, tamano: $("s-tamano").value,
    });
  } catch (e) { aviso(e); }
}));

function pintarRender(d) {
  const p = d.p;
  const faltan = p.escenas.filter((e) => e.elegida === null).map((e) => e.orden);
  const motivos = [];
  if (!p.escenas.length) motivos.push("Esperando el plan de escenas.");
  if (!p.voz) motivos.push("Falta la voz.");
  if (faltan.length) motivos.push(`Faltan clips en las escenas ${faltan.join(", ")}.`);
  $("r-falta").textContent = motivos.join(" ") || (p.final ? `Renderizado ${p.final.renderizado}. Puedes volver a renderizar tras cambiar tomas o subtítulos.` : "Todo listo.");
  $("r-boton").disabled = motivos.length > 0 || p.trabajo.ocupado;
  $("r-final").hidden = !p.final;
  if (p.final) {
    const src = `${urlMedio(p.final.archivo)}?v=${encodeURIComponent(p.final.renderizado)}`;
    if ($("r-video").dataset.src !== src) { $("r-video").src = src; $("r-video").dataset.src = src; }
    $("r-descargar").href = src;
    $("r-descargar").download = `${(p.titulo || "studio4").replace(/[^\w\- ]+/g, "").trim() || "studio4"}.mp4`;
  }
}
$("r-boton").addEventListener("click", async () => {
  try { await api("/api/render", {}); await refrescar(); } catch (e) { aviso(e); }
});

function pintarPublicar(p) {
  $("pub-titulo").textContent = p.titulo;
  $("pub-desc").textContent = [p.descripcion, (p.hashtags || []).join(" ")].filter(Boolean).join("\n\n");
  $("pub-guion").textContent = p.guion;
  const b = p.biblia || {};
  $("pub-biblia").innerHTML = b.escenario_en ? `
    <p><b>Escenario:</b> ${esc(b.escenario_en)}</p><p><b>Luz:</b> ${esc(b.luz_en)}</p><p><b>Paleta:</b> ${esc(b.paleta_en)}</p>
    ${(b.personajes || []).map((x) => `<p><b>${esc(x.nombre)}:</b> ${esc(x.aspecto_en)}</p>`).join("")}` : "";
}
document.addEventListener("click", async (ev) => {
  const id = ev.target.dataset?.copiar;
  if (!id) return;
  await navigator.clipboard.writeText($(id).textContent);
  ev.target.textContent = "Copiado ✓";
  setTimeout(() => { ev.target.textContent = "Copiar"; }, 1500);
});

// --- Ciclo -------------------------------------------------------------------------------------
async function refrescar() {
  const [d, lista] = await Promise.all([api("/api/estado"), api("/api/producciones")]);
  estado = d;
  const o = d.opciones;
  llenarSelect($("op-estilo"), Object.fromEntries(o.estilos.map((k) => [k, k])));
  llenarSelect($("op-voz"), o.voces);
  $("aviso-gemini").hidden = !o.salud.length;
  $("aviso-gemini").textContent = o.salud.join(" ");
  pintarFlow(d);
  siCambia("registro-flow", d.extension, pintarRegistroFlow);
  siCambia("lista", { lista, activa: d.produccion?.id }, () => pintarLista(lista));
  siCambia("consumo", { consumo: d.consumo, restantes: d.elevenlabs_restantes }, pintarConsumo);

  const p = d.produccion;
  $("prod").hidden = !p;
  if (!p) return;
  siCambia("cabecera", { p: { ...p, trabajo: null } }, () => pintarCabecera(p));
  siCambia("trabajo", p.trabajo, pintarTrabajo);
  siCambia("escenas", { id: p.id, escenas: p.escenas, activa: p.escena_activa }, pintarEscenas);
  siCambia("voz", { id: p.id, voz: p.voz, proveedor: p.proveedor_voz, opciones: o.voces }, pintarVoz);
  siCambia("subtitulos", { id: p.id, subtitulos: p.subtitulos, paletas: o.paletas }, pintarSubtitulos);
  siCambia("render", { p }, pintarRender);
  siCambia("publicar", { id: p.id, t: p.titulo, d: p.descripcion, g: p.guion, b: p.biblia }, () => pintarPublicar(p));
}

refrescar().catch(aviso);
setInterval(() => refrescar().catch(() => {}), 2000);
