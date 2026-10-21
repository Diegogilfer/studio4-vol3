---
name: auditar-repo
description: >-
  Auditoría con ingeniería inversa de un repositorio externo (GitHub) que el autor quiere evaluar para STUDIO 4:
  qué es de verdad, cómo funciona por dentro, si cumple lo que promete, riesgos, coste, requisitos de hardware y
  si sirve en el PC del autor. Activar cuando el autor pegue «gh repo clone …», un enlace de GitHub o pregunte
  si una herramienta nos sirve.
---

# Auditar un repositorio para STUDIO 4

## 1 · Clonar sin tocar el proyecto
Clona en la carpeta temporal de la sesión (nunca dentro de `studio4-vol3`), con `--depth 50`. Si en Windows
fallan rutas largas, lee los archivos con `git show HEAD:ruta` y `git ls-tree` (y anótalo: no se descarga
entero en Windows).

## 2 · Qué hay que mirar (en este orden)
1. **Qué es**: README, `pyproject`/`package.json`, autores, licencia, fecha y ritmo de commits, tamaño.
2. **Cómo funciona por dentro**: los módulos centrales (no el README): el flujo real de principio a fin.
3. **Promesas vs realidad**: cada cifra del README contra el código, la guía de instalación y los requisitos
   (en qué GPU, en qué sistema, con qué modelo).
4. **Riesgos**: permisos peligrosos (`--dangerously-*`, sandbox desactivado), qué variables de entorno pasa a
   procesos (claves), descargas sin verificar, `shell=True`, `eval`, `pickle`, red sin límites, telemetría.
5. **Coste**: APIs de pago, GPU en la nube, multiplicadores (varias sesiones por tarea).
6. **Licencias** del código y de los modelos o datos que usa (uso comercial en un canal monetizado).
7. **Encaje con STUDIO 4 y el PC del autor**. El PC: portátil Intel Core i5-10310U, gráfica integrada Intel
   UHD (sin NVIDIA), 24 GB de RAM, Windows 11. Nada que necesite CUDA corre en local.

## 3 · Entregar
En español, corto, con este orden: veredicto en una línea → qué es → cómo funciona → tabla promesa/realidad
→ riesgos y coste → ¿nos sirve? (sí/no/en parte, y qué idea se puede aprovechar aunque no se instale).
No instales nada ni pegues claves para probarlo sin que el autor lo pida.

## Ya auditados
- `google-research/harness2` (2026-10-21): investigación de agentes, de pago (Vertex), permisos peligrosos,
  solo Linux. No se instala. Idea aprovechada: biblioteca de lecciones → habilidad `lecciones-canal`.
- `hao-ai-lab/FastVideo` (2026-10-21): generación de vídeo con IA; necesita GPU NVIDIA (mín. 8 GB) o Mac M;
  «Windows» solo con WSL. No corre en el PC del autor. Licencias de modelos variables (FLUX.1-dev no comercial).
