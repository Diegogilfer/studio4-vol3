"""Configuración única de STUDIO 4: rutas, claves, formatos y el código de emparejamiento con Flow."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv, set_key

RAIZ = Path(__file__).resolve().parent.parent
ENV_FILE = RAIZ / ".env"
load_dotenv(ENV_FILE)

PRODUCCIONES = RAIZ / "producciones"
WEB = RAIZ / "web"
PUERTO = int(os.getenv("STUDIO4_PUERTO", "8000"))

# --- Google Gemini (API gratuita de AI Studio): guion, plan de escenas y voz ---------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODELO_TEXTO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MODELOS_TEXTO_RESERVA = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash"]
MODELO_TTS = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
MODELOS_TTS_RESERVA = ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
VOZ_GEMINI = os.getenv("GEMINI_TTS_VOICE", "Charon")
# Voces de Gemini TTS buenas para narrar, con el carácter que les da Google.
VOCES_GEMINI = {
    "Charon": "Informativa y grave: documental (hombre)",
    "Sadaltager": "Con aire de experto: divulgación (hombre)",
    "Orus": "Firme y segura (hombre)",
    "Gacrux": "Madura y pausada (mujer)",
    "Iapetus": "Clara y cercana (hombre)",
    "Algenib": "Rasgada, con carácter (hombre)",
    "Kore": "Firme y nítida (mujer)",
    "Sulafat": "Cálida (mujer)",
    "Aoede": "Ligera y fresca (mujer)",
    "Puck": "Animada (hombre)",
    "Fenrir": "Enérgica, emocionante (hombre)",
    "Enceladus": "Suave, casi susurrada (hombre)",
    # el resto de las 30 voces de Google (todas gratis): más variedad para no repetir siempre las mismas
    "Zephyr": "Brillante (mujer)",
    "Leda": "Juvenil (mujer)",
    "Callirrhoe": "Relajada (mujer)",
    "Autonoe": "Luminosa (mujer)",
    "Despina": "Suave y fluida (mujer)",
    "Erinome": "Clara (mujer)",
    "Laomedeia": "Alegre (mujer)",
    "Achernar": "Delicada (mujer)",
    "Pulcherrima": "Directa (mujer)",
    "Vindemiatrix": "Amable (mujer)",
    "Umbriel": "Tranquila (hombre)",
    "Algieba": "Suave y fluida (hombre)",
    "Rasalgethi": "Informativa (hombre)",
    "Alnilam": "Firme (hombre)",
    "Schedar": "Equilibrada (hombre)",
    "Achird": "Amigable (hombre)",
    "Zubenelgenubi": "Informal (hombre)",
    "Sadachbia": "Vivaz (hombre)",
}
ESTILO_VOZ = os.getenv(
    "GEMINI_TTS_ESTILO",
    "Narra en español latino neutro, como un documental intrigante: ritmo ágil, pausas cortas entre frases",
)

# --- fal.ai (de pago por uso, con saldo previo): imágenes Nano Banana y vídeo Veo 3.1 sin la facturación de Google --
FAL_KEY = (os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY") or "").strip()

# --- DeepSeek (de pago por uso, céntimos por guion): escribe los guiones ---------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")   # V4.1-Flash (ve imágenes); o deepseek-v4-pro, más caro
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com").rstrip("/")
BUSQUEDA_WEB = os.getenv("STUDIO4_BUSQUEDA_WEB", "") == "1"   # búsqueda web de DeepSeek: de pago, se activa a mano

# --- Xiaomi MiMo (API compatible con OpenAI en api.xiaomimimo.com/v1): guionista y voz TTS --------
XIAOMIMIMO_API_KEY = os.getenv("XIAOMIMIMO_API_KEY", "").strip()
XIAOMIMIMO_MODEL = os.getenv("XIAOMIMIMO_MODEL", "mimo-v2.6-flash")
XIAOMIMIMO_TTS_MODEL = os.getenv("XIAOMIMIMO_TTS_MODEL", "mimo-v2.5-tts")
XIAOMIMIMO_URL = os.getenv("XIAOMIMIMO_URL", "https://api.xiaomimimo.com/v1").rstrip("/")

# --- YouTube (solo lectura). Con la clave basta para datos públicos: búsquedas y estadísticas de tu canal.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
YOUTUBE_CANAL = os.getenv("YOUTUBE_CANAL", "").strip()   # @usuario o id UC… de tu canal

# Duración de cada versión: el corto sirve para Shorts y Reels; el largo, para YouTube.
VERSIONES = {
    "corto": {"nombre": "Corto · Shorts y Reels", "formato": "vertical", "segundos": 48},   # 6 clips de 8 s
    "largo": {"nombre": "Largo · YouTube", "formato": "horizontal", "segundos": 300},
}

# --- ElevenLabs (opcional; el plan gratis no permite uso comercial) ------------------------------
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_v3")   # el más natural; eleven_multilingual_v2 como alternativa
ELEVENLABS_CREDITOS_MES = int(os.getenv("ELEVENLABS_CREDITOS_MES", "10000"))

# --- Modo sin coste: STUDIO4_SIN_PAGO=1 apaga todo lo que se cobra (DeepSeek, Xiaomi MiMo, ElevenLabs, fal.ai).
# El guion lo escribe Gemini y la voz es Gemini TTS: sirve para probar la secuencia entera gratis.
SIN_PAGO = os.getenv("STUDIO4_SIN_PAGO", "").strip().lower() in ("1", "true", "si", "sí")
if SIN_PAGO:
    DEEPSEEK_API_KEY = ""
    XIAOMIMIMO_API_KEY = ""
    ELEVENLABS_API_KEY = ""
    FAL_KEY = ""

# --- Render -----------------------------------------------------------------------------------
FORMATOS = {
    "vertical": {"ancho": 1080, "alto": 1920, "aspecto": "9:16", "nombre": "Vertical 9:16 (Shorts, Reels, TikTok)"},
    "horizontal": {"ancho": 1920, "alto": 1080, "aspecto": "16:9", "nombre": "Horizontal 16:9 (YouTube)"},
    "cuadrado": {"ancho": 1080, "alto": 1080, "aspecto": "1:1", "nombre": "Cuadrado 1:1 (Feed)"},
}
FPS = 30
VOLUMEN_AMBIENTE = float(os.getenv("STUDIO4_VOLUMEN_AMBIENTE", "0.15"))  # sonido de Veo bajo la voz; 0 = sin él
VOLUMEN_MUSICA = float(os.getenv("STUDIO4_VOLUMEN_MUSICA", "0.18"))      # música de fondo; baja sola cuando habla la voz
SEGUNDOS_CLIP = 8       # lo más largo que genera Flow (Veo) por clip
VELOCIDADES = (0.9, 1.0, 1.1, 1.2)   # velocidad de la voz: FFmpeg acelera sin cambiar el tono
CAMARA_LENTA_MAX = 1.5  # si la voz dura más que el clip, se ralentiza hasta aquí y luego se congela el final

# Estilos visuales que el director inyecta en cada prompt de Flow (siempre en inglés para Veo).
from .estilos import ESTILOS as _FICHAS   # el texto de cada estilo sale de studio4/estilos.py
# Los 13 del panel clásico, en su orden (web/panel.js tiene la misma lista). «videojuego» se conserva para vídeos viejos.
_CLASICOS = ("cinematografico", "hiperrealista", "documental", "videojuego", "animacion3d", "anime", "cartoon",
             "stickman", "comic", "pixelart", "stopmotion", "noir", "scifi")
_VIEJOS = {"videojuego": "modern AAA video game graphics, Unreal Engine 5 render, real-time ray tracing, in-game camera, open-world look",
           "stickman": "minimalist stick figure animation, simple black line characters on a plain white background, clean doodle style",
           "pixelart": "retro pixel art, 16-bit video game style, limited color palette, crisp pixels"}
ESTILOS = {k: (_FICHAS.get(k) or {}).get("visual") or _VIEJOS[k] for k in _CLASICOS}
ESTILO_POR_DEFECTO = "cinematografico"


def estilo_valido(estilo: str) -> str:
    """El estilo si existe; si no (vacío o uno viejo), el de por defecto."""
    return estilo if estilo in ESTILOS else ESTILO_POR_DEFECTO

def _equipo_ligero() -> bool:
    """Modo ligero para PCs flojos (menos de 4 núcleos o menos de 8 GB): 720p, sin cámara lenta interpolada y
    Whisper «base». STUDIO4_LIGERO=1 lo fuerza y =0 lo apaga."""
    v = os.getenv("STUDIO4_LIGERO", "").strip().lower()
    if v in ("1", "si", "sí", "true"):
        return True
    if v in ("0", "no", "false"):
        return False
    try:
        import psutil
        return (psutil.cpu_count(logical=False) or 4) < 4 or psutil.virtual_memory().total < 8 * 2**30
    except Exception:  # noqa: BLE001 - sin psutil, modo normal
        return False


MODO_LIGERO = _equipo_ligero()
WHISPER_MODELO = os.getenv("STUDIO4_WHISPER", "base" if MODO_LIGERO else "small")

MAX_BYTES_MEDIO = 400 * 1024 * 1024
MAX_BYTES_VIDEO = 8 * 1024 * 1024 * 1024   # vídeos de tu PC para editar (gameplay grabado puede pesar varios GB)


def salud() -> list[str]:
    """Lo que falta para poder producir; el panel lo muestra arriba."""
    import shutil
    faltas = []
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        faltas.append("Falta FFmpeg (ffmpeg y ffprobe) en el PATH: sin él no hay voz ni render.")
    if SIN_PAGO:
        faltas.append("Modo sin coste (STUDIO4_SIN_PAGO=1): el guion lo escribe Gemini y no se usa nada de pago.")
    elif not DEEPSEEK_API_KEY and not XIAOMIMIMO_API_KEY:
        faltas.append("Sin DEEPSEEK_API_KEY en .env: los guiones los escribirá Gemini (platform.deepseek.com › API keys).")
    if not GEMINI_API_KEY:
        faltas.append("Falta GEMINI_API_KEY en .env (gratis en https://aistudio.google.com/apikey).")
    return faltas


# --- Código de emparejamiento con la extensión de Flow ------------------------------------------
VAR_TOKEN = "STUDIO4_FLOW_TOKEN"


def token_flow() -> str:
    """El código que comparte la extensión. Si no existe, se crea y se guarda en .env."""
    return os.getenv(VAR_TOKEN, "").strip() or renovar_token_flow()


def renovar_token_flow() -> str:
    nuevo = secrets.token_urlsafe(18)
    os.environ[VAR_TOKEN] = nuevo
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), VAR_TOKEN, nuevo, quote_mode="never")
    return nuevo
