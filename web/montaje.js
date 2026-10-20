// Studio 4 · panel de montaje: un vídeo 16:9 en 5 pasos (guion → material → montaje → previa → final).
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

let datos = null;          // el vídeo abierto: {video, paso, fuentes}
let firma = "";            // para no repintar si nada cambió (y no borrar lo que estás escribiendo)
let fraseEligiendo = 0, fuenteViendo = "";

// ============================================================ inicio
async function pintarInicio() {
  datos = null; firma = "";
  const d = await api("/api/m");
  $("canal").textContent = d.canal?.nombre || "";
  $("vista").innerHTML = `
    <section class="portada">
      <h1>Tus <em>vídeos</em></h1>
      <p>Un vídeo en 16:9 con material real, en cinco pasos y en orden. De ahí sale el Short.</p>
    </section>
    <form class="nuevo-form" id="nuevo-form" hidden>
      <h2>Vídeo <em>nuevo</em></h2>
      <input class="campo" id="n-titulo" placeholder="Título de trabajo (p. ej. Lo que GTA 6 hereda de The Warriors)" required>
      <textarea class="campo" id="n-guion" placeholder="Pega aquí el guion: solo lo que dirá la voz. Deja una línea en blanco entre bloques: ahí irá la transición."></textarea>
      <div class="fila"><button class="primario" type="submit">Crear vídeo</button><button class="boton" type="button" id="n-cancelar">Cancelar</button></div>
    </form>
    <section class="videos">
      <article class="tarjeta nuevo" id="abrir-nuevo"><span>+</span><b>Nuevo vídeo</b><small>Pega tu guion y empieza</small></article>
      ${d.videos.map((v) => `
        <article class="tarjeta" data-abrir="${esc(v.id)}">
          <b>${esc(v.titulo)}</b>
          <div class="puntos">${[1, 2, 3, 4, 5].map((n) => `<i class="${n < v.paso || v.final ? "si" : ""}"></i>`).join("")}</div>
          <small>${v.final ? "Terminado" : `Paso ${v.paso} de 5`} · ${v.con_clip}/${v.frases} frases con imagen · ${esc(v.creado)}</small>
        </article>`).join("")}
    </section>`;
  $("abrir-nuevo").onclick = () => { $("nuevo-form").hidden = false; $("n-titulo").focus(); };
  $("n-cancelar").onclick = () => { $("nuevo-form").hidden = true; };
  $("nuevo-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await api("/api/m/nuevo", { titulo: $("n-titulo").value, guion: $("n-guion").value });
      location.hash = `v=${r.id}`;
    } catch (e) { aviso(e); }
  };
  document.querySelectorAll("[data-abrir]").forEach((t) => { t.onclick = () => { location.hash = `v=${t.dataset.abrir}`; }; });
}

// ============================================================ un vídeo
async function cargarVideo(id) {
  datos = await api(`/api/m/ver?id=${encodeURIComponent(id)}`);
  const { trabajo, ...resto } = datos.video;
  const nueva = JSON.stringify([resto, Object.keys(datos.fuentes)]);
  pintarTrabajo(trabajo);
  const escribiendo = document.activeElement && $("vista").contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
  if (nueva !== firma && !(escribiendo && firma)) { firma = nueva; pintarVideo(); }
}

function miniaturaDe(f) {
  if (f.panel) return `<span>Panel: ${esc(f.panel.titulo || "texto")}</span>`;
  if (!f.clip) return `<span>Elegir plano</span>`;
  const fu = datos.fuentes[f.clip.fuente];
  const pl = fu?.planos[f.clip.plano - 1];
  return `<img src="/fv/${esc(f.clip.fuente)}/${pad3(f.clip.plano)}.jpg" alt="" loading="lazy"><em>${esc(fu?.nombre || "")} · ${pl ? (pl.fin - pl.ini).toFixed(1) : "?"} s</em>`;
}

function pintarVideo() {
  const v = datos.video, paso = datos.paso;
  const estado = (n) => (n < paso || (n === 5 && v.final) ? "hecho" : n === paso ? "ahora" : "");
  const nombres = ["Guion", "Material", "Montaje", "Previa", "Final"];
  let bloque = -1;
  const frases = v.frases.map((f) => {
    const sep = f.bloque !== bloque ? `<div class="bloque-sep">Bloque ${f.bloque + 1}${f.bloque > 0 ? " · entra con la rejilla" : ""}</div>` : "";
    bloque = f.bloque;
    return `${sep}<div class="frase">
      <button class="miniatura" type="button" data-elegir="${f.n}" title="Elegir el plano de esta frase">${miniaturaDe(f)}</button>
      <div class="cuerpo"><small>FRASE ${f.n}</small><p>${esc(f.texto)}</p>
        <div class="fila">
          <input class="campo rotulo" data-rotulo="${f.n}" value="${esc(f.rotulo || "")}" placeholder="Rótulo (opcional): THE WARRIORS · 2005">
          <button class="boton" type="button" data-panel="${f.n}">${f.panel ? "Editar panel" : "Panel de texto"}</button>
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
  const conClip = v.frases.filter((f) => f.clip || f.panel).length;
  const t = v.textos;
  const fotosMini = v.frases.filter((f) => f.clip);
  $("vista").innerHTML = `
    <a class="volver" data-ir="inicio">← Tus vídeos</a>
    <div class="cabeza"><h1>${esc(v.titulo)}</h1>
      <button class="boton" type="button" id="abrir-carpeta">Abrir carpeta</button></div>
    <nav class="pasos">${nombres.map((n, k) => `<a data-ir-paso="${k + 1}" class="${estado(k + 1)}"><b>${estado(k + 1) === "hecho" ? "✓" : k + 1}</b><span>${n}</span></a>`).join("")}</nav>

    <section class="paso ${estado(1)}" id="p1">
      <div class="paso-cab"><span class="num">1</span><div><h2>Guion</h2>
        <p>${v.frases.length} frases en ${new Set(v.frases.map((f) => f.bloque)).size} bloques. Una línea en blanco separa los bloques.</p></div></div>
      ${v.avisos?.length ? `<div class="avisos">${v.avisos.map((a) => `<p>${esc(a)}</p>`).join("")}</div>` : ""}
      <textarea class="campo" id="guion">${esc(v.guion)}</textarea>
      <div class="fila"><button class="boton" type="button" id="guardar-guion">Guardar cambios del guion</button></div>
    </section>

    <section class="paso ${estado(2)}" id="p2">
      <div class="paso-cab"><span class="num">2</span><div><h2>Material</h2>
        <p>Tráilers oficiales y gameplay sin comentario. Se baja en baja calidad solo para ver los planos; en alta, solo lo que uses.</p></div></div>
      <form class="material-form" id="material-form">
        <input class="campo" id="m-url" placeholder="Enlace del vídeo (YouTube…)" required>
        <input class="campo" id="m-desde" placeholder="Desde (2:33:55)">
        <input class="campo" id="m-hasta" placeholder="Hasta (2:50:33)">
        <button class="primario" type="submit">Añadir</button>
      </form>
      <p class="meta">En un gameplay de horas, pon desde y hasta (el capítulo de la misión): así solo se baja ese tramo.</p>
      <div class="fuentes">${v.fuentes.map((fid) => { const f = datos.fuentes[fid]; return `
        <div class="fuente"><img src="/fv/${esc(fid)}/${pad3((f.planos.find((x) => !x.pobre) || f.planos[0]).n)}.jpg" alt=""><div><b>${esc(f.nombre)}</b>
          <small class="meta">${f.planos.length} planos · ${esc(f.canal || "")}</small></div></div>`; }).join("")}</div>
      <div id="banco"></div>
    </section>

    <section class="paso ${estado(3)}" id="p3">
      <div class="paso-cab"><span class="num">3</span><div><h2>Montaje</h2>
        <p>${conClip} de ${v.frases.length} frases con imagen. Toca una imagen para cambiar el plano.</p></div></div>
      <div class="fila"><button class="primario" type="button" id="proponer" ${v.fuentes.length ? "" : "disabled"}>Proponer planos para las frases vacías</button></div>
      ${frases}
    </section>

    <section class="paso ${estado(4)}" id="p4">
      <div class="paso-cab"><span class="num">4</span><div><h2>Previa</h2>
        <p>En silencio, con los efectos y las transiciones. Gratis: revisa antes de la voz.</p></div></div>
      ${v.previa ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/previa.mp4?v=${encodeURIComponent(v.actualizado)}"></video>` : ""}
      <div class="fila"><button class="primario" type="button" id="hacer-previa" ${conClip === v.frases.length ? "" : "disabled"}>${v.previa ? "Rehacer previa" : "Hacer previa"}</button>
        ${conClip < v.frases.length ? `<span class="meta">Faltan ${v.frases.length - conClip} frases por elegir.</span>` : ""}</div>
    </section>

    <section class="paso ${estado(5)}" id="p5">
      <div class="paso-cab"><span class="num">5</span><div><h2>Final</h2>
        <p>Voz, planos en alta calidad, subtítulos, logo y música. Luego el Short, los textos y la miniatura.</p></div></div>
      <div class="fila"><span class="voz">Voz: ${esc(v.voz_nombre)} · gratis</span>
        <button class="primario" type="button" id="montar-final" ${v.previa ? "" : "disabled"}>${v.final ? "Volver a montar" : "Montar vídeo final"}</button></div>
      ${v.final ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/final_16x9.mp4?v=${encodeURIComponent(v.final.hecho)}"></video>
      <div class="dos">
        <div class="textos"><span class="etiqueta">Short vertical</span>
          <div class="fila"><input class="campo" style="max-width:120px" id="s-desde" value="${reloj(v.short?.desde ?? 0)}">
            <input class="campo" style="max-width:120px" id="s-hasta" value="${reloj(v.short?.hasta ?? Math.min(45, v.voz?.duracion || 45))}">
            <button class="boton" type="button" id="hacer-short">${v.short ? "Rehacer Short" : "Sacar Short"}</button></div>
          ${v.short ? `<video class="vertical" controls preload="metadata" src="/m/${esc(v.id)}/short_9x16.mp4?v=${encodeURIComponent(v.actualizado)}"></video>` : `<p class="meta">Elige de qué segundo a qué segundo (máx. 60).</p>`}
        </div>
        <div class="textos"><span class="etiqueta">Miniatura</span>
          <input class="campo" id="mini-texto" value="${esc(t?.texto_miniatura || "")}" placeholder="Texto grande: ¿LO COPIÓ?">
          <div class="fila"><select class="campo" id="mini-a" style="flex:1">${fotosMini.map((f) => `<option value="${f.n}">Frase ${f.n}</option>`).join("")}</select>
            <select class="campo" id="mini-b" style="flex:1"><option value="">Una sola imagen</option>${fotosMini.map((f, k) => `<option value="${f.n}" ${k === fotosMini.length - 1 ? "selected" : ""}>Frase ${f.n}</option>`).join("")}</select></div>
          <button class="boton" type="button" id="hacer-mini">${v.miniatura ? "Rehacer miniatura" : "Hacer miniatura"}</button>
          ${v.miniatura ? `<img class="miniatura-hecha" src="/m/${esc(v.id)}/miniatura.jpg?v=${encodeURIComponent(v.actualizado)}" alt="Miniatura">` : ""}
        </div>
      </div>
      <div class="textos"><span class="etiqueta">Textos para publicar</span>
        ${t ? `${t.titulos.map((x) => `<div class="copiable"><p>${esc(x)}</p><button class="boton" data-copiar="${esc(x)}">Copiar</button></div>`).join("")}
          <div class="copiable"><p>${esc([t.descripcion, "", ...(t.capitulos || []), "", t.creditos, "", t.hashtags.join(" ")].join("\n"))}</p>
            <button class="boton" data-copiar="${esc([t.descripcion, "", ...(t.capitulos || []), "", t.creditos, "", t.hashtags.join(" ")].join("\n"))}">Copiar</button></div>`
          : `<p class="meta">Se escriben solos al montar el vídeo final.</p>`}
        <div class="fila"><button class="boton" type="button" id="rehacer-textos">${t ? "Rehacer textos" : "Escribir textos"}</button></div>
      </div>` : ""}
    </section>`;
  pintarBanco();
  enlazarVideo();
  if (!pintarVideo.hecho) {   // al abrir un vídeo, directo a su paso
    pintarVideo.hecho = true;
    document.getElementById(`p${paso}`)?.scrollIntoView({ block: "start" });
  }
}

async function pintarBanco() {
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

function enlazarVideo() {
  const v = datos.video;
  $("guardar-guion").onclick = () => enviar("/api/m/guion", { guion: $("guion").value });
  $("abrir-carpeta").onclick = () => enviar("/api/m/carpeta");
  $("material-form").onsubmit = (ev) => {
    ev.preventDefault();
    enviar("/api/m/fuente", { url: $("m-url").value, desde: segundos($("m-desde").value), hasta: segundos($("m-hasta").value) });
  };
  $("proponer").onclick = () => enviar("/api/m/proponer");
  $("hacer-previa").onclick = () => enviar("/api/m/previa");
  $("montar-final").onclick = () => enviar("/api/m/final");
  if ($("hacer-short")) $("hacer-short").onclick = () => enviar("/api/m/short", { desde: segundos($("s-desde").value), hasta: segundos($("s-hasta").value) });
  if ($("rehacer-textos")) $("rehacer-textos").onclick = () => enviar("/api/m/textos");
  if ($("hacer-mini")) $("hacer-mini").onclick = () => {
    const clip = (n) => v.frases.find((f) => f.n === Number(n))?.clip;
    const fotos = [clip($("mini-a").value), $("mini-b").value ? clip($("mini-b").value) : null].filter(Boolean);
    enviar("/api/m/miniatura", { texto: $("mini-texto").value, fotos });
  };
}

// delegación: lo que se repite por frase y el banco
$("vista").addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-elegir],[data-panel],[data-guardar-panel],[data-quitar-panel],[data-usar],[data-copiar],[data-ir],[data-ir-paso]");
  if (!el) return;
  if (el.dataset.irPaso) { $(`p${el.dataset.irPaso}`).scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  if (el.dataset.ir) { location.hash = ""; return; }
  if (el.dataset.elegir) return abrirSelector(Number(el.dataset.elegir));
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
  const r = ev.target.closest("[data-rotulo]");
  if (r) enviar("/api/m/asignar", { n: Number(r.dataset.rotulo), rotulo: r.value });
});
document.querySelector(".marca").addEventListener("click", (ev) => { ev.preventDefault(); location.hash = ""; });

// ============================================================ elegir plano
function abrirSelector(n) {
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

// ============================================================ trabajo en marcha
function pintarTrabajo(t) {
  const caja = $("trabajo");
  if (!t || (!t.ocupado && !t.error)) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.classList.toggle("error", !!t.error);
  $("trabajo-fase").textContent = t.error || t.fase || t.nombre || "";
  $("trabajo-pct").textContent = t.ocupado ? `${t.progreso || 0} %` : "";
  $("trabajo-barra").style.width = `${t.ocupado ? t.progreso || 0 : 100}%`;
}

// ============================================================ ciclo
async function ir() {
  $("trabajo").hidden = true;
  const m = location.hash.match(/^#v=([\w-]+)/);
  try {
    if (m) { pintarVideo.hecho = false; firma = ""; await cargarVideo(m[1]); }
    else await pintarInicio();
  } catch (e) { aviso(e); if (m) location.hash = ""; }
  const carga = $("carga");
  if (carga) { carga.style.opacity = 0; setTimeout(() => carga.remove(), 300); }
}
window.addEventListener("hashchange", ir);
ir();
// mientras trabaja, se mira cada segundo y medio; si no, cada 6 s (por si terminó algo en otra ventana)
setInterval(() => { if (datos && datos.video.trabajo?.ocupado) cargarVideo(datos.video.id).catch(() => {}); }, 1500);
setInterval(() => { if (datos && !datos.video.trabajo?.ocupado) cargarVideo(datos.video.id).catch(() => {}); }, 6000);
