# STUDIO #4 Vol. 4

Estudio de vídeo local (Windows) que convierte una idea, un guion o un vídeo existente en **tres entregas listas para publicar** (vídeo completo, Reels y Shorts, con portadas y textos), organizado por **canal**.

```
 Tema ─► Fuentes del canal + Wikipedia + YouTube ─► Dossier
                │
                ▼
         DeepSeek (o Gemini gratis) ─► Guion con las reglas y el manual del canal
                │
                ▼
         Gemini (gratis) ─► Escenas: texto de voz + prompt para Flow (biblia visual fija)
                │                                   │
                ▼                                   ▼
   Gemini TTS (gratis) o ElevenLabs        Google Flow (extensión), tarjetas gratis,
   una sola llamada por vídeo              fotos de archivo (Wikimedia) o API con tope
   + tiempo de cada escena y palabra
                │                                   │
                └──────────────► FFmpeg (tu PC) ◄───┘
                     carátula de entrada, cada clip a su trozo de voz,
                     sonido ambiente bajo la voz, subtítulos ASS, −14 LUFS
                                   │
                                   ▼
                     Vídeo completo + Reels + Shorts + Portadas
```

## Qué es gratis y qué no

| Paso | Servicio | Coste |
|---|---|---|
| Investigación, escenas, entregas | Gemini API (AI Studio), nivel gratis + Wikipedia + YouTube Data API v3 | 0 $ |
| Guion | DeepSeek (`deepseek-flash`) o Gemini gratis (`STUDIO4_SIN_PAGO=1`) | Céntimos o 0 $ |
| Voz | Gemini TTS, nivel gratis (ElevenLabs opcional) | 0 $ |
| Visuales gratis | Google Flow en el navegador (con la extensión), tarjetas de diseño (Edge headless) y fotos de dominio público (Wikimedia Commons) | 0 $ / tu suscripción |
| Visuales por API (opcional) | fal.ai o Google Imagen/Veo con tope de gasto por producción (`Presupuesto`) | Prepago con tope |
| Render y transcripción | FFmpeg, yt-dlp y faster-whisper en tu PC | 0 $ |

## Instalar

1. Python 3.10+ y **FFmpeg** en el PATH.
2. `pip install -r requirements.txt`
3. Copia `.env.example` como `.env` y pon tu `GEMINI_API_KEY` (gratis en https://aistudio.google.com/apikey).
4. Carga la extensión: `chrome://extensions` › Modo de desarrollador › **Cargar sin empaquetar** › carpeta `extension-flow`.

## Usar

1. Doble clic en **`iniciar.bat`** (o `python servidor.py`). Se abre http://127.0.0.1:8000.
2. Pulsa **«Flow: conectar»** arriba a la derecha: la extensión queda vinculada en un clic.
3. Escribe el tema, elige formato, duración, estilo y voz, y pulsa **Continuar**. Gemini escribe el guion
   y las escenas, y la voz se genera sola.
4. Abre Google Flow. El panel flotante de STUDIO te enseña la escena que toca: **Copiar prompt**, lo pegas
   en Flow y generas. El vídeo llega solo a esa escena. Si Flow saca varias variantes, todas quedan
   como tomas y en el panel eliges la mejor.
   Desde la escena 2, «Copiar imagen inicial» te da el último fotograma de la anterior para usarlo en
   «Fotogramas a vídeo»: así la secuencia no salta.
5. Cuando todas las escenas tienen clip, **Renderizar vídeo**. Copia el título, la descripción y los hashtags
   desde «Para publicar».

## Primero, el guion

- **Desde una idea:** Gemini investiga (búsqueda de Google si tu proyecto la tiene; si no, Wikipedia en español
  e inglés, gratis) y arma un dossier con fuentes. **DeepSeek** escribe con esos datos el guion **corto**
  (Shorts y Reels comparten vídeo vertical) y/o el **largo** (YouTube), con reglas contra el estilo IA y
  3 ganchos alternativos. Sin `DEEPSEEK_API_KEY` escribe Gemini con las mismas reglas.
- **Tengo mi guion:** se respeta tal cual.
- Lo revisas y editas; al pulsar **Aprobar guion**, Gemini lo convierte en escenas para Flow y avisa de las
  frases difíciles de filmar. Un largo de 5 min son ~35-40 escenas de Flow.

## Flow y STUDIO a la vez

Google no deja meter Flow dentro de otra página, así que va al revés: **STUDIO entra en el panel
lateral de Chrome, junto a Flow**. En la pestaña de Flow pulsa el icono **S4** de la extensión y se
abre la vista compacta: la escena que toca con «Copiar prompt», la imagen inicial para la continuidad,
y la lista de escenas con sus tomas. También puedes usar «Abrir Flow al lado» en el panel principal
(abre Flow en una ventana a la derecha).

## Miniaturas y entregas

Con los clips elegidos, **Generar miniaturas**: Gemini (gratis) mira los fotogramas, elige el que más
engancha, dónde está el sujeto, y escribe 2-4 palabras (con 3 alternativas). Se componen en tu PC:

| Formato del vídeo | Entregas |
|---|---|
| Vertical 9:16 | Portada **Shorts** y portada **Reels** 1080×1920 (texto dentro del recorte 3:4 del perfil) |
| Horizontal 16:9 | Miniatura **YouTube** 1280×720 (< 2 MB) |
| Cuadrado 1:1 | Portada feed 1080×1080 |

Puedes cambiar el texto, la palabra en amarillo y la imagen de fondo, subir la tuya o pulsar
«Generar la imagen en Flow»: copia un prompt de miniatura y la próxima imagen que generes en Flow
llega como fondo.

## Estructura

```
servidor.py            panel local (solo 127.0.0.1; solo sirve web/ y los medios de cada producción)
iniciar.bat            arranca el panel y abre el navegador
studio4/
  config.py            claves, modelos, formatos, estilos y el código de vinculación con Flow
  canales.py           canales (nicho, tono, público, voz, referentes y fuentes de confianza)
  tendencias.py        tendencias de YouTube y análisis de canales referentes
  aprender.py          estudia transcripciones del nicho y escribe el manual del canal
  fuentes.py           lee las webs de confianza del canal (respeta robots.txt)
  investigacion.py     dossier con hechos verificados (Wikipedia ES/EN o Google)
  referencias.py       fotos, documentos, enlaces y lugares de Google Maps aportados por el autor
  youtube.py           YouTube Data API v3 (solo lectura)
  deepseek.py          cliente de DeepSeek en streaming
  gemini.py            cliente de Gemini con modelos de reserva y reintentos
  guion.py             guion corto y largo (DeepSeek; Gemini de reserva)
  director.py          escenas + biblia visual + fichas de personajes + prompt de Flow
  voz.py               Gemini TTS / ElevenLabs y tiempos de cada escena y palabra
  flow.py              recibe los clips de la extensión y los coloca en su escena
  archivo.py           fotos históricas de dominio público (Wikimedia Commons)
  tarjetas.py          tarjetas de diseño y carátula de entrada con Edge headless
  visuales_api.py      imágenes y vídeo por API (fal.ai / Google) con presupuesto máximo
  importar.py          importa un vídeo propio (yt-dlp + faster-whisper + cortes de plano)
  render.py            montaje con FFmpeg y vista previa de subtítulos
  subtitulos.py        subtítulos ASS palabra a palabra (viral o cine) y sonidos
  sonidos.py           detecta ruidos y música en las tomas para los subtítulos
  entregas.py          paquete de 3 formatos (completo, Reels y Shorts)
  miniaturas.py        miniaturas de YouTube, Shorts, Reels y feed (Gemini elige, Pillow compone)
  carpetas.py          estructura en Vídeos\STUDIO 4\<canal>\
  produccion.py        guarda cada producción en producciones/<id>/proyecto.json y lanza las fases
  medios.py            utilidades de FFmpeg/FFprobe con tiempos límite
  registro.py          consumo del mes (llamadas, tokens y gasto en $)
web/                   el panel web (Inicio, Crear, Canales, Tendencias, Flow, Render, Entregas)
extension-flow/        extensión de Chrome/Edge para Google Flow
producciones/          tus vídeos (no se suben a git)
```

## Seguridad

- El servidor solo escucha en tu equipo y solo entrega `web/` y los medios de cada producción. Nunca entrega `.env` ni el código.
- Rechaza peticiones con un `Host` ajeno (protege contra el «DNS rebinding») y acciones que vengan de otras webs.
- La extensión entra con el código de vinculación. **Nueva vinculación** genera otro y anula el anterior.
