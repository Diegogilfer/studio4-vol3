# STUDIO #4 Vol. 3

Vídeos cortos hechos solo con Google: lo **gratis** de Gemini y tu **suscripción** de Google Flow.
El montaje final se hace en tu PC con FFmpeg, también gratis.

```
 Tema ─► Gemini (gratis) ─► guion
                │
                ▼
         Gemini (gratis) ─► escenas: texto de voz + prompt para Flow (biblia visual fija)
                │                                   │
                ▼                                   ▼
   Gemini TTS (gratis) o ElevenLabs        Google Flow / Veo (tu suscripción)
   una sola llamada por vídeo              tú pegas el prompt y generas;
   + tiempo de cada escena y palabra       la extensión trae el clip a su escena
                │                                   │
                └──────────────► FFmpeg (tu PC) ◄───┘
                     cada clip se ajusta a su trozo de voz,
                     sonido ambiente de Veo bajo la voz,
                     subtítulos palabra a palabra, −14 LUFS
                                   │
                                   ▼
                     producciones/<id>/final.mp4
```

## Qué es gratis y qué no

| Paso | Servicio | Coste |
|---|---|---|
| Guion y escenas | Gemini API (AI Studio), nivel gratis | 0 $ (2 llamadas por vídeo) |
| Voz | Gemini TTS, nivel gratis | 0 $ (1 llamada por vídeo; en preview hay ~50 al día) |
| Voz (opcional) | ElevenLabs, plan gratis | 0 $, pero 10.000 créditos/mes, **sin uso comercial** y hay que citarlo |
| Vídeo | Google Flow (Veo) en el navegador | tus créditos del plan; Flow **no tiene API**, por eso va con la extensión |
| Render | FFmpeg en tu PC | 0 $ |

La generación de imagen y de vídeo **por API** (Imagen/Veo) se cobra aparte, así que STUDIO no la usa.

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
  gemini.py            cliente de Gemini con modelos de reserva y reintentos
  investigacion.py     fase 0: dossier con fuentes (Google o Wikipedia)
  deepseek.py          cliente de DeepSeek
  guion.py             fase 1: guion corto y largo (DeepSeek; Gemini de reserva)
  director.py          fase 2: escenas + biblia visual + prompt de Flow por escena
  voz.py               fase 3: Gemini TTS / ElevenLabs y tiempos de cada escena y palabra
  flow.py              fase 4: recibe los clips de la extensión y los coloca en su escena
  render.py            fase 5: FFmpeg
  subtitulos.py        subtítulos ASS palabra a palabra
  miniaturas.py        miniaturas de YouTube, Shorts, Reels y feed (Gemini elige, Pillow compone)
  produccion.py        guarda cada producción en producciones/<id>/proyecto.json y lanza las fases
  medios.py            utilidades de FFmpeg/FFprobe
  registro.py          consumo del mes (llamadas a Gemini, tomas de Flow, créditos de ElevenLabs)
web/                   el panel, con el diseño del STUDIO #4 original
extension-flow/        extensión de Chrome/Edge para Google Flow
producciones/          tus vídeos (no se suben a git)
```

## Seguridad

- El servidor solo escucha en tu equipo y solo entrega `web/` y los medios de cada producción. Nunca entrega `.env` ni el código.
- Rechaza peticiones con un `Host` ajeno (protege contra el «DNS rebinding») y acciones que vengan de otras webs.
- La extensión entra con el código de vinculación. **Nueva vinculación** genera otro y anula el anterior.
