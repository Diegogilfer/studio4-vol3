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

## Estructura

```
servidor.py            panel local (solo 127.0.0.1; solo sirve web/ y los medios de cada producción)
iniciar.bat            arranca el panel y abre el navegador
studio4/
  config.py            claves, modelos, formatos, estilos y el código de vinculación con Flow
  gemini.py            cliente de Gemini con modelos de reserva y reintentos
  guion.py             fase 1: guion
  director.py          fase 2: escenas + biblia visual + prompt de Flow por escena
  voz.py               fase 3: Gemini TTS / ElevenLabs y tiempos de cada escena y palabra
  flow.py              fase 4: recibe los clips de la extensión y los coloca en su escena
  render.py            fase 5: FFmpeg
  subtitulos.py        subtítulos ASS palabra a palabra
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
