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
const num = (n) => Number(n || 0).toLocaleString("es");
const corto = (n) => n >= 1e6 ? `${(n / 1e6).toFixed(1).replace(".", ",")} M` : n >= 1e3 ? `${(n / 1e3).toFixed(1).replace(".", ",")} K` : String(n || 0);
const seguro = async (ruta) => { try { return await api(ruta); } catch (_) { return null; } };
let temasAbiertos = new Set();

async function pintarInicio() {
  datos = null; firma = "";
  const [m, panel, ideasDia, bib, tend] = await Promise.all([api("/api/m"), seguro("/api/panel"), seguro("/api/ideas/diarias"),
    seguro("/api/biblioteca"), seguro("/api/tendencias")]);
  $("canal").textContent = m.canal?.nombre || "";
  const activo = panel?.canales.find((c) => c.canal.id === panel.activo) || null;
  $("vista").innerHTML = `
    ${pintarCanal(activo, panel)}
    ${pintarIdeas(ideasDia)}
    <section class="bloque-inicio">
      <div class="seccion-cab"><h2>Tus <em>vídeos</em></h2><p class="meta">En 16:9 con material real, cinco pasos. De ahí sale el Short.</p></div>
      <form class="nuevo-form" id="nuevo-form" hidden>
        <input class="campo" id="n-titulo" placeholder="Título de trabajo" required>
        <textarea class="campo" id="n-guion" placeholder="Pega aquí el guion: solo lo que dirá la voz. Deja una línea en blanco entre bloques: ahí irá la transición."></textarea>
        <div class="fila"><button class="primario" type="submit">Crear vídeo</button><button class="boton" type="button" id="n-cancelar">Cancelar</button></div>
      </form>
      <div class="videos">
        <article class="tarjeta nuevo" id="abrir-nuevo"><span>+</span><b>Nuevo vídeo</b><small>Pega tu guion y empieza</small></article>
        ${m.videos.map((v) => `
          <article class="tarjeta" data-abrir="${esc(v.id)}">
            <b>${esc(v.titulo)}</b>
            <div class="puntos">${[1, 2, 3, 4, 5].map((n) => `<i class="${n < v.paso || v.final ? "si" : ""}"></i>`).join("")}</div>
            <small>${v.final ? "Terminado" : `Paso ${v.paso} de 5`} · ${v.con_clip}/${v.frases} frases con imagen · ${esc(v.creado)}</small>
          </article>`).join("")}
      </div>
    </section>
    ${pintarBiblioteca(bib, new Set(m.videos.map((v) => v.id)))}
    ${pintarTendencias(tend)}
    <section class="bloque-inicio">
      <div class="seccion-cab"><h2>Más <em>herramientas</em></h2></div>
      <div class="herramientas">
        <a class="herramienta" href="/clasico#url"><b>Desde URL</b><small>Un vídeo tuyo por enlace → editado en los 3 formatos</small></a>
        <a class="herramienta" href="/youtube" target="_blank"><b>Vista YouTube</b><small>Tus vídeos y miniaturas como se verán publicados</small></a>
        <a class="herramienta" href="/clasico#canales"><b>Ajustes de canales</b><small>Redes, fuentes de confianza, voz y estilo</small></a>
        <a class="herramienta" href="/clasico"><b>Panel clásico</b><small>Todo lo de antes, tal cual</small></a>
      </div>
    </section>`;
  pintarMantenimiento();
  enlazarInicio(ideasDia, bib);
}

function pintarCanal(c, panel) {
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

function pintarBiblioteca(d, mios = new Set()) {
  const guiones = d?.guiones || [];
  if (!guiones.length) return "";
  const temas = new Map();
  guiones.forEach((g) => { if (!temas.has(g.codigo)) temas.set(g.codigo, []); temas.get(g.codigo).push(g); });
  return `<section class="bloque-inicio">
    <div class="seccion-cab"><h2>Biblioteca de <em>guiones</em></h2>
      <p class="meta">${temas.size} temas de Agron. El largo se monta en 16:9 y de él salen los Shorts.</p></div>
    <div class="temas">${[...temas].map(([codigo, gs]) => {
      const largo = gs.find((g) => g.tipo === "largo") || gs[0];
      const repe = gs.some((g) => g.parecido_a?.length);
      return `<article class="tema ${mios.has(largo.producido) ? "hecho" : ""}">
        <span class="tema-cod">${esc(codigo)}</span>
        <div><b>${esc(largo.titulo || largo.guion.slice(0, 70))}</b>
          <small>${largo.palabras} palabras · ${gs.length - 1} cortos${largo.producido && !mios.has(largo.producido) ? " · ya empezado en el panel clásico" : ""}${repe ? ` · <span class="repe">algún corto se parece a otro tema</span>` : ""}</small></div>
        ${mios.has(largo.producido) ? `<button class="boton" type="button" data-abrir="${esc(largo.producido)}">Abrir</button>`
          : `<button class="primario" type="button" data-bib="${esc(largo.id)}">${largo.producido ? "Crear en 16:9" : "Crear vídeo"}</button>`}
      </article>`; }).join("")}</div></section>`;
}

function pintarTendencias(t) {
  const i = t?.datos?.informe;
  return `<section class="bloque-inicio">
    <div class="seccion-cab"><h2><em>Tendencias</em> de tu nicho</h2>
      <p class="meta">${t?.datos ? `Informe del ${esc(t.datos.fecha.slice(0, 10))}${t.caducado ? " · ya es viejo" : ""}` : "Aún no hay informe."}</p></div>
    ${i ? `<div class="tendencias">
      <p class="resumen">${esc(i.resumen)}</p>
      <div class="tend-col"><span class="etiqueta">Nichos que crecen</span>
        ${(i.nichos || []).slice(0, 4).map((n) => `<div class="tend-item"><b>${esc(n.nombre)}</b><small>${esc((n.por_que || "").slice(0, 160))}</small></div>`).join("")}</div>
      <div class="tend-col"><span class="etiqueta">Consejos de hoy</span>
        ${(i.consejos || []).slice(0, 4).map((c) => `<div class="tend-item"><small>${esc(c)}</small></div>`).join("")}
        <span class="etiqueta">Evita</span>${(i.evitar || []).slice(0, 2).map((c) => `<div class="tend-item"><small>${esc(c)}</small></div>`).join("")}</div>
    </div>` : ""}
    <div class="fila"><button class="boton" type="button" id="act-tendencias" ${t?.ocupado ? "disabled" : ""}>${t?.ocupado ? esc(t.fase || "Analizando…") : "Actualizar tendencias"}</button>
      <button class="boton" type="button" id="ver-vivo">Lo que más crece esta semana</button></div>
    <div id="vivo"></div></section>`;
}

function enlazarInicio(ideasDia, bib) {
  $("abrir-nuevo").onclick = () => { $("nuevo-form").hidden = false; $("n-titulo").focus(); };
  $("n-cancelar").onclick = () => { $("nuevo-form").hidden = true; };
  $("nuevo-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try { location.hash = `v=${(await api("/api/m/nuevo", { titulo: $("n-titulo").value, guion: $("n-guion").value })).id}`; } catch (e) { aviso(e); }
  };
  document.querySelectorAll("[data-abrir]").forEach((t) => { t.onclick = () => { location.hash = `v=${t.dataset.abrir}`; }; });
  document.querySelectorAll("[data-bib]").forEach((b) => { b.onclick = async () => {
    b.disabled = true;
    try { location.hash = `v=${(await api("/api/m/desde-biblioteca", { item: b.dataset.bib })).id}`; } catch (e) { aviso(e); b.disabled = false; }
  }; });
  document.querySelectorAll("[data-idea]").forEach((b) => { b.onclick = async () => {
    b.disabled = true; b.textContent = "Investigando…";
    try { location.hash = `v=${(await api("/api/m/desde-idea", { n: Number(b.dataset.idea) })).id}`; } catch (e) { aviso(e); b.disabled = false; }
  }; });
  if ($("cambiar-canal")) $("cambiar-canal").onchange = async (ev) => {
    if (!ev.target.value) return;
    try { await api("/api/canales/activar", { id: ev.target.value }); pintarInicio(); } catch (e) { aviso(e); }
  };
  $("act-tendencias").onclick = async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Analizando tu nicho…";
    try { await api("/api/tendencias", {}); setTimeout(pintarInicio, 4000); } catch (e) { aviso(e); }
  };
  $("ver-vivo").onclick = async (ev) => {
    ev.target.disabled = true; ev.target.textContent = "Buscando…";
    try {
      const d = await api("/api/ideas/vivo");
      $("vivo").innerHTML = `<div class="vivo">${d.videos.map((v) => `<a class="vivo-item" href="${esc(v.url)}" target="_blank" rel="noopener">
        <b>${esc(v.titulo)}</b><small>${esc(v.canal)} · ${corto(v.vistas_hora)} vistas/hora · ${corto(v.vistas)} vistas</small></a>`).join("")}</div>`;
      ev.target.textContent = "Lo que más crece esta semana";
    } catch (e) { aviso(e); ev.target.disabled = false; ev.target.textContent = "Lo que más crece esta semana"; }
  };
}

// Mantenimiento: espacio en disco y descargador al día (sin sorpresas a mitad de un vídeo)
const mb = (b) => b > 1e9 ? `${(b / 1e9).toFixed(1).replace(".", ",")} GB` : `${Math.round(b / 1e6)} MB`;
async function pintarMantenimiento() {
  try {
    const m = await api("/api/m/mantenimiento");
    const caja = document.createElement("section");
    caja.className = "mantenimiento";
    caja.innerHTML = `<span class="etiqueta">Mantenimiento</span>
      <div class="fila"><span class="meta">Vídeos ${mb(m.espacio.montajes)} · banco de clips ${mb(m.espacio.banco)}${m.espacio.papelera ? ` · papelera del panel clásico ${mb(m.espacio.papelera)}` : ""}</span>
        ${m.espacio.liberable > 50e6 ? `<button class="boton" id="liberar">Liberar ${mb(m.espacio.liberable)} de temporales</button>` : ""}</div>
      <div class="fila"><span class="meta">Descargador ${esc(m.descargador.version)}${m.descargador.viejo ? ` · tiene ${m.descargador.dias} días: conviene actualizarlo` : " · al día"}</span>
        ${m.descargador.viejo ? `<button class="boton" id="actualizar-dl">Actualizar descargador</button>` : ""}</div>`;
    $("vista").appendChild(caja);
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
      ${!v.frases.length && v.trabajo?.ocupado ? `<p class="meta">Studio está investigando y escribiendo el guion: aparecerá aquí al terminar.</p>` : ""}
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
