# STUDIO 4 Vol. 3 🎬

Pipeline automatizado de generación audiovisual de alta retención combinando inteligencia artificial generativa, síntesis vocal y renderizado de video con FFmpeg.

---

## ⚡ Arquitectura del Sistema

```
                        ┌─────────────────────────────────────┐
                        │          USUARIO / CLI              │
                        │      python main.py "Tema"          │
                        │      [--writer gemini | claude]     │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │ 1. writer.py (Google Gemini / Claude)   │
                      │    - Por defecto: Gemini 2.5            │
                      │    - Guion magnético de alta retención   │
                      │    - Gancho viral en los 1ros 3 segundos│
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │ 2. gemini_director.py (Gemini 2.5 Flash)│
                      │    - Salida estructurada JSON estricta  │
                      │    - Título viral + Descripción SEO     │
                      │    - Desglose de escenas + B-roll Pexels│
                      └─────────────┬─────────────────┬─────────┘
                                    │                 │
                   ┌────────────────┴──────┐   ┌──────┴────────────────┐
                   │ 3. voice.py           │   │ 4. video_maker.py     │
                   │    - Google Cloud TTS │   │    - Pexels API       │
                   │    - Neural2/Journey  │   │    - Descarga B-roll  │
                   │    - Audio WAV        │   │      en HD por escena │
                   └───────────────┬───────┘   └──────┬────────────────┘
                                   │                  │
                                   └─────────┬────────┘
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │ 5. video_maker.py (FFmpeg)│
                               │    - Normalización y trim │
                               │    - Concat de escenas    │
                               │    - Mezcla de audio final│
                               │    - output/video_final   │
                               └───────────────────────────┘
```

---

## 🛠 Requisitos Previos

- **Python 3.10+** (Detectado: Python 3.13)
- **FFmpeg y FFprobe** instalados y disponibles en el PATH del sistema.

---

## 📦 Instalación

1. Crear un entorno virtual (recomendado) y activar:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate   # En Windows
   ```

2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔑 Configuración (`.env`)

Copia la plantilla `.env.example` como `.env`:

```bash
copy .env.example .env
```

Edita `.env` con tus credenciales:

```ini
# Anthropic Claude API Key (Guionista Creativo)
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini API Key (Director Técnico)
GEMINI_API_KEY=AIzaSy...

# Pexels API Key (B-roll & Footage)
PEXELS_API_KEY=...

# Google Cloud Service Account (Google Cloud TTS)
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
```

---

## 🚀 Uso

### Ejecución básica:
```bash
python main.py "La paradoja de Fermi y el silencio del universo"
```

### Opciones avanzadas:
```bash
# Formato vertical (Shorts / Reels / TikTok) de 45 segundos:
python main.py "3 hábitos estoicos que cambiarán tu vida" --duration 45 --orientation portrait

# Especificar una voz particular de Google Cloud TTS:
python main.py "El telescopio James Webb" --voice es-US-Journey-F

# Cambiar ruta de salida:
python main.py "El origen de la inteligencia artificial" --output output/ia_origen.mp4
```

---

## 📂 Archivos Generados en Cada Ejecución

- `output/script.txt`: Guion limpio generado por Claude.
- `output/production_plan.json`: Estructura JSON con desglose de escenas, palabras clave de Pexels, título y descripción SEO generados por Gemini.
- `output/audio.wav`: Pista de locución continua de Google Cloud TTS.
- `temp_clips/`: Metraje B-roll descargado y clips normalizados.
- `output/video_final.mp4`: Video ensamblado y sincronizado listo para publicar.

