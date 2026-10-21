---
name: elegir-planos
description: >-
  Elegir a mano, por lo que dice cada frase, los planos de gameplay o tráiler de un vídeo del panel de montaje
  de STUDIO 4 (16:9), con hojas de contacto numeradas, reglas de calidad y comprobación de que cada plano da
  para su frase. Activar al preparar el material de un vídeo nuevo, cuando el autor diga que las imágenes «no
  concuerdan», «saltan a otra cosa» o «se ven mal», o antes de montar una previa.
---

# Elegir planos por lo que dice la frase (STUDIO 4)

Lee antes las lecciones del canal (habilidad `lecciones-canal`): ahí están las fuentes buenas y malas.

## 1 · Ver todo el material
```
python .claude/skills/elegir-planos/planos.py hojas FUENTE [FUENTE...]
```
Hojas de 56 miniaturas en `producciones/_hojas/`: `número · duración`. Verde ≥3 s · amarillo corto · rojo
«pobre» (oscuro o casi fijo: puede servir, míralo antes). Para dudar entre varios:
```
python .claude/skills/elegir-planos/planos.py ver FUENTE 120,124,148
```
Tres fotogramas por plano (10 · 50 · 90 %): se ve si se mueve, si tiene letreros o texto de tutorial encima.

## 2 · Reglas
1. **La imagen cuenta lo que dice la frase.** «Robar un estéreo» → el minijuego del estéreo; «asaltar una
   tienda» → el plano del tráiler donde asaltan la tienda. Si no hay nada que encaje, un panel (cristal con
   datos) es mejor que un plano cualquiera.
2. **Nunca encadenar el plano siguiente sin mirarlo**: en un tráiler el plano siguiente es otra escena.
   Varios planos en una frase solo si se eligen a propósito (`mas`, máximo 3, misma fuente).
3. **Planos de tráiler (1-2 s)**: 2-3 por frase, al ritmo del tráiler. **Gameplay** (planos de 6 s): uno por
   frase; si la frase es larga, el plano siguiente del mismo vídeo es continuo y sirve como `mas`.
4. **Fuera**: marcas de agua de otros canales, letreros del tráiler («ROCKSTAR GAMES PRESENTS»), ESRB, menús,
   pantallas negras, escenas con subtítulos en inglés quemados si hay alternativa, y planos quietos largos
   (portadas, logos) salvo un instante.
5. **Paneles** (3-5 en un vídeo de 4-5 min): para listas, datos y comparaciones. Iconos con nombre válido
   (`animacion.ICONOS_NOMBRES`) o se deducen del texto.
6. **Rótulos** solo al presentar algo (juego y año, lugar, «TRÁILER 1»); no en todas las frases.

## 3 · Asignar
Con el servidor de prueba (8011) o el del autor si él lo pide, frase a frase:
```
POST /api/m/asignar {"id": VIDEO, "n": 4, "fuente": FID, "plano": 8, "mas": [2], "rotulo": "GTA 6 · 2026"}
POST /api/m/asignar {"id": VIDEO, "n": 9, "panel": {"titulo": "...", "items": ["..."], "iconos": ["auto"], "nota": "..."}}
```
Guarda el plan en un script (lista n → plano) para poder rehacerlo y cambiar solo lo que el autor corrija.

## 4 · Comprobar antes de montar
```
python .claude/skills/elegir-planos/planos.py cobertura VIDEO_ID
```
«SE CONGELA» no se monta: añade un plano a `mas` o elige uno más largo. «se estira» es aceptable (cámara lenta
con cuadros intermedios), pero si son muchos, mejor más planos. Después: previa → habilidad `revisar-video`.
