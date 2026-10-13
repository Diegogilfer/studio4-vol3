// STUDIO #4 · Recoger de Google Flow — proceso de fondo de la extensión.
//
// Recibe los vídeos e imágenes que ve `recoger.js` y los entrega a STUDIO #4 (por defecto en tu equipo,
// http://127.0.0.1:8000) con el código de emparejamiento. El código se copia una vez desde
// STUDIO #4 › Ajustes › Conexiones › Google Flow. No se usa ninguna credencial de Google.

const POR_DEFECTO = { servidor: "http://127.0.0.1:8000", codigo: "", activo: true };
const VERSION = chrome.runtime.getManifest().version;

// El icono S4 abre STUDIO en el panel lateral de Chrome, al lado de Flow (los ajustes están abajo del panel).
chrome.sidePanel?.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

async function ajustes() {
  return { ...POR_DEFECTO, ...(await chrome.storage.local.get(["servidor", "codigo", "activo"])) };
}

function deBase64(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function bytesDe(msg) {
  if (msg.b64) return { cuerpo: deBase64(msg.b64), mime: msg.mime || "application/octet-stream" };
  if (!msg.url) throw new Error("No se pudo leer el clip en Flow.");
  const r = await fetch(msg.url, { credentials: "include" });
  if (!r.ok) throw new Error(`Flow no dejó bajar el clip (${r.status}).`);
  const blob = await r.blob();
  return { cuerpo: blob, mime: blob.type || "application/octet-stream" };
}

async function anotar(cambio) {
  const d = await chrome.storage.local.get(["enviadas"]);
  const nuevo = { ...cambio };
  if (cambio.ok) nuevo.enviadas = (d.enviadas || 0) + 1;
  await chrome.storage.local.set({ ...nuevo, ultima: Date.now() });
  const n = nuevo.enviadas ?? d.enviadas ?? 0;
  chrome.action.setBadgeBackgroundColor({ color: cambio.error ? "#d97706" : "#8b5cf6" });
  chrome.action.setBadgeText({ text: cambio.error ? "!" : n ? String(Math.min(n, 999)) : "" });
}

// Lo que ve y hace la extensión llega al panel de STUDIO #4 (Escenas › «Lo que ve la extensión»).
async function diagnostico(tipo, detalle) {
  try {
    const a = await ajustes();
    if (!a.codigo) return;
    await fetch(`${a.servidor.replace(/\/+$/, "")}/api/flow/diagnostico`, {
      method: "POST",
      headers: { "X-Studio4-Token": a.codigo, "X-Flow-Version": VERSION, "Content-Type": "application/json" },
      body: JSON.stringify({ tipo, detalle: String(detalle).slice(0, 300) }),
    });
  } catch (_) { /* STUDIO cerrado: nada que anotar */ }
}

async function entregar(msg) {
  const a = await ajustes();
  if (!a.activo) return { omitida: true };
  if (!a.codigo) throw new Error("Falta el código de emparejamiento: cópialo de STUDIO #4 › Ajustes › Conexiones.");
  const { cuerpo, mime } = await bytesDe(msg);
  const r = await fetch(`${a.servidor.replace(/\/+$/, "")}/api/flow/recibir`, {
    method: "POST",
    headers: {
      "Content-Type": mime,
      "X-Studio4-Token": a.codigo,
      "X-Flow-Prompt": encodeURIComponent(String(msg.prompt || "").slice(0, 600)),
      "X-Flow-Pagina": encodeURIComponent(String(msg.pagina || "").slice(0, 250)),
      "X-Flow-Version": VERSION,
    },
    body: cuerpo,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `STUDIO #4 respondió ${r.status}.`);
  return d;
}

// STUDIO #4 cerrado un momento: se reintenta un par de veces antes de dar el aviso.
async function conReintentos(fn, esperas = [2000, 6000]) {
  for (let i = 0; ; i += 1) {
    try {
      return await fn();
    } catch (e) {
      const deRed = e instanceof TypeError;            // fetch sin respuesta: el estudio no está abierto
      if (!deRed || i >= esperas.length) throw e;
      await new Promise((ok) => setTimeout(ok, esperas[i]));
    }
  }
}

async function hola(codigo, servidor) {
  const a = await ajustes();
  codigo = codigo ?? a.codigo;
  servidor = servidor ?? a.servidor;
  if (!codigo) return { ok: false, error: "Falta el código de emparejamiento." };
  const r = await fetch(`${servidor.replace(/\/+$/, "")}/api/flow/hola`, {
    method: "POST", headers: { "X-Studio4-Token": codigo, "X-Flow-Version": VERSION },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return { ok: false, error: d.error || `STUDIO #4 respondió ${r.status}.` };
  return { ok: true, sesion: d.sesion || null };
}

// Emparejar con un clic: la página local /flow/emparejar de STUDIO #4 trae el código. Solo se
// guarda si ese mismo STUDIO #4 lo acepta (un código falso no pisa uno bueno).
async function emparejar(codigo, servidor) {
  if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(servidor || "")) {
    return { ok: false, error: "Solo se empareja con un STUDIO #4 de este equipo." };
  }
  const r = await hola(codigo, servidor);
  if (!r.ok) return r;
  await chrome.storage.local.set({ codigo, servidor, activo: true, conexion: "ok", error: "", probada: Date.now() });
  chrome.action.setBadgeBackgroundColor({ color: "#8b5cf6" });
  chrome.action.setBadgeText({ text: "✓" });
  return { ok: true };
}

// Cambiar la escena que toca (desde el panel flotante de Flow).
async function activa(escena) {
  const a = await ajustes();
  const r = await fetch(`${a.servidor.replace(/\/+$/, "")}/api/flow/activa`, {
    method: "POST",
    headers: { "X-Studio4-Token": a.codigo, "X-Flow-Version": VERSION, "Content-Type": "application/json" },
    body: JSON.stringify({ escena }),
  });
  const d = await r.json().catch(() => ({}));
  return r.ok ? { ok: true, sesion: d.sesion } : { ok: false, error: d.error || `STUDIO #4 respondió ${r.status}.` };
}

// El portapapeles solo acepta PNG: la imagen inicial de la escena se convierte aquí.
async function imagenPng(url) {
  const a = await ajustes();
  if (!url.startsWith(a.servidor.replace(/\/+$/, ""))) throw new Error("Solo imágenes de tu STUDIO #4");
  const bmp = await createImageBitmap(await (await fetch(url)).blob());
  const lienzo = new OffscreenCanvas(bmp.width, bmp.height);
  lienzo.getContext("2d").drawImage(bmp, 0, 0);
  const png = await lienzo.convertToBlob({ type: "image/png" });
  const bytes = new Uint8Array(await png.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return { b64: btoa(bin) };
}

chrome.runtime.onMessage.addListener((msg, _quien, responder) => {
  if (msg?.tipo === "abrir-lateral") {
    // Solo funciona como respuesta a un clic; si Chrome no lo permite, se indica el icono.
    chrome.sidePanel.open({ tabId: _quien.tab.id })
      .then(() => responder({ ok: true }))
      .catch(() => responder({ ok: false }));
    return true;
  }
  if (msg?.tipo === "diagnostico") {
    diagnostico(msg.evento, msg.detalle).then(() => responder({ ok: true }));
    return true;
  }
  if (msg?.tipo === "activa") {
    activa(Number(msg.escena)).then(responder).catch(() => responder({ ok: false }));
    return true;
  }
  if (msg?.tipo === "imagen-png") {
    imagenPng(String(msg.url || "")).then(responder).catch(() => responder({ error: true }));
    return true;
  }
  if (msg?.tipo === "emparejar") {
    emparejar(String(msg.codigo || ""), String(msg.servidor || ""))
      .then(responder)
      .catch(() => responder({ ok: false, error: "STUDIO #4 no responde en esta dirección." }));
    return true;
  }
  if (msg?.tipo === "imagen") {
    conReintentos(() => entregar(msg))
      .then(async (d) => { if (!d.omitida) await anotar({ ok: true, error: "" }); responder({ ok: true, ...d }); })
      .catch(async (e) => {
        const error = e instanceof TypeError
          ? "STUDIO #4 no responde: ábrelo (python servidor.py) y vuelve a generar."
          : String(e.message || e);
        await anotar({ ok: false, error });
        diagnostico("error", `${msg.esVideo ? "vídeo" : "imagen"}: ${error}`);
        responder({ ok: false, error });
      });
    return true;
  }
  if (msg?.tipo === "hola" || msg?.tipo === "probar") {
    hola()
      .then(async (d) => { await chrome.storage.local.set({ conexion: d.ok ? "ok" : d.error, probada: Date.now() }); responder(d); })
      .catch(async () => {
        const error = "STUDIO #4 no responde: ¿está abierto en 127.0.0.1:8000?";
        await chrome.storage.local.set({ conexion: error, probada: Date.now() });
        responder({ ok: false, error });
      });
    return true;
  }
  return false;
});
