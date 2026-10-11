// STUDIO #4 · Recoger de Google Flow — proceso de fondo de la extensión.
//
// Recibe las imágenes que ve `recoger.js` y las entrega a STUDIO #4 (por defecto en tu equipo,
// http://127.0.0.1:8000) con el código de emparejamiento. El código se copia una vez desde
// STUDIO #4 › Ajustes › Conexiones › Google Flow. No se usa ninguna credencial de Google.

const POR_DEFECTO = { servidor: "http://127.0.0.1:8000", codigo: "", activo: true };
const VERSION = chrome.runtime.getManifest().version;

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
  if (!msg.url) throw new Error("No se pudo leer la imagen en Flow.");
  const r = await fetch(msg.url, { credentials: "include" });
  if (!r.ok) throw new Error(`Flow no dejó bajar la imagen (${r.status}).`);
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

chrome.runtime.onMessage.addListener((msg, _quien, responder) => {
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
          ? "STUDIO #4 no responde: ábrelo (iniciar_panel.bat) y vuelve a generar."
          : String(e.message || e);
        await anotar({ ok: false, error });
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
