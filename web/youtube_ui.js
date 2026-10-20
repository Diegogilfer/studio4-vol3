/**
 * youtube_ui.js - Componentes modulares y lógica de la interfaz tipo YouTube
 */

// Estado global de la vista
const YTState = {
  activeCategory: "all",
  searchQuery: "",
  videos: [],
  channelInfo: null,
  sidebarExpanded: true
};

// ==========================================================================
// Componentes Reutilizables
// ==========================================================================

export const ChannelAvatar = (name, url = null) => {
  const initial = (name || "Y").trim().charAt(0).toUpperCase();
  if (url) {
    return `<img class="yt-channel-avatar" src="${url}" alt="${name}" onerror="this.outerHTML='<div class=\\'yt-channel-avatar\\'>${initial}</div>'">`;
  }
  return `<div class="yt-channel-avatar">${initial}</div>`;
};

const medio = (video, archivo) => `/media/${encodeURIComponent(video.id)}/${archivo}`;

export const VideoCard = (video) => {
  const thumbUrl = video.portada
    ? (video.portada.startsWith("http") ? video.portada : medio(video, video.portada))
    : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 9' fill='%231f1f1f'%3E%3Crect width='16' height='9'/%3E%3Ctext x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' fill='%23666' font-family='sans-serif' font-size='1.5'%3ESIN MINIATURA%3C/text%3E%3C/svg%3E";

  const durationBadge = video.version === "corto" || video.formato === "vertical"
    ? `<span class="yt-card-badge" style="background:#ff0033;">SHORTS</span>`
    : video.duracion
    ? `<span class="yt-card-badge">${formatDuration(video.duracion)}</span>`
    : (video.version === "corto" ? `<span class="yt-card-badge" style="background:#ff0033;">SHORTS</span>` : `<span class="yt-card-badge">HD</span>`);

  return `
    <article class="yt-card" data-video-id="${escapeHtml(video.id)}" tabindex="0" role="button">
      <div class="yt-card-thumbnail-wrapper">
        <img class="yt-card-thumbnail" src="${thumbUrl}" alt="${escapeHtml(video.titulo || video.tema)}" loading="lazy">
        ${durationBadge}
      </div>
      <div class="yt-card-details">
        <div class="yt-card-avatar">
          ${ChannelAvatar(escapeHtml(video.canal || "FourLevel"))}
        </div>
        <div class="yt-card-info">
          <h3 class="yt-card-title" title="${escapeHtml(video.titulo || video.tema)}">
            ${escapeHtml(video.titulo || video.tema)}
          </h3>
          <span class="yt-card-channel-name">
            ${escapeHtml(video.canal_nombre || video.canal || "FourLevel")}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#aaa"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm-1.9 14.7l-4-4 1.4-1.4 2.6 2.6 6.6-6.6 1.4 1.4-8 8z"/></svg>
          </span>
          <div class="yt-card-meta">
            <span>${video.vistas ? formatViews(video.vistas) + " vistas" : (video.estado || "Borrador")}</span>
            <span>•</span>
            <span>${timeAgo(video.creado || Date.now())}</span>
          </div>
        </div>
      </div>
    </article>
  `;
};

export const VideoGrid = (videos) => {
  if (!videos || videos.length === 0) {
    return `
      <div class="yt-empty-state">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="#666"><path d="M21.58 7.19a3.016 3.016 0 0 0-2.12-2.14C17.59 4.5 12 4.5 12 4.5s-5.59 0-7.46.55A3.016 3.016 0 0 0 2.42 7.19 31.5 31.5 0 0 0 2 12c0 1.63.14 3.25.42 4.81.27 1.05 1.07 1.87 2.12 2.14 1.87.55 7.46.55 7.46.55s5.59 0 7.46-.55c1.05-.27 1.85-1.09 2.12-2.14.28-1.56.42-3.18.42-4.81 0-1.63-.14-3.25-.42-4.81zM9.75 15.02V8.98L15 12l-5.25 3.02z"/></svg>
        <h3 style="margin-top:16px;">No se encontraron vídeos</h3>
        <p>Intenta con otros términos de búsqueda o selecciona otra categoría.</p>
      </div>
    `;
  }
  return videos.map(v => VideoCard(v)).join("");
};

export const CategoryFilters = (categories, activeId) => {
  return categories.map(cat => `
    <button class="yt-chip ${cat.id === activeId ? 'active' : ''}" data-category-id="${cat.id}">
      ${cat.label}
    </button>
  `).join("");
};

// ==========================================================================
// Helpers de Formato y Utilidades
// ==========================================================================

function formatDuration(segundos) {
  const m = Math.floor(segundos / 60);
  const s = Math.floor(segundos % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function formatViews(v) {
  if (v >= 1000000) return (v / 1000000).toFixed(1).replace(".0", "") + " M";
  if (v >= 1000) return (v / 1000).toFixed(1).replace(".0", "") + " K";
  return String(v);
}

function timeAgo(fecha) {
  const segs = Math.floor((Date.now() - new Date(fecha).getTime()) / 1000);
  if (isNaN(segs)) return "reciente";
  if (segs < 3600) return "hace poco";
  if (segs < 86400) return `hace ${Math.floor(segs / 3600)} h`;
  const dias = Math.floor(segs / 86400);
  return dias === 1 ? "hace 1 día" : `hace ${dias} días`;
}

function escapeHtml(t) {
  return String(t ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ==========================================================================
// Inicializador de Interfaz
// ==========================================================================

export async function initYouTubeUI() {
  const gridContainer = document.getElementById("yt-video-grid");
  const categoriesContainer = document.getElementById("yt-category-filters");
  const searchInput = document.getElementById("yt-search-input");
  const searchForm = document.getElementById("yt-search-form");
  const menuToggle = document.getElementById("yt-menu-toggle");
  const sidebar = document.getElementById("yt-sidebar");

  const categories = [
    { id: "all", label: "Todos" },
    { id: "largo", label: "Videos Largos" },
    { id: "corto", label: "Shorts" },
    { id: "gta", label: "GTA / Gaming" },
    { id: "ideas", label: "Ideas en Tendencia" },
    { id: "finalizados", label: "Listos para Publicar" }
  ];

  if (categoriesContainer) {
    categoriesContainer.innerHTML = CategoryFilters(categories, YTState.activeCategory);
  }

  // Cargar producciones desde la API nativa de Studio 4
  try {
    const res = await fetch("/api/producciones");
    if (res.ok) {
      YTState.videos = await res.json();
    }
  } catch (err) {
    console.warn("Cargando catálogo local:", err);
  }

  // Render inicial
  renderGrid();

  // Escuchadores de Categoría
  categoriesContainer?.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-category-id]");
    if (!chip) return;
    YTState.activeCategory = chip.dataset.categoryId;
    categoriesContainer.innerHTML = CategoryFilters(categories, YTState.activeCategory);
    renderGrid();
  });

  // Búsqueda
  searchForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    YTState.searchQuery = searchInput.value.trim().toLowerCase();
    renderGrid();
  });

  searchInput?.addEventListener("input", (e) => {
    YTState.searchQuery = e.target.value.trim().toLowerCase();
    renderGrid();
  });

  // Toggle de Menú Lateral
  menuToggle?.addEventListener("click", () => {
    if (window.innerWidth <= 1024) {
      sidebar?.classList.toggle("open-mobile");
    } else {
      sidebar?.classList.toggle("collapsed");
    }
  });

  // Pantalla de ver: el vídeo montado (o su miniatura si aún no está montado) con sus textos de publicación.
  const ver = document.getElementById("yt-ver");
  function abrir(id) {
    const v = YTState.videos.find((x) => x.id === id);
    if (!v || !ver) return;
    const vertical = v.version === "corto" || v.formato === "vertical";
    const portada = v.portada ? medio(v, v.portada) : "";
    const reproductor = v.final
      ? `<video class="yt-ver-video" controls autoplay playsinline preload="metadata" ${portada ? `poster="${portada}"` : ""}
           src="${medio(v, v.final)}"></video>`
      : `<div class="yt-ver-pendiente">${portada ? `<img src="${portada}" alt="">` : ""}<span>Aún sin montar</span></div>`;
    ver.innerHTML = `
      <button class="yt-chip" type="button" data-volver="1">← Volver</button>
      <div class="yt-ver-marco ${vertical ? "vertical" : ""}">${reproductor}</div>
      <h1 class="yt-ver-titulo">${escapeHtml(v.titulo || v.tema)}</h1>
      <div class="yt-ver-canal">${ChannelAvatar(escapeHtml(v.canal || "F"))}
        <div><b>${escapeHtml(v.canal_nombre || v.canal || "FourLevel")}</b><small>${escapeHtml(v.estado || "")}</small></div>
        <span class="yt-ver-sub">Suscribirse</span></div>
      <div class="yt-ver-descripcion">
        <small>${v.duracion ? formatDuration(v.duracion) + " · " : ""}${timeAgo(v.creado)}</small>
        <p>${escapeHtml(v.descripcion || "Sin descripción todavía.")}</p>
        ${(v.hashtags || []).length ? `<p class="yt-ver-tags">${v.hashtags.map(escapeHtml).join(" ")}</p>` : ""}
      </div>`;
    ver.hidden = false;
    location.hash = `ver=${encodeURIComponent(id)}`;
    window.scrollTo({ top: 0 });
    renderGrid();
  }
  function cerrar() {
    if (!ver) return;
    ver.querySelector("video")?.pause();
    ver.hidden = true; ver.innerHTML = "";
    history.replaceState(null, "", location.pathname);
    renderGrid();
  }
  gridContainer?.addEventListener("click", (e) => {
    const c = e.target.closest("[data-video-id]");
    if (c) abrir(c.dataset.videoId);
  });
  gridContainer?.addEventListener("keydown", (e) => {
    const c = e.target.closest("[data-video-id]");
    if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); abrir(c.dataset.videoId); }
  });
  ver?.addEventListener("click", (e) => { if (e.target.closest("[data-volver]")) cerrar(); });
  const pedido = decodeURIComponent((location.hash.match(/^#ver=(.+)$/) || [])[1] || "");
  if (pedido) abrir(pedido);

  function renderGrid() {
    if (!gridContainer) return;
    let filtrados = [...YTState.videos];

    // Filtro por categoría
    if (YTState.activeCategory === "corto") {
      filtrados = filtrados.filter(v => v.version === "corto" || v.formato === "vertical");
    } else if (YTState.activeCategory === "largo") {
      filtrados = filtrados.filter(v => v.version === "largo" || v.formato === "horizontal");
    } else if (YTState.activeCategory === "finalizados") {
      filtrados = filtrados.filter(v => v.estado === "terminado" || v.final);
    } else if (YTState.activeCategory === "gta") {
      filtrados = filtrados.filter(v => (v.titulo + " " + v.tema).toLowerCase().includes("gta"));
    }

    // Filtro por buscador
    if (YTState.searchQuery) {
      filtrados = filtrados.filter(v =>
        (v.titulo || "").toLowerCase().includes(YTState.searchQuery) ||
        (v.tema || "").toLowerCase().includes(YTState.searchQuery) ||
        (v.canal || "").toLowerCase().includes(YTState.searchQuery)
      );
    }

    gridContainer.innerHTML = VideoGrid(filtrados);
  }
}
