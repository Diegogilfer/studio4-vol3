// STUDIO #4 · Recoger de Google Flow — corre DENTRO de la pestaña de Flow.
//
// Dos cosas, y ninguna toca Flow por ti (modo «Recoger + copiar», elegido por Diego):
//  1. Un panelito flotante con la escena que toca: su texto de voz, su prompt y «Copiar».
//     Tú lo pegas en Flow y pulsas Generar.
//  2. Desde que pulsas «Copiar prompt» (y durante 20 min), cada vídeo o imagen NUEVOS del tamaño de
//     una generación van a STUDIO #4, a esa escena. Lo que ya había en Flow no se manda.
//  Todo lo que ve, manda o falla se anota en el panel de STUDIO para poder diagnosticar.
(() => {
  const VISTAS = new Set();
  const LADO_MIN = 384;              // iconos, avatares y miniaturas de la interfaz quedan fuera
  const ARMADO_MS = 20 * 60 * 1000;  // tras «Copiar prompt», 20 min recogiendo lo nuevo
  let armadoHasta = 0;               // antes de copiar no se manda nada: lo viejo del proyecto no se cuela
  let escenaArmada = 0;

  const fuente = (el) => el.currentSrc || el.src || el.querySelector?.("source")?.src || "";
  const visible = (el) => { const r = el.getBoundingClientRect(); return Math.max(r.width, r.height) >= 140; };
  // Un vídeo de Flow puede estar sin precargar (preload="none"): sin metadatos aún, decide su tamaño en pantalla
  // y el servidor rechaza lo que resulte ser una miniatura.
  const esGenerada = (el) => {
    const src = fuente(el);
    if (!src || src.startsWith("data:image/svg")) return false;
    if (el.tagName === "VIDEO") {
      return el.readyState >= 1 && el.videoWidth ? Math.min(el.videoWidth, el.videoHeight) >= LADO_MIN : visible(el);
    }
    return Math.min(el.naturalWidth || 0, el.naturalHeight || 0) >= LADO_MIN;
  };
  const textoDe = (el) => (el.alt || el.getAttribute("aria-label") || el.title
    || el.closest("[aria-label]")?.getAttribute("aria-label") || "").trim();
  const avisar = (evento, detalle) => chrome.runtime.sendMessage({ tipo: "diagnostico", evento, detalle }).catch(() => {});
  const origenDe = (src) => { try { const u = new URL(src); return u.protocol === "blob:" ? "blob" : u.host; } catch (_) { return "?"; } };

  const aBase64 = (blob) => new Promise((ok, mal) => {
    const lector = new FileReader();
    lector.onload = () => ok(String(lector.result).split(",")[1] || "");
    lector.onerror = mal;
    lector.readAsDataURL(blob);
  });

  async function mandar(el, forzar = false) {
    const src = fuente(el);
    if (!src || VISTAS.has(src)) return;
    VISTAS.add(src);
    const tipo = el.tagName === "VIDEO" ? "vídeo" : "imagen";
    if (!forzar && Date.now() > armadoHasta) return;   // visto antes de copiar un prompt: se ignora
    const { activo = true } = await chrome.storage.local.get("activo");
    if (!activo) return;
    let b64 = "", mime = "";
    // blob: solo se puede leer desde la página; lo demás lo baja el fondo con los permisos de la extensión.
    if (src.startsWith("blob:") || src.startsWith("data:")) {
      try {
        const blob = await (await fetch(src)).blob();
        mime = blob.type;
        b64 = await aBase64(blob);
      } catch (e) {
        avisar("error", `${tipo} en ${origenDe(src)}: no se pudo leer (${e?.message || e}). Usa «Subir clip» en STUDIO.`);
        return;
      }
    }
    avisar("enviando", `${tipo} de ${origenDe(src)} → escena ${escenaArmada || "activa"}`);
    chrome.runtime.sendMessage({
      tipo: "imagen", b64, mime, url: b64 ? "" : src,
      esVideo: el.tagName === "VIDEO", prompt: textoDe(el), pagina: location.href,
    });
  }

  function revisar(el, forzar = false) {
    if (!el || (el.tagName !== "IMG" && el.tagName !== "VIDEO")) return;
    const probar = () => { if (esGenerada(el)) mandar(el, forzar); };
    if (el.tagName === "IMG" && !(el.complete && el.naturalWidth)) {
      el.addEventListener("load", probar, { once: true });
      return;
    }
    probar();
    if (el.tagName === "VIDEO" && el.readyState < 1) {
      el.addEventListener("loadedmetadata", () => { VISTAS.delete(fuente(el)); probar(); }, { once: true });
    }
  }

  const observador = new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "attributes") revisar(c.target.tagName === "SOURCE" ? c.target.parentElement : c.target);
      for (const n of c.addedNodes || []) {
        if (n.nodeType !== 1) continue;
        if (n.tagName === "SOURCE") revisar(n.parentElement);
        else revisar(n);
        n.querySelectorAll?.("img, video").forEach((x) => revisar(x));
      }
    }
  });
  observador.observe(document.documentElement, {
    subtree: true, childList: true, attributes: true, attributeFilter: ["src", "srcset"],
  });

  function armar(escena) {
    // Lo que ya está en pantalla al copiar es de antes: se marca como visto.
    document.querySelectorAll("img, video").forEach((el) => { const s = fuente(el); if (s) VISTAS.add(s); });
    armadoHasta = Date.now() + ARMADO_MS;
    escenaArmada = escena;
    const v = document.querySelectorAll("video").length;
    avisar("armada", `escena ${escena}: recogiendo lo nuevo 20 min (en pantalla: ${v} vídeos, ${document.images.length} imágenes)`);
  }

  // «Enviar las que hay en pantalla» (desde la ventana de la extensión): manda todo lo visible ya.
  chrome.runtime.onMessage.addListener((msg, _quien, responder) => {
    if (msg?.tipo !== "enviar-visibles") return;
    let n = 0;
    document.querySelectorAll("img, video").forEach((el) => {
      if (esGenerada(el)) { VISTAS.delete(fuente(el)); mandar(el, true); n += 1; }
    });
    avisar("pantalla", `enviando ${n} de la pantalla`);
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
        <button class="btn sec" id="lateral">Abrir STUDIO al lado ⇥</button>
      </div>
    </div>`;
  const $ = (id) => sombra.getElementById(id);
  let sesion = null;
  let armadoVisto = 0;   // último «empieza a recoger» del servidor ya aplicado aquí
  let servidor = "http://127.0.0.1:8000";

  function pintar() {
    const viva = sesion?.viva;
    anfitrion.hidden = !viva && !sesion?.preparando;
    if (!viva) { $("tit").textContent = sesion?.preparando ? `STUDIO #4 · ${sesion.preparando}` : "STUDIO #4"; return; }
    const s = sesion.siguiente;
    const e = sesion.escenas[s.escena - 1];
    $("tit").textContent = s.escena === 0 ? "Imagen para la miniatura"
      : `Escena ${s.escena} de ${sesion.total}${e?.video ? " · ya tiene vídeo" : ""}`;
    $("voz").textContent = s.escena === 0 ? s.voz : `«${s.voz}»`;
    $("prompt").textContent = s.prompt;
    $("aspecto").textContent = s.escena === 0 ? `Pon Flow en ${sesion.aspecto}`
      : `Haz ${s.tipo === "imagen" ? "una IMAGEN" : "un VÍDEO"} en Flow · ${sesion.aspecto}`;
    $("puntos").innerHTML = sesion.escenas.map((x) =>
      `<i class="${x.video ? "ok" : ""} ${x.escena === s.escena ? "ya" : ""}" title="Escena ${x.escena}"></i>`).join("");
    $("ref").hidden = !s.referencia;
    if (s.referencia && $("ref-img").dataset.src !== servidor + s.referencia) {
      $("ref-img").src = servidor + s.referencia;
      $("ref-img").dataset.src = servidor + s.referencia;
    }
    $("nota").textContent = s.referencia
      ? `Para que no salte: usa la imagen inicial (${s.referencia_de}) en «Fotogramas a vídeo».`
      : "Pulsa «Copiar prompt» (así empieza a recoger), pégalo en Flow y genera. El vídeo llegará solo a esta escena.";
  }

  async function actualizar() {
    const d = await chrome.storage.local.get(["servidor"]);
    servidor = (d.servidor || servidor).replace(/\/+$/, "");
    const r = await chrome.runtime.sendMessage({ tipo: "hola" }).catch(() => null);
    if (!r?.ok) return;
    sesion = r.sesion;
    // Copiaste el prompt desde el panel de STUDIO: también empieza a recoger aquí.
    if (sesion?.viva && sesion.armado > armadoVisto) {
      if (armadoVisto) armar(sesion.siguiente.escena);
      armadoVisto = sesion.armado;
    }
    pintar();
  }

  async function irA(escena) {
    const r = await chrome.runtime.sendMessage({ tipo: "activa", escena }).catch(() => null);
    if (r?.ok) { sesion = r.sesion; armadoVisto = sesion.armado || armadoVisto; pintar(); }
  }

  $("cab").addEventListener("click", (ev) => { if (!ev.target.closest("button")) $("caja").classList.toggle("min"); });
  $("ant").addEventListener("click", () => sesion?.viva && irA(Math.max(1, sesion.siguiente.escena - 1)));
  $("sig").addEventListener("click", () => sesion?.viva && irA(Math.min(sesion.total, sesion.siguiente.escena + 1)));
  $("copiar").addEventListener("click", async () => {
    await navigator.clipboard.writeText($("prompt").textContent);
    $("copiar").textContent = "Copiado: pégalo en Flow";
    setTimeout(() => { $("copiar").textContent = "Copiar prompt"; }, 2000);
    // Confirma a qué va lo que llegue ahora (una escena o, con escena 0, la miniatura) y empieza a recoger.
    if (sesion.siguiente.escena > 0) irA(sesion.siguiente.escena);
    armar(sesion.siguiente.escena);
  });
  $("lateral").addEventListener("click", async () => {
    const r = await chrome.runtime.sendMessage({ tipo: "abrir-lateral" }).catch(() => null);
    if (!r?.ok) $("lateral").textContent = "Pulsa el icono S4 de la barra de Chrome";
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
