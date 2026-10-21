# Prompt para crear la herramienta «Guion a vídeo» dentro de Google Flow

Cómo usarlo: en Google Flow → **Nuevo proyecto** → **Crear herramienta** → pega TODO el bloque de abajo → Enter.
Flow la construye a su manera (el diseño no saldrá idéntico). Si algo no funciona, pulsa **Editar** y díselo en
español («el botón de regenerar escena no hace nada, corrígelo»). Necesitas tu cuenta de pago de Google: cada
imagen y cada escena gasta créditos de Flow; la herramienta te enseña lo que va a gastar antes de cada paso.

---

```text
Crea una herramienta llamada «Studio 4 · Guion a vídeo» que convierta un guion en un vídeo largo completo, por
pasos, con consistencia de personajes, ambientes y voz. Toda la interfaz en español. Diseño oscuro, limpio, con
bloques grandes y acentos verde neón (#39ff88). Sin barras de desplazamiento internas innecesarias.

ENTRADAS (pantalla inicial)
- Caja grande para pegar el guion (puede ser largo, varios párrafos).
- Estilo visual: cinematográfico realista · documental · animación 3D · anime · ilustración. Por defecto:
  cinematográfico realista.
- Formato: 16:9 horizontal (por defecto) o 9:16 vertical.
- Calidad: 720p (por defecto) o 360p económico.
- Audio: «Solo narración» (por defecto) · «Narración + diálogos con sincronía labial» · «Solo diálogos».
- Voz del narrador: masculina o femenina, español latinoamericano neutro (nunca acento de España), tono de
  documental intrigante. Ritmo natural con pausas breves entre frases.
- Modo de trabajo: «Revisión paso a paso» (por defecto) o «Automático» (hace todos los pasos seguidos).
- Botones: «Analizar guion» y «Nuevo guion» (limpia todo y empieza de cero, pidiendo confirmación).

PASO 1 · ANÁLISIS DEL GUION
- Divide el guion en capítulos (cada párrafo o cambio de tema) y en escenas de 4 a 8 segundos. Nunca partas una
  frase a la mitad; una frase larga puede ocupar dos escenas seguidas.
- Muestra un resumen: duración total estimada, número de capítulos, número de escenas y créditos estimados
  de cada paso.
- Muestra una tabla editable: nº, capítulo, texto que se narra en esa escena, personajes que aparecen,
  ambiente, acción, tipo de plano (general, medio, primer plano, detalle) y movimiento de cámara.
- Botón «Avanzar a personajes».

PASO 2 · PERSONAJES
- Saca la lista de personajes del guion. Para cada uno crea una ficha fija: nombre, edad, rasgos físicos
  (cara, pelo, piel, complexión), ropa exacta y colores. Esta ficha se repite palabra por palabra en todos los
  prompts donde aparezca el personaje.
- Genera una imagen de referencia por personaje: cuerpo entero, de frente, fondo neutro, luz suave.
- Cada ficha se puede editar; botón «Regenerar» por personaje. Botón «Aprobar personajes».

PASO 3 · AMBIENTES
- Igual que los personajes, para cada lugar del guion: ficha fija (época, luz, colores, elementos clave) e
  imagen de referencia sin personajes. Editar, regenerar y «Aprobar ambientes».

PASO 4 · STORYBOARD
- Para cada escena genera un fotograma fijo usando SIEMPRE las imágenes de referencia de sus personajes y de su
  ambiente, con el plano y la acción de la tabla.
- Vista en cuadrícula con el texto narrado debajo de cada fotograma. Por escena: editar el prompt y
  «Regenerar». Botón «Generar todos» y botón final «Aprobar storyboard y generar vídeo».

PASO 5 · ESCENAS DE VÍDEO
- Genera cada escena como vídeo a partir de su fotograma del storyboard (imagen a vídeo), con sus referencias
  de personajes y ambiente, en el formato y la calidad elegidos. La duración de cada escena se ajusta a lo que
  dura su narración.
- Narración: la voz elegida lee el texto de la escena, sincronizada con ella. Si la escena tiene diálogo y el
  modo lo permite, el personaje habla con sincronía labial y su voz es siempre la misma.
- Estado por escena (pendiente, generando, lista, error). Si una falla, se marca y se sigue con las demás.
  Por escena: reproducir, editar prompt y «Rehacer esta escena» sin tocar las demás.

PASO 6 · MONTAJE FINAL
- Botón «Montar vídeo final»: une las escenas en orden con transiciones suaves y cortas, volumen de voz parejo
  y, opcional, música de fondo suave que baje cuando habla la voz.
- Reproductor para verlo y botón «Descargar vídeo» (MP4). Botones extra: «Descargar escenas sueltas» y
  «Descargar guion por escenas» (texto con nº, segundos de inicio y fin y texto narrado de cada escena).
- Botón «Exportar para Studio 4»: descarga un único ZIP con
  · escenas/escena_001.mp4, escena_002.mp4… (cada escena suelta, en orden, SIN subtítulos, SIN música y SIN
    textos grabados en la imagen);
  · narracion.wav (toda la narración seguida, limpia, sin música ni efectos) y, si hay diálogos, la voz de
    cada escena aparte en voces/escena_001.wav…;
  · escenas.json con una lista en orden: {"n", "capitulo", "texto", "inicio", "fin", "personajes", "ambiente",
    "archivo"} (inicio y fin en segundos dentro del vídeo final);
  · personajes/ y ambientes/ con sus imágenes de referencia y sus fichas en texto.
  Este paquete es para terminar el vídeo en otro programa (subtítulos, logo, música, Short y miniatura), así
  que no le añadas nada encima.

REGLAS
- Consistencia por encima de todo: las fichas y las imágenes de referencia de personajes y ambientes se usan en
  cada imagen y cada escena; mismo estilo visual en todo el proyecto.
- Antes de cada paso que gaste créditos, muestra cuántos va a usar y pide confirmación (salvo en modo
  Automático, donde se confirma una sola vez al principio con el total estimado).
- Guarda el proyecto para poder cerrar y seguir después en el mismo paso.
- Sin texto ni letreros dentro de las imágenes salvo que el guion lo pida; sin marcas de agua.
```
