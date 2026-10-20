"""Fase 5 · Render local con FFmpeg (gratis): cada escena se ajusta a su trozo de voz, se unen y se
mezclan con la locución, el sonido ambiente de Veo y los subtítulos."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from . import config, medios, registro, sonidos, subtitulos

logger = logging.getLogger("studio4.render")
COLA_FINAL = 0.6  # segundos de imagen tras la última palabra
ENTRADA = 2.0     # carátula de entrada (título y marca) antes de que empiece la voz


# Edición: se aplica a cada trozo por separado, así la duración no cambia y la voz sigue sincronizada.
TRANSICIONES = {"corte": "Corte", "fundido": "Fundido a negro", "destello": "Destello"}
EFECTOS = {"ninguno": "Ninguno", "cine": "Color cine", "grano": "Grano de película", "byn": "Blanco y negro", "zoom": "Zoom suave"}
EDICION_POR_DEFECTO = {"transicion": "corte", "efecto": "ninguno", "caratula": True, "inicio": 0.0, "final": 0.0,
                       "musica": True}
# Movimiento de cámara sobre las imágenes fijas, distinto en cada escena (parallax 2.5D con FFmpeg, gratis):
# acercar, alejar, desplazar a la derecha y a la izquierda. Antes todas hacían el mismo zoom.
MOVIMIENTOS = ("acercar", "derecha", "alejar", "izquierda")
FUNDIDO = 0.22


def edicion_de(p: dict[str, Any]) -> dict[str, Any]:
    return {**EDICION_POR_DEFECTO, "caratula": p.get("entrada", True), **(p.get("edicion") or {})}


def _acabado(ed: dict[str, Any], d: float, primero: bool, ultimo: bool, video: bool, ancho: int, alto: int) -> list[str]:
    """Filtros de efecto y transición para un trozo de `d` segundos."""
    f: list[str] = []
    efecto = ed.get("efecto", "ninguno")
    if efecto == "cine":
        f.append("eq=contrast=1.06:saturation=1.12,vignette=PI/5")
    elif efecto == "grano":
        f.append("noise=alls=10:allf=t+u")
    elif efecto == "byn":
        f.append("hue=s=0,eq=contrast=1.1")
    elif efecto == "zoom" and video:   # las imágenes ya llevan su acercamiento
        frames = int(d * config.FPS) + 1
        f.append(f"zoompan=z='min(1+0.06*on/{frames},1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={ancho}x{alto}:fps={config.FPS}")
    t = ed.get("transicion", "corte")
    if t == "fundido" and d > 4 * FUNDIDO:
        if not primero:
            f.append(f"fade=t=in:st=0:d={FUNDIDO}")
        if not ultimo:
            f.append(f"fade=t=out:st={d - FUNDIDO:.3f}:d={FUNDIDO}")
    elif t == "destello" and not primero:
        f.append("fade=t=in:st=0:d=0.25:color=white")
    return f


def recortar_final(video: Path, inicio: float, final: float) -> None:
    """Quita segundos del principio y del final del vídeo montado (si hay algo que quitar)."""
    inicio, final = max(0.0, float(inicio or 0)), max(0.0, float(final or 0))
    if inicio < 0.05 and final < 0.05:
        return
    total = medios.duracion(video)
    queda = total - inicio - final
    if queda < 3:
        raise ValueError(f"Con ese recorte quedarían {max(0, queda):.1f} s de vídeo.")
    tmp = video.with_name(video.stem + "_recortado.mp4")
    medios.ffmpeg("-ss", f"{inicio:.3f}", "-i", str(video), "-t", f"{queda:.3f}", "-c:v", "libx264", "-preset", "medium",
                  "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp))
    tmp.replace(video)


def _es_tarjeta(esc: dict[str, Any]) -> bool:
    """La toma elegida es una tarjeta de diseño: ya lleva su titular, así que no se le pone el rótulo de gancho."""
    return esc.get("elegida") is not None and esc["tomas"][esc["elegida"]].get("origen") == "tarjeta"


def _encuadre(ancho: int, alto: int) -> str:
    return f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},setsar=1"


def musica_de(p: dict[str, Any]) -> Path | None:
    """La música de fondo: la que eligió el autor (`musica_pista`) o la de su carpeta que más encaja con el vídeo.
    Ninguna si el autor la quitó en la edición o si su carpeta de música está vacía."""
    from . import carpetas
    if not edicion_de(p).get("musica", True):
        return None
    propia = p.get("musica_pista")
    if propia and Path(propia).exists():
        return Path(propia)
    return carpetas.elegir_musica(" ".join(str(p.get(k) or "") for k in ("tema", "titulo", "estilo", "tono")))


def _mezcla(voz: str, ambiente: float, total: float, musica: Path | None, desde: float = 0.0) -> tuple[list[str], str]:
    """Entradas extra y filtro de audio: voz + ambiente (+ música que baja sola cuando habla la voz).
    `voz` es la cadena de filtros de la entrada 1 (voz) y `desde` el segundo de la pista en que empieza la música."""
    if not musica:
        return [], (f"[1:a]{voz}[voz];[0:a]volume={ambiente}[amb];"
                    f"[voz][amb]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    extra = ["-stream_loop", "-1", "-ss", f"{desde:.3f}", "-i", str(musica)]
    fin = max(0.0, total - 2.0)
    filtro = (f"[1:a]{voz},asplit=2[voz][llave];"
              f"[0:a]volume={ambiente}[amb];"
              f"[2:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={config.VOLUMEN_MUSICA},"
              f"afade=t=in:st=0:d=1,afade=t=out:st={fin:.3f}:d=2[mus0];"
              f"[mus0][llave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[mus];"
              f"[voz][amb][mus]amix=inputs=3:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    return extra, filtro


def _segmento_video(origen: Path, destino: Path, d: float, ancho: int, alto: int, acabado: list[str] | tuple = ()) -> None:
    inf = medios.info(origen)
    c = max(0.1, inf["duracion"])
    lento = min(max(d / c, 1.0), config.CAMARA_LENTA_MAX)
    vf = [f"setpts={lento:.4f}*PTS"] if lento > 1.001 else []
    vf += [_encuadre(ancho, alto), f"fps={config.FPS}"]
    if c * lento < d:
        vf.append(f"tpad=stop_mode=clone:stop_duration={d - c * lento + 0.2:.3f}")  # congela el último fotograma
    vf += list(acabado)

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


def _zoompan(movimiento: str, frames: int, ancho: int, alto: int) -> str:
    """El filtro de cámara de una imagen fija (sin saltos: la imagen va escalada a 2x antes)."""
    centro_y = "ih/2-(ih/zoom/2)"
    if movimiento in ("derecha", "izquierda"):   # paneo lateral con algo de zoom: sensación de profundidad
        signo = "+" if movimiento == "derecha" else "-"
        z = "1.10"
        x = f"(iw-iw/zoom)/2{signo}(iw-iw/zoom)/2*(on/{frames}-0.5)*1.6"
    elif movimiento == "alejar":
        z = f"max(1.12-0.12*on/{frames},1)"
        x = "iw/2-(iw/zoom/2)"
    else:
        z = f"min(1+0.12*on/{frames},1.12)"
        x = "iw/2-(iw/zoom/2)"
    return f"zoompan=z='{z}':x='{x}':y='{centro_y}':d={frames}:s={ancho}x{alto}:fps={config.FPS}"


def _segmento_imagen(origen: Path, destino: Path, d: float, ancho: int, alto: int, acabado: list[str] | tuple = (),
                     movimiento: str = "acercar") -> None:
    """Imagen fija → movimiento lento de cámara (acercar, alejar o paneo lateral)."""
    frames = int(d * config.FPS) + 1
    vf = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,crop={ancho * 2}:{alto * 2},"
          f"{_zoompan(movimiento, frames, ancho, alto)},setsar=1")
    vf = ",".join([vf, *acabado])
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
    ajustes_vista = {**(p.get("subtitulos") or {}), **(ajustes or {})}
    if ajustes_vista.get("estilo") == "cine":   # en cine se ve la frase entera, como quedará
        ritmo = [{"palabra": w["palabra"], "ini": 0.0, "fin": 3.0} for w in palabras[:12]]
    ejemplo = sonidos.leer(trabajo / "sonidos.json")[:1] or [{"ini": 0.0, "fin": 3.0, "texto": "Música tensa"}]
    ass = subtitulos.construir(ritmo, trabajo / "vista.ass", ancho, alto, ajustes_vista,
                               gancho=esc.get("texto_pantalla", "") if esc else "", segundos_gancho=5,
                               sonidos=[{**ejemplo[0], "ini": 0.0, "fin": 3.0}])
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
    entrada = 0.0
    ed = edicion_de(p)
    if ed["caratula"]:   # la carátula: si no se puede dibujar, el vídeo sale igual, sin ella
        try:
            from . import canales, tarjetas
            avisar("Dibujando la carátula de entrada", 6)
            caratula = tarjetas.dibujar_caratula(p, carpeta, canales.de_produccion(p)["nombre"])
            _segmento_imagen(caratula, trabajo / "seg_00.mp4", ENTRADA, ancho, alto)
            lista.append(trabajo / "seg_00.mp4")
            entrada = ENTRADA
        except Exception as e:  # noqa: BLE001
            logger.warning("Sin carátula de entrada: %s", e)
    n = len(p["escenas"])
    for i, (esc, t) in enumerate(zip(p["escenas"], voz["escenas"])):
        avisar(f"Ajustando escena {i + 1} de {n} a su voz", 10 + int(70 * i / n))
        d = t["fin"] - t["ini"] + (COLA_FINAL if i == n - 1 else 0)
        toma = esc["tomas"][esc["elegida"]]
        seg = trabajo / f"seg_{esc['orden']:02d}.mp4"
        origen = carpeta / toma["archivo"]
        if not origen.exists():
            raise RuntimeError(f"Escena {esc['orden']}: falta el archivo de la toma elegida; elige otra o súbela de nuevo.")
        acabado = _acabado(ed, d, primero=i == 0 and not entrada, ultimo=i == n - 1, video=toma["tipo"] == "video",
                           ancho=ancho, alto=alto)
        try:
            if toma["tipo"] == "video":
                _segmento_video(origen, seg, d, ancho, alto, acabado)
            else:
                _segmento_imagen(origen, seg, d, ancho, alto, acabado, movimiento=MOVIMIENTOS[i % len(MOVIMIENTOS)])
        except (RuntimeError, ValueError) as e:
            raise RuntimeError(f"Escena {esc['orden']}: el clip no se pudo procesar ({str(e)[-300:]}). Elige otra toma.") from e
        lista.append(seg)

    avisar("Uniendo escenas", 82)
    concat = trabajo / "lista.txt"
    concat.write_text("".join(f"file '{s.as_posix()}'\n" for s in lista), encoding="utf-8")
    cuerpo = trabajo / "cuerpo.mp4"
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(cuerpo))

    total = entrada + voz["duracion"] + COLA_FINAL
    ambiente = 0.0 if p.get("version") == "importado" else config.VOLUMEN_AMBIENTE
    ruidos: list[dict[str, Any]] = []
    if (p.get("subtitulos") or {}).get("sonidos", subtitulos.POR_DEFECTO["sonidos"]):
        avisar("Escuchando el sonido para subtitular los ruidos", 86)
        ruidos = sonidos.detectar(cuerpo, total, produccion=p["id"])
    sonidos.guardar(trabajo / "sonidos.json", ruidos)   # Reels y Shorts los reutilizan sin volver a escuchar

    avisar("Mezclando voz, ambiente y subtítulos", 90)
    palabras = [{**w, "ini": w["ini"] + entrada, "fin": w["fin"] + entrada} for w in voz["palabras"]]
    ass = subtitulos.construir(palabras, trabajo / "subtitulos.ass", ancho, alto, p.get("subtitulos"),
                               gancho="" if _es_tarjeta(p["escenas"][0]) else p["escenas"][0].get("texto_pantalla", ""), sonidos=ruidos,
                               inicio_gancho=entrada)
    retraso = int(entrada * 1000)
    extra, mezcla = _mezcla(f"aresample=48000,aformat=channel_layouts=stereo,adelay={retraso}:all=1", ambiente, total,
                            musica_de(p))
    final = carpeta / "final.mp4"
    # El filtro ass lee la ruta relativa a la carpeta de trabajo: evita escapar «C:\» en Windows.
    medios.ffmpeg(
        "-i", str(cuerpo), "-i", str(carpeta / voz["archivo"]), *extra,
        "-filter_complex", f"[0:v]ass={ass.name}[v];{mezcla}", "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(final),
        cwd=trabajo,
    )
    recortar_final(final, ed.get("inicio", 0.0), ed.get("final", 0.0))
    registro.apuntar("Render local (FFmpeg)", f"{n} escenas · {fmt['aspecto']} · {total:.1f}s", produccion=p["id"])
    return final


def recorte(p: dict[str, Any], carpeta: Path, desde: int, hasta: int, destino: Path, ancho: int = 1080, alto: int = 1920,
            gancho: str = "", avisar: Callable[[str, int], None] = lambda *_: None) -> Path:
    """Un trozo del vídeo (de la escena `desde` a la `hasta`, ambas incluidas) montado en otro formato —vertical
    para Reels y Shorts—, con su voz, ambiente y subtítulos ajustados al trozo y un rótulo propio al empezar."""
    voz = p["voz"]
    n = len(p["escenas"])
    desde, hasta = max(1, desde), min(n, hasta)
    if desde > hasta:
        raise ValueError("Recorte vacío")
    ini = voz["escenas"][desde - 1]["ini"]
    fin = voz["escenas"][hasta - 1]["fin"] + (COLA_FINAL if hasta == n else 0.35)
    trabajo = carpeta / "render" / f"recorte_{destino.stem}"
    trabajo.mkdir(parents=True, exist_ok=True)

    lista = []
    for k, orden in enumerate(range(desde, hasta + 1)):
        avisar(f"{destino.stem}: escena {orden}", 10 + int(60 * k / (hasta - desde + 1)))
        esc, t = p["escenas"][orden - 1], voz["escenas"][orden - 1]
        toma = esc["tomas"][esc["elegida"]]
        d = t["fin"] - t["ini"] + (COLA_FINAL if orden == n else 0.4 if orden == hasta else 0)
        seg = trabajo / f"seg_{orden:02d}.mp4"
        acabado = _acabado(edicion_de(p), d, primero=orden == desde, ultimo=orden == hasta, video=toma["tipo"] == "video",
                           ancho=ancho, alto=alto)
        (_segmento_video if toma["tipo"] == "video" else _segmento_imagen)(carpeta / toma["archivo"], seg, d, ancho, alto, acabado)
        lista.append(seg)
    concat = trabajo / "lista.txt"
    concat.write_text("".join(f"file '{x.as_posix()}'\n" for x in lista), encoding="utf-8")
    cuerpo = trabajo / "cuerpo.mp4"
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(cuerpo))

    largo = fin - ini
    palabras = [{**w, "ini": w["ini"] - ini, "fin": w["fin"] - ini} for w in voz["palabras"]
                if w["ini"] >= ini - 0.05 and w["ini"] < fin]
    ambiente = 0.0 if p.get("version") == "importado" else config.VOLUMEN_AMBIENTE
    ruidos = [{**s, "ini": s["ini"] - ini, "fin": min(s["fin"], fin) - ini}
              for s in sonidos.leer(carpeta / "render" / "sonidos.json") if ini <= s["ini"] < fin - 0.5]
    ass = subtitulos.construir(palabras, trabajo / "subtitulos.ass", ancho, alto, p.get("subtitulos"),
                               gancho="" if _es_tarjeta(p["escenas"][desde - 1]) else gancho, sonidos=ruidos)
    extra, mezcla = _mezcla("aresample=48000,aformat=channel_layouts=stereo", ambiente, largo, musica_de(p), desde=ini)
    destino.parent.mkdir(parents=True, exist_ok=True)
    medios.ffmpeg(
        "-i", str(cuerpo), "-ss", f"{ini:.3f}", "-t", f"{largo:.3f}", "-i", str(carpeta / voz["archivo"]), *extra,
        "-filter_complex", f"[0:v]ass={ass.name}[v];{mezcla}", "-map", "[v]", "-map", "[a]",
        "-t", f"{largo:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(destino.resolve()),
        cwd=trabajo,
    )
    registro.apuntar("Render local (FFmpeg)", f"recorte {destino.stem} · escenas {desde}-{hasta} · {largo:.1f}s", produccion=p["id"])
    return destino
