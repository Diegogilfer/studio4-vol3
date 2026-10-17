# Para cualquier agente que trabaje en Studio 4 (Antigravity, Claude, otros)

Antes de tocar nada, lee **TRASPASO.md** entero: reglas del autor, estado y errores que ya costaron caro.

## Dónde se trabaja

- La copia **`C:\Users\Lenovo\studio4-vol3`** es la que usa el autor cada día (rama `reestructura-google`, su
  servidor en el puerto 8000). **No edites ahí** si no eres el agente principal.
- Cada agente extra trabaja en **su propia carpeta y su propia rama** (un `git worktree`), p. ej.
  `C:\Users\Lenovo\studio4-antigravity` en la rama `antigravity`. Así lo que hagas no rompe el estudio del autor.
- Nunca hagas `git push --force`, `git reset --hard` ni borres ramas o carpetas de otros.

## Cómo se trabaja

1. Un cambio pequeño cada vez, con su prueba en `tests/test_studio4.py`.
2. **Commit solo si pasan todas las pruebas**: `python -m pytest tests/test_studio4.py -q -p no:cacheprovider`.
   No escondas el resultado con tuberías (`| tail`): mira que diga «passed» y ningún «failed».
3. Las pruebas nunca tocan `producciones/` ni `.env` reales (usa el fixture `aislado`).
4. Para ver el panel, levanta un servidor de prueba en **otro puerto (8011)**; nunca reinicies ni uses el del 8000.
5. Nada de gastos (fal, ElevenLabs, Veo) sin el visto bueno del autor. Google Flow no se automatiza.
6. Mismo estilo que el código que rodea: español, nombres en español, comentarios cortos que dicen el porqué.
7. Al terminar, apunta en **TRASPASO.md › Bitácora** qué cambiaste, en qué commits y qué quedó a medias.

## Cómo vuelve el trabajo al proyecto

El agente principal revisa la rama (`git diff reestructura-google...antigravity`), pasa las pruebas y la une.
Nada se une sin revisión.
