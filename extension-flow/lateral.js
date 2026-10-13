// Panel lateral de Chrome: STUDIO #4 (vista /lateral) al lado de Google Flow, en la misma ventana.
const POR_DEFECTO = "http://127.0.0.1:8000";
const marco = document.getElementById("studio");
const aviso = document.getElementById("sin-studio");
const direccion = document.getElementById("direccion");
direccion.textContent = "Conectando con STUDIO #4…";
aviso.hidden = false;

// Si leer los ajustes se atasca, se usa la dirección de siempre: el panel nunca se queda en negro.
function servidorGuardado() {
  return Promise.race([
    chrome.storage.local.get("servidor").then((d) => d.servidor || POR_DEFECTO).catch(() => POR_DEFECTO),
    new Promise((ok) => setTimeout(() => ok(POR_DEFECTO), 1000)),
  ]);
}

async function conectar() {
  const base = (await servidorGuardado()).replace(/\/+$/, "");
  try {
    const r = await fetch(`${base}/api/estado`, { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    if (marco.hidden) { marco.src = `${base}/lateral`; marco.hidden = false; aviso.hidden = true; }
  } catch (_) {
    marco.hidden = true; marco.removeAttribute("src"); aviso.hidden = false;
    direccion.textContent = `Dirección: ${base}`;
  }
}

conectar();
setInterval(conectar, 4000);
