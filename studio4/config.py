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
    "Charon": "Informativa y grave: documental",
    "Sadaltager": "Con aire de experto: divulgación",
    "Orus": "Firme y segura",
    "Gacrux": "Madura y pausada",
    "Iapetus": "Clara y cercana",
    "Algenib": "Rasgada, con carácter",
    "Kore": "Firme y nítida",
    "Sulafat": "Cálida",
    "Aoede": "Ligera y fresca",
    "Puck": "Animada",
    "Fenrir": "Enérgica, emocionante",
    "Enceladus": "Suave, casi susurrada",
}
ESTILO_VOZ = os.getenv(
    "GEMINI_TTS_ESTILO",
    "Narra en español neutro, como un documental intrigante: ritmo ágil, pausas cortas entre frases",
)

# --- fal.ai (de pago por uso, con saldo previo): imágenes Nano Banana y vídeo Veo 3.1 sin la facturación de Google --
FAL_KEY = (os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY") or "").strip()

# --- DeepSeek (de pago por uso, céntimos por guion): escribe los guiones ---------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")   # o deepseek-v4-pro, más fino y más caro
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com").rstrip("/")

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

# --- Modo sin coste: STUDIO4_SIN_PAGO=1 apaga todo lo que se cobra (DeepSeek, ElevenLabs, fal.ai).
# El guion lo escribe Gemini y la voz es Gemini TTS: sirve para probar la secuencia entera gratis.
SIN_PAGO = os.getenv("STUDIO4_SIN_PAGO", "").strip().lower() in ("1", "true", "si", "sí")
if SIN_PAGO:
    DEEPSEEK_API_KEY = ""
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
SEGUNDOS_CLIP = 8       # lo más largo que genera Flow (Veo) por clip
CAMARA_LENTA_MAX = 1.5  # si la voz dura más que el clip, se ralentiza hasta aquí y luego se congela el final

# Estilos visuales que el director inyecta en cada prompt de Flow (siempre en inglés para Veo).
ESTILOS = {
    "cinematografico": "cinematic live-action, anamorphic 35mm lens, shallow depth of field, film grain, natural color grading",
    "documental": "documentary realism, handheld camera feel, natural light, authentic textures",
    "anime": "high-quality anime, cel shading, vibrant colors, detailed backgrounds, Studio-style lighting",
    "animacion3d": "high-end 3D animated film, soft global illumination, expressive characters, rich materials",
    "noir": "neo-noir, high-contrast low-key lighting, deep shadows, wet streets, teal and amber palette",
    "scifi": "epic science fiction, volumetric light, atmospheric haze, futuristic production design",
}

MAX_BYTES_MEDIO = 400 * 1024 * 1024


def salud() -> list[str]:
    """Lo que falta para poder producir; el panel lo muestra arriba."""
    import shutil
    faltas = []
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        faltas.append("Falta FFmpeg (ffmpeg y ffprobe) en el PATH: sin él no hay voz ni render.")
    if SIN_PAGO:
        faltas.append("Modo sin coste (STUDIO4_SIN_PAGO=1): el guion lo escribe Gemini y no se usa nada de pago.")
    elif not DEEPSEEK_API_KEY:
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
