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
   al autor antes de aprobar. **Voz:** ahora está disponible y verificada **Voz Xiaomi MiMo gratis (`mimo` · `mimo-v2.5-tts`, $0)**
   con `XIAOMIMIMO_API_KEY` en `.env` (además de Gemini TTS gratis y como reserva automática suya), por lo que **no hace falta
   gastar en ElevenLabs ni en fal** para locutar FL-001. Después «Imágenes reales para todas · gratis» (salen primero de las
   FUENTES del paquete) → montar → revisar con el autor.
2. **Biblioteca de material en el panel (HECHO en commit `2ea420a`):** bloque `#material-bib` en Inicio con filtro «Lo más usado»
   primero, 12 piezas con «Ver más», reproducción bajo demanda (`preload="none"`) y apertura de carpeta segura.
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
| **Voz gratis Xiaomi MiMo (`mimo-v2.5-tts`) y reserva sin costo** | `studio4/voz.py` (`_mimo_tts`, `VOCES_MIMO`, `reserva`), `studio4/config.py` (`XIAOMIMIMO_*`, `SIN_PAGO`) |
| **Catálogo ElevenLabs (`/v1/voices`), `preview_url` y separar selección de generación** | `studio4/voz.py` (`catalogo_elevenlabs`, `estimar_voz`), `studio4/produccion.py` (`seleccionar_voz`), `servidor.py` (`/api/voces/elevenlabs`, `/api/voz/seleccionar`), `web/panel.js` |
| **Biblioteca de material del canal en Inicio (`#material-bib`)** | `studio4/carpetas.py` (`listar_material_canal`), `servidor.py` (`/api/material`, `/material/`, `/api/carpeta/abrir`), `web/panel.js` |
| Reserva de texto (Gemini → DeepSeek / Xiaomi MiMo) y cortocircuito ante 402 | `studio4/gemini.py`, `studio4/deepseek.py` (`_proveedores`) |
| Aprender del nicho, vídeo modelo (sin nombre ni frases ajenas) | `studio4/aprender.py` |
| Ideas en tendencia y 3 ideas diarias | `studio4/ideas.py` |
| Imágenes reales de las fuentes | `studio4/galeria.py` |
| Fotos de archivo (dominio público) | `studio4/archivo.py` |
| Desde URL: importar → montar → 3 formatos, edición, cola de 3 | `studio4/importar.py`, `produccion.py`, `render.py` |
| Registro y caídas | `producciones/servidor.log`, `producciones/caidas.log` |
| Arranque con pantalla de carga | `iniciar.bat`, `web/arranque.html` |
| Términos y licencias | `web/legal.html` (ruta `/legal`) |
| **Skill de Ingeniería Inversa (alta complejidad · Antigravity y Claude)** | `.agents/skills/ingenieria-inversa/SKILL.md`, `.claude/skills/ingenieria-inversa/SKILL.md` |

## Nota para Claude: por qué se hicieron estos cambios (Voz Xiaomi MiMo + ElevenLabs)

1. **Por qué se incorporó Xiaomi MiMo (`mimo` · `mimo-v2.5-tts`):**
   - El autor añadió `XIAOMIMIMO_API_KEY` en `.env` y pidió verificar si conectaba gratis para no depender de ElevenLabs (pago) cuando produce vídeos.
   - Se verificó contra `https://api.xiaomimimo.com/v1`:
     - `mimo-v2.5-tts` responde **`200 OK` gratis**, devolviendo audio WAV base64 a 24 kHz mono (16-bit PCM) mediante `/v1/chat/completions` con el texto a locutar en el mensaje de rol `assistant` y la dirección/estilo en el rol `user`.
     - Los modelos de texto (`mimo-v2.6-flash` / `mimo-v2.5`) quedaron configurados en `studio4/deepseek.py` como respaldo detrás de DeepSeek, aunque actualmente la cuenta de Xiaomi devuelve `402 Insufficient account balance` para texto (el cortocircuito de `_sin_saldo` en `deepseek.py` lo detecta al instante y no reintenta en balde).
   - Con `mimo` en `voz.PROVEEDORES` y en `config.SIN_PAGO`, `VOZ_MIMO_POR_DEFECTO = "es_mx_002"` usa **narrador en español latino nativo gratis (`_espanol_gratis_tts`: `es_mx_002` con respaldo automático a Google `es-US`)**, locutando escena por escena a 24 kHz mono con tiempos de corte exactos (`cortes_exactos`) porque el fonemizador de `mimo-v2.5-tts` pronuncia números y palabras españolas con fonemas en inglés/chino. Si se elige explícitamente `Milo`, `Dean`, `Mia`, `Chloe` o `mimo_default`, llama a `api.xiaomimimo.com`.

2. **Por qué se separó la selección de voz de la generación en ElevenLabs:**
   - Antes, cambiar de voz o pulsar el botón de voz en el panel ejecutaba directamente `POST /api/voz` (`produccion.rehacer_voz`), consumiendo créditos de ElevenLabs sin dejar explorar el catálogo ni escuchar muestras gratuitas primero, y usaba siempre el `ELEVENLABS_VOICE_ID` fijo de `.env`.
   - Ahora:
     - `GET /api/voces/elevenlabs` consulta `https://api.elevenlabs.io/v1/voices` desde el backend (nunca expone `ELEVENLABS_API_KEY` al navegador), guarda caché de 1 hora en `producciones/_voces/catalogo_elevenlabs.json` y entrega `voice_id`, nombre, idioma, acento, etiquetas y `preview_url`.
     - El panel permite escuchar/detener `preview_url` con `<audio id="oir-voz">` sin descargar ni guardar muestras remotas como archivos del proyecto y **sin disparar nunca TTS de pago** (si una voz no tiene `preview_url`, avisa al usuario sin generar audio).
     - `POST /api/voz/seleccionar` (`produccion.seleccionar_voz`) guarda `proveedor_voz`, `voice_id` y `voz_elevenlabs_nombre` en `proyecto.json` y devuelve `estimacion` (caracteres, modelo, créditos y USD estimado) **sin ejecutar locución**.
     - `POST /api/voz` (`produccion.rehacer_voz` y `_generar_voz`) pide confirmación en el navegador cuando el proveedor consume créditos y envía exactamente el `voice_id` elegido al endpoint de ElevenLabs.

## Errores que ya costaron caro (no repetir)

- Una variable con el mismo nombre que un parámetro (`paginas`) rompió la investigación en las fuentes sin que
  ninguna prueba lo viera: añade una prueba de punta a punta cuando toques una función.
- Reiniciar el servidor con un trabajo en marcha lo mataba (ahora las importaciones se retoman solas).
- Parches con acentos pasados por la consola (heredoc) fallan: escribe el script de cambio en un archivo.

## Bitácora (cada agente apunta aquí lo que hizo)

- 2026-10-17 · Claude (rama `reestructura-google`): metodología común de guion, biblioteca por temas con plan del mes y
  aviso de repetidos, imágenes reales en las ideas del día, precarga completa, clave gratis de Google desde el panel
  (commits 9f3b206…fed942c). Creada la carpeta `../studio4-antigravity` (rama `antigravity`) para Antigravity.
- 2026-10-17 · Antigravity (rama `antigravity` → unida en `reestructura-google`): biblioteca de material del canal en Inicio
  (`#material-bib`) con filtro «Lo más usado» primero, 12 piezas con «Ver más», carga tras `precargar()` (`data-sin-precarga`),
  rutas seguras en `/material/` (`is_relative_to(RAIZ_USUARIO)` y solo extensiones de audio/imagen/vídeo) y apertura de carpeta
  calculada en el servidor en `/api/carpeta/abrir`; además se asegura `config.PRODUCCIONES` en `visuales_api.generar_escenas`
  (commits `85c4a20` y `2ea420a`, 117 pruebas en verde).
- 2026-10-17 · Antigravity (rama `antigravity` → unida en `reestructura-google`, commits `6518e53`, `08352d6`, `289d40e`, `2b0915a`):
  catálogo oficial y selector de voces de ElevenLabs (`GET /api/voces/elevenlabs` con caché en disco de 1 h, muestras gratuitas
  `preview_url`, selección persistida como `voice_id` en `POST /api/voz/seleccionar` separada de la generación `POST /api/voz`,
  estimación de caracteres/créditos/USD y confirmación antes de consumir créditos) + voz en español nativo gratis por escena
  (`_espanol_gratis_tts` con `es_mx_002` y respaldo `es-US` Google TTS + Xiaomi MiMo `mimo-v2.5-tts`, botón directo en cartel `402`
  y reserva automática prioritaria) + creación de la skill `ingenieria-inversa` (`.agents/skills/ingenieria-inversa/` y
  `.claude/skills/ingenieria-inversa/`, con sonda `sondar_api.py`; 119 pruebas en verde).

