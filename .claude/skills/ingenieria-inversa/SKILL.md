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

Lee las instrucciones completas y ejecuta el script de sondeo en:
- [`.agents/skills/ingenieria-inversa/SKILL.md`](../../.agents/skills/ingenieria-inversa/SKILL.md)
- [`.agents/skills/ingenieria-inversa/scripts/sondar_api.py`](../../.agents/skills/ingenieria-inversa/scripts/sondar_api.py)
