"""La composición de un vídeo: 4 elementos que se eligen y se combinan, cada uno con su efecto real.

- Gancho: cómo arranca el guion (los primeros 3 segundos deciden si se quedan).
- Ritmo: largo de las frases y cada cuánto cambia la imagen (cada frase es un plano).
- Leyenda: el estilo de los subtítulos.
- Estilo: el visual (studio4/estilos.py).
"""

from __future__ import annotations

from typing import Any

GANCHOS: dict[str, dict[str, str]] = {
    "dato_imposible": {"nombre": "Dato imposible", "ejemplo": "«En 1901 sacaron del mar un ordenador de 2.000 años.»",
                       "guion": "La PRIMERA frase es un dato real que parece imposible, con número o fecha; sin saludo."},
    "pregunta": {"nombre": "Pregunta", "ejemplo": "«¿Cómo desaparecen tres hombres de una isla sin salida?»",
                 "guion": "La PRIMERA frase es una pregunta concreta que el espectador no sabe responder y que el vídeo responde."},
    "nadie_conto": {"nombre": "Nadie te lo contó", "ejemplo": "«Lo que no te contaron del faro de Flannan…»",
                    "guion": "La PRIMERA frase promete un detalle poco conocido y verdadero que se revela más adelante."},
    "contradiccion": {"nombre": "Contradicción", "ejemplo": "«Todos creen que fue un fantasma. El informe dice otra cosa.»",
                      "guion": "La PRIMERA frase contradice lo que la mayoría cree y el vídeo lo demuestra con datos."},
    "final_primero": {"nombre": "Final primero", "ejemplo": "«Sus cuerpos nunca aparecieron. Así empezó todo.»",
                      "guion": "Empieza por el desenlace en una frase y después cuenta cómo se llegó hasta ahí."},
    "cuenta_atras": {"nombre": "Lista / cuenta atrás", "ejemplo": "«3 pistas que nadie supo explicar.»",
                     "guion": "Estructura en lista numerada anunciada en la PRIMERA frase («3 pistas…»), de menor a mayor impacto."},
}

RITMOS: dict[str, dict[str, Any]] = {
    "rapido": {"nombre": "Rápido", "cada": "1,5-2 s", "palabras": 8,
               "guion": "Frases muy cortas (máximo 8 palabras): cada frase es un cambio de imagen. Ritmo de Short."},
    "medio": {"nombre": "Medio", "cada": "3 s", "palabras": 14,
              "guion": "Frases de hasta 14 palabras; alterna una corta con una media."},
    "lento": {"nombre": "Lento", "cada": "5 s", "palabras": 24,
              "guion": "Frases largas y pausadas, de narración documental; deja respirar cada idea."},
}

LEYENDAS: dict[str, dict[str, Any]] = {
    "viral_dorado": {"nombre": "Viral dorado", "ajustes": {"estilo": "viral", "paleta": "dorado", "posicion": "abajo", "tamano": "normal"}},
    "viral_amarillo": {"nombre": "Viral amarillo", "ajustes": {"estilo": "viral", "paleta": "amarillo", "posicion": "abajo", "tamano": "normal"}},
    "viral_cian": {"nombre": "Neón cian", "ajustes": {"estilo": "viral", "paleta": "cian", "posicion": "centro", "tamano": "grande"}},
    "viral_rosa": {"nombre": "Rosa eléctrico", "ajustes": {"estilo": "viral", "paleta": "rosa", "posicion": "abajo", "tamano": "normal"}},
    "cine": {"nombre": "Cine", "ajustes": {"estilo": "cine", "paleta": "blanco", "posicion": "abajo", "tamano": "normal"}},
    "minimal": {"nombre": "Minimal", "ajustes": {"estilo": "viral", "paleta": "blanco", "posicion": "abajo", "tamano": "pequeno"}},
}

POR_DEFECTO = {"gancho": "dato_imposible", "ritmo": "medio", "leyenda": "viral_amarillo"}


def valida(o: dict[str, Any], canal: dict[str, Any] | None = None) -> dict[str, str]:
    """Gancho, ritmo y leyenda pedidos; si no valen, los del canal; si tampoco, los de por defecto."""
    base = {**POR_DEFECTO, **{k: v for k, v in ((canal or {}).get("composicion") or {}).items() if v}}
    salida = {}
    for clave, catalogo in (("gancho", GANCHOS), ("ritmo", RITMOS), ("leyenda", LEYENDAS)):
        pedido = o.get(clave)
        salida[clave] = pedido if pedido in catalogo else (base[clave] if base[clave] in catalogo else POR_DEFECTO[clave])
    return salida


def para_guion(c: dict[str, str]) -> str:
    return f"GANCHO: {GANCHOS[c['gancho']]['guion']} RITMO: {RITMOS[c['ritmo']]['guion']}"


def subtitulos(c: dict[str, str]) -> dict[str, Any]:
    return {"activos": True, **LEYENDAS[c["leyenda"]]["ajustes"]}


def catalogo() -> dict[str, list[dict[str, str]]]:
    """Para el panel: las fichas de cada elemento con su ejemplo."""
    return {"gancho": [{"id": k, "nombre": g["nombre"], "detalle": g["ejemplo"]} for k, g in GANCHOS.items()],
            "ritmo": [{"id": k, "nombre": r["nombre"], "detalle": f"Imagen nueva cada {r['cada']}"} for k, r in RITMOS.items()],
            "leyenda": [{"id": k, "nombre": l["nombre"], "detalle": f"{l['ajustes']['estilo']} · {l['ajustes']['posicion']}",
                         "paleta": l["ajustes"]["paleta"], "estilo": l["ajustes"]["estilo"]} for k, l in LEYENDAS.items()]}
