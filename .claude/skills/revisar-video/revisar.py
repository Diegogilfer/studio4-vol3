"""Control de calidad de un vídeo de Studio 4 desde la consola (la lógica vive en studio4/calidad.py).

Uso:
    python .claude/skills/revisar-video/revisar.py RUTA/final_16x9.mp4 [--proyecto RUTA/proyecto.json]

Sale con código 1 si hay fallos (para usarlo en pruebas).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from studio4 import calidad  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video", type=Path)
    ap.add_argument("--proyecto", type=Path, default=None, help="proyecto.json del vídeo (para los subtítulos)")
    a = ap.parse_args()
    palabras, voz = None, None
    if a.proyecto and a.proyecto.exists():
        p = json.loads(a.proyecto.read_text(encoding="utf-8"))
        v = p.get("voz") or {}
        palabras = (v.get("pausas") or v).get("palabras")
        voz = a.proyecto.parent / "render" / "voz_pausas.wav"
    r = calidad.revisar(a.video, palabras, voz)
    print(f"{a.video.name} · {r['duracion']} s · {r['resolucion']} · {r['lufs']:.1f} LUFS · {len(r['cortes'])} cortes")
    for t in r["avisos"]:
        print("  aviso:", t)
    if r["fallos"]:
        print("NO SE ENTREGA. Fallos:")
        for t in r["fallos"]:
            print("  ✗", t)
        return 1
    print("OK: sin congelados, huecos ni subtítulos sueltos")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
