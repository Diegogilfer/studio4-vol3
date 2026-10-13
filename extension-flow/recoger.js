// STUDIO #4 · Recoger de Google Flow — corre DENTRO de la pestaña de Flow.
//
// Dos cosas, y ninguna toca Flow por ti (modo «Recoger + copiar», elegido por Diego):
//  1. Un panelito flotante con la escena que toca: su texto de voz, su prompt y «Copiar».
//     Tú lo pegas en Flow y pulsas Generar.
//  2. Cuando aparece en la página un vídeo o una imagen NUEVOS del tamaño de una generación,
//     los manda a STUDIO #4 marcados con la escena que copiaste.
(() => {
  const VISTAS = new Set();
  const LADO_MIN = 384;           // iconos, avatares y miniaturas de la interfaz quedan fuera
  const ESPERA_BASE_MS = 4000;    // lo que ya estaba en pantalla al abrir Flow no se manda
  let mirando = false;

  const fuente = (el) => el.currentSrc || el.src || el.querySelector?.("source")?.src || "";
  const lado = (el) => el.tagName === "VIDEO"
    ? Math.min(el.videoWidth || 0, el.videoHeight || 0)
    : Math.min(el.naturalWidth || 0, el.naturalHeight || 0);
  const esGenerada = (el) => {
    const src = fuente(el);
    if (!src || src.startsWith("data:image/svg")) return false;
    return lado(el) >= LADO_MIN;
  };
  const textoDe = (el) => (el.alt || el.getAttribute("aria-label") || el.title || "").trim();

  const aBase64 = (blob) => new Promise((ok, mal) => {
    const lector = new FileReader();
    lector.onload = () => ok(String(lector.result).split(",")[1] || "");
    lector.onerror = mal;
    lector.readAsDataURL(blob);
  });

  async function mandar(el) {
    const src = fuente(el);
    if (!src || VISTAS.has(src)) return;
    VISTAS.add(src);
    const { activo = true } = await chrome.storage.local.get("activo");
    if (!activo) return;
    let b64 = "", mime = "";
    // blob: solo se puede leer desde la página; lo demás lo baja el fondo con los permisos de la extensión
    // (así un vídeo de varios MB no viaja dos veces).
    if (src.startsWith("blob:") || src.startsWith("data:")) {
      try {
        const blob = await (await fetch(src)).blob();
        mime = blob.type;
        b64 = await aBase64(blob);
      } catch (_) { return; }
    }
    chrome.runtime.sendMessage({
      tipo: "imagen", b64, mime, url: b64 ? "" : src,
      esVideo: el.tagName === "VIDEO", prompt: textoDe(el), pagina: location.href,
    });
  }

  function revisar(el) {
    if (!mirando) return;
    if (el instanceof HTMLImageElement) {
      if (el.complete && el.naturalWidth) { if (esGenerada(el)) mandar(el); }
      else el.addEventListener("load", () => { if (esGenerada(el)) mandar(el); }, { once: true });
    } else if (el instanceof HTMLVideoElement) {
      if (el.readyState >= 1) { if (esGenerada(el)) mandar(el); }
      else el.addEventListener("loadedmetadata", () => { if (esGenerada(el)) mandar(el); }, { once: true });
    }
  }

  const observador = new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "attributes") revisar(c.target.tagName === "SOURCE" ? c.target.parentElement : c.target);
      for (const n of c.addedNodes || []) {
        if (n.nodeType !== 1) continue;
        if (n.tagName === "IMG" || n.tagName === "VIDEO") revisar(n);
        n.querySelectorAll?.("img, video").forEach(revisar);
      }
    }
  });

  setTimeout(() => {
    document.querySelectorAll("img, video").forEach((el) => { const s = fuente(el); if (s) VISTAS.add(s); });
    mirando = true;
    observador.observe(document.documentElement, {
      subtree: true, childList: true, attributes: true, attributeFilter: ["src", "srcset"],
    });
  }, ESPERA_BASE_MS);

  // «Enviar las que hay en pantalla» (desde la ventana de la extensión).
  chrome.runtime.onMessage.addListener((msg, _quien, responder) => {
    if (msg?.tipo !== "enviar-visibles") return;
    let n = 0;
    document.querySelectorAll("img, video").forEach((el) => {
      if (esGenerada(el)) { VISTAS.delete(fuente(el)); mandar(el); n += 1; }
    });
    responder({ enviadas: n });
  });

  // ---------------------------------------------------------------- panel flotante
  const anfitrion = document.createElement("div");
  anfitrion.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647";
  const sombra = anfitrion.attachShadow({ mode: "closed" });
  sombra.innerHTML = `
    <style>
      :host { all: initial; }
      .caja { width: 340px; font: 13px/1.45 "Segoe UI", system-ui, sans-serif; color: #eef1f6; background: rgb(18 20 29 / .96);
              border: 1px solid rgb(255 255 255 / .12); border-radius: 20px; box-shadow: 0 24px 60px -20px #000; backdrop-filter: blur(16px); overflow: hidden; }
      .cab { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; }
      .logo { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; font-weight: 700; font-size: 10px;
              background: linear-gradient(135deg, #8b5cf6, #2dd4bf); color: #fff; }
      .tit { flex: 1; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .nav button { background: #1b1e2a; border: 1px solid #323849; color: #eef1f6; width: 26px; height: 26px; border-radius: 999px; cursor: pointer; }
      .cuerpo { padding: 0 12px 12px; display: grid; gap: 8px; }
      .voz { font-style: italic; color: #cfd3dc; }
      pre { margin: 0; max-height: 150px; overflow: auto; white-space: pre-wrap; font: 11.5px/1.45 Consolas, monospace; color: #9aa3b2;
            background: #07080d; border: 1px solid #232736; border-radius: 12px; padding: 8px 10px; }
      .fila { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
      .btn { border: 0; border-radius: 12px; padding: 8px 12px; font: inherit; font-weight: 600; cursor: pointer; background: #8b5cf6; color: #fff; }
      .btn.sec { background: #1b1e2a; border: 1px solid #323849; font-weight: 500; }
      .ref img { height: 46px; border-radius: 8px; vertical-align: middle; }
      .nota { color: #9aa3b2; font-size: 12px; }
      .puntos { display: flex; gap: 3px; flex-wrap: wrap; }
      .puntos i { width: 9px; height: 9px; border-radius: 3px; background: #323849; }
      .puntos i.ok { background: #34d399; } .puntos i.ya { outline: 2px solid #8b5cf6; }
      .min .cuerpo { display: none; }
    </style>
    <div class="caja" id="caja">
      <div class="cab" id="cab"><span class="logo">S4</span><span class="tit" id="tit">STUDIO #4</span>
        <span class="nav"><button id="ant" title="Escena anterior">‹</button> <button id="sig" title="Escena siguiente">›</button></span></div>
      <div class="cuerpo">
        <div class="puntos" id="puntos"></div>
        <div class="voz" id="voz"></div>
        <pre id="prompt"></pre>
        <div class="fila"><button class="btn" id="copiar">Copiar prompt</button><span class="nota" id="aspecto"></span></div>
        <div class="fila ref" id="ref" hidden><img id="ref-img" alt=""><button class="btn sec" id="copiar-ref">Copiar imagen inicial</button></div>
        <div class="nota" id="nota"></div>
      </div>
    </div>`;
  const $ = (id) => sombra.getElementById(id);
  let sesion = null;
  let servidor = "http://127.0.0.1:8000";

  function pintar() {
    const viva = sesion?.viva;
    anfitrion.hidden = !viva && !sesion?.preparando;
    if (!viva) { $("tit").textContent = sesion?.preparando ? `STUDIO #4 · ${sesion.preparando}` : "STUDIO #4"; return; }
    const s = sesion.siguiente;
    const e = sesion.escenas[s.escena - 1];
    $("tit").textContent = `Escena ${s.escena} de ${sesion.total}${e?.video ? " · ✓ ya tiene vídeo" : ""}`;
    $("voz").textContent = `«${s.voz}»`;
    $("prompt").textContent = s.prompt;
    $("aspecto").textContent = `Pon Flow en ${sesion.aspecto}`;
    $("puntos").innerHTML = sesion.escenas.map((x) =>
      `<i class="${x.video ? "ok" : ""} ${x.escena === s.escena ? "ya" : ""}" title="Escena ${x.escena}"></i>`).join("");
    $("ref").hidden = !s.referencia;
    if (s.referencia && $("ref-img").dataset.src !== servidor + s.referencia) {
      $("ref-img").src = servidor + s.referencia;
      $("ref-img").dataset.src = servidor + s.referencia;
    }
    $("nota").textContent = s.referencia
      ? `Para que no salte: usa la imagen inicial (${s.referencia_de}) en «Fotogramas a vídeo».`
      : "Copia el prompt, pégalo en Flow y genera. El vídeo llegará solo a esta escena.";
  }

  async function actualizar() {
    const d = await chrome.storage.local.get(["servidor"]);
    servidor = (d.servidor || servidor).replace(/\/+$/, "");
    const r = await chrome.runtime.sendMessage({ tipo: "hola" }).catch(() => null);
    if (r?.ok) { sesion = r.sesion; pintar(); }
  }

  async function irA(escena) {
    const r = await chrome.runtime.sendMessage({ tipo: "activa", escena }).catch(() => null);
    if (r?.ok) { sesion = r.sesion; pintar(); }
  }

  $("cab").addEventListener("click", (ev) => { if (!ev.target.closest("button")) $("caja").classList.toggle("min"); });
  $("ant").addEventListener("click", () => sesion?.viva && sesion.siguiente.escena > 1 && irA(sesion.siguiente.escena - 1));
  $("sig").addEventListener("click", () => sesion?.viva && sesion.siguiente.escena < sesion.total && irA(sesion.siguiente.escena + 1));
  $("copiar").addEventListener("click", async () => {
    await navigator.clipboard.writeText($("prompt").textContent);
    $("copiar").textContent = "Copiado ✓ · pégalo en Flow";
    setTimeout(() => { $("copiar").textContent = "Copiar prompt"; }, 2000);
    irA(sesion.siguiente.escena);   // confirma que lo que llegue ahora es de esta escena
  });
  $("copiar-ref").addEventListener("click", async () => {
    try {
      const r = await chrome.runtime.sendMessage({ tipo: "imagen-png", url: $("ref-img").dataset.src });
      const bytes = Uint8Array.from(atob(r.b64), (c) => c.charCodeAt(0));
      await navigator.clipboard.write([new ClipboardItem({ "image/png": new Blob([bytes], { type: "image/png" }) })]);
      $("copiar-ref").textContent = "Copiada: Ctrl+V en Flow";
    } catch (_) { $("copiar-ref").textContent = "No se pudo copiar"; }
    setTimeout(() => { $("copiar-ref").textContent = "Copiar imagen inicial"; }, 2000);
  });

  anfitrion.hidden = true;
  document.documentElement.appendChild(anfitrion);
  actualizar();
  setInterval(actualizar, 4000);
})();
