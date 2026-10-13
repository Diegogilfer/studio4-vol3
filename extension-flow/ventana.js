// La ventana de la extensión: emparejar con STUDIO #4, probar la conexión y ver lo enviado.
const $ = (id) => document.getElementById(id);

function pintarEstado(conexion, error) {
  const caja = $("estado");
  if (error) {
    caja.className = "estado mal";
    caja.textContent = error;
  } else if (conexion === "ok") {
    caja.className = "estado ok";
    caja.textContent = "Conectada con STUDIO #4. Genera en Flow y los clips aparecerán en su escena.";
  } else {
    caja.className = "estado mal";
    caja.textContent = conexion || "Sin probar todavía.";
  }
}

async function cargar() {
  const d = await chrome.storage.local.get(["servidor", "codigo", "activo", "enviadas", "ultima", "conexion", "error"]);
  $("servidor").value = d.servidor || "http://127.0.0.1:8000";
  servidorActual = $("servidor").value.replace(/\/+$/, "");
  $("codigo").value = d.codigo || "";
  $("activo").checked = d.activo !== false;
  $("enviadas").textContent = String(d.enviadas || 0);
  $("ultima").textContent = d.ultima ? `Última: ${new Date(d.ultima).toLocaleTimeString("es")}` : "";
  pintarEstado(d.conexion, d.error);
}

// La escena que toca generar (la producción las pide en el orden del guion).
function pintarEscena(sesion) {
  const caja = $("escena");
  const sig = sesion?.viva ? sesion.siguiente : null;
  caja.hidden = !sig;
  if (!sig) return;
  const de = sesion.total ? ` de ${sesion.total}` : "";
  if (sig.estado === "propuesta") {
    caja.className = "estado mal";
    $("escena-titulo").textContent = `Escena ${sig.escena}${de}: la última imagen sale ${sig.brusco}`;
    $("escena-nota").textContent = "Genera otra (con la imagen anterior como referencia) o decide en STUDIO #4.";
  } else {
    caja.className = "estado ok";
    $("escena-titulo").textContent = `Escena ${sig.escena}${de} · genera esta en Flow`;
    $("escena-nota").textContent = sig.escena > 1
      ? "Para que no haya saltos, añade en Flow la referencia de abajo (con varias escenas, es la hoja del personaje)."
      : "Es la primera: marca el estilo de todo el vídeo.";
  }
  $("escena-prompt").textContent = sig.prompt;
  const ref = sig.estado !== "propuesta" && sig.referencia ? servidorActual + sig.referencia : "";
  $("referencia").hidden = !ref;
  if (ref && $("referencia-img").dataset.src !== ref) {
    $("referencia-img").src = ref;
    $("referencia-img").dataset.src = ref;
    $("copiar-ref").title = `Es ${sig.referencia_de}. Pégala en Flow con Ctrl+V como referencia.`;
  }
}

let servidorActual = "http://127.0.0.1:8000";

// El portapapeles solo acepta PNG: la imagen base se pasa por un lienzo.
$("copiar-ref").addEventListener("click", async () => {
  try {
    const r = await fetch($("referencia-img").dataset.src);
    const bmp = await createImageBitmap(await r.blob());
    const lienzo = new OffscreenCanvas(bmp.width, bmp.height);
    lienzo.getContext("2d").drawImage(bmp, 0, 0);
    const png = await lienzo.convertToBlob({ type: "image/png" });
    await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
    $("copiar-ref").textContent = "Copiada: Ctrl+V en Flow";
  } catch (_) {
    $("copiar-ref").textContent = "No se pudo copiar";
  }
  setTimeout(() => { $("copiar-ref").textContent = "Copiar imagen base"; }, 2000);
});

async function probar(silencioso = false) {
  if (!silencioso) pintarEstado("Probando…");
  const r = await chrome.runtime.sendMessage({ tipo: "probar" });
  if (r?.ok) await chrome.storage.local.set({ error: "" });
  pintarEstado(r?.ok ? "ok" : r?.error, "");
  pintarEscena(r?.sesion);
}

$("copiar").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("escena-prompt").textContent || "");
  $("copiar").textContent = "Copiada";
  setTimeout(() => { $("copiar").textContent = "Copiar instrucción"; }, 1500);
});

$("guardar").addEventListener("click", async () => {
  await chrome.storage.local.set({
    servidor: $("servidor").value.trim() || "http://127.0.0.1:8000",
    codigo: $("codigo").value.trim(),
    activo: $("activo").checked,
  });
  await probar();
});

$("activo").addEventListener("change", () => chrome.storage.local.set({ activo: $("activo").checked }));

$("visibles").addEventListener("click", async () => {
  const [pestana] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!pestana?.url?.startsWith("https://labs.google/")) {
    pintarEstado("", "Abre Google Flow (labs.google) en esta pestaña para enviar sus clips.");
    return;
  }
  const r = await chrome.tabs.sendMessage(pestana.id, { tipo: "enviar-visibles" }).catch(() => null);
  pintarEstado("ok");
  $("ultima").textContent = r ? `Enviando ${r.enviadas} de la pantalla…` : "Recarga la pestaña de Flow y vuelve a probar.";
});

cargar().then(() => probar(true));
setInterval(() => probar(true), 3000);
