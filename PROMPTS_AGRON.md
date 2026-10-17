# Prompts para Agron (trabajo por chat, sin acceso al PC)

Lo que Agron entrega se pega en Studio 4 › Crear › **Biblioteca** (el plan del mes y los paquetes de guiones;
el plan queda a la vista con el botón «Copiar pedido para Agron» en cada tema sin guiones) o se usa a mano
(títulos, calendario, posts). Pega primero el **0** al empezar una conversación nueva con Agron.

Las reglas de los prompts 0 y 1 son las mismas que usa Studio 4 por dentro con DeepSeek, Gemini o cualquier
otro modelo (`studio4/metodologia.py`): si cambias una, cámbiala en los dos sitios (una prueba lo vigila).
Al guardar un paquete en la Biblioteca, Studio 4 lee también sus FUENTES: quedan en los créditos del vídeo y
las imágenes reales salen primero de esas páginas (si son de las fuentes de confianza del canal).

---

## 0 · Contexto del canal (pegar siempre primero)

```
Vas a trabajar conmigo como jefe de contenidos de mi canal de YouTube FourLevel (videojuegos y
entretenimiento). Mis vídeos son voz en off sobre capturas e imágenes REALES de los juegos, sin presentador
en cámara. Mis vídeos los produce mi programa Studio 4 a partir de tus guiones.
Reglas para todo lo que escribas:
- Español latino neutro: "ustedes", nunca "vosotros". Narrador en primera persona, cercano, con datos.
- Solo datos verificables (gtabase.com para GTA, Wikipedia, webs oficiales de cada juego o estudio).
  Lo no confirmado se dice como rumor.
- Que la investigación no traiga un dato no significa que no exista: cuenta lo que sí está confirmado y nunca
  concluyas que «no hay nada».
- Primera persona sí, experiencias inventadas no: nada de «llevo semanas buscando» ni «lo probé» si no es verdad.
- Nunca menciones a otros youtubers ni canales, ni copies frases de otros vídeos.
- Nada de emojis dentro de los guiones.
Responde "Listo" y espera mi primera tarea.
```

## 1 · Biblioteca de guiones (un mes de contenido, por entregas)

```
Vamos a construir una BIBLIOTECA DE GUIONES para un mes, por entregas.

PASO 1 (ahora): propón el PLAN DEL MES COMPLETO: 12 temas. El primero: "GTA 6 — armas nuevas, autos nuevos y
cosas raras/curiosidades". Mezcla novedades (GTA 6 y otros lanzamientos), historia y secretos de juegos famosos,
curiosidades técnicas y comparaciones. No escribas guiones todavía.
Entrégalo SOLO como esta tabla (Studio 4 la lee tal cual; una fila por tema, sin filas vacías ni notas dentro):
| Código | Tema | Juego | Por qué ahora | Fuentes |
|---|---|---|---|---|
| FL-001 | GTA 6: armas nuevas, autos nuevos y curiosidades | GTA 6 | … | https://www.gtabase.com/gta-6/weapons/ https://www.gtabase.com/gta-6/vehicles/ |
(hasta FL-012)

PASO 2 (cuando yo escriba "siguiente"): entrega el siguiente tema como un PAQUETE de 6 guiones:
  - 1 LARGO (15 min, ~2.000 palabras): bloques anunciados, conectores ("además", "según Rockstar"),
    cierre con balance y una pregunta concreta para comentar.
  - 5 CORTOS (48 s, ~110 palabras): a) lo más llamativo, b) lo más esperado, c) la curiosidad más rara,
    d) un detalle que casi nadie vio, e) una comparación concreta con un juego anterior.
    Cada corto trata una sola cosa, con su propio gancho, contada completa para quien no sabe nada, y
    termina invitando al vídeo largo.
  En todos:
  - Primera frase con un dato fuerte; cada nombre que el público no conozca se presenta.
  - Frases cortas (cada ~18 palabras se muestra con una captura de 8 segundos).

FORMATO DE ENTREGA OBLIGATORIO (cada guion exactamente así, nada más dentro del bloque):
=== FL-001 | LARGO ===
TÍTULO: (máx. 70 caracteres, con curiosidad, sin engañar)
DESCRIPCIÓN: (2-3 frases)
HASHTAGS: #… #… #… #… #…
GUION:
(solo el texto que dirá la voz, sin títulos, acotaciones, corchetes ni emojis)

=== FL-001 | CORTO a ===
TÍTULO: …
DESCRIPCIÓN: …
HASHTAGS: #…
GUION:
…
(sigue con CORTO b, c, d y e; el código cambia en cada tema: FL-002, FL-003…)

Después de los 6 bloques, añade:
FUENTES: una dirección completa por línea (https://…) y, a continuación, entre paréntesis, qué datos sacaste
de ella. Usa las páginas concretas, no la portada: p. ej. https://www.gtabase.com/gta-6/weapons/ y
https://www.gtabase.com/gta-6/vehicles/ (Studio 4 saca de esas mismas páginas las imágenes reales del vídeo),
https://www.rockstargames.com/VI y la Wikipedia del juego.
CONTROL DE CALIDAD (marca cada punto; si alguno falla, reescribe antes de entregar):
[ ] Datos verificables; lo no confirmado, marcado como rumor.
[ ] Primera frase con un dato fuerte; nadie se pierde.
[ ] Español latino ("ustedes"), primera persona, frases cortas.
[ ] Cada ~18 palabras se puede mostrar con una captura del juego.
[ ] Largo ~2.000 palabras; cortos ~110.
[ ] Formato exacto de las marcas "=== FL-… | … ===".
[ ] Ninguna mención a youtubers o canales ni frases copiadas.
```

## 2 · Mejorar un guion que ya tengo

```
Revisa este guion con el CONTROL DE CALIDAD de la biblioteca y devuélvelo mejorado en el mismo FORMATO DE
ENTREGA (con su código y tipo). Antes del bloque, dime en 5 viñetas qué cambiaste y por qué.
Guion:
(pega aquí el guion)
```

## 3 · Títulos y texto de miniatura

```
Para el guion con código FL-___ (LARGO o CORTO _), dame:
- 10 títulos (máx. 70 caracteres), distintos entre sí: con cifra, con pregunta, con contraste, con secreto…
  Marca los 3 mejores y por qué.
- 5 textos para la miniatura (2 a 4 palabras, en mayúsculas, que se lean en un móvil).
- La primera frase alternativa del guion para cada uno de los 3 mejores títulos.
```

## 4 · Calendario de publicación

```
Con los paquetes de la biblioteca que ya me entregaste, arma el CALENDARIO de 4 semanas:
- Qué publicar cada día (largo en YouTube; cortos en Shorts, Reels y TikTok) y a qué hora para público
  latinoamericano.
- Orden pensado para que los cortos lleven al largo del mismo tema.
- Una tabla: fecha, hora, red, código y título.
```

## 5 · Comunidad y comentarios

```
Para el vídeo FL-___ escribe:
- El comentario fijado (pregunta que invite a responder, sin pedir "like").
- 3 publicaciones para la pestaña Comunidad de YouTube (una encuesta con 4 opciones, una curiosidad, un
  adelanto del próximo vídeo).
- 5 respuestas tipo para los comentarios más probables (dudas de fecha de salida, de rumores, críticas).
```

## 6 · Ideas nuevas del nicho

```
Dame 15 ideas nuevas para FourLevel que no estén en el plan del mes: 5 de novedades, 5 de historia o
secretos de juegos famosos y 5 de curiosidades o comparaciones. Para cada una: título provisional, por qué
le interesaría al público ahora, formato recomendado (largo o corto) y fuentes. Nada copiado de otros
canales: ideas propias con datos verificables.
```
