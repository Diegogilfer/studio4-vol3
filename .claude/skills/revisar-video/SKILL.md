---
name: revisar-video
description: >-
  Control de calidad de un vídeo de STUDIO 4 antes de entregarlo o enseñarlo al autor: imagen quieta
  (congelados), cortes, huecos de sonido, sonido que muere antes del final, subtítulos que salen sin voz y
  volumen de YouTube (LUFS). Activar SIEMPRE que termine un montaje (previa, final o Short) y antes de decir
  «está listo», y cuando el autor diga que algo «se corta», «se para», «salta» o «suena raro» en un segundo.
---

# Revisar un vídeo antes de entregarlo (STUDIO 4)

Regla del autor: **completo no es bueno**. Un vídeo que terminó de montarse no está listo hasta pasar esta
revisión. Nunca digas «listo» sin el resultado del script.

## 1 · Medir
```
python .claude/skills/revisar-video/revisar.py RUTA/final_16x9.mp4 --proyecto RUTA/proyecto.json
```
- Sale `OK` (código 0) o `NO SE ENTREGA` con cada fallo y su segundo exacto (código 1).
- `--proyecto` añade la comparación de subtítulos contra la voz (necesita `render/voz_pausas.wav`).
- Una previa (960x540) no falla por resolución; un final sí si no es 1920x1080.

| Medida | Umbral | Qué nota el autor |
|---|---|---|
| Imagen quieta | ≥0,8 s fallo · 0,4-0,8 s aviso | «se para el vídeo» |
| Hueco de sonido | 12 dB por debajo del fondo | «corta el sonido» / «corta el guion» |
| Sonido al final | cae a silencio antes del fundido | «el final se corta» |
| Subtítulo sin voz | palabra en pantalla sin voz debajo | «error en el segundo X» |
| Volumen | -12,5 a -9,5 LUFS | «suena bajo» o «distorsiona» |

## 2 · Si hay fallos, la causa (lo que ya pasó y cómo se arregló)
- **Quieto en un plano de juego**: el juego está quieto (menú, minijuego, título). El montaje ya acerca la cámara
  (`montaje.ACERCA`); si aun así falla, cambia el plano (habilidad `elegir-planos`).
- **Quieto al final de un plano**: el plano no da para la frase (se congela su último cuadro). Añade un plano
  elegido a `clip.mas` o elige uno más largo. Mira también que la descarga no saliera corta.
- **Hueco al callarse la voz**: compresores que «respiran». La mezcla no lleva compresor ni sidechain con la
  cama (`sonido.masterizar`, loudnorm lineal).
- **Subtítulo antes de tiempo tras una pausa**: palabra asignada al lado equivocado del corte (`_respirar` usa el
  centro de cada palabra).
- **Saltos en la entrada o salida de un panel**: la tarjeta debe seguir el mismo plano (`_segmentos`: arranque ·
  plano · cola de una sola pasada) y el encogido empezar despacio.

## 3 · Después, a ojo
El script no ve el contenido: saca fotogramas de los cortes que lista y míralos (¿cada corte cae en una pausa?,
¿hay letreros o marcas de agua?, ¿la imagen cuenta lo que dice la frase?). Solo entonces entrega, con:
la ruta del archivo, la duración, el resultado de esta revisión y lo que aún podría mejorar.

## 4 · Apunta lo aprendido
Si encontraste un fallo nuevo, añádelo a la habilidad `lecciones-canal` (archivo del canal).
