---
name: ingenieria-inversa
description: >-
  Metodología de ingeniería inversa de alta complejidad para diagnosticar fallos
  ocultos, descubrir contratos reales de APIs sin documentación completa (como
  Xiaomi MiMo TTS, ElevenLabs, Google Gemini o fal.ai), inspeccionar el estado
  en vivo del servidor y verificar formatos binarios de audio/vídeo antes de
  integrar cambios en STUDIO 4. Activar ante integraciones complejas, errores
  400/401/402/404/429 inesperados o cuando algo parece conectado en código pero
  no se refleja en pantalla.
---

# Ingeniería Inversa de Alta Complejidad (STUDIO 4)

Usa esta habilidad cuando debas:
1. Integrar o depurar una API externa cuyo contrato real no coincida con lo esperado (rutas, modelos, roles de mensajes, cabeceras o formatos binarios).
2. Diagnosticar por qué una función que pasa pruebas unitarias no se refleja en el panel en vivo (`http://127.0.0.1:8000` o `8011`).
3. Desarmar un flujo complejo de extremo a extremo (UI → `panel.js` → `servidor.py` → `produccion.py` → adaptador externo → `proyecto.json`).

---

## Fase 1 · Sondeo empírico de APIs externas (nunca adivinar contratos)

Antes de escribir un adaptador nuevo o dar por muerta una clave en `.env`:

1. **Descubrir la URL base y el listado real de modelos (`/v1/models`):**
   - Ejecuta [sondar_api.py](./scripts/sondar_api.py) o una consulta `GET /v1/models` con la clave de `.env` sin imprimir nunca el secreto.
   - Anota los identificadores exactos devueltos por el servidor (ej. en Xiaomi MiMo `https://api.xiaomimimo.com/v1/models` devuelve `mimo-v2.5-tts` y `mimo-v2.6-flash`, no `mimo-v2-tts`).
2. **Aislar el esquema exacto de entrada/salida con carga mínima:**
   - Si un endpoint devuelve `400` o `402`, lee el mensaje literal del cuerpo JSON (`error.message`).
   - Ejemplo real en STUDIO 4 (Xiaomi MiMo TTS): el modelo `mimo-v2.5-tts` exige que el texto a sintetizar vaya en el último mensaje con `"role": "assistant"` (mientras la dirección de voz va en `"role": "user"`) y `"audio": {"voice": "Milo", "format": "wav"}`.
3. **Inspeccionar el binario devuelto antes de pasarlo a FFmpeg:**
   - Comprueba la cabecera real de los primeros bytes (`RIFF....WAVE` para WAV, `ID3` o `\xff\xfb` para MP3, PCM crudo para Gemini TTS) y verifica frecuencia de muestreo, canales y duración con `wave` o `ffprobe`.

---

## Fase 2 · Trazabilidad de extremo a extremo (Panel ↔ Servidor ↔ Disco)

Cuando el usuario reporta «no hay indicio de que funcione» o muestra una captura:

1. **Inspeccionar el estado vivo que entrega el servidor (`/api/estado`):**
   - Consulta `GET http://127.0.0.1:8000/api/estado` (solo lectura) y revisa:
     - `produccion.id`, `produccion.estado`, `produccion.trabajo` (`ocupado`, `error`, `fase_fallida`).
     - `opciones` (`mimo_ok`, `elevenlabs_ok`, `gemini_ok`, `voces`).
2. **Revisar si un estado persistido antiguo tapa la interfaz nueva:**
   - En `web/panel.js`, revisa `pintarTrabajo(t)`: si `proyecto.json` guardó un `trabajo.error` anterior (como un `(402)` viejo), el cartel rojo permanece visible hasta que se limpie o se ejecute la acción desde ese mismo cartel.
   - Asegúrate de que el propio cartel de error ofrezca el botón de salida gratuita disponible (ej. `data-voz-mimo="1"`).
3. **Contrastar `producciones/servidor.log` y `producciones/caidas.log`:**
   - Lee las últimas 80 líneas de `servidor.log` para distinguir entre desconexiones normales del navegador (`WinError 10053`) y excepciones reales de negocio (`400`, `402`, `RuntimeError`).

---

## Fase 3 · Verificación y sincronización entre ramas (`antigravity` ↔ `reestructura-google`)

1. Ejecuta la prueba puntual con `pytest -k "<nombre>"` y luego la suite completa sin tuberías:
   `python -m pytest tests/test_studio4.py -q -p no:cacheprovider`
2. Documenta en `TRASPASO.md` **qué** se descubrió por ingeniería inversa y **por qué** se implementó así, para que tanto Claude como Antigravity compartan el mismo contexto.
3. Cuando el autor pida aplicarlo al estudio principal (`C:\Users\Lenovo\studio4-vol3`), comprueba primero `git -C "C:\Users\Lenovo\studio4-vol3" status -s` y une con `git -C "C:\Users\Lenovo\studio4-vol3" merge --ff-only antigravity`.
