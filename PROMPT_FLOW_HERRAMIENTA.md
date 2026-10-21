# Herramienta «Guion a vídeo» en Google Flow · proceso de principio a fin con Studio 4

Versión 2 (2026-10-21), auditada contra lo que Flow y Veo hacen de verdad hoy:
- Las herramientas de Flow se crean describiéndolas («Crear herramienta»): Flow escribe el código y la
  interfaz; se arreglan con «Editar». Crear herramientas pide Google AI Plus, Pro o Ultra. Lo que generan se
  guarda en el proyecto abierto y gasta créditos (Flow avisa con un banner). Quien tenga el enlace ve el código.
- Veo 3.1 genera clips de **4, 6 u 8 segundos** como máximo, con sonido, diálogo con labios sincronizados,
  imagen a vídeo (primer fotograma) e «ingredientes» (imágenes de referencia). Imágenes con Nano Banana Pro.
- Créditos por clip de 8 s: **Lite 10 · Fast 20 · Quality 100**. 50 créditos gratis al día; AI Pro 1.000 al mes.
  Un vídeo de 5 min son unos 40-60 clips: en Lite, 400-600 créditos solo de vídeo, más las imágenes.
- Flow rechaza personajes con derechos (GTA, Rockstar…) y personas reales: este modo es para canales con
  personajes propios (historias, cuentos, misterio…). FourLevel sigue con gameplay real.

## El proceso (quién hace cada cosa)

| Paso | Dónde | Qué sale |
|---|---|---|
| 1. Guion | Studio 4 (Biblioteca o pegado) | guion revisado |
| 2. Voz y tiempos | Studio 4 (Sadaltager, gratis) | la narración y el segundo exacto de cada frase |
| 3. Escaleta para Flow | Studio 4 → botón «Escaleta para Flow» | un texto para pegar (escenas de 4/6/8 s con su narración, personajes y ambiente) |
| 4. Personajes, ambientes, storyboard, escenas | Flow → esta herramienta | escenas de vídeo sin voz en off ni texto |
| 5. Exportar | Flow → «Exportar para Studio 4» | escenas numeradas + escenas.json |
| 6. Importar y acabado | Studio 4 → «Importar de Flow» | vídeo con voz, subtítulos, logo, música, paneles, Short, textos, miniatura y revisión de calidad |
| 7. Publicar | Diego, en YouTube | — |

Por qué la narración la pone Studio 4 y no Veo: la voz de Veo cambia de un clip a otro (cada clip se genera
aparte); Sadaltager es siempre la misma, gratis, y Studio ya sabe sincronizar subtítulos palabra a palabra con
ella. Veo solo pone voz cuando un personaje habla en pantalla (diálogo con labios).

## Cómo crear la herramienta
Google Flow → **Nuevo proyecto** → **Herramientas** → **Crear herramienta** → pega TODO el bloque de abajo →
Enter. El diseño no saldrá idéntico. Si algo falla, **Editar** y díselo en español («el botón X no hace nada,
corrígelo»). Prueba primero con una escaleta corta (5-6 escenas) en Veo 3.1 Lite.

---

```text
Crea una herramienta llamada «Studio 4 · Guion a vídeo» que convierta una escaleta de escenas en las escenas de
vídeo de un vídeo largo, por pasos, con personajes y ambientes siempre iguales. Toda la interfaz en español.
Diseño oscuro y limpio, bloques grandes, acentos verde neón (#39ff88). Todo lo que genere se guarda en el
proyecto abierto para poder cerrar y seguir después en el mismo paso.

ENTRADA
- Una caja grande donde se pega la escaleta. Acepta dos formatos:
  A) La ESCALETA DE STUDIO 4: un bloque JSON que empieza por {"escaleta_studio4": 1, ...} con:
     "titulo", "estilo", "formato" ("16:9" o "9:16"), "personajes": [{"nombre", "descripcion"}],
     "ambientes": [{"nombre", "descripcion"}] y "escenas": [{"n", "capitulo", "duracion" (4, 6 u 8),
     "narracion" (lo que dirá la voz en off: NO se pronuncia en el vídeo, solo sirve para saber qué mostrar),
     "personajes" (nombres), "ambiente", "accion", "plano", "camara", "dialogo" (opcional: texto que un
     personaje dice en pantalla y quién lo dice)}].
     Con este formato NO cambies el número, el orden ni la duración de las escenas.
  B) Un guion normal en texto: entonces divídelo tú en capítulos y escenas de 4, 6 u 8 segundos (nunca partas
     una frase a la mitad) y crea la misma estructura.
- Ajustes: estilo visual (cinematográfico realista por defecto; documental, animación 3D, anime,
  ilustración); formato 16:9 o 9:16; modelo de vídeo Veo 3.1 Lite (por defecto, borradores), Fast o Quality;
  modo «Revisión paso a paso» (por defecto) o «Automático».
- Botones «Cargar escaleta» y «Nuevo proyecto» (borra todo, pidiendo confirmación).

CRÉDITOS (obligatorio)
- Antes de cada paso que genere imágenes o vídeo, muestra cuántas imágenes o clips va a crear, el modelo y los
  créditos estimados, y pide confirmación. En modo Automático, una sola confirmación al principio con el total.
- Muestra siempre el total gastado en el proyecto.

PASO 1 · ESCALETA
- Tabla editable con todas las escenas (nº, capítulo, duración, narración, personajes, ambiente, acción,
  plano, cámara, diálogo). Resumen arriba: duración total, capítulos, escenas, clips y créditos estimados.
- Botón «Avanzar a personajes».

PASO 2 · PERSONAJES
- Una ficha fija por personaje: nombre, edad, cara, pelo, piel, complexión, ropa exacta y colores. Esa ficha
  se copia palabra por palabra en cada prompt donde aparezca.
- Una imagen de referencia por personaje: cuerpo entero, de frente, fondo neutro, luz suave.
- Editar ficha y «Regenerar» por personaje. «Aprobar personajes».

PASO 3 · AMBIENTES
- Igual: ficha fija (época, hora, luz, colores, elementos clave) e imagen de referencia sin personajes.
  Editar, regenerar y «Aprobar ambientes».

PASO 4 · STORYBOARD
- Un fotograma por escena (será el primer fotograma del vídeo), generado con las imágenes de referencia de sus
  personajes y su ambiente como ingredientes, con su plano y su acción.
- Cuadrícula con la narración debajo de cada fotograma. Por escena: editar prompt y «Regenerar».
  «Generar todos» y «Aprobar storyboard».

PASO 5 · ESCENAS DE VÍDEO
- Cada escena: imagen a vídeo desde su fotograma del storyboard, con las referencias de sus personajes y su
  ambiente como ingredientes, la cámara de la escaleta y EXACTAMENTE su duración (4, 6 u 8 s).
- Sonido de cada clip: solo ambiente y efectos (pasos, viento, multitud…). SIN voz en off, SIN música, SIN
  subtítulos ni texto en pantalla. Solo si la escena tiene «dialogo», ese personaje lo dice con labios
  sincronizados y siempre con la misma voz.
- Estado por escena (pendiente, generando, lista, error). Si una falla (por ejemplo, la rechaza el filtro de
  seguridad), se marca con el motivo y se sigue con las demás. Por escena: reproducir, editar prompt y
  «Rehacer esta escena» sin tocar las demás.

PASO 6 · VER Y EXPORTAR
- «Ver todo seguido»: reproduce las escenas en orden para revisarlas.
- «Exportar para Studio 4»: descarga las escenas numeradas escena_001.mp4, escena_002.mp4… (si se puede, todo
  en un ZIP; si no, una a una con esos nombres) y escenas.json con la escaleta final:
  {"escaleta_studio4": 1, "titulo", "formato", "escenas": [{"n", "capitulo", "archivo", "duracion",
  "narracion", "personajes", "ambiente", "dialogo"}]}. Muestra también escenas.json en una caja con botón
  «Copiar», por si la descarga del archivo no funciona.
- «Descargar referencias»: las imágenes y fichas de personajes y ambientes (para reutilizarlas en el próximo
  vídeo del mismo canal).

REGLAS
- Consistencia por encima de todo: mismas fichas, mismas imágenes de referencia y mismo estilo en todo.
- Nunca texto, letreros, subtítulos ni marcas de agua dentro de las imágenes o los vídeos.
- Nunca personas reales ni personajes o marcas con derechos de autor.
```

## Comprobación al recibir la herramienta (antes de un vídeo de verdad)
1. Pega una escaleta de 5 escenas: el resumen debe decir 5 escenas y la suma de sus duraciones.
2. Cada paso pide confirmación de créditos antes de generar.
3. Un personaje sale igual en el storyboard y en sus escenas.
4. Los clips no tienen voz en off, ni música, ni texto encima, y duran lo que dice la escaleta.
5. «Exportar para Studio 4» descarga las escenas con su número y escenas.json (o lo deja en la caja para copiar).
6. Studio 4 → «Importar de Flow» con ese paquete monta el vídeo con voz y subtítulos (cuando esté hecho el botón).
