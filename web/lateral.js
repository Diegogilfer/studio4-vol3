// STUDIO #4 junto a Flow: la escena que toca, su prompt y lo que va llegando, en el panel lateral de Chrome.
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const firmas = {};
try { document.documentElement.dataset.tema = localStorage.getItem("studio4-tema") || "cristal"; } catch (_) { /* tema por defecto */ }
let estado = null;
let sesion = null;

async function api(ruta, datos) {
  const r = await fetch(ruta, datos === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
}
function siCambia(clave, datos, pintar) {
  const f = JSON.stringify(datos);
  if (firmas[clave] !== f) { firmas[clave] = f; pintar(datos); }
}
function mostrarError(texto) {
  $("l-error").textContent = texto; $("l-error").hidden = false;
  setTimeout(() => { $("l-error").hidden = true; }, 8000);
}
const urlMedio = (archivo) => `/media/${estado.produccion.id}/${archivo}`;

// El portapapeles dentro de un iframe del panel lateral puede estar bloqueado: plan B con execCommand.
async function copiarTexto(texto) {
  try { await navigator.clipboard.writeText(texto); return true; } catch (_) { /* plan B */ }
  const area = document.createElement("textarea");
  area.value = texto; area.style.cssText = "position:fixed;opacity:0";
  document.body.appendChild(area); area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}

function pintarAhora(s) {
  $("l-ahora").hidden = !s?.viva;
  if (!s?.viva) return;
  const sig = s.siguiente;
  const miniatura = sig.escena === 0;
  const e = s.escenas[sig.escena - 1];
  $("l-ahora-tit").textContent = miniatura ? "Imagen para la miniatura" : `Escena ${sig.escena} de ${s.total}`;
  $("l-ahora-est").textContent = miniatura ? "genera una imagen" : e?.video ? "ya tiene vídeo" : "genera esta en Flow";
  $("l-voz").textContent = miniatura ? sig.voz : `«${sig.voz}»`;
  $("l-prompt").textContent = sig.prompt;
  $("l-aspecto").textContent = miniatura ? `Flow en ${s.aspecto}` : `Haz ${sig.tipo === "imagen" ? "una imagen" : "un vídeo"} · ${s.aspecto}`;
  $("l-ref").hidden = !sig.referencia;
  if (sig.referencia && $("l-ref-img").dataset.src !== sig.referencia) {
    $("l-ref-img").src = sig.referencia; $("l-ref-img").dataset.src = sig.referencia;
  }
}

function pintarEscenas(d) {
  const { p } = d;
  const listas = p.escenas.filter((e) => e.elegida !== null).length;
  $("l-cuenta").textContent = `· ${listas}/${p.escenas.length} con clip`;
  $("l-escenas").innerHTML = p.escenas.map((e) => {
    const activa = p.recoger_para !== "miniatura" && e.orden === p.escena_activa;
    const tomas = e.tomas.slice(-3).map((t, k) => {
      const i = e.tomas.length - Math.min(3, e.tomas.length) + k;
      return `<div class="toma ${i === e.elegida ? "elegida" : ""}" data-orden="${e.orden}" data-toma="${i}" title="Usar esta toma">
        ${t.tipo === "video" ? `<video src="${urlMedio(t.archivo)}#t=0.5" muted preload="metadata"></video>` : `<img src="${urlMedio(t.archivo)}" alt="">`}</div>`;
    }).join("");
    return `<li data-escena="${e.orden}" class="${activa ? "activa" : ""} ${e.elegida !== null ? "ok" : ""}">
      <span class="l-num">${e.orden}</span>
      <span class="l-txt">${esc(e.texto_voz)}</span>
      <span class="l-tomas">${tomas}</span></li>`;
  }).join("");
}

function pintarCabecera(d) {
  const p = d.produccion;
  $("l-vacio").hidden = !!p;
  $("l-titulo").textContent = p ? p.titulo || p.tema : "STUDIO #4";
  $("l-meta").textContent = p ? `${p.formato} · ${p.estado}` : "";
  const ext = d.extension;
  $("l-flow").className = `pildora ${ext.conectada ? "ok" : "aviso"}`;
  $("l-flow").lastElementChild.textContent = "Flow";
  $("l-flow").title = ext.conectada ? "La extensión está conectada con Flow" : "Sin conexión: abre Google Flow con la extensión cargada";
  $("l-vieja").hidden = !ext.desactualizada;
  const t = p?.trabajo || {};
  $("l-trabajo").hidden = !t.ocupado;
  $("l-fase").textContent = t.fase || "";
  $("l-pct").textContent = `${t.progreso || 0}%`;
  $("l-barra").style.width = `${t.progreso || 0}%`;
  if (t.error) mostrarError(t.error);
  const faltan = p ? p.escenas.filter((e) => e.elegida === null).length : 1;
  $("l-render").disabled = !p || !p.voz || faltan > 0 || t.ocupado;
  $("l-render").textContent = p?.final ? "Volver a renderizar" : faltan ? `Faltan ${faltan} clips para renderizar` : "Renderizar vídeo";
  $("l-eventos").innerHTML = (ext.eventos || []).map((e) =>
    `<li class="${esc(e.tipo)}"><span>${esc(e.t)}</span><b>${esc(e.tipo)}</b><span>${esc(e.detalle)}</span></li>`).join("");
}

$("l-copiar").addEventListener("click", async () => {
  if (!sesion?.viva) return;
  const sig = sesion.siguiente;
  try {
    // Marcar la escena arma la extensión: lo que genere Flow a partir de ahora va a esta escena.
    if (sig.escena === 0) await api("/api/miniaturas/flow", {});
    else await api("/api/escena/activa", { escena: sig.escena });
    const ok = await copiarTexto(sig.prompt);
    $("l-copiar").textContent = ok ? "Copiado: pégalo en Flow" : "Selecciona y copia el prompt";
    setTimeout(() => { $("l-copiar").textContent = "Copiar prompt"; }, 2500);
  } catch (e) { mostrarError(e.message); }
});

$("l-copiar-ref").addEventListener("click", async () => {
  try {
    const bmp = await createImageBitmap(await (await fetch($("l-ref-img").dataset.src)).blob());
    const lienzo = document.createElement("canvas");
    lienzo.width = bmp.width; lienzo.height = bmp.height;
    lienzo.getContext("2d").drawImage(bmp, 0, 0);
    const png = await new Promise((ok) => lienzo.toBlob(ok, "image/png"));
    await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
    $("l-copiar-ref").textContent = "Copiada: Ctrl+V en Flow";
  } catch (_) {
    $("l-copiar-ref").textContent = "No se pudo: arrástrala a Flow";
  }
  setTimeout(() => { $("l-copiar-ref").textContent = "Copiar imagen inicial"; }, 2500);
});

$("l-escenas").addEventListener("click", async (ev) => {
  try {
    const toma = ev.target.closest(".toma");
    if (toma) {
      await api("/api/escena", { orden: Number(toma.dataset.orden), elegida: Number(toma.dataset.toma) });
    } else {
      const li = ev.target.closest("li[data-escena]");
      if (li) await api("/api/escena/activa", { escena: Number(li.dataset.escena) });
    }
    await refrescar();
  } catch (e) { mostrarError(e.message); }
});

$("l-render").addEventListener("click", async () => {
  try { await api("/api/render", {}); await refrescar(); } catch (e) { mostrarError(e.message); }
});

async function refrescar() {
  const [d, s] = await Promise.all([api("/api/estado"), api("/api/sesion-flow")]);
  estado = d;
  sesion = s;
  siCambia("cab", { p: d.produccion && { ...d.produccion, escenas: d.produccion.escenas.map((e) => e.elegida) }, ext: d.extension }, () => pintarCabecera(d));
  siCambia("ahora", s, pintarAhora);
  if (d.produccion) siCambia("escenas", { p: d.produccion }, pintarEscenas);
}

refrescar().catch((e) => mostrarError(`STUDIO no responde: ${e.message}`));
setInterval(() => refrescar().catch(() => {}), 2000);
