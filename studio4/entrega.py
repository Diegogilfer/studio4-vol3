"""Vídeo que traes (enlace o archivo) → los 3 formatos listos, SIN guion: 16:9, 9:16 y 1:1.

Cualquier forma de origen sirve: si no encaja en el formato, va centrado sobre su propia imagen desenfocada (nunca se
recorta la acción). Subtítulos opcionales sacados de su propio audio con Whisper en tu PC (gratis), en el idioma del
vídeo o traducidos (español, inglés, chino o japonés) y quemados en los tres, más su .srt para YouTube. Y miniatura.
El 16:9 es el vídeo entero; el 9:16 y el 1:1, enteros si duran ≤ 3 min (Shorts) y, si no, el primer minuto.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from . import config, extractor, gemini, medios, montaje, subtitulos

logger = logging.getLogger("studio4.entrega")

FORMATOS = {"final_16x9.mp4": (1920, 1080), "short_9x16.mp4": (1080, 1920), "cuadrado_1x1.mp4": (1080, 1080)}
IDIOMAS = ("original", "es", "en", "zh", "ja")
FUENTE_LETRA = {"zh": "Microsoft YaHei", "ja": "Yu Gothic"}
TAMANO_LETRA = {"final_16x9.mp4": 17, "short_9x16.mp4": 10, "cuadrado_1x1.mp4": 13}   # en la escala de libass (alto 288)
MAX_SHORT = 180
_whisper = None


def _original(meta: dict[str, Any]) -> Path:
    """El vídeo en alta: el subido ya está en el banco; el de un enlace se baja una vez a 1080p con su sonido."""
    if meta.get("alta"):
        return extractor.CACHE / meta["alta"]
    return extractor.descargar_tramo(meta["url"], meta["desde"], meta["hasta"], alto=1080, nombre=f"{meta['id']}_entrega")


def _transcribir(video: Path, trabajo: Path) -> tuple[list[dict[str, Any]], str]:
    """Palabras con su tiempo y el idioma detectado (faster-whisper en local)."""
    global _whisper
    from faster_whisper import WhisperModel
    audio = trabajo / "audio.wav"
    medios.ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(audio))
    if _whisper is None:
        _whisper = WhisperModel(config.WHISPER_MODELO, device="cpu", compute_type="int8")
    segmentos, info = _whisper.transcribe(str(audio), word_timestamps=True, vad_filter=True)
    palabras = [{"palabra": w.word.strip(), "ini": round(w.start, 3), "fin": round(w.end, 3)}
                for s in segmentos for w in (s.words or []) if w.word.strip()]
    return palabras, getattr(info, "language", "") or ""


def _filtro(ancho: int, alto: int, subs: str, marca: str) -> str:
    return (f"[0:v]fps={config.FPS},split=2[a][b];"
            f"[a]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},gblur=sigma=30,eq=brightness=-0.12[fondo];"
            f"[b]scale={ancho}:{alto}:force_original_aspect_ratio=decrease[centro];"
            f"[fondo][centro]overlay=(W-w)/2:(H-h)/2,setsar=1{subs}[base];{marca}")


def _tramo(total: float) -> float:
    return total if total <= MAX_SHORT else 59.0


def entregar(mid: str, opciones: dict[str, Any] | None = None,
             transcribir: Callable[[Path, Path], tuple[list[dict[str, Any]], str]] = _transcribir) -> None:
    """Lanza la entrega en segundo plano. opciones: {subtitulos: bool, idioma: original|es|en|zh|ja}."""
    o = opciones or {}
    con_subs = bool(o.get("subtitulos"))
    idioma = str(o.get("idioma") or "original")
    if idioma not in IDIOMAS:
        raise ValueError("Idioma de subtítulos: original, español, inglés, chino o japonés.")
    p = montaje.cargar(mid)
    if not p["fuentes"]:
        raise ValueError("Primero trae el vídeo (enlace o archivo).")
    meta = montaje.fuente(p["fuentes"][0])

    def avisar(fase: str, n: int) -> None:
        montaje._avisar(mid, fase, n)

    def fase() -> None:
        base = montaje.carpeta(mid)
        trabajo = base / "render_entrega"
        shutil.rmtree(trabajo, ignore_errors=True)
        trabajo.mkdir()
        avisar("Preparando el vídeo en alta", 5)
        origen = _original(meta)
        total = medios.duracion(origen)
        srt_final = ""
        if con_subs:
            avisar("Escuchando el vídeo para los subtítulos", 15)
            palabras, hablado = transcribir(origen, trabajo)
            if palabras:
                srt_orig = trabajo / "subs_original.srt"
                subtitulos.srt(palabras, srt_orig)
                texto = srt_orig.read_text(encoding="utf-8")
                if idioma not in ("original", hablado):
                    avisar(f"Traduciendo los subtítulos ({subtitulos.IDIOMAS.get(idioma, idioma)})", 30)
                    texto = subtitulos.traducir_srt(texto, idioma, lambda pr: gemini.generar(
                        pr, temperatura=0.2, detalle="traducir subtítulos", produccion=mid))
                (trabajo / "subs.srt").write_text(texto, encoding="utf-8")
                srt_final = f"subtitulos.{idioma if idioma != 'original' else (hablado or 'original')}.srt"
                (base / srt_final).write_text(texto, encoding="utf-8")
            else:
                logger.info("Entrega %s: el vídeo no tiene voz que subtitular.", mid)
        hechos = {}
        for k, (nombre, (ancho, alto)) in enumerate(FORMATOS.items()):
            avisar(f"Montando {ancho}×{alto}", 40 + 18 * k)
            dur = total if nombre == "final_16x9.mp4" else _tramo(total)
            subs = ""
            if srt_final:
                letra = FUENTE_LETRA.get(idioma, "Arial")
                subs = (f",subtitles=subs.srt:force_style='FontName={letra},FontSize={TAMANO_LETRA[nombre]},Bold=1,"
                        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=24'")
            capas, marca = montaje._capas_marca({"canal": p["canal"]}, 0.0, dur, ancho, alto, "[base]", 1, emojis=False)
            medios.ffmpeg("-t", f"{dur:.3f}", "-i", str(origen), *capas, "-filter_complex", _filtro(ancho, alto, subs, marca),
                          "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                          "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1:LRA=11", "-c:a", "aac", "-b:a", "192k",
                          "-movflags", "+faststart", str(base / nombre), cwd=trabajo)
            hechos[nombre] = round(dur, 2)
        ahora = time.strftime("%Y-%m-%d %H:%M")
        montaje.modificar(mid, lambda q: q.update(
            final={"archivo": "final_16x9.mp4", "hecho": ahora},
            short={"archivo": "short_9x16.mp4", "desde": 0.0, "hasta": hechos["short_9x16.mp4"]},
            cuadrado={"archivo": "cuadrado_1x1.mp4", "desde": 0.0, "hasta": hechos["cuadrado_1x1.mp4"]},
            entrega={"hecha": ahora, "subtitulos": bool(srt_final), "idioma": idioma, "srt": srt_final, "duracion": round(total, 2)}))
        buenos = [pl["n"] for pl in meta["planos"] if not pl.get("pobre")] or [pl["n"] for pl in meta["planos"]]
        if buenos:
            avisar("Miniatura", 97)
            fotos = [{"fuente": meta["id"], "plano": buenos[len(buenos) // 3]}, {"fuente": meta["id"], "plano": buenos[(2 * len(buenos)) // 3]}]
            try:
                montaje.miniatura(mid, montaje.cargar(mid)["titulo"][:40].upper(), fotos[:1] if len(buenos) < 2 else fotos)
            except Exception as e:  # noqa: BLE001 - los vídeos ya están; la miniatura se rehace a mano
                logger.warning("Miniatura de la entrega: %s", e)
        shutil.rmtree(trabajo, ignore_errors=True)

    montaje._en_fondo(mid, "Entrega", fase)
