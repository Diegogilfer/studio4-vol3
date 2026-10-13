"""Fase 5 · Render local con FFmpeg (gratis): cada escena se ajusta a su trozo de voz, se unen y se
mezclan con la locución, el sonido ambiente de Veo y los subtítulos."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from . import config, medios, registro, subtitulos

logger = logging.getLogger("studio4.render")
COLA_FINAL = 0.6  # segundos de imagen tras la última palabra


def _encuadre(ancho: int, alto: int) -> str:
    return f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},setsar=1"


def _segmento_video(origen: Path, destino: Path, d: float, ancho: int, alto: int) -> None:
    inf = medios.info(origen)
    c = max(0.1, inf["duracion"])
    lento = min(max(d / c, 1.0), config.CAMARA_LENTA_MAX)
    vf = [f"setpts={lento:.4f}*PTS"] if lento > 1.001 else []
    vf += [_encuadre(ancho, alto), f"fps={config.FPS}"]
    if c * lento < d:
        vf.append(f"tpad=stop_mode=clone:stop_duration={d - c * lento + 0.2:.3f}")  # congela el último fotograma

    entradas = ["-i", str(origen)]
    if inf["audio"] and config.VOLUMEN_AMBIENTE > 0:
        af = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={d:.3f},afade=t=out:st={max(0, d - 0.3):.3f}:d=0.3[a]"
    else:
        entradas += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        af = "[1:a]anull[a]"
    medios.ffmpeg(
        *entradas, "-filter_complex", f"[0:v]{','.join(vf)}[v];{af}", "-map", "[v]", "-map", "[a]",
        "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(destino),
    )


def _segmento_imagen(origen: Path, destino: Path, d: float, ancho: int, alto: int) -> None:
    """Imagen fija → acercamiento lento (Ken Burns), sin saltos: se escala a 2x antes del zoompan."""
    frames = int(d * config.FPS) + 1
    vf = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,crop={ancho * 2}:{alto * 2},"
          f"zoompan=z='min(1+0.12*on/{frames},1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={ancho}x{alto}:fps={config.FPS},setsar=1")
    medios.ffmpeg(
        "-loop", "1", "-i", str(origen), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-vf", vf, "-map", "0:v", "-map", "1:a", "-t", f"{d:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", str(destino),
    )


def vista_subtitulos(p: dict[str, Any], carpeta: Path, ajustes: dict[str, Any] | None = None) -> Path:
    """Un fotograma real del vídeo con el rótulo inicial y la primera línea de subtítulos, con los ajustes
    actuales (o los que se pasen para comparar). Tarda menos de un segundo: sirve para decidir antes de renderizar."""
    fmt = config.FORMATOS[p["formato"]]
    ancho, alto = fmt["ancho"], fmt["alto"]
    trabajo = carpeta / "render"
    trabajo.mkdir(exist_ok=True)
    fondo = trabajo / "vista_fondo.jpg"

    # Fondo: el plano de la escena 1 (la toma elegida) o, si aún no hay clips, un degradado oscuro.
    esc = p["escenas"][0] if p.get("escenas") else None
    toma = esc["tomas"][esc["elegida"]] if esc and esc.get("elegida") is not None else None
    if toma and (carpeta / toma["archivo"]).exists():
        if toma["tipo"] == "video":
            medios.ffmpeg("-ss", "1.0", "-i", str(carpeta / toma["archivo"]), "-frames:v", "1",
                          "-vf", _encuadre(ancho, alto), "-q:v", "3", str(fondo))
        else:
            medios.ffmpeg("-i", str(carpeta / toma["archivo"]), "-frames:v", "1", "-vf", _encuadre(ancho, alto), "-q:v", "3", str(fondo))
    else:
        medios.ffmpeg("-f", "lavfi", "-i", f"gradients=s={ancho}x{alto}:c0=0x1b1e2a:c1=0x07080d:duration=1",
                      "-frames:v", "1", "-q:v", "3", str(fondo))

    # Primera línea de la voz, con su segunda palabra resaltada (así se ve el color de resalte).
    palabras = (p.get("voz") or {}).get("palabras") or [
        {"palabra": w, "ini": 0.0, "fin": 0.0} for w in (esc["texto_voz"].split() if esc else ["Así", "se", "verán", "tus", "subtítulos"])]
    muestra = palabras[:6]
    ritmo = [{"palabra": w["palabra"], "ini": 0.6 * (i - 1) - 0.3, "fin": 0.6 * (i - 1) + 0.3} for i, w in enumerate(muestra)]
    ass = subtitulos.construir(ritmo, trabajo / "vista.ass", ancho, alto, {**(p.get("subtitulos") or {}), **(ajustes or {})},
                               gancho=esc.get("texto_pantalla", "") if esc else "", segundos_gancho=5)
    salida = trabajo / "vista_subtitulos.jpg"
    medios.ffmpeg("-loop", "1", "-i", fondo.name, "-vf", f"ass={ass.name}", "-frames:v", "1", "-q:v", "3", salida.name,
                  cwd=trabajo)
    return salida


def renderizar(p: dict[str, Any], carpeta: Path, avisar: Callable[[str, int], None] = lambda *_: None) -> Path:
    voz = p.get("voz") or {}
    if not voz.get("archivo"):
        raise RuntimeError("Falta la voz: genérala antes de renderizar.")
    if len(voz["escenas"]) != len(p["escenas"]):
        raise RuntimeError("La voz no corresponde a las escenas actuales: vuelve a generarla.")
    faltan = [e["orden"] for e in p["escenas"] if e.get("elegida") is None]
    if faltan:
        raise RuntimeError(f"Faltan clips de Flow en las escenas: {', '.join(map(str, faltan))}.")

    fmt = config.FORMATOS[p["formato"]]
    ancho, alto = fmt["ancho"], fmt["alto"]
    trabajo = carpeta / "render"
    trabajo.mkdir(exist_ok=True)

    lista = []
    n = len(p["escenas"])
    for i, (esc, t) in enumerate(zip(p["escenas"], voz["escenas"])):
        avisar(f"Ajustando escena {i + 1} de {n} a su voz", 10 + int(70 * i / n))
        d = t["fin"] - t["ini"] + (COLA_FINAL if i == n - 1 else 0)
        toma = esc["tomas"][esc["elegida"]]
        seg = trabajo / f"seg_{esc['orden']:02d}.mp4"
        origen = carpeta / toma["archivo"]
        if not origen.exists():
            raise RuntimeError(f"Escena {esc['orden']}: falta el archivo de la toma elegida; elige otra o súbela de nuevo.")
        hacer = _segmento_video if toma["tipo"] == "video" else _segmento_imagen
        try:
            hacer(origen, seg, d, ancho, alto)
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(f"Escena {esc['orden']}: el clip no se pudo procesar ({str(e)[-300:]}). Elige otra toma.") from e
        lista.append(seg)

    avisar("Uniendo escenas", 82)
    concat = trabajo / "lista.txt"
    concat.write_text("".join(f"file '{s.as_posix()}'\n" for s in lista), encoding="utf-8")
    cuerpo = trabajo / "cuerpo.mp4"
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(cuerpo))

    avisar("Mezclando voz, ambiente y subtítulos", 90)
    ass = subtitulos.construir(voz["palabras"], trabajo / "subtitulos.ass", ancho, alto, p.get("subtitulos"),
                               gancho=p["escenas"][0].get("texto_pantalla", ""))
    total = voz["duracion"] + COLA_FINAL
    mezcla = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo[voz];"
              f"[0:a]volume={config.VOLUMEN_AMBIENTE}[amb];"
              f"[voz][amb]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    final = carpeta / "final.mp4"
    # El filtro ass lee la ruta relativa a la carpeta de trabajo: evita escapar «C:\» en Windows.
    medios.ffmpeg(
        "-i", str(cuerpo), "-i", str(carpeta / voz["archivo"]),
        "-filter_complex", f"[0:v]ass={ass.name}[v];{mezcla}", "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(final),
        cwd=trabajo,
    )
    registro.apuntar("Render local (FFmpeg)", f"{n} escenas · {fmt['aspecto']} · {total:.1f}s", produccion=p["id"])
    return final
