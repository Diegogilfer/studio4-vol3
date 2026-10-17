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

## Estado ahora (17-oct-2026)

- **Clave de Gemini bloqueada (402, prepago a 0 $).** El texto va por la reserva (DeepSeek). Para la voz, el panel ya
  ofrece pegar una **clave nueva gratis** (`gemini.cambiar_clave`, la prueba con una voz antes de guardarla). El
  autor aún no la ha puesto; mientras, voz por fal (de pago, con su visto bueno).
- **Biblioteca de guiones llena:** 12 temas (FL-001…FL-012), 72 guiones escritos por Agron (asistente por chat), en
  `producciones/biblioteca_fourlevel.json`. Ya se creó la producción del **largo de FL-001**
  (`20261017-140843-gta-6-todas-las-armas-autos-nuevos-y-rar`). **Repetido detectado:** FL-001 corto e ≈ FL-006
  corto a (crear solo uno).
- **Producciones antiguas:** el autor pidió empezar limpio; quedan 2 importaciones de prueba (Rai Can, no se publican).
  Borrarlas lo hace el autor desde el panel (a un agente se le bloqueó el borrado).
- **Ideas del día:** 3 cada día con imagen REAL de su tema (gtabase entero → Wikipedia → archivo), nunca la miniatura
  del vídeo ajeno.

## Pendiente, en orden

1. **Producir FL-001** (el largo ya creado y sus 5 cortos), uno a uno desde Crear › Biblioteca, enseñando cada guion
   al autor antes de aprobar. Voz: la gratis de Google si el autor pone la clave nueva; si no, fal (≈1,10 $ el largo,
   ≈0,07 $ cada corto). Después «Imágenes reales para todas · gratis» (salen primero de las FUENTES del paquete) →
   montar → revisar con el autor.
2. **Biblioteca de material en el panel** (lo pidió el autor): ver como ítems la voz, las imágenes y los clips de cada
   producción y lo más usado. El material ya se guarda en `Vídeos\STUDIO 4\<canal>\<vídeo>\4 Voz y material`
   (`carpetas.guardar_material`).
3. **Voz local gratis (KittenTTS, Apache-2.0):** auditado; solo una voz en español y su normalizador es solo para
   inglés. Pendiente de que el autor apruebe una prueba aislada (entorno aparte, un párrafo, medir tiempo y calidad).
4. **Cola visible** de trabajos en la galería (idea sacada de otra app): un marcador «en espera» por pieza.
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
