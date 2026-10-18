"""Fase 3 · Voz: locución de todo el guion en UNA sola llamada, y los tiempos de cada escena y palabra.

- Gemini TTS (gratis con GEMINI_API_KEY; ~50 peticiones/día en preview, por eso una llamada por vídeo).
  Los cortes entre escenas se calculan por proporción de texto y se ajustan al silencio más cercano.
- ElevenLabs (opcional): devuelve el tiempo de cada letra, así que la sincronía es exacta.
  Ojo: el plan gratis (10.000 créditos/mes) exige citar a ElevenLabs y no permite uso comercial.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
import wave
from pathlib import Path
from typing import Any

import requests

from . import config, medios, registro

logger = logging.getLogger("studio4.voz")

PROVEEDORES = {
    "gemini": "Voz de Google (gratis)",
    "mimo": "Voz Xiaomi MiMo (gratis · mimo-v2.5-tts)",
    "elevenlabs": "Voz ElevenLabs",
    "fal": "Voz ElevenLabs por fal (de pago · ~0,10 $ cada 1.000 letras)",
}
VOCES_MIMO = {
    "Milo": "Narrador masculino claro y dinámico",
    "Dean": "Narrador masculino profundo y sereno",
    "Mia": "Narradora femenina cálida y natural",
    "Chloe": "Narradora femenina expresiva y ágil",
    "mimo_default": "Voz automática de Xiaomi MiMo",
}
VOZ_MIMO_POR_DEFECTO = "Milo"
FAL_TTS = "fal-ai/elevenlabs/tts/multilingual-v2"
FAL_TTS_POR_MIL = 0.10   # $ por cada 1.000 caracteres (ficha de fal, octubre de 2026)
VOZ_FAL = "George"       # voz de narrador de ElevenLabs; el modelo multilingüe habla en español
LIMITE_TROZO = 3200      # caracteres por llamada (~3 min de voz): un vídeo largo se graba por partes y se une
VOZ_ELEVENLABS_POR_DEFECTO = "JBFqnCBsd6RMkjVDRZzb"  # «George», voz prediseñada disponible en el plan gratis
CACHE_CATALOGO_S = 3600  # 1 hora de caché del catálogo de ElevenLabs para no consultar de más

VOCES_ELEVENLABS_BASE: list[dict[str, Any]] = [
    {
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "nombre": "George",
        "categoria": "premade",
        "idioma": "Multilingüe (español / inglés)",
        "acento": "británico cálido",
        "descripcion": "Narrador cálido y resonante, ideal para documentales y relatos.",
        "etiquetas": ["narración", "cálida", "masculina", "madura"],
        "preview_url": "",
    },
    {
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "nombre": "Adam",
        "categoria": "premade",
        "idioma": "Multilingüe (español / inglés)",
        "acento": "americano profundo",
        "descripcion": "Voz grave y firme para historias intensas y divulgación.",
        "etiquetas": ["narración", "profunda", "masculina"],
        "preview_url": "",
    },
    {
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "nombre": "Rachel",
        "categoria": "premade",
        "idioma": "Multilingüe (español / inglés)",
        "acento": "americano claro",
        "descripcion": "Voz serena, clara y equilibrada para explicar temas complejos.",
        "etiquetas": ["calmada", "femenina", "joven"],
        "preview_url": "",
    },
    {
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "nombre": "Bella",
        "categoria": "premade",
        "idioma": "Multilingüe (español / inglés)",
        "acento": "americano suave",
        "descripcion": "Voz suave y cercana para relatos expresivos.",
        "etiquetas": ["suave", "femenina", "narración"],
        "preview_url": "",
    },
]


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
def _gemini(texto: str, destino: Path, produccion: str, voz_nombre: str | None = None, estilo_voz: str = "") -> None:
    from google.genai import types
    from .gemini import cliente

    cfg = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz_nombre or config.VOZ_GEMINI)
            )
        ),
    )
    import time
    ultimo: Exception | None = None
    for modelo in dict.fromkeys([config.MODELO_TTS, *config.MODELOS_TTS_RESERVA]):
        for intento in range(2 if modelo == config.MODELO_TTS else 1):
            try:
                base = estilo_voz or config.ESTILO_VOZ
                estilo = (base + ". Las indicaciones entre corchetes son dirección de actor: interprétalas, "
                          "nunca las leas en voz alta") if "[" in texto else base
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
                if "402" in str(e) or "prepayment credits" in str(e):
                    raise RuntimeError("Tu proyecto de Google se quedó sin saldo de prepago (402): crea una clave de API en un "
                                       "proyecto SIN facturación para volver al nivel gratuito.") from e
                logger.warning("Gemini TTS %s: %s", modelo, e)
                if intento == 0 and ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and "limit: 0" not in str(e):
                    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e), re.IGNORECASE)
                    espera = min(40.0, float(m.group(1)) + 1.0) if m else 6.0
                    time.sleep(espera)
                    continue
                break
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
def _normalizar_voz_elevenlabs(v: dict[str, Any]) -> dict[str, Any]:
    """Convierte un elemento de /v1/voices de ElevenLabs al formato del panel."""
    etiquetas_raw = v.get("labels") or {}
    idioma = str(etiquetas_raw.get("language") or (v.get("fine_tuning") or {}).get("language") or "").strip()
    acento = str(etiquetas_raw.get("accent") or "").strip()
    desc = str(v.get("description") or etiquetas_raw.get("description") or "").strip()
    etiquetas: list[str] = []
    for k in ("use_case", "use case", "gender", "age", "descriptive", "accent", "language"):
        val = str(etiquetas_raw.get(k) or "").strip()
        if val and val not in etiquetas:
            etiquetas.append(val)
    for k, val in etiquetas_raw.items():
        s = str(val or "").strip()
        if k != "description" and s and s not in etiquetas:
            etiquetas.append(s)
    url_muestra = str(v.get("preview_url") or "").strip()
    if url_muestra and not url_muestra.startswith(("https://", "http://")):
        url_muestra = ""
    return {
        "voice_id": str(v.get("voice_id") or "").strip(),
        "nombre": str(v.get("name") or v.get("nombre") or v.get("voice_id") or "").strip(),
        "categoria": str(v.get("category") or "premade").strip(),
        "idioma": idioma,
        "acento": acento,
        "descripcion": desc,
        "etiquetas": etiquetas[:8],
        "preview_url": url_muestra,
    }


def _combinar_voces_elevenlabs(remotas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une las voces de la cuenta con las predeterminadas sin duplicar voice_id."""
    vistas: set[str] = set()
    salida: list[dict[str, Any]] = []
    for v in remotas + [dict(b) for b in VOCES_ELEVENLABS_BASE]:
        vid = v.get("voice_id", "")
        if not vid or vid in vistas:
            continue
        vistas.add(vid)
        salida.append(v)
    return salida


def catalogo_elevenlabs(forzar: bool = False) -> dict[str, Any]:
    """Consulta el catálogo oficial de ElevenLabs (/v1/voices) con caché en disco, sin generar audio TTS."""
    por_defecto = config.ELEVENLABS_VOICE_ID or VOZ_ELEVENLABS_POR_DEFECTO
    restantes = registro.creditos_elevenlabs_restantes()
    base_resp = {
        "modelo": config.ELEVENLABS_MODEL,
        "creditos_restantes": restantes,
        "creditos_mes": config.ELEVENLABS_CREDITOS_MES,
        "por_defecto": por_defecto,
    }
    if not config.ELEVENLABS_API_KEY:
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "sin_clave",
            "error": "Falta ELEVENLABS_API_KEY en .env (elevenlabs.io › Profile › API keys). Se muestran las voces predeterminadas.",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    huella_clave = hashlib.sha256(config.ELEVENLABS_API_KEY.encode("utf-8")).hexdigest()[:12]
    archivo_cache = config.PRODUCCIONES / "_voces" / "catalogo_elevenlabs.json"
    if not forzar and archivo_cache.exists():
        try:
            guardado = json.loads(archivo_cache.read_text(encoding="utf-8"))
            if (guardado.get("huella") == huella_clave
                    and time.time() - float(guardado.get("ts") or 0) < CACHE_CATALOGO_S
                    and isinstance(guardado.get("voces"), list) and guardado["voces"]):
                return {**base_resp, "ok": True, "codigo_error": "", "error": "", "cache": True, "voces": guardado["voces"]}
        except (OSError, ValueError, TypeError):
            pass
    try:
        r = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY},
            timeout=15,
        )
    except requests.RequestException as e:
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "catalogo",
            "error": f"No se pudo conectar con el catálogo de ElevenLabs: {e}",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    if r.status_code in (401, 403):
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "autenticacion",
            "error": f"ElevenLabs rechazó la clave ({r.status_code}): revisa ELEVENLABS_API_KEY y sus permisos en elevenlabs.io.",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    if r.status_code == 429 or "quota" in r.text.lower():
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "cuota",
            "error": f"Límite o cuota de ElevenLabs alcanzado ({r.status_code}): {r.text[:180]}",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    if r.status_code != 200:
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "catalogo",
            "error": f"ElevenLabs respondió {r.status_code} al pedir el catálogo: {r.text[:180]}",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    try:
        datos = r.json()
        remotas = [_normalizar_voz_elevenlabs(x) for x in (datos.get("voices") or []) if isinstance(x, dict) and x.get("voice_id")]
    except (ValueError, TypeError) as e:
        return {
            **base_resp,
            "ok": False,
            "codigo_error": "catalogo",
            "error": f"Respuesta de catálogo no válida de ElevenLabs: {e}",
            "cache": False,
            "voces": [dict(b) for b in VOCES_ELEVENLABS_BASE],
        }
    voces = _combinar_voces_elevenlabs(remotas)
    try:
        archivo_cache.parent.mkdir(parents=True, exist_ok=True)
        archivo_cache.write_text(json.dumps({"huella": huella_clave, "ts": time.time(), "voces": voces}, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except OSError:
        pass
    return {**base_resp, "ok": True, "codigo_error": "", "error": "", "cache": False, "voces": voces}


def _elevenlabs(texto: str, destino: Path, produccion: str, voice_id: str | None = None) -> dict[str, Any]:
    if not config.ELEVENLABS_API_KEY:
        raise RuntimeError("Falta ELEVENLABS_API_KEY en .env (elevenlabs.io › Profile › API keys).")
    restantes = registro.creditos_elevenlabs_restantes()
    if len(texto) > restantes:
        raise RuntimeError(f"ElevenLabs: este guion usa {len(texto)} créditos y te quedan ~{restantes} este mes. Usa Gemini TTS.")
    voz_id = (voice_id or "").strip() or config.ELEVENLABS_VOICE_ID or VOZ_ELEVENLABS_POR_DEFECTO
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voz_id}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        json={"text": texto, "model_id": config.ELEVENLABS_MODEL},
        timeout=180,
    )
    if r.status_code in (401, 403):
        raise RuntimeError(f"ElevenLabs rechazó la autenticación ({r.status_code}): revisa ELEVENLABS_API_KEY en .env.")
    if r.status_code == 429 or "quota_exceeded" in r.text.lower():
        raise RuntimeError(f"Cuota de ElevenLabs agotada ({r.status_code}): {r.text[:240]}")
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs respondió {r.status_code}: {r.text[:300]}")
    d = r.json()
    mp3 = destino.with_suffix(".mp3")
    mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    medios.ffmpeg("-i", str(mp3), "-ac", "1", "-ar", "24000", str(destino))
    mp3.unlink(missing_ok=True)
    registro.apuntar("ElevenLabs", f"{len(texto)} caracteres · {config.ELEVENLABS_MODEL} · {voz_id}", cantidad=len(texto),
                     unidad="créditos", produccion=produccion)
    return d.get("alignment") or d.get("normalized_alignment") or {}


def _mimo_tts(texto: str, destino: Path, produccion: str, voice_id: str | None = None, estilo_voz: str = "") -> str:
    """Voz de Xiaomi MiMo (mimo-v2.5-tts) por su API compatible con OpenAI: devuelve WAV a 24.000 Hz mono."""
    if not config.XIAOMIMIMO_API_KEY:
        raise RuntimeError("Falta XIAOMIMIMO_API_KEY en .env (api.xiaomimimo.com).")
    voz_mimo = (voice_id or "").strip()
    if voz_mimo not in VOCES_MIMO:
        voz_mimo = VOZ_MIMO_POR_DEFECTO
    instruccion = (estilo_voz or config.ESTILO_VOZ or "Narra en español latino neutro, con ritmo ágil y claro.").strip()
    r = requests.post(
        f"{config.XIAOMIMIMO_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.XIAOMIMIMO_API_KEY}"},
        json={
            "model": config.XIAOMIMIMO_TTS_MODEL,
            "messages": [
                {"role": "user", "content": instruccion},
                {"role": "assistant", "content": texto},
            ],
            "audio": {"voice": voz_mimo, "format": "wav"},
        },
        timeout=180,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Xiaomi MiMo TTS respondió {r.status_code}: {r.text[:300]}")
    d = r.json()
    audio_b64 = (((d.get("choices") or [{}])[0].get("message") or {}).get("audio") or {}).get("data")
    if not audio_b64:
        raise RuntimeError(f"Xiaomi MiMo TTS no devolvió audio: {str(d)[:200]}")
    crudo = base64.b64decode(audio_b64)
    tmp = destino.with_name(destino.stem + "_mimo.wav")
    tmp.write_bytes(crudo)
    try:
        medios.ffmpeg("-i", str(tmp), "-ac", "1", "-ar", "24000", str(destino))
        tmp.unlink(missing_ok=True)
    except Exception:
        tmp.replace(destino)
    registro.apuntar("Xiaomi MiMo TTS", f"{len(texto)} caracteres · {config.XIAOMIMIMO_TTS_MODEL} · {voz_mimo}",
                     cantidad=len(texto), unidad="caracteres", produccion=produccion)
    return voz_mimo


def _fal_tts(texto: str, destino: Path, produccion: str, antes: str = "", despues: str = "") -> None:
    """ElevenLabs Multilingual v2 a través de fal (con el saldo de fal). `antes` y `despues` son el texto vecino:
    así cada trozo de un vídeo largo se entona como parte de la misma narración."""
    from . import visuales_api
    if not config.FAL_KEY or config.SIN_PAGO:
        raise RuntimeError("La voz de ElevenLabs por fal necesita FAL_KEY en .env (y STUDIO4_SIN_PAGO apagado).")
    cuerpo = {"text": texto, "voice": VOZ_FAL, "language_code": "es"}
    if antes:
        cuerpo["previous_text"] = antes[-600:]
    if despues:
        cuerpo["next_text"] = despues[:600]
    res = visuales_api._fal(FAL_TTS, cuerpo, limite_s=900)
    url = (res.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai no devolvió el audio: {str(res)[:160]}")
    mp3 = destino.with_suffix(".mp3")
    visuales_api._bajar(url, mp3)
    medios.ffmpeg("-i", str(mp3), "-ac", "1", "-ar", "24000", str(destino))
    mp3.unlink(missing_ok=True)
    registro.apuntar("fal.ai · voz ElevenLabs", f"{len(texto)} caracteres", cantidad=len(texto), unidad="caracteres",
                     produccion=produccion, usd=round(len(texto) / 1000 * FAL_TTS_POR_MIL, 4))


def coste_voz(segmentos: list[str], proveedor: str) -> float:
    """Lo que costará la locución (0 si es gratis)."""
    return round(sum(len(" ".join(x.split())) for x in segmentos) / 1000 * FAL_TTS_POR_MIL, 2) if proveedor == "fal" else 0.0


def estimar_voz(segmentos: list[str], proveedor: str, voice_id: str = "") -> dict[str, Any]:
    """Calcula los caracteres y el coste estimado de la locución según el proveedor y el modelo configurados."""
    limpios = [" ".join(s.split()) for s in segmentos if s and s.strip()]
    texto, _ = _spans_escenas(limpios) if limpios else ("", [])
    caracteres = len(texto)
    estimable = caracteres > 0
    if proveedor == "elevenlabs":
        restantes = registro.creditos_elevenlabs_restantes()
        vid = (voice_id or "").strip() or config.ELEVENLABS_VOICE_ID or VOZ_ELEVENLABS_POR_DEFECTO
        resumen = (f"{caracteres} caracteres · {caracteres} créditos en {config.ELEVENLABS_MODEL} "
                   f"(quedan ~{restantes} créditos este mes)"
                   if estimable else "No se pudo estimar el costo: aún no hay escenas con texto.")
        return {
            "proveedor": "elevenlabs",
            "modelo": config.ELEVENLABS_MODEL,
            "voice_id": vid,
            "caracteres": caracteres,
            "creditos": caracteres if estimable else 0,
            "creditos_restantes": restantes,
            "usd": 0.0,
            "consume_creditos": True,
            "estimable": estimable,
            "resumen": resumen,
        }
    if proveedor == "fal":
        usd = round(caracteres / 1000 * FAL_TTS_POR_MIL, 2) if estimable else 0.0
        resumen = (f"{caracteres} caracteres · ~{usd:.2f} $ en fal.ai ({FAL_TTS})"
                   if estimable else "No se pudo estimar el costo: aún no hay escenas con texto.")
        return {
            "proveedor": "fal",
            "modelo": FAL_TTS,
            "voice_id": VOZ_FAL,
            "caracteres": caracteres,
            "creditos": 0,
            "creditos_restantes": 0,
            "usd": usd,
            "consume_creditos": True,
            "estimable": estimable,
            "resumen": resumen,
        }
    if proveedor == "mimo":
        vid = (voice_id or "").strip() if (voice_id or "").strip() in VOCES_MIMO else VOZ_MIMO_POR_DEFECTO
        return {
            "proveedor": "mimo",
            "modelo": config.XIAOMIMIMO_TTS_MODEL,
            "voice_id": vid,
            "caracteres": caracteres,
            "creditos": 0,
            "creditos_restantes": 0,
            "usd": 0.0,
            "consume_creditos": False,
            "estimable": estimable,
            "resumen": f"{caracteres} caracteres · gratis con Xiaomi MiMo ({config.XIAOMIMIMO_TTS_MODEL} · {vid})" if estimable else f"Gratis con Xiaomi MiMo ({vid})",
        }
    return {
        "proveedor": "gemini",
        "modelo": config.MODELO_TTS,
        "voice_id": "",
        "caracteres": caracteres,
        "creditos": 0,
        "creditos_restantes": 0,
        "usd": 0.0,
        "consume_creditos": False,
        "estimable": estimable,
        "resumen": f"{caracteres} caracteres · gratis con Gemini TTS ({config.MODELO_TTS})" if estimable else "Gratis con Gemini TTS",
    }


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
    """La otra voz, si está configurada (Gemini, ElevenLabs o Xiaomi MiMo)."""
    if proveedor == "gemini":
        if config.ELEVENLABS_API_KEY:
            return "elevenlabs"
        if config.XIAOMIMIMO_API_KEY:
            return "mimo"
    if proveedor in ("elevenlabs", "mimo"):
        if config.GEMINI_API_KEY:
            return "gemini"
        if proveedor == "elevenlabs" and config.XIAOMIMIMO_API_KEY:
            return "mimo"
    return None


# --- Entrada única ----------------------------------------------------------------------------
FRASE_MUESTRA = ("Así sonaría la narración de tu vídeo: tranquila cuando la historia respira, "
                 "y con fuerza cuando llega el momento que nadie esperaba.")


def muestra_generica(voz_nombre: str) -> Path:
    """La frase de presentación de una voz, grabada una sola vez y guardada para escucharla al instante."""
    if voz_nombre not in config.VOCES_GEMINI:
        raise ValueError(f"Voz desconocida: {voz_nombre}")
    destino = config.PRODUCCIONES / "_voces" / f"{voz_nombre}.wav"
    if not destino.exists() or destino.stat().st_size < 2000:
        destino.parent.mkdir(parents=True, exist_ok=True)
        _gemini(FRASE_MUESTRA, destino, "", voz_nombre)
    return destino


def muestra(texto: str, voz_nombre: str, destino: Path, produccion: str = "") -> Path:
    """Unos segundos de tu guion con una voz concreta, para compararlas antes de elegir."""
    if voz_nombre not in config.VOCES_GEMINI:
        raise ValueError(f"Voz desconocida: {voz_nombre}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    _gemini(" ".join(texto.split()), destino, produccion, voz_nombre)
    return destino


def acelerar(wav: Path, velocidad: float) -> None:
    """Cambia la velocidad de la locución sin cambiar el tono (atempo de FFmpeg)."""
    if abs(float(velocidad) - 1.0) < 0.01:
        return
    tmp = wav.with_name(wav.stem + "_vel.wav")
    medios.ffmpeg("-i", str(wav), "-filter:a", f"atempo={float(velocidad):.2f}", str(tmp))
    tmp.replace(wav)


def trozos(segmentos: list[str], limite: int | None = None) -> list[tuple[int, int]]:
    """Escenas agrupadas en trozos de como mucho `limite` caracteres, sin partir ninguna escena: [(desde, hasta)]."""
    limite = limite or LIMITE_TROZO
    salida, desde, suma = [], 0, 0
    for i, s in enumerate(segmentos):
        n = len(" ".join(s.split())) + 1
        if i > desde and suma + n > limite:
            salida.append((desde, i))
            desde, suma = i, 0
        suma += n
    salida.append((desde, len(segmentos)))
    return salida


def locutar(segmentos: list[str], destino: Path, proveedor: str = "gemini", produccion: str = "",
            direcciones: list[dict[str, str]] | None = None, voz_nombre: str | None = None,
            estilo_voz: str = "", velocidad: float = 1.0, voice_id: str | None = None) -> dict[str, Any]:
    """Genera la locución y devuelve {'duracion', 'escenas': [{ini, fin}], 'palabras': [{palabra, ini, fin}]}.
    Un guion largo (más de ~3 min de voz) se graba por trozos de escenas enteras y se une: ninguna voz admite
    15 minutos en una sola llamada. Los tiempos de cada trozo se recolocan sobre el total."""
    grupos = trozos(segmentos)
    extra = {"voice_id": voice_id} if voice_id else {}
    if len(grupos) == 1:
        return _locutar_uno(segmentos, destino, proveedor, produccion, direcciones, voz_nombre, estilo_voz, velocidad, **extra)
    destino.parent.mkdir(parents=True, exist_ok=True)
    partes, escenas, palabras, desplazamiento, resultado = [], [], [], 0.0, {}
    for k, (a, b) in enumerate(grupos):
        parte = destino.with_name(f"{destino.stem}_trozo{k + 1:02d}.wav")
        contexto = (" ".join(segmentos[max(0, a - 3):a]), " ".join(segmentos[b:b + 3]))
        resultado = _locutar_uno(segmentos[a:b], parte, proveedor, produccion, direcciones[a:b] if direcciones else None,
                                 voz_nombre, estilo_voz, velocidad, contexto=contexto, **extra)
        escenas += [{"ini": round(x["ini"] + desplazamiento, 3), "fin": round(x["fin"] + desplazamiento, 3)} for x in resultado["escenas"]]
        palabras += [{**w, "ini": round(w["ini"] + desplazamiento, 3), "fin": round(w["fin"] + desplazamiento, 3)}
                     for w in resultado["palabras"]]
        desplazamiento += resultado["duracion"]
        partes.append(parte)
    entradas = [x for parte in partes for x in ("-i", str(parte))]
    unir = "".join(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono[a{i}];" for i in range(len(partes)))
    unir += "".join(f"[a{i}]" for i in range(len(partes))) + f"concat=n={len(partes)}:v=0:a=1[o]"
    medios.ffmpeg(*entradas, "-filter_complex", unir, "-map", "[o]", str(destino))
    for parte in partes:
        parte.unlink(missing_ok=True)
    return {**resultado, "duracion": round(medios.duracion(destino), 3), "escenas": escenas, "palabras": palabras,
            "trozos": len(partes)}


def _locutar_uno(segmentos: list[str], destino: Path, proveedor: str = "gemini", produccion: str = "",
                 direcciones: list[dict[str, str]] | None = None, voz_nombre: str | None = None,
                 estilo_voz: str = "", velocidad: float = 1.0, contexto: tuple[str, str] = ("", ""),
                 voice_id: str | None = None) -> dict[str, Any]:
    """Genera la locución y devuelve {'duracion', 'escenas': [{ini, fin}], 'palabras': [{palabra, ini, fin}]}.
    Con `direcciones` (tono y ritmo por escena), Gemini TTS interpreta cada escena como toca."""
    limpios = [" ".join(s.split()) for s in segmentos]
    texto, spans = _spans_escenas(limpios)   # los tiempos se calculan siempre sobre el texto sin etiquetas
    destino.parent.mkdir(parents=True, exist_ok=True)

    alineacion = None
    dirigida = False
    voz_el_id = (voice_id or "").strip() or config.ELEVENLABS_VOICE_ID or VOZ_ELEVENLABS_POR_DEFECTO
    if proveedor == "elevenlabs":
        alineacion = _elevenlabs(texto, destino, produccion, voice_id=voz_el_id)
    elif proveedor == "mimo":
        voz_el_id = _mimo_tts(texto, destino, produccion, voice_id=voice_id or voz_nombre, estilo_voz=estilo_voz)
    elif proveedor == "fal":   # sus tiempos se miden por los silencios, como con Gemini
        _fal_tts(texto, destino, produccion, *contexto)
    else:
        dirigido = _texto_dirigido(limpios, direcciones)
        _gemini(dirigido, destino, produccion, voz_nombre, estilo_voz)
        dirigida = dirigido != texto
        if dirigida and _leyo_etiquetas(destino, texto, produccion):
            # Si la voz pronunció alguna etiqueta, se repite la toma sin dirección por escena.
            _gemini(texto, destino, produccion, voz_nombre, estilo_voz)
            dirigida = False
    if abs(float(velocidad) - 1.0) >= 0.01:   # los tiempos se miden después, sobre la voz ya acelerada
        acelerar(destino, velocidad)
        alineacion = None
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
            "dirigida": dirigida, "voz_nombre": voz_nombre or config.VOZ_GEMINI if proveedor == "gemini" else (voz_el_id if proveedor == "mimo" else (voz_nombre or "")),
            "voice_id": voz_el_id if proveedor in ("elevenlabs", "mimo") else ""}
