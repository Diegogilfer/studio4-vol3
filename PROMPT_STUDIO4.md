# Prompt de contexto · Studio 4

> Pega este documento al empezar una conversación con una IA (o léelo tú) para trabajar sobre Studio 4.
> Todo lo que dice está sacado del código del proyecto (`C:\Users\Lenovo\studio4-vol3`, rama `reestructura-google`)
> y de pruebas hechas el 2026-10-15. Si algo cambia en el código, este documento hay que actualizarlo.

---

## 1. Qué es Studio 4

Un estudio de vídeo **local** (tu PC, Windows) que convierte una idea, un guion o un vídeo existente en
**tres entregas listas para publicar**: vídeo completo, Reels y Shorts, con portadas y textos.
Funciona por **canal** (hoy: FourLevel y ARIGAB): cada canal tiene su nicho, tono, referentes y fuentes, y cada
producción es independiente (borrarla la desvincula; va a `producciones/_papelera`).

- Servidor: `servidor.py` en `http://127.0.0.1:8000` (se abre con el acceso directo «STUDIO 4» / `iniciar.bat`).
- Panel web: `web/` (vistas Inicio, Crear, Canales, Tendencias, Flow, Render, Entregas).
- Código: `studio4/` (un módulo por paso). Pruebas: `tests/test_studio4.py`.
- Claves: `studio4-vol3\.env` (no se sube a git).
- Entregas: `Vídeos\STUDIO 4\<canal>\<fecha> · <título> (<versión>)\` con 3 subcarpetas:
  `1 Clips de Flow`, `2 Guion y escenas`, `3 Entregas`.

## 2. El esquema, paso a paso

| # | Paso | Qué hace | Quién lo hace (módulo) |
|---|---|---|---|
| 1 | Investigación | Dossier con hechos, fechas, nombres, "lo que casi nadie sabe", dudas. Primero las **fuentes de confianza del canal** (p. ej. gtabase.com), luego Wikipedia ES/EN; YouTube aporta qué existe ya sobre el tema y qué funciona en tu canal | `investigacion.py`, `fuentes.py` (respeta robots.txt, 1 petición/s), `youtube.py`, `tendencias.py` |
| 2 | Guion | Texto de la voz en off con las reglas del canal | `guion.py` → DeepSeek (`deepseek-v4-flash`); si falla, Gemini |
| 3 | Escenas | Gemini divide el guion en escenas: texto de voz, plano, cámara, acción, personajes con ficha fija, vídeo o imagen, segundos (máx. 8 por clip) | `director.py` |
| 4 | Voz | Gemini TTS (voz por defecto «Charon»), tiempos de cada escena y palabra | `voz.py` (ElevenLabs opcional) |
| 5 | Visuales | Cada escena necesita un clip o imagen. Opciones: **Google Flow a mano** con la extensión, subir tus archivos, fotos de archivo de dominio público (Wikimedia Commons), tarjetas de diseño gratis o API de pago (fal.ai / Google con facturación) | `flow.py` + `extension-flow/`, `archivo.py`, `tarjetas.py`, `visuales_api.py` |
| 6 | Montaje | FFmpeg: carátula de entrada (2 s), cada toma ajustada a su trozo de voz, zoom lento en imágenes, subtítulos palabra a palabra (estilo viral o cine, también los ruidos), sonido ambiente bajo la voz, −14 LUFS | `render.py`, `subtitulos.py`, `sonidos.py` |
| 7 | Entregas | Gemini elige el mejor momento para Reels y Shorts; portadas y descripciones | `entregas.py`, `miniaturas.py` |

Otras entradas: **guion propio** (pegado o en archivo; si es demasiado corto se investiga y se completa),
**importar vídeo** por enlace o archivo (yt-dlp descarga, faster-whisper transcribe en tu PC, FFmpeg detecta
cortes de plano y se rehace por escenas).

## 3. Qué es gratis y qué se paga (real)

| Servicio | Para qué | Coste real | Nota comprobada |
|---|---|---|---|
| **Gemini API (Google AI Studio), nivel gratis** | Escenas, investigación, voz TTS, elegir momentos, revisar imágenes | 0 $ | La clave debe ser de un proyecto **sin facturación**. Si el proyecto pasa a prepago con saldo 0, Google responde **402** y deja de funcionar todo, también lo gratis |
| Gemini: imágenes y vídeo (Veo) por API | Generar visuales automáticamente | De pago | En el nivel gratis responde **429 "limit: 0"**: no hay cupo gratis |
| Gemini: búsqueda de Google integrada | Investigación | — | En el nivel gratis da 429; el estudio usa Wikipedia en su lugar |
| **Google Flow (Veo)** | Clips de vídeo e imágenes de cada escena | Tu suscripción de Google (gasta sus créditos) | Se usa **a mano**: la extensión muestra el prompt y trae lo generado a su escena. No se automatiza (normas de Google) |
| **YouTube Data API v3** | Datos de tu canal, referentes, tendencias, lo que ya existe | 0 $ (cupo de 10.000 unidades al día) | Solo lectura: Studio 4 **no publica** |
| Enlaces de Google Maps | Lugar de referencia para el guion | 0 $ | Solo se lee el nombre y las coordenadas del enlace; no usa la API de Maps |
| Wikipedia, Wikimedia Commons | Investigación y fotos históricas de dominio público | 0 $ | Solo fotos con licencia de dominio público |
| FFmpeg, yt-dlp, faster-whisper, Edge | Montaje, descargas/subtítulos, transcripción, dibujar tarjetas y carátulas | 0 $ (en tu PC) | |
| DeepSeek | Escribe los guiones | Céntimos por guion | Opcional: sin clave escribe Gemini (`STUDIO4_SIN_PAGO=1` apaga todo lo de pago) |
| fal.ai | Imágenes Nano Banana (0,04 $/imagen) y vídeo Veo 3.1 Fast | Saldo prepagado | Opcional. Con `FAL_KEY` en `.env` se usa en lugar de la API de Google |
| ElevenLabs | Otra voz | Opcional | El plan gratis no permite uso comercial |

## 3 bis. Mapa: qué genera cada paso, qué hace tu código y dónde entra Google

| Paso | Qué sale | Tu código (en tu PC) | Servicio externo y dónde se llama | Si ese servicio falla |
|---|---|---|---|---|
| Investigación | Dossier con hechos, fechas y fuentes | `investigacion.py`, `fuentes.py` (lee webs de confianza, robots.txt) | **Gemini + Búsqueda de Google** (`investigacion.py:_con_google`); Gemini resume Wikipedia y tus fuentes | Wikipedia; los resúmenes los hace DeepSeek (reserva) |
| Contexto de YouTube | Competencia, tu canal, tendencias | `youtube.py`, `tendencias.py` | **YouTube Data API v3** (`youtube.py`, `API = googleapis.com/youtube/v3`); Gemini escribe el informe | El informe lo hace DeepSeek; sin YouTube no hay datos |
| Aprender del nicho | Manual del canal | `aprender.py` (lee subtítulos con yt-dlp, mide ritmo) | YouTube Data API para elegir vídeos; **DeepSeek** analiza | Gemini de reserva |
| Guion / Completar | Texto de la voz | `guion.py` (reglas, longitud, limpieza) | **DeepSeek** escribe | Gemini de reserva |
| Escenas | Plano, cámara, acción, personajes, prompts | `director.py` (arma el prompt final con fichas, luz y estilo) | **Gemini** planifica | DeepSeek (reserva) |
| Voz | `voz.wav` y tiempos de cada palabra | `voz.py` (une, corta por silencios, reparte palabras) | **Gemini TTS** (`voz.py:_gemini`); Gemini escucha si leyó etiquetas (`voz.py:_leyo_etiquetas`) | ElevenLabs si hay clave; si no, **no hay voz** |
| Visuales | Clip o imagen por escena | `flow.py` + `extension-flow/` (recoge), `archivo.py`, `tarjetas.py` (Edge local) | **Google Flow** a mano (`labs.google`); API de imagen/Veo de Google (`visuales_api.py`, exige facturación); fal.ai | Fotos de Commons, tarjetas o subir tus archivos |
| Revisión de imágenes | ¿Mismo personaje? ¿Cuenta la escena? | `visuales_api.py:revisar` | **Gemini** (ve imágenes) | Se da por buena (sin reserva) |
| Montaje | `final.mp4` con carátula y subtítulos | `render.py`, `subtitulos.py`, `medios.py` (FFmpeg) | — | — |
| Sonidos subtitulados | Rótulos de ruidos | `sonidos.py` (FFmpeg mide silencios) | **Gemini** escucha el audio | Sale sin rótulos de ruido |
| Entregas | Reels, Short, portadas, textos | `entregas.py`, `miniaturas.py` (recorta y compone) | **Gemini** elige momentos (texto) y analiza fotogramas (imagen) | Momentos: DeepSeek; análisis de imagen: sin reserva |
| Referencias tuyas | Lo que aportan fotos, PDF y enlaces | `referencias.py` (enlaces de Maps sin API) | **Gemini** ve fotos y PDF | Sin reserva para fotos y PDF |
| Importar vídeo | Escenas con texto y trozo de vídeo | `importar.py` (yt-dlp, faster-whisper y FFmpeg, todo local) | — | — |

Cortocircuito: tras un 402 o con el cupo del día agotado, Gemini queda en pausa (30/60 min) y los pasos de texto
van directos a la reserva sin esperas.

## 4. Cómo conectar todo lo gratis de Google

1. **Gemini** → en Google AI Studio, *API keys* → *Crear clave de API* en un **proyecto nuevo sin facturación**.
   En `.env`: `GEMINI_API_KEY=...`
2. **YouTube (lectura)** → en Google Cloud, activar *YouTube Data API v3* y crear una clave de API.
   En `.env`: `YOUTUBE_API_KEY=...` y `YOUTUBE_CANAL=@tucanal`. (O el botón «Conectar YouTube», que usa OAuth
   de solo lectura y además da estadísticas privadas).
3. **Google Flow** → con tu suscripción, abre Flow en Chrome/Edge y carga la extensión sin empaquetar desde
   `studio4-vol3\extension-flow` (versión 2.2.0). Si el panel avisa de una versión vieja, recárgala desde esa carpeta.
4. Arranca Studio 4 con el acceso directo «STUDIO 4».

## 5. El camino más fácil para un vídeo (y solo con lo gratis de Google)

1. **Crear** → escribe la idea (o pega tu guion) → elige *Corto* (vertical, 50 s) o *Largo* (horizontal, 300 s).
2. Revisa el **guion** → «Aprobar guion y crear escenas». Opciones: «Escribir otra versión», «Completar la historia».
3. **Flow** → cada escena trae su prompt (con la ficha de cada personaje, la luz y el estilo, y la duración del clip).
   Genera en Flow; la extensión trae el clip a su escena. Puedes «Añadir escena después», «Quitar escena» o «Subir clip».
4. **Render** → «Renderizar»: monta el vídeo completo con carátula, subtítulos y sonido.
5. **Entregas** → vídeo completo, Reels y Short con portadas y textos, en tu carpeta de Vídeos.

Coste con esta ruta: 0 $ fuera de los créditos de tu suscripción de Flow (y céntimos si el guion lo escribe DeepSeek).

## 6. Reglas del proyecto (decididas por el autor)

- Respuestas y textos en español. Sin etiquetas de IA ni nombres de modelos en el panel.
- Nada de interfaz escondida; poco texto; botones con acciones precisas.
- Dos fuentes: Geist e Instrument Serif. Diseño suave, redondeado, animaciones tranquilas; 14 temas de color.
- Cada producción es independiente: lo que se elimina se olvida.
- Primero lo gratis y de Google; lo de pago solo con presupuesto explícito y aprobación previa.
- No tocar la sesión abierta del autor (producción o canal activo) para hacer pruebas.
- No publicar en redes sin aprobación expresa.

## 7. En pruebas (2026-10-15)

- **Aprender del nicho** (`aprender.py`): lee los subtítulos de los vídeos más vistos de los canales referentes
  y del nicho (sin descargarlos), estudia cómo enganchan, presentan, estructuran y cierran, y escribe el
  **manual del canal** que el guionista debe seguir. Pendiente: conectarlo al guion y mostrarlo en el panel.
- Guion corto = **historia completa** (contexto → hechos en orden → giro → cierre) y regla
  **"el espectador no sabe nada"** (presentar a cada persona, juego o lugar la primera vez).
