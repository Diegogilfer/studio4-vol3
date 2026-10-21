"""Tareas programadas de Studio 4 (las lanza el Programador de tareas de Windows; ver scripts/programar_tareas.ps1).

    python scripts/tareas.py ideas    # las 3 ideas del día del canal activo, listas al abrir el panel
    python scripts/tareas.py semana   # resumen semanal del canal en «Vídeos\\STUDIO 4\\Informes»

No publican nada ni gastan en voz o imagen. «ideas» usa lo mismo que el panel cada mañana (YouTube en lectura y
DeepSeek o Gemini para escribir las ideas). «semana» solo lee YouTube. Lo que pasa queda en
producciones/_informes/tareas.log.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from studio4 import canales, carpetas, config, ideas, youtube  # noqa: E402

INFORMES = config.PRODUCCIONES / "_informes"
logger = logging.getLogger("studio4.tareas")


def tarea_ideas() -> str:
    c = canales.activo()
    hechas = json.loads(ideas._archivo(c["id"]).read_text(encoding="utf-8")) if ideas._archivo(c["id"]).exists() else {}
    if hechas.get("fecha") == ideas._hoy() and hechas.get("ideas"):
        return f"{c['nombre']}: las ideas de hoy ya estaban ({len(hechas['ideas'])})"
    datos = ideas.generar_diarias(c["id"])
    return f"{c['nombre']}: {len(datos['ideas'])} ideas del día listas"


def _num(n: int | float) -> str:
    return f"{int(n):,}".replace(",", ".")


def tarea_semana() -> str:
    """Suscriptores, vistas y los vídeos que más crecieron desde el último resumen (sin gastar cupo de búsqueda)."""
    c = canales.activo()
    datos = youtube.canal()
    INFORMES.mkdir(parents=True, exist_ok=True)
    hoy = time.strftime("%Y-%m-%d")
    previos = sorted(INFORMES.glob(f"canal_{c['id']}_*.json"))
    antes = json.loads(previos[-1].read_text(encoding="utf-8")) if previos else None
    (INFORMES / f"canal_{c['id']}_{hoy}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    vistos = {v["id"]: v for v in (datos.get("mas_vistos") or []) + (datos.get("recientes") or [])}
    previos_v = {v["id"]: v for v in ((antes or {}).get("mas_vistos") or []) + ((antes or {}).get("recientes") or [])}
    crecen = sorted(((v["vistas"] - previos_v.get(i, {}).get("vistas", 0), v) for i, v in vistos.items()),
                    key=lambda x: -x[0])[:5]
    lineas = [f"# Resumen semanal · {datos['nombre']} · {hoy}", ""]
    if antes:
        lineas += [f"- Suscriptores: **{_num(datos['suscriptores'])}** ({datos['suscriptores'] - antes['suscriptores']:+d} desde el último resumen)",
                   f"- Vistas totales: **{_num(datos['vistas'])}** ({datos['vistas'] - antes['vistas']:+,d} desde el último resumen)".replace(",", "."),
                   f"- Vídeos publicados: {datos['videos']} ({datos['videos'] - antes['videos']:+d})"]
    else:
        lineas += [f"- Suscriptores: **{_num(datos['suscriptores'])}**", f"- Vistas totales: **{_num(datos['vistas'])}**",
                   f"- Vídeos publicados: {datos['videos']}", "", "_Primer resumen: la semana que viene verás cuánto creció._"]
    lineas += ["", "## Los que más crecieron" if antes else "## Los más vistos", ""]
    for delta, v in crecen:
        extra = f" (+{_num(delta)} esta semana)" if antes else ""
        lineas.append(f"- {v.get('titulo', v['id'])}: {_num(v['vistas'])} vistas{extra}")
    lineas += ["", "Siguiente vídeo: repite el tema o el formato del que más creció; pide a Claude que lo compare con las ideas del día."]
    carpeta = carpetas.RAIZ_USUARIO / "Informes"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"Resumen semanal {hoy}.md"
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return f"{datos['nombre']}: resumen en {destino}"


def main() -> int:
    INFORMES.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=INFORMES / "tareas.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    tareas = {"ideas": tarea_ideas, "semana": tarea_semana}
    if orden not in tareas:
        print(__doc__)
        return 2
    try:
        res = tareas[orden]()
    except Exception:  # noqa: BLE001 - queda en el registro para verlo luego
        logger.exception("Tarea %s falló", orden)
        return 1
    logger.info("%s: %s", orden, res)
    print(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
