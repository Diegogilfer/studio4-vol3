// STUDIO #4 · Recoger de Google Flow — corre DENTRO de la pestaña de Flow.
//
// Solo mira: cuando aparece en la página una imagen nueva del tamaño de una generación, la manda
// al proceso de fondo de la extensión, que la entrega a tu STUDIO #4. No escribe prompts ni pulsa
// nada en Flow, y no lee tu cuenta (modo «Recoger», elegido por Diego el 2026-10-07).
(() => {
  const VISTAS = new Set();
  const LADO_MIN = 384;           // iconos, avatares y miniaturas de la interfaz quedan fuera
  const ESPERA_BASE_MS = 4000;    // lo que ya estaba en pantalla al abrir Flow no se manda
  let mirando = false;

  const fuente = (img) => img.currentSrc || img.src || "";
  const esGenerada = (img) => {
    const src = fuente(img);
    if (!src || src.startsWith("data:image/svg")) return false;
    return Math.min(img.naturalWidth || 0, img.naturalHeight || 0) >= LADO_MIN;
  };
  const textoDe = (img) => (img.alt || img.getAttribute("aria-label") || img.title || "").trim();

  const aBase64 = (blob) => new Promise((ok, mal) => {
    const lector = new FileReader();
    lector.onload = () => ok(String(lector.result).split(",")[1] || "");
    lector.onerror = mal;
    lector.readAsDataURL(blob);
  });

  async function mandar(img) {
    const src = fuente(img);
    if (!src || VISTAS.has(src)) return;
    VISTAS.add(src);
    const { activo = true } = await chrome.storage.local.get("activo");
    if (!activo) return;
    let b64 = "", mime = "";
    try {
      // blob:, data: y lo que la página puede leer: aquí mismo.
      const r = await fetch(src, { credentials: "include" });
      if (r.ok) {
        const blob = await r.blob();
        mime = blob.type;
        b64 = await aBase64(blob);
      }
    } catch (_) {
      // Otro dominio sin permiso para la página: la pide el fondo con los permisos de la extensión.
    }
    chrome.runtime.sendMessage({
      tipo: "imagen", b64, mime, url: src.startsWith("blob:") ? "" : src,
      prompt: textoDe(img), pagina: location.href,
    });
  }

  function revisar(img) {
    if (!mirando || !(img instanceof HTMLImageElement)) return;
    if (img.complete && img.naturalWidth) {
      if (esGenerada(img)) mandar(img);
    } else {
      img.addEventListener("load", () => { if (esGenerada(img)) mandar(img); }, { once: true });
    }
  }

  const observador = new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "attributes") revisar(c.target);
      for (const n of c.addedNodes || []) {
        if (n.nodeType !== 1) continue;
        if (n.tagName === "IMG") revisar(n);
        n.querySelectorAll?.("img").forEach(revisar);
      }
    }
  });

  setTimeout(() => {
    document.querySelectorAll("img").forEach((i) => { const s = fuente(i); if (s) VISTAS.add(s); });
    mirando = true;
    observador.observe(document.documentElement, {
      subtree: true, childList: true, attributes: true, attributeFilter: ["src", "srcset"],
    });
  }, ESPERA_BASE_MS);

  chrome.runtime.sendMessage({ tipo: "hola" });

  // «Enviar las que hay en pantalla» (desde la ventana de la extensión).
  chrome.runtime.onMessage.addListener((msg, _quien, responder) => {
    if (msg?.tipo !== "enviar-visibles") return;
    let n = 0;
    document.querySelectorAll("img").forEach((i) => {
      if (esGenerada(i)) { VISTAS.delete(fuente(i)); mandar(i); n += 1; }
    });
    responder({ enviadas: n });
  });
})();
