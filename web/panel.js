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

// --- Nueva producción: desde una idea (investigación + DeepSeek) o con tu guion --------------------
const form = $("nuevo");
const ESTADOS = { investigando: "investigando", escribiendo: "escribiendo guion", guion_listo: "guion por revisar",
  escenas: "creando escenas", rodando: "en Flow", renderizando: "renderizando", terminado: "terminado", error: "error" };
const VERSION = { corto: "Corto", largo: "Largo", propio: "Tu guion" };

function modo() { return document.querySelector('input[name="modo"]:checked').value; }
function pintarModo() {
  const propio = modo() === "propio";
  form.idea.hidden = propio;
  form.guion_propio.hidden = !propio;
  document.querySelector(".solo-idea").hidden = propio;
  document.querySelector(".solo-propio").hidden = !propio;
  $("nuevo-txt").textContent = propio ? "Usar mi guion" : "Investigar y escribir";
  $("nuevo-explica").textContent = propio
    ? "Tu texto se respeta tal cual. Lo revisas y, al aprobarlo, Gemini lo convierte en escenas para Flow."
    : `Gemini investiga el tema (Google o Wikipedia, con fuentes), ${estado?.opciones.deepseek_ok ? "DeepSeek" : "Gemini (falta la clave de DeepSeek)"} escribe el guion con esos datos y tú lo revisas antes de pasar a escenas.`;
}
document.querySelectorAll('input[name="modo"]').forEach((r) => r.addEventListener("change", pintarModo));
form.s_corto.addEventListener("input", () => { $("s-corto-v").textContent = `${form.s_corto.value} s`; });
form.s_largo.addEventListener("input", () => { $("s-largo-v").textContent = `${form.s_largo.value} min`; });

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const propio = modo() === "propio";
  const versiones = ["corto", "largo"].filter((v) => form[`v_${v}`].checked);
  const datos = {
    idea: form.idea.value, estilo: form.estilo.value, voz: form.voz.value,
    versiones, segundos: { corto: Number(form.s_corto.value), largo: Number(form.s_largo.value) * 60 },
    guion_propio: propio ? form.guion_propio.value : "", formato: form.formato.value,
  };
  if (!propio && !versiones.length) return alertaError("Marca al menos una versión: corto o largo.");
  try {
    form.querySelector("button[type=submit]").disabled = true;
    await api("/api/producciones", datos);
    form.idea.value = ""; form.guion_propio.value = "";
    await refrescar();
    location.hash = "#guion-sec";
  } catch (e) { aviso(e); } finally { form.querySelector("button[type=submit]").disabled = false; }
});

function pintarLista(lista) {
  const activa = estado.produccion?.id;
  $("lista").innerHTML = lista.length ? lista.map((p) => `
    <button type="button" data-id="${esc(p.id)}" class="${p.id === activa ? "activa" : ""}">
      <b>${esc(p.titulo || p.tema)}</b><small>${p.version ? `${esc(VERSION[p.version] || p.version)} · ` : ""}${esc(p.creado.slice(0, 16))} · ${esc(ESTADOS[p.estado] || p.estado)}</small>
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
  if (!p.guion || !p.guion_aprobado) return "guion";
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

// Flow en una ventana a la derecha (Google no deja meter Flow dentro de otra página).
$("abrir-flow").addEventListener("click", () => {
  const ancho = Math.round(screen.availWidth / 2);
  window.open("https://labs.google/fx/tools/flow", "studio4-flow",
    `popup,left=${screen.availLeft + ancho},top=${screen.availTop},width=${ancho},height=${screen.availHeight}`);
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

// --- Guion -----------------------------------------------------------------------------------
function pintarGuion(d) {
  const { p } = d;
  const ocupado = p.trabajo.ocupado;
  const aprobado = p.guion_aprobado;
  $("g-autor").textContent = p.autor_guion ? `escrito por ${p.autor_guion}` : "";
  $("g-autor").hidden = !p.autor_guion;
  const palabras = p.guion ? p.guion.split(/\s+/).length : 0;
  $("g-meta").textContent = p.guion
    ? `${palabras} palabras · ~${Math.round(palabras / 2.4)} s de voz${p.version ? ` · ${VERSION[p.version] || p.version}` : ""}`
    : ocupado ? "Investigando y escribiendo… (suele tardar menos de un minuto)" : "Aún sin guion.";
  // Corto y largo de la misma idea: se cambia de uno a otro con estas pestañas.
  const hermanas = p.hermanas || [];
  $("g-versiones").hidden = hermanas.length < 2;
  $("g-versiones").innerHTML = hermanas.map((h) =>
    `<label><input type="radio" name="g-version" value="${esc(h.id)}" ${h.id === p.id ? "checked" : ""}>${esc(VERSION[h.version] || h.version)}</label>`).join("");
  const area = $("g-texto");
  if (document.activeElement !== area || area.dataset.pid !== p.id) area.value = p.guion || "";
  area.dataset.pid = p.id;
  area.readOnly = aprobado || ocupado;
  $("g-ia").hidden = !(p.ia_detectada || []).length || aprobado;
  $("g-ia").innerHTML = `<span class="meta">Suena a IA, conviene cambiarlo:</span>` +
    (p.ia_detectada || []).map((f) => `<span class="aviso-ia">«${esc(f)}»</span>`).join("");
  $("g-ganchos").hidden = aprobado || !(p.ganchos || []).length;
  $("g-ganchos").innerHTML = `<span class="meta">Otros ganchos (clic para usarlo como primera frase):</span>` +
    (p.ganchos || []).map((g) => `<button class="chip-alt" data-gancho="${esc(g)}">${esc(g)}</button>`).join("");
  $("g-aprobar").hidden = false;
  $("g-aprobar").disabled = ocupado || !p.guion;
  $("g-aprobar").firstChild.textContent = aprobado ? "Rehacer escenas con este guion " : "Aprobar guion y crear escenas ";
  $("g-guardar").hidden = aprobado;
  $("g-guardar").disabled = ocupado;
  $("g-otra").hidden = aprobado || !["corto", "largo"].includes(p.version);
  $("g-otra").disabled = ocupado;
  $("g-estado").textContent = aprobado ? "Aprobado: las escenas salen de este texto." : "";
  const inv = p.investigacion;
  $("g-investigacion").hidden = !inv;
  if (inv) {
    $("g-dossier").textContent = inv.dossier;
    $("g-fuentes-n").textContent = `· ${inv.metodo || "Google"} · ${inv.fuentes.length} fuentes`;
    $("g-fuentes").innerHTML = inv.fuentes.map((f) =>
      `<li><a href="${esc(f.url)}" target="_blank" rel="noreferrer">${esc(f.titulo)}</a></li>`).join("");
  }
}

$("g-versiones").addEventListener("change", async (ev) => {
  try { await api("/api/activar", { id: ev.target.value }); await refrescar(); } catch (e) { aviso(e); }
});
$("g-ganchos").addEventListener("click", (ev) => {
  const g = ev.target.dataset?.gancho;
  if (!g) return;
  const area = $("g-texto");
  // Sustituye la primera frase del guion por el gancho elegido.
  area.value = area.value.replace(/^[\s\S]*?[.!?…](\s|$)/, `${g.replace(/\s*$/, "")} `);
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
  if (conClips && !confirm("Esta producción ya tiene clips de Flow. Rehacer las escenas los descarta. ¿Seguir?")) return;
  try {
    await api("/api/guion/aprobar", { guion: p.guion_aprobado ? p.guion : $("g-texto").value, forzar: conClips });
    await refrescar();
  } catch (e) { aviso(e); }
});

function pintarAvisos(avisos) {
  $("avisos").hidden = !avisos.length;
  $("avisos").innerHTML = avisos.map((a) =>
    `<div><b>Difícil de filmar:</b> «${esc(a.frase)}» — ${esc(a.problema)}<br><span class="meta">Sugerencia: ${esc(a.sugerencia)}</span></div>`).join("");
}

// --- Miniaturas y entregas --------------------------------------------------------------------
const PLATAFORMA_VIDEO = { youtube: "YouTube", shorts: "Shorts", reels: "Reels", feed: "Feed" };
const nombreArchivo = (p, sufijo, ext) =>
  `${(p.titulo || "studio4").replace(/[^\p{L}\p{N}\- ]+/gu, "").trim() || "studio4"} - ${sufijo}.${ext}`;

function pintarMiniaturas(d) {
  const { p, plataformas } = d;
  const m = p.miniaturas;
  const sinClips = !p.escenas.some((e) => e.elegida !== null);
  $("m-generar").disabled = sinClips || p.trabajo.ocupado;
  $("m-generar").firstChild.textContent = m ? "Volver a generar " : "Generar miniaturas ";
  $("m-info").textContent = sinClips
    ? "Las miniaturas salen de tus clips: elige al menos una toma en Escenas (o sube una imagen tras generar)."
    : "Gemini elige el fotograma con más gancho de tus clips y escribe el texto. Todo se compone en tu PC.";
  $("m-cuerpo").hidden = !m;
  if (!m) return;

  const v = encodeURIComponent(m.version || "");
  $("m-entregas").innerHTML = Object.entries(m.salidas || {}).map(([pl, archivo]) => {
    const clase = pl === "youtube" ? "h" : pl === "feed" ? "c" : "v";
    const video = p.final ? `<a class="boton" href="${urlMedio(p.final.archivo)}" download="${esc(nombreArchivo(p, PLATAFORMA_VIDEO[pl], "mp4"))}">Vídeo MP4</a>` : "";
    return `<div class="entrega ${clase}">
      <b>${esc(plataformas[pl] || pl)}</b>
      <img src="${urlMedio(archivo)}?v=${v}" alt="${esc(plataformas[pl] || pl)}">
      <div class="fila">
        <a class="boton" href="${urlMedio(archivo)}?v=${v}" download="${esc(nombreArchivo(p, `miniatura ${PLATAFORMA_VIDEO[pl]}`, "jpg"))}">Miniatura JPG</a>
        ${video}
      </div>
    </div>`;
  }).join("") + (p.final ? "" : `<p class="meta">El vídeo aparecerá aquí para descargar cuando lo renderices.</p>`);

  const enfocado = document.activeElement;
  if (enfocado !== $("m-texto")) $("m-texto").value = m.texto || "";
  if (enfocado !== $("m-resalte")) $("m-resalte").value = m.resalte || "";
  $("m-alternativas").innerHTML = (m.alternativas || []).map((t) =>
    `<button class="chip-alt" data-alt="${esc(t)}">${esc(t)}</button>`).join("");
  $("m-candidatos").innerHTML = m.candidatos.map((c, i) => `
    <div class="toma ${i === m.elegido ? "elegida" : ""}" data-cand="${i}" title="${c.escena ? `Escena ${c.escena}` : c.origen === "flow" ? "Generada en Flow" : "Subida"}">
      <img src="${urlMedio(c.archivo)}" alt="" loading="lazy"><span>${c.escena ? `esc. ${c.escena}` : c.origen === "flow" ? "Flow" : "subida"}</span>
    </div>`).join("");
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
  const t = ev.target.dataset?.alt;
  if (!t) return;
  $("m-texto").value = t;
  const palabras = t.split(/\s+/);
  $("m-resalte").value = palabras.reduce((a, b) => (b.length > a.length ? b : a), "");
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
    await api("/api/subir?escena=0", undefined, {
      method: "POST", headers: { "Content-Type": archivo.type || "image/jpeg" }, body: archivo,
    });
    await refrescar();
  } catch (e) { aviso(e); } finally { ev.target.value = ""; }
});

// --- Ciclo -------------------------------------------------------------------------------------
async function refrescar() {
  const [d, lista] = await Promise.all([api("/api/estado"), api("/api/producciones")]);
  estado = d;
  const o = d.opciones;
  llenarSelect($("op-estilo"), Object.fromEntries(o.estilos.map((k) => [k, k])));
  llenarSelect($("op-voz"), o.voces);
  if (!firmas.modo) { firmas.modo = 1; pintarModo(); }
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
  siCambia("guion", { p: { ...p, escenas: p.escenas.map((e) => e.tomas.length) } }, () => pintarGuion({ p }));
  siCambia("avisos", p.avisos || [], pintarAvisos);
  siCambia("escenas", { id: p.id, escenas: p.escenas, activa: p.escena_activa }, pintarEscenas);
  siCambia("voz", { id: p.id, voz: p.voz, proveedor: p.proveedor_voz, opciones: o.voces }, pintarVoz);
  siCambia("subtitulos", { id: p.id, subtitulos: p.subtitulos, paletas: o.paletas }, pintarSubtitulos);
  siCambia("render", { p }, pintarRender);
  siCambia("miniaturas", { p, plataformas: o.plataformas }, pintarMiniaturas);
  siCambia("publicar", { id: p.id, t: p.titulo, d: p.descripcion, g: p.guion, b: p.biblia }, () => pintarPublicar(p));
}

refrescar().catch(aviso);
setInterval(() => refrescar().catch(() => {}), 2000);
