# Traspaso · Studio 4 (16-10-2026)

> Para el agente que continúe el trabajo (Agron u otro). Léelo entero antes de tocar nada.
> Proyecto: `C:\Users\Lenovo\studio4-vol3`, rama `reestructura-google`. Contexto general en `PROMPT_STUDIO4.md`.
> Último commit al escribir esto: `e58ae62`.

## Reglas del autor (no negociables)

1. Todo en **español**. FourLevel habla en **español latino** («ustedes», nunca «vosotros»).
2. **Nada escondido** en el panel; poco texto; botones con acciones precisas. Dos fuentes: Geist e Instrument
   Serif (en HTML generado usa los nombres `"S4 Serif"` / `"S4 Sans"` entre comillas: `Serif` sin comillas es la
   familia genérica de CSS y sale Times).
3. **Nunca tocar la sesión en vivo** del autor: su servidor es el del **puerto 8000**. Para probar, copia el
   código a una carpeta temporal y arranca otro en el **8011** (`STUDIO4_PUERTO=8011`, `STUDIO4_CARPETA=<temporal>`).
   Antes de cerrar un proceso, comprueba que es el del 8011.
4. **No reiniciar el servidor del autor con trabajos en marcha**; si hace falta, avísale primero.
5. **Nada de pago sin su visto bueno** y con tope. Ya aprobado: voz **ElevenLabs por fal** para el vídeo de 15 min
   (~1,20 $, tope 2 $). Imágenes por fal: solo si lo pide.
6. **Google Flow no se automatiza** (riesgo para su cuenta): la extensión solo muestra prompts y recoge clips.
7. **Commit solo si pasan las pruebas** (`python -m pytest tests/test_studio4.py -q -p no:cacheprovider`, 115 hoy).
   Comprueba el resultado con `grep failed`, no con el código de salida de una tubería.
8. **Comprueba visualmente** cada cambio de panel (captura con Edge sin ventana contra el servidor de prueba).
9. **Vídeos de otros canales** (p. ej. el de Rai Can): solo ideas y forma. **Nunca** mencionarlo, enlazarlo ni copiar
   su contenido o sus frases. No publicar vídeos ajenos.
10. Imágenes reales de GTA: de las **páginas recomendadas** del canal (gtabase.com), con comentario propio y edición;
    sin música ni trozos largos de tráileres oficiales.

## Estado ahora

- **Clave de Gemini bloqueada (402, prepago a 0 $).** El texto funciona por la reserva (DeepSeek); la voz de Google
  no. El autor debe crear una clave en un proyecto **sin facturación**. Mientras, voz por fal.
- **Vídeo importado (Rai Can)** `20261015-225825-importado-video`: terminado (4 piezas) tras retomarse solo.
  Es solo de prueba: **no se publica**.
- **Vídeo de 15 min** `20261016-223818-largo-gta-6-las-armas-nuevas-que-veremos-los-a`: el guion (2.010 palabras)
  salió **solo con Wikipedia** por un fallo ya corregido (`e58ae62`): la lectura de gtabase fallaba siempre.
  **Hay que rehacer la investigación** (el «Escribir otra versión» reutiliza la investigación vieja).

## Pendiente, en orden

1. **Vídeo de 15 min** (tema: armas nuevas, autos nuevos y cosas raras/curiosidades de GTA 6):
   - Rehacer investigación + guion con las fuentes ya arregladas (borra `investigacion` de esa producción y vuelve a
     lanzar, o crea una nueva igual). Comprobar que en `investigacion.fuentes` aparecen páginas de **gtabase.com**.
   - Enseñar el guion al autor antes de seguir.
   - Antes de aprobar: `proveedor_voz = "fal"` (voz por trozos, ya implementada). Escenas por clips de 8 s.
   - «Imágenes reales para todas · gratis» (galeria.py, ~110 escenas, formato largo 16:9) → montar → revisar.
2. ~~Pruebas completas~~: hechas (101 de 101 con la CPU libre).
3. **Biblioteca en el panel** (lo pidió el autor): ver como ítems la voz, las imágenes y los clips de cada producción
   y lo más usado. El material ya se guarda en `Vídeos\STUDIO 4\<canal>\<vídeo>\4 Voz y material` con
   «Fuentes y créditos.txt» (`carpetas.guardar_material`).
4. ~~Biblioteca de guiones~~: hecha (Crear › Biblioteca, `studio4/biblioteca.py`). Los prompts para el asistente por
   chat están en `PROMPTS_AGRON.md`. Lo que se pidió: el autor prepara guiones por chat con otro asistente, en paquetes
   por tema (FL-001…: 1 guion largo de 15 min + 5 cortos de 48 s, cada uno con título, descripción, hashtags y
   fuentes). Studio 4 debería tener una pestaña donde pegar un paquete entero y crear solas las 6 producciones
   (guion propio, formato 16:9 o 9:16 según el tipo, con sus textos), marcando qué código ya se produjo.
5. Preguntar qué quiere decir con **«Instagram agent skill»**.
6. Futuro (no ahora): productos en 3D, estudio de pódcast, DeepSeek como acompañante por chat o voz.

## Dónde está cada cosa (lo de estos días)

| Qué | Dónde |
|---|---|
| Guion por clips de 8 s y velocidad de voz | `studio4/clips.py`, `guion.py`, `director.py` (bloques) |
| Voz por trozos y voz ElevenLabs por fal | `studio4/voz.py` (`locutar`, `trozos`, `_fal_tts`) |
| Reserva de texto (Gemini → DeepSeek) y cortocircuito ante 402 | `studio4/gemini.py` |
| Aprender del nicho, vídeo modelo (sin nombre ni frases ajenas) | `studio4/aprender.py` |
| Ideas en tendencia y 3 ideas diarias | `studio4/ideas.py` |
| Imágenes reales de las fuentes | `studio4/galeria.py` |
| Fotos de archivo (dominio público) | `studio4/archivo.py` |
| Desde URL: importar → montar → 3 formatos, edición, cola de 3 | `studio4/importar.py`, `produccion.py`, `render.py` |
| Registro y caídas | `producciones/servidor.log`, `producciones/caidas.log` |
| Arranque con pantalla de carga | `iniciar.bat`, `web/arranque.html` |
| Términos y licencias | `web/legal.html` (ruta `/legal`) |

## Errores que ya costaron caro (no repetir)

- Una variable con el mismo nombre que un parámetro (`paginas`) rompió la investigación en las fuentes sin que
  ninguna prueba lo viera: añade una prueba de punta a punta cuando toques una función.
- Reiniciar el servidor con un trabajo en marcha lo mataba (ahora las importaciones se retoman solas).
- Parches con acentos pasados por la consola (heredoc) fallan: escribe el script de cambio en un archivo.

## Bitácora (cada agente apunta aquí lo que hizo)

- 2026-10-17 · Claude (rama `reestructura-google`): metodología común de guion, biblioteca por temas con plan del mes y
  aviso de repetidos, imágenes reales en las ideas del día, precarga completa, clave gratis de Google desde el panel
  (commits 9f3b206…fed942c). Creada la carpeta `../studio4-antigravity` (rama `antigravity`) para Antigravity.
