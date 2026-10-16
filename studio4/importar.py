"""Importar un vídeo ya hecho (enlace o archivo) y convertirlo en una producción lista para Render y Entregas.

1. yt-dlp lo descarga (o se usa el archivo subido). Solo vídeos tuyos o con derechos: el panel lo pide.
2. faster-whisper lo transcribe EN TU PC, gratis, con el tiempo de cada palabra.
3. FFmpeg detecta los cambios de plano; las escenas se cortan en finales de frase, cerca de esos cambios.
4. Cada escena es un trozo del vídeo (su «toma») con su texto; el audio original hace de «voz».
   Desde ahí todo es igual que una producción normal: corregir textos, cambiar una toma, subtítulos de cine o
   virales con sonidos, y los 3 formatos (completo, Reels y Shorts) con portadas y textos para publicar.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from . import config, medios

logger = logging.getLogger("studio4.importar")

MAX_MINUTOS = 90
MODELO_WHISPER = os.getenv("STUDIO4_WHISPER", "small")   # tiny, base, small, medium: más grande = más fino y más lento
_whisper = None


PLATAFORMAS = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook",
               "twitter": "X", "x": "X", "vimeo": "Vimeo", "twitch": "Twitch"}


def plataforma(url: str) -> str:
    """«youtube», «tiktok»… a partir del enlace (sin preguntar a nadie)."""
    m = re.match(r"https?://(?:[\w-]+\.)*?([\w-]+)\.(?:com|be|tv|net|co|watch)\b", url or "")
    host = (m.group(1) if m else "").lower()
    return {"youtu": "youtube", "fb": "facebook"}.get(host, host if host in PLATAFORMAS else "")


def vista_previa(url: str) -> dict[str, Any]:
    """Lo que hay detrás del enlace, sin descargar nada: título, canal, duración y miniatura (para confirmar)."""
    import yt_dlp
    if not re.match(r"https?://\S+$", url or ""):
        raise ValueError("Pega un enlace completo al vídeo (https://…).")
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True, "socket_timeout": 20}) as ydl:
        info = ydl.extract_info(url, download=False)
    duracion = int(info.get("duration") or 0)
    return {"titulo": info.get("title") or "", "canal": info.get("uploader") or info.get("channel") or "",
            "duracion": duracion, "miniatura": info.get("thumbnail") or "", "plataforma": plataforma(url),
            "vistas": int(info.get("view_count") or 0), "url": url,
            "demasiado_largo": duracion > MAX_MINUTOS * 60, "max_minutos": MAX_MINUTOS}


def descargar(url: str, carpeta: Path, avisar: Callable[[str], None] = lambda _f: None) -> dict[str, Any]:
    """Descarga el vídeo (hasta 1080p) a carpeta/origen.mp4 y devuelve {titulo, canal, url}."""
    import yt_dlp
    if not re.match(r"https?://\S+$", url or ""):
        raise ValueError("Pega un enlace completo al vídeo (https://…).")
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    if (info.get("duration") or 0) > MAX_MINUTOS * 60:
        raise ValueError(f"El vídeo dura más de {MAX_MINUTOS} minutos.")
    avisar("Descargando el vídeo")
    opciones = {"quiet": True, "noplaylist": True, "outtmpl": str(carpeta / "descarga.%(ext)s"),
                "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
                "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url])
    bajado = next(iter(sorted(carpeta.glob("descarga.*"))), None)
    if not bajado:
        raise RuntimeError("No se pudo descargar el vídeo.")
    bajado.replace(carpeta / "origen.mp4")
    return {"titulo": info.get("title") or "Vídeo importado", "canal": info.get("uploader") or "", "url": url}


def transcribir(audio: Path, avisar: Callable[[str], None] = lambda _f: None) -> list[dict[str, Any]]:
    """Palabras con su tiempo exacto ({palabra, ini, fin}), con Whisper en local (la primera vez baja el modelo)."""
    global _whisper
    from faster_whisper import WhisperModel
    if _whisper is None:
        avisar("Preparando el transcriptor (solo la primera vez tarda)")
        _whisper = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    avisar("Transcribiendo el vídeo palabra por palabra")
    segmentos, _info = _whisper.transcribe(str(audio), word_timestamps=True, vad_filter=True)
    palabras = []
    for s in segmentos:
        for w in s.words or []:
            texto = w.word.strip()
            if texto:
                palabras.append({"palabra": texto, "ini": round(w.start, 3), "fin": round(w.end, 3)})
    return palabras


def cortes_de_plano(video: Path, umbral: float = 0.3) -> list[float]:
    """Segundos en los que cambia el plano (FFmpeg)."""
    log = medios.ffmpeg("-i", str(video), "-an", "-vf", f"select='gt(scene,{umbral})',showinfo", "-f", "null", "-")
    return sorted({round(float(x), 2) for x in re.findall(r"pts_time:([\d.]+)", log)})


def escenas(palabras: list[dict[str, Any]], cortes: list[float], total: float,
            minimo: float = 3.0, ideal: float = 6.0, maximo: float = 9.0) -> list[dict[str, Any]]:
    """Escenas consecutivas que cubren todo el vídeo: cada una termina en un final de frase o pausa, mejor si cae
    cerca de un cambio de plano, entre `minimo` y `maximo` segundos. Devuelve [{ini, fin, palabras}]."""
    salida: list[dict[str, Any]] = []
    ini, actual = 0.0, []
    for i, w in enumerate(palabras):
        actual.append(w)
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else None
        dur = w["fin"] - ini
        fin_frase = w["palabra"].endswith((".", "?", "!", "…"))
        pausa = siguiente is not None and siguiente["ini"] - w["fin"] > 0.5
        corte_cerca = siguiente is not None and any(w["fin"] - 0.4 <= c <= siguiente["ini"] + 0.4 for c in cortes)
        coma = w["palabra"].endswith((",", ";", ":"))
        cerrar = siguiente is None or dur >= maximo or (dur >= minimo and (fin_frase or pausa or corte_cerca)) \
            or (dur >= ideal and coma)
        if cerrar and siguiente is not None:
            fin = round((w["fin"] + siguiente["ini"]) / 2, 3)   # el corte, en medio del hueco entre palabras
            if fin - ini < 0.3:   # Whisper dio tiempos solapados o desordenados: esta escena sigue con la siguiente
                continue
            salida.append({"ini": ini, "fin": fin, "palabras": actual})
            ini, actual = fin, []
    salida.append({"ini": ini, "fin": round(max(total, ini + 0.3), 3), "palabras": actual})
    if len(salida) > 1 and salida[-1]["fin"] - salida[-1]["ini"] < 1.0:   # un resto mínimo se une al anterior
        ultimo = salida.pop()
        salida[-1].update(fin=ultimo["fin"], palabras=salida[-1]["palabras"] + ultimo["palabras"])
    return salida


def formato_de(video: Path) -> str:
    inf = medios.info(video)
    if abs(inf["ancho"] - inf["alto"]) < 0.1 * max(inf["ancho"], inf["alto"]):
        return "cuadrado"
    return "vertical" if inf["alto"] > inf["ancho"] else "horizontal"


def preparar(carpeta: Path, avisar: Callable[[str, int], None] = lambda *_: None) -> dict[str, Any]:
    """Con carpeta/origen.mp4 ya en su sitio: voz, transcripción, escenas y una toma por escena.
    Devuelve los campos de la producción (escenas, voz, guion, formato)."""
    origen = carpeta / "origen.mp4"
    total = medios.info(origen)["duracion"]
    if total > MAX_MINUTOS * 60:
        raise ValueError(f"El vídeo dura más de {MAX_MINUTOS} minutos.")
    if not (carpeta / "voz.wav").exists():
        medios.ffmpeg("-i", str(origen), "-vn", "-ac", "2", "-ar", "48000", str(carpeta / "voz.wav"))
    guardada = carpeta / "transcripcion.json"   # si se cortó después de transcribir, no se repite
    try:
        palabras = json.loads(guardada.read_text(encoding="utf-8"))
        avisar("Usando la transcripción ya hecha", 60)
    except (OSError, ValueError):
        avisar("Transcribiendo el vídeo palabra por palabra", 25)
        palabras = transcribir(carpeta / "voz.wav", lambda f: avisar(f, 25))
        tmp = guardada.with_suffix(".tmp")
        tmp.write_text(json.dumps(palabras, ensure_ascii=False), encoding="utf-8")
        tmp.replace(guardada)
    avisar("Buscando los cambios de plano", 65)
    tramos = escenas(palabras, cortes_de_plano(origen), total)
    tomas = carpeta / "tomas"
    tomas.mkdir(exist_ok=True)
    lista = []
    for n, t in enumerate(tramos, start=1):
        avisar(f"Preparando la escena {n} de {len(tramos)}", 70 + int(25 * n / len(tramos)))
        archivo = f"tomas/escena_{n:02d}_original.mp4"
        try:
            medios.ffmpeg("-ss", f"{t['ini']:.3f}", "-to", f"{t['fin']:.3f}", "-i", str(origen), "-c:v", "libx264",
                          "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", str(carpeta / archivo))
        except RuntimeError as e:
            raise RuntimeError(f"No se pudo cortar la escena {n} ({t['ini']:.1f}-{t['fin']:.1f} s del vídeo): {e}") from e
        texto = " ".join(w["palabra"] for w in t["palabras"])
        lista.append({"orden": n, "texto_voz": texto, "texto_pantalla": "", "tipo_clip": "video", "prompt_flow": "",
                      "segundos": round(t["fin"] - t["ini"], 1), "personajes": [],
                      "tomas": [{"archivo": archivo, "tipo": "video", "duracion": round(t["fin"] - t["ini"], 2), "origen": "original"}],
                      "elegida": 0})
    return {"escenas": lista, "guion": " ".join(e["texto_voz"] for e in lista).strip(), "formato": formato_de(origen),
            "voz": {"proveedor": "original", "archivo": "voz.wav", "duracion": round(total, 3), "generada": "original",
                    "escenas": [{"ini": t["ini"], "fin": t["fin"]} for t in tramos], "palabras": palabras}}


def retemporizar(palabras: list[dict[str, Any]], ini: float, fin: float, texto: str) -> list[dict[str, Any]]:
    """Cuando corriges el texto de una escena: las palabras nuevas se reparten en el tiempo que ocupaban las viejas
    (el audio no cambia; cambian los subtítulos)."""
    viejas = [w for w in palabras if ini <= w["ini"] < fin]
    a = viejas[0]["ini"] if viejas else ini
    b = viejas[-1]["fin"] if viejas else fin
    nuevas = texto.split()
    letras = sum(len(x) for x in nuevas) or 1
    t, salida = a, []
    for x in nuevas:
        d = (b - a) * len(x) / letras
        salida.append({"palabra": x, "ini": round(t, 3), "fin": round(t + d, 3)})
        t += d
    return [w for w in palabras if w["ini"] < ini] + salida + [w for w in palabras if w["ini"] >= fin]


def subida_a_origen(tmp: Path, carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    shutil.copy(tmp, carpeta / "origen.mp4")
