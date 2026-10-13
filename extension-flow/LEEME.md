# STUDIO #4 · Google Flow

Hace dos cosas dentro de Google Flow (labs.google), **sin pulsar nada por ti** y sin leer tu cuenta:

1. **Panel flotante** con la escena que toca: lo que dice la voz, el prompt listo y «Copiar prompt».
   Con ‹ › cambias de escena. Desde la escena 2, «Copiar imagen inicial» copia el último fotograma
   de la escena anterior para usarlo en «Fotogramas a vídeo».
2. **Recoger**: cada vídeo o imagen nuevos que generas los manda a STUDIO #4, a la escena que copiaste.

## Instalar (una vez)

1. Abre `chrome://extensions` (en Edge, `edge://extensions`).
2. Activa **Modo de desarrollador**.
3. **Cargar extensión sin empaquetar** › elige esta carpeta (`studio4-vol3/extension-flow`).
4. En STUDIO #4 (http://127.0.0.1:8000) pulsa **«Flow: conectar»**: se vincula sola.

Si cambias de código («Nueva vinculación» en el panel), vuelve a pulsar «Flow: conectar».

## Detalles

- Lo que ya estaba en la pantalla de Flow al abrirla no se manda; «Enviar las de pantalla» lo manda también.
- Ignora iconos y miniaturas (menos de 384 px de lado).
- El mismo clip dos veces no se duplica en STUDIO #4.
- Flow tiene sus propias condiciones de uso, también para uso comercial: revísalas antes de vender vídeos.
