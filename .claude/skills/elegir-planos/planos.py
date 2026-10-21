"""Herramientas para elegir los planos de un vídeo de Studio 4 por lo que dice cada frase.

    python .claude/skills/elegir-planos/planos.py hojas FUENTE [FUENTE...]   # hojas de contacto numeradas
    python .claude/skills/elegir-planos/planos.py ver FUENTE 120,124,148     # 3 fotogramas de cada plano
    python .claude/skills/elegir-planos/planos.py cobertura VIDEO_ID         # ¿cada plano da para su frase?

Las hojas y fotogramas se guardan en producciones/_hojas/ (fuera de git). Leen el banco de clips
(producciones/_fuentes_video/*.banco.json), así que la fuente tiene que estar preparada en el panel.
Ejecutar desde la raíz del proyecto (C:\\Users\\Lenovo\\studio4-vol3).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from studio4 import config, extractor, montaje  # noqa: E402

SALIDA = config.PRODUCCIONES / "_hojas"
ANCHO, ALTO, COLUMNAS, FILAS = 240, 135, 8, 7


def _letra(tam: int):
    return ImageFont.truetype("arialbd.ttf", tam)


def hojas(fid: str) -> list[Path]:
    """Todas las miniaturas de una fuente, 56 por hoja: número · duración. Verde ≥3 s, amarillo corto, rojo
    «pobre» (oscuro, plano, ESRB…): se puede usar, pero míralo antes."""
    meta = montaje.fuente(fid)
    planos, f, salida = meta["planos"], _letra(20), []
    SALIDA.mkdir(parents=True, exist_ok=True)
    por_hoja = COLUMNAS * FILAS
    for h in range(0, len(planos), por_hoja):
        hoja = Image.new("RGB", (ANCHO * COLUMNAS, ALTO * FILAS), "black")
        for i, pl in enumerate(planos[h:h + por_hoja]):
            n = h + i + 1
            im = Image.open(extractor.CACHE / f"{fid}_planos" / f"{n:03d}.jpg").convert("RGB").resize((ANCHO, ALTO))
            d = ImageDraw.Draw(im)
            dur = pl["fin"] - pl["ini"]
            color = "red" if pl.get("pobre") else ("lime" if dur >= 3 else "yellow")
            texto = f"{n} · {dur:.1f}s"
            d.rectangle([0, 0, d.textlength(texto, font=f) + 10, 26], fill="black")
            d.text((5, 2), texto, fill=color, font=f)
            hoja.paste(im, ((i % COLUMNAS) * ANCHO, (i // COLUMNAS) * ALTO))
        ruta = SALIDA / f"{fid}_{h // por_hoja + 1:02d}.jpg"
        hoja.save(ruta, quality=85)
        salida.append(ruta)
    return salida


def ver(fid: str, numeros: list[int]) -> Path:
    """Tres fotogramas (10 %, 50 %, 90 %) de cada plano: para ver si se mueve, si tiene letreros o texto encima."""
    meta = montaje.fuente(fid)
    f = _letra(22)
    hoja = Image.new("RGB", (400 * 3, 225 * len(numeros)), "black")
    SALIDA.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(numeros):
        pl = meta["planos"][n - 1]
        for j, fr in enumerate((0.1, 0.5, 0.9)):
            t = pl["ini"] + (pl["fin"] - pl["ini"]) * fr
            tmp = SALIDA / f"_tmp_{n}_{j}.jpg"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(extractor.CACHE / meta["baja"]),
                            "-frames:v", "1", "-vf", "scale=400:225", str(tmp)], stdin=subprocess.DEVNULL)
            im = Image.open(tmp).convert("RGB")
            ImageDraw.Draw(im).text((6, 4), f"{n} @{fr:.0%}", fill="yellow", font=f)
            hoja.paste(im, (j * 400, i * 225))
            tmp.unlink()
    ruta = SALIDA / f"{fid}_ver_{'-'.join(map(str, numeros))[:60]}.jpg"
    hoja.save(ruta, quality=85)
    return ruta


def cobertura(mid: str) -> list[str]:
    """Las frases cuyo plano (más sus «mas») no da para lo que dura la frase: se estiran o se congelan."""
    p = montaje.cargar(mid)
    t = montaje._tiempos_estimados(p)
    tramos = [(0.0 if k == 0 else a, t[k + 1][0] if k + 1 < len(t) else b + 1.2) for k, (a, b) in enumerate(t)]
    avisos = []
    for k, (f, (a, b)) in enumerate(zip(p["frases"], tramos)):
        if f.get("panel"):
            continue
        if not f.get("clip"):
            avisos.append(f"frase {f['n']}: SIN PLANO")
            continue
        meta = montaje.fuente(f["clip"]["fuente"])
        nums = [f["clip"]["plano"], *f["clip"].get("mas", [])]
        largo = sum(meta["planos"][x - 1]["fin"] - meta["planos"][x - 1]["ini"] for x in nums)
        nuevo = k > 0 and f["bloque"] != p["frases"][k - 1]["bloque"]
        d = (b - a) - (montaje.TRANSICION if nuevo and (b - a) > montaje.TRANSICION + 0.8 else 0)
        if largo < d:
            como = "se estira" if largo * montaje.LENTO_MAX >= d else "SE CONGELA: añade un plano a «mas»"
            avisos.append(f"frase {f['n']}: necesita {d:.1f} s, hay {largo:.1f} s ({como})")
    return avisos


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3 or sys.argv[1] not in ("hojas", "ver", "cobertura"):
        print(__doc__)
        return 2
    orden = sys.argv[1]
    if orden == "hojas":
        for fid in sys.argv[2:]:
            for r in hojas(fid):
                print(r)
    elif orden == "ver":
        print(ver(sys.argv[2], [int(x) for x in sys.argv[3].split(",")]))
    else:
        avisos = cobertura(sys.argv[2])
        print("\n".join(avisos) if avisos else "Todas las frases tienen imagen de sobra.")
        return 1 if any("CONGELA" in a or "SIN PLANO" in a for a in avisos) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
