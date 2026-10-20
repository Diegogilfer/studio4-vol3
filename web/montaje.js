// Studio 4 · panel: seis pantallas (Inicio, Vídeos, Biblioteca, Tendencias, Canal, Herramientas) y, dentro de cada
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
    <small>${v.final ? "Terminado" : `Paso ${v.paso} de 5`} · ${v.con_clip}/${v.frases} frases con imagen · ${esc(v.creado)}</small>
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
    <div id="i-canal"><section class="canal-hero cargando"><div class="canal-logo"></div><div class="canal-datos"><h1>${esc(m.canal?.nombre || "")}</h1>
      <p class="meta">Leyendo tu canal en YouTube…</p></div></section></div>
    <div id="i-ideas"></div>
    <section class="bloque-inicio">
      <div class="seccion-cab fila-entre"><h2>Sigue con <em>tus vídeos</em></h2><a class="boton" href="#videos">Ver todos</a></div>
      <div class="videos">
        <article class="tarjeta nuevo" data-nuevo><span>+</span><b>Nuevo vídeo</b><small>Pega tu guion y empieza</small></article>
        ${m.videos.slice(0, 5).map(tarjetaVideo).join("")}
      </div>
    </section>`;
  seguro("/api/ideas/diarias").then((d) => { if ($("i-ideas")) { $("i-ideas").innerHTML = pintarIdeas(d); enlazarIdeas(); } });
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
      <article class="tarjeta nuevo" data-nuevo><span>+</span><b>Nuevo vídeo</b><small>Pega tu guion y empieza</small></article>
      ${m.videos.map(tarjetaVideo).join("")}
    </div>`;
  $("n-cancelar").onclick = () => { $("nuevo-form").hidden = true; };
  $("nuevo-form").onsubmit = async (ev) => {
    ev.preventDefault();
    try { location.hash = `v=${(await api("/api/m/nuevo", { titulo: $("n-titulo").value, guion: $("n-guion").value })).id}`; } catch (e) { aviso(e); }
  };
  if (sessionStorage.getItem("s4-nuevo")) { sessionStorage.removeItem("s4-nuevo"); abrirNuevo(); }
}
function abrirNuevo() {
  if (!$("nuevo-form")) { sessionStorage.setItem("s4-nuevo", "1"); location.hash = "videos"; return; }
  $("nuevo-form").hidden = false; $("n-titulo").focus();
}

// ============================================================ Biblioteca
async function vistaBiblioteca() {
  const [m, d] = await Promise.all([api("/api/m"), seguro("/api/biblioteca")]);
  const mios = new Set(m.videos.map((v) => v.id));
  const guiones = d?.guiones || [];
  const temas = new Map();
  guiones.forEach((g) => { if (!temas.has(g.codigo)) temas.set(g.codigo, []); temas.get(g.codigo).push(g); });
  $("vista").innerHTML = `
    ${cabecera("Biblioteca de <em>guiones</em>", `${temas.size} temas · ${guiones.length} guiones. El largo se monta en 16:9 y de él salen los Shorts.`)}
    ${!temas.size ? `<p class="meta">Aún no hay guiones: pégalos en el panel clásico › Crear › Biblioteca.</p>` : ""}
    <div class="temas">${[...temas].map(([codigo, gs]) => {
      const largo = gs.find((g) => g.tipo === "largo") || gs[0];
      const cortos = gs.filter((g) => g !== largo);
      const repe = gs.some((g) => g.parecido_a?.length);
      return `<details class="tema-caja ${mios.has(largo.producido) ? "hecho" : ""}">
        <summary class="tema">
          <span class="tema-cod">${esc(codigo)}</span>
          <div><b>${esc(largo.titulo || largo.guion.slice(0, 70))}</b>
            <small>${largo.palabras} palabras · ${cortos.length} cortos${largo.producido && !mios.has(largo.producido) ? " · empezado en el panel clásico" : ""}${repe ? ` · <span class="repe">algún corto se parece a otro tema</span>` : ""}</small></div>
          ${mios.has(largo.producido) ? `<button class="boton" type="button" data-abrir="${esc(largo.producido)}">Abrir</button>`
            : `<button class="primario" type="button" data-bib="${esc(largo.id)}">Crear en 16:9</button>`}
        </summary>
        <div class="tema-cuerpo">
          <p class="guion-previo">${esc(largo.guion.slice(0, 420))}${largo.guion.length > 420 ? "…" : ""}</p>
          ${cortos.length ? `<span class="etiqueta">Cortos de este tema</span>
            ${cortos.map((g) => `<div class="corto-item"><b>${esc(g.etiqueta)}</b><span>${esc(g.titulo || g.guion.slice(0, 80))}</span>
              ${g.parecido_a?.length ? `<small class="repe">se parece a ${esc(g.parecido_a.join(", "))}</small>` : ""}</div>`).join("")}` : ""}
        </div>
      </details>`; }).join("")}</div>`;
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
    ${cabecera("Tus <em>canales</em>", "Estadísticas públicas de YouTube y lo hecho en Studio. Los ajustes (redes, fuentes, voz) siguen en el panel clásico.")}
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
      </section>`; }).join("")}
    <a class="boton" href="/clasico#canales">Ajustes de canales (panel clásico)</a>`;
  document.querySelectorAll("[data-activar]").forEach((b) => { b.onclick = async () => {
    try { await api("/api/canales/activar", { id: b.dataset.activar }); ir(); } catch (e) { aviso(e); }
  }; });
}

// ============================================================ Herramientas
async function vistaHerramientas() {
  $("vista").innerHTML = `
    ${cabecera("<em>Herramientas</em>", "Lo que todavía vive en el panel clásico y el mantenimiento del estudio.")}
    <div class="herramientas">
      <a class="herramienta" href="/clasico#url"><svg><use href="#i-enlace"/></svg><b>Desde URL</b><small>Un vídeo tuyo por enlace → editado en los 3 formatos</small></a>
      <a class="herramienta" href="/youtube" target="_blank"><svg><use href="#i-yt"/></svg><b>Vista YouTube</b><small>Tus vídeos y miniaturas como se verán publicados</small></a>
      <a class="herramienta" href="/clasico#crear"><svg><use href="#i-crear"/></svg><b>Pegar guiones de Agron</b><small>Biblioteca y plan del mes (panel clásico)</small></a>
      <a class="herramienta" href="/clasico"><svg><use href="#i-render"/></svg><b>Panel clásico</b><small>Todo lo de antes, tal cual</small></a>
    </div>
    <div id="mantenimiento"></div>`;
  try {
    const m = await api("/api/m/mantenimiento");
    $("mantenimiento").innerHTML = `<section class="mantenimiento"><span class="etiqueta">Mantenimiento</span>
      <div class="fila"><span class="meta">Vídeos ${mb(m.espacio.montajes)} · banco de clips ${mb(m.espacio.banco)}${m.espacio.papelera ? ` · papelera del panel clásico ${mb(m.espacio.papelera)}` : ""}</span>
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

// ============================================================ Un vídeo, paso a paso
async function cargarVideo(id) {
  datos = await api(`/api/m/ver?id=${encodeURIComponent(id)}`);
  const { trabajo, ...resto } = datos.video;
  const nueva = JSON.stringify([resto, Object.keys(datos.fuentes), pasoVisto]);
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

const NOMBRES = ["Guion", "Material", "Montaje", "Previa", "Final"];
function pintarVideo() {
  const v = datos.video, paso = datos.paso;
  const p = pasoVisto || paso;
  const estado = (n) => (n < paso || (n === 5 && v.final) ? "hecho" : n === paso ? "toca" : "");
  const conClip = v.frases.filter((f) => f.clip || f.panel).length;
  $("vista").innerHTML = `
    <a class="volver" href="#videos">← Tus vídeos</a>
    <div class="cabeza"><h1>${esc(v.titulo)}</h1>
      <button class="boton" type="button" id="abrir-carpeta">Abrir carpeta</button></div>
    <nav class="pasos">${NOMBRES.map((n, k) => `<a href="#v=${esc(v.id)}/${k + 1}" class="${estado(k + 1)} ${p === k + 1 ? "visto" : ""}">
      <b>${estado(k + 1) === "hecho" ? "✓" : k + 1}</b><span>${n}</span></a>`).join("")}</nav>
    ${[pasoGuion, pasoMaterial, pasoMontaje, pasoPrevia, pasoFinal][p - 1](v, conClip)}
    <div class="navegar">
      ${p > 1 ? `<a class="boton" href="#v=${esc(v.id)}/${p - 1}">← ${NOMBRES[p - 2]}</a>` : "<span></span>"}
      ${p < 5 ? `<a class="primario" href="#v=${esc(v.id)}/${p + 1}">${NOMBRES[p]} →</a>` : ""}
    </div>`;
  enlazarVideo(p);
}

const pasoCab = (n, titulo, texto) => `<div class="paso-cab"><span class="num">${n}</span><div><h2>${titulo}</h2><p>${texto}</p></div></div>`;

function pasoGuion(v) {
  return `<section class="paso">
    ${pasoCab(1, "Guion", `${v.frases.length} frases en ${new Set(v.frases.map((f) => f.bloque)).size} bloques. Una línea en blanco separa los bloques: ahí entra la rejilla.`)}
    ${v.avisos?.length ? `<div class="avisos">${v.avisos.map((a) => `<p>${esc(a)}</p>`).join("")}</div>` : ""}
    ${!v.frases.length && v.trabajo?.ocupado ? `<p class="meta">Studio está investigando y escribiendo el guion: aparecerá aquí al terminar.</p>` : ""}
    <textarea class="campo guion" id="guion">${esc(v.guion)}</textarea>
    <div class="fila"><button class="boton" type="button" id="guardar-guion">Guardar cambios del guion</button></div>
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
    <p class="meta">En un gameplay de horas, pon desde y hasta (el capítulo de la misión): así solo se baja ese tramo.</p>
    <div class="fuentes">${v.fuentes.map((fid) => { const f = datos.fuentes[fid]; return `
      <div class="fuente"><img src="/fv/${esc(fid)}/${pad3((f.planos.find((x) => !x.pobre) || f.planos[0]).n)}.jpg" alt=""><div><b>${esc(f.nombre)}</b>
        <small class="meta">${f.planos.length} planos · ${esc(f.canal || "")}</small></div></div>`; }).join("")}</div>
    <div id="banco"></div>
  </section>`;
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
    <div class="fila"><button class="primario" type="button" id="proponer" ${v.fuentes.length ? "" : "disabled"}>Proponer planos para las frases vacías</button></div>
    <div class="linea" id="linea"><p class="meta">Cargando la línea de tiempo…</p></div>
    ${frases}
  </section>`;
}

function pasoPrevia(v, conClip) {
  return `<section class="paso">
    ${pasoCab(4, "Previa", "En silencio, con los efectos y las transiciones. Gratis: revísala antes de la voz.")}
    ${v.previa ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/previa.mp4?v=${encodeURIComponent(v.actualizado)}"></video>` : `<div class="pantalla vacia">Aún no hay previa</div>`}
    <div class="fila"><button class="primario" type="button" id="hacer-previa" ${conClip === v.frases.length && v.frases.length ? "" : "disabled"}>${v.previa ? "Rehacer previa" : "Hacer previa"}</button>
      ${conClip < v.frases.length ? `<span class="meta">Faltan ${v.frases.length - conClip} frases por elegir (paso 3).</span>` : ""}</div>
  </section>`;
}

function pasoFinal(v) {
  const t = v.textos;
  const fotosMini = v.frases.filter((f) => f.clip);
  const descripcion = t ? [t.descripcion, "", ...(t.capitulos || []), "", t.creditos, "", (t.hashtags || []).join(" ")].join("\n") : "";
  return `<section class="paso">
    ${pasoCab(5, "Final", "Voz, planos en alta calidad, subtítulos, logo y música. Luego el Short, los textos y la miniatura.")}
    <div class="fila"><span class="voz">Voz: ${esc(v.voz_nombre)} · gratis</span>
      <button class="primario" type="button" id="montar-final" ${v.previa ? "" : "disabled"}>${v.final ? "Volver a montar" : "Montar vídeo final"}</button>
      ${!v.previa ? `<span class="meta">Primero haz la previa (paso 4).</span>` : ""}</div>
    ${v.final ? `<video class="pantalla" controls preload="metadata" src="/m/${esc(v.id)}/final_16x9.mp4?v=${encodeURIComponent(v.final.hecho)}"></video>
    <div class="dos">
      <div class="textos"><span class="etiqueta">Short vertical</span>
        <div class="fila"><input class="campo corto-t" id="s-desde" value="${reloj(v.short?.desde ?? 0)}">
          <input class="campo corto-t" id="s-hasta" value="${reloj(v.short?.hasta ?? Math.min(45, v.voz?.duracion || 45))}">
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
            return `<button class="clip clip-video ${c.transitionIn ? "con-entrada" : ""}" style="left:${izq}%;width:${ancho}%;background-image:url('/fv/${esc(fid)}/${pad3(pl)}.jpg')"
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
  if (p === 1) $("guardar-guion").onclick = () => enviar("/api/m/guion", { guion: $("guion").value });
  if (p === 2) {
    $("material-form").onsubmit = (ev) => {
      ev.preventDefault();
      enviar("/api/m/fuente", { url: $("m-url").value, desde: segundos($("m-desde").value), hasta: segundos($("m-hasta").value) });
    };
    pintarBanco();
  }
  if (p === 3) { $("proponer").onclick = () => enviar("/api/m/proponer"); pintarLinea(); }
  if (p === 4) $("hacer-previa").onclick = () => enviar("/api/m/previa");
  if (p === 5) {
    $("montar-final").onclick = () => enviar("/api/m/final");
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
  const el = ev.target.closest("[data-elegir],[data-panel],[data-guardar-panel],[data-quitar-panel],[data-usar],[data-copiar],[data-abrir],[data-nuevo]");
  if (!el) return;
  if (el.dataset.nuevo !== undefined) return abrirNuevo();
  if (el.dataset.abrir) { ev.preventDefault(); location.hash = `v=${el.dataset.abrir}`; return; }
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
const VISTAS = { inicio: vistaInicio, videos: vistaVideos, biblioteca: vistaBiblioteca, tendencias: vistaTendencias,
  canal: vistaCanal, herramientas: vistaHerramientas };
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
