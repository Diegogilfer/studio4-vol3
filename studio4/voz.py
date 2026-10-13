"""Fase 3 · Voz: locución de todo el guion en UNA sola llamada, y los tiempos de cada escena y palabra.

- Gemini TTS (gratis con GEMINI_API_KEY; ~50 peticiones/día en preview, por eso una llamada por vídeo).
  Los cortes entre escenas se calculan por proporción de texto y se ajustan al silencio más cercano.
- ElevenLabs (opcional): devuelve el tiempo de cada letra, así que la sincronía es exacta.
  Ojo: el plan gratis (10.000 créditos/mes) exige citar a ElevenLabs y no permite uso comercial.
"""

from __future__ import annotations

import base64
import logging
import re
import wave
from pathlib import Path
from typing import Any

import requests

from . import config, medios, registro

logger = logging.getLogger("studio4.voz")

PROVEEDORES = {
    "gemini": "Voz de Google (gratis)",
    "elevenlabs": "Voz ElevenLabs",
}
VOZ_ELEVENLABS_POR_DEFECTO = "JBFqnCBsd6RMkjVDRZzb"  # «George», voz prediseñada disponible en el plan gratis


def _spans_palabras(texto: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", texto)]


def _spans_escenas(segmentos: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Une los textos de las escenas y devuelve el texto completo y el rango de caracteres de cada una."""
    spans, pos = [], 0
    for s in segmentos:
        spans.append((pos, pos + len(s)))
        pos += len(s) + 1
    return " ".join(segmentos), spans


# --- Dirección de voz por escena (etiquetas en línea de Gemini 3.1 Flash TTS) ---------------------
TONOS = {
    "narrativo": "calm, measured documentary narration",
    "intrigante": "intriguing, low voice, building curiosity",
    "tenso": "tense, suspenseful",
    "emocionante": "excited, energetic",
    "cinematografico": "epic, cinematic trailer voice",
    "intimo": "soft, intimate, close to the microphone",
    "solemne": "solemn, grave",
    "asombro": "amazed, full of wonder",
    "triunfal": "triumphant, uplifting",
}
RITMOS = {"lento": "slowly", "rapido": "fast", "normal": ""}


def etiqueta(tono: str, ritmo: str = "normal") -> str:
    partes = [TONOS.get(tono, TONOS["narrativo"]), RITMOS.get(ritmo, "")]
    return "[" + ", ".join(p for p in partes if p) + "]"


def _texto_dirigido(segmentos: list[str], direcciones: list[dict[str, str]] | None) -> str:
    """El guion con su dirección delante de cada escena; solo se pone etiqueta cuando el tono cambia."""
    if not direcciones:
        return " ".join(segmentos)
    trozos, previa = [], None
    for seg, d in zip(segmentos, direcciones):
        tag = etiqueta(d.get("tono", "narrativo"), d.get("ritmo", "normal"))
        trozos.append(seg if tag == previa else f"{tag} {seg}")
        previa = tag
    return " ".join(trozos)


def _leyo_etiquetas(wav: Path, texto: str, produccion: str) -> bool:
    """Gemini escucha la locución: ¿ha leído en voz alta alguna etiqueta en inglés? (gratis, no bloquea si falla)."""
    import re
    from google.genai import types
    from . import gemini
    try:
        if wav.stat().st_size > 19 * 1024 * 1024:
            return False
        r = gemini.cliente().models.generate_content(
            model=config.MODELO_TEXTO,
            contents=[types.Part.from_bytes(data=wav.read_bytes(), mime_type="audio/wav"),
                      "Transcribe exactamente lo que se oye, palabra por palabra, sin corregir nada."])
        oido = (r.text or "").lower()
        registro.apuntar("Gemini (escucha de la voz)", "comprobación de etiquetas", produccion=produccion)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo comprobar la locución: %s", e)
        return False
    guion = set(re.findall(r"[a-záéíóúñü]+", texto.lower()))
    sospechosas = {w for d in TONOS.values() for w in re.findall(r"[a-z]+", d)} | {"slowly", "fast"}
    leidas = [w for w in re.findall(r"[a-z]+", oido) if w in sospechosas and w not in guion]
    if leidas:
        logger.warning("La voz leyó etiquetas en voz alta: %s", sorted(set(leidas)))
    return len(leidas) >= 2


# --- Gemini TTS -------------------------------------------------------------------------------
def _gemini(texto: str, destino: Path, produccion: str) -> None:
    from google.genai import types
    from .gemini import cliente

    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOZ_GEMINI)
            )
        ),
    )
    ultimo: Exception | None = None
    for modelo in dict.fromkeys([config.MODELO_TTS, *config.MODELOS_TTS_RESERVA]):
        try:
            estilo = (config.ESTILO_VOZ + ". Las indicaciones entre corchetes son dirección de actor: interprétalas, "
                      "nunca las leas en voz alta") if "[" in texto else config.ESTILO_VOZ
            r = cliente().models.generate_content(model=modelo, contents=f"{estilo}:\n\n{texto}", config=cfg)
            pcm = next(p.inline_data.data for p in r.candidates[0].content.parts if p.inline_data and p.inline_data.data)
            with wave.open(str(destino), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(pcm)
            registro.apuntar("Gemini TTS", f"{len(texto)} caracteres · {modelo}", produccion=produccion)
            return
        except Exception as e:  # noqa: BLE001
            ultimo = e
            logger.warning("Gemini TTS %s: %s", modelo, e)
    raise RuntimeError(f"Gemini TTS no generó audio: {ultimo}")


def _cortes_por_silencio(wav: Path, texto: str, spans: list[tuple[int, int]]) -> list[float]:
    """Instante de inicio de cada escena: proporción de letras, ajustada al silencio más próximo."""
    total = medios.duracion(wav)
    silencios = medios.silencios(wav)
    inicio_voz = silencios[0][1] if silencios and silencios[0][0] < 0.05 else 0.0
    fin_voz = silencios[-1][0] if silencios and silencios[-1][1] >= total - 0.05 else total
    # (centro, duración) de cada pausa: los cortes de escena caen en fin de frase, que es una pausa larga.
    huecos = [((a + b) / 2, b - a) for a, b in silencios if a > inicio_voz and b < fin_voz]

    letras = lambda a, b: len(re.sub(r"\s", "", texto[a:b]))  # noqa: E731
    total_letras = max(1, letras(0, len(texto)))
    estimados = [inicio_voz + (fin_voz - inicio_voz) * letras(0, ini) / total_letras for ini, _ in spans[1:]]
    if not estimados:
        return [0.0]
    if len(huecos) < len(estimados):  # pocas pausas: se queda la proporción de texto
        return [0.0, *estimados]

    # Asignación óptima y en orden: cada corte a una pausa distinta, cerca de su estimación y
    # prefiriendo pausas largas (fin de frase) a las cortas (comas).
    coste = lambda k, j: abs(huecos[j][0] - estimados[k]) - 2 * huecos[j][1]  # noqa: E731
    K, M = len(estimados), len(huecos)
    inf = float("inf")
    dp = [[inf] * M for _ in range(K)]
    desde = [[-1] * M for _ in range(K)]
    for j in range(M):
        dp[0][j] = coste(0, j)
    for k in range(1, K):
        mejor, arg = inf, -1
        for j in range(M):
            if j > 0 and dp[k - 1][j - 1] < mejor:
                mejor, arg = dp[k - 1][j - 1], j - 1
            if arg >= 0:
                dp[k][j] = mejor + coste(k, j)
                desde[k][j] = arg
    j = min(range(M), key=lambda x: dp[K - 1][x])
    elegidos = []
    for k in range(K - 1, -1, -1):
        elegidos.append(huecos[j][0])
        j = desde[k][j]
    return [0.0, *reversed(elegidos)]


def _palabras_proporcionales(texto: str, spans: list[tuple[int, int]], cortes: list[float], total: float) -> list[dict]:
    palabras = []
    for i, (a, b) in enumerate(spans):
        ini, fin = cortes[i], (cortes[i + 1] if i + 1 < len(cortes) else total)
        trozos = _spans_palabras(texto[a:b])
        peso = sum(e - s + 1 for s, e in trozos) or 1
        t = ini + 0.05
        hueco = max(0.1, fin - ini - 0.25)
        for s, e in trozos:
            d = hueco * (e - s + 1) / peso
            palabras.append({"palabra": texto[a + s:a + e], "ini": round(t, 3), "fin": round(t + d, 3)})
            t += d
    return palabras


# --- ElevenLabs -------------------------------------------------------------------------------
def _elevenlabs(texto: str, destino: Path, produccion: str) -> dict[str, Any]:
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("Falta ELEVENLABS_API_KEY en .env (elevenlabs.io › Profile › API keys).")
    restantes = registro.creditos_elevenlabs_restantes()
    if len(texto) > restantes:
        raise RuntimeError(f"ElevenLabs: este guion usa {len(texto)} créditos y te quedan ~{restantes} este mes. Usa Gemini TTS.")
    voz = config.ELEVENLABS_VOICE_ID or VOZ_ELEVENLABS_POR_DEFECTO
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        json={"text": texto, "model_id": config.ELEVENLABS_MODEL},
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs respondió {r.status_code}: {r.text[:300]}")
    d = r.json()
    mp3 = destino.with_suffix(".mp3")
    mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    medios.ffmpeg("-i", str(mp3), "-ac", "1", "-ar", "24000", str(destino))
    mp3.unlink(missing_ok=True)
    registro.apuntar("ElevenLabs", f"{len(texto)} caracteres · {config.ELEVENLABS_MODEL}", cantidad=len(texto),
                     unidad="créditos", produccion=produccion)
    return d.get("alignment") or d.get("normalized_alignment") or {}


def _tiempos_alineados(texto: str, spans: list[tuple[int, int]], al: dict, total: float) -> tuple[list[float], list[dict]]:
    inicios = al.get("character_start_times_seconds", [])
    fines = al.get("character_end_times_seconds", [])
    if len(inicios) != len(texto):
        raise ValueError("La alineación de ElevenLabs no coincide con el texto")
    cortes = [0.0] + [inicios[a] for a, _ in spans[1:]]
    palabras = [{"palabra": texto[s:e], "ini": round(inicios[s], 3), "fin": round(fines[e - 1], 3)}
                for s, e in _spans_palabras(texto)]
    return cortes, palabras


def reserva(proveedor: str) -> str | None:
    """La otra voz, si está configurada (Gemini siempre lo está si hay GEMINI_API_KEY)."""
    if proveedor == "gemini" and config.ELEVENLABS_API_KEY:
        return "elevenlabs"
    if proveedor == "elevenlabs" and config.GEMINI_API_KEY:
        return "gemini"
    return None


# --- Entrada única ----------------------------------------------------------------------------
def locutar(segmentos: list[str], destino: Path, proveedor: str = "gemini", produccion: str = "",
            direcciones: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Genera la locución y devuelve {'duracion', 'escenas': [{ini, fin}], 'palabras': [{palabra, ini, fin}]}.
    Con `direcciones` (tono y ritmo por escena), Gemini TTS interpreta cada escena como toca."""
    limpios = [" ".join(s.split()) for s in segmentos]
    texto, spans = _spans_escenas(limpios)   # los tiempos se calculan siempre sobre el texto sin etiquetas
    destino.parent.mkdir(parents=True, exist_ok=True)

    alineacion = None
    dirigida = False
    if proveedor == "elevenlabs":
        alineacion = _elevenlabs(texto, destino, produccion)
    else:
        dirigido = _texto_dirigido(limpios, direcciones)
        _gemini(dirigido, destino, produccion)
        dirigida = dirigido != texto
        if dirigida and _leyo_etiquetas(destino, texto, produccion):
            # Si la voz pronunció alguna etiqueta, se repite la toma sin dirección por escena.
            _gemini(texto, destino, produccion)
            dirigida = False
    total = medios.duracion(destino)

    try:
        if alineacion is None:
            raise ValueError("sin alineación")
        cortes, palabras = _tiempos_alineados(texto, spans, alineacion, total)
    except ValueError:
        cortes = _cortes_por_silencio(destino, texto, spans)
        palabras = _palabras_proporcionales(texto, spans, cortes, total)

    escenas = [{"ini": round(c, 3), "fin": round(cortes[i + 1] if i + 1 < len(cortes) else total, 3)}
               for i, c in enumerate(cortes)]
    return {"proveedor": proveedor, "duracion": round(total, 3), "escenas": escenas, "palabras": palabras,
            "dirigida": dirigida}
