// STUDIO #4 · emparejar con un clic (Diego, 2026-10-07: «botón que redirige a conexión inmediata,
// no copiar y pegar»). Corre SOLO en la página local /flow/emparejar de tu STUDIO #4: toma el código
// que trae la dirección, el fondo lo comprueba contra ese mismo STUDIO #4 y, si vale, lo guarda.
(() => {
  document.documentElement.dataset.studio4Extension = "1";
  const avisar = (estado, error = "") =>
    window.postMessage({ studio4: "extension", estado, error }, location.origin);
  async function emparejar() {
    const codigo = new URLSearchParams(location.hash.slice(1)).get("c") || "";
    if (!codigo) { avisar("sin-codigo"); return; }
    try {
      const r = await chrome.runtime.sendMessage({ tipo: "emparejar", codigo, servidor: location.origin });
      avisar(r?.ok ? "emparejada" : "error", r?.error || "");
    } catch (e) {
      avisar("error", String(e?.message || e));
    }
  }
  emparejar();
  // Otro clic en «Conectar» con esta pestaña abierta solo cambia el «#»: se vuelve a emparejar.
  window.addEventListener("hashchange", () => { if (location.hash.includes("c=")) emparejar(); });
})();
