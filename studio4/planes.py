"""Las suscripciones de Studio 4, sacadas de lo que cuesta producir: cada plan tiene cupos (Shorts, vídeos largos,
imágenes con IA, voz premium, segundos de vídeo con IA) y su coste MÁXIMO (si el cliente gasta todo) se calcula con
las tarifas de abajo. Si cambia una tarifa, se recalculan solos el coste y el margen de cada plan.

Tarifas (octubre de 2026): DeepSeek V4 Flash 0,14 $/0,28 $ por millón de tokens; voz de Google (Gemini TTS de pago)
20 $ por millón de tokens de audio a 25 tokens/s; ElevenLabs por fal 0,10 $ cada 1.000 letras; imagen nano-banana
0,04 $ (registro de Studio); Veo 3.1 Fast 0,10 $/s. Subtítulos, 3 formatos, marca y miniaturas: en el PC, 0 $.
"""

from __future__ import annotations

from typing import Any

# lo que le cuesta a Studio cada cosa (USD)
COSTES = {
    "short": 0.01 + 60 * 0.0005,          # guion + investigación (DeepSeek) + voz de Google 60 s  ≈ 0,04
    "largo": 0.02 + 300 * 0.0005,         # ídem, 5 minutos                                          ≈ 0,17
    "imagen": 0.04,                       # una imagen con IA
    "voz_premium": 0.09,                  # ElevenLabs para un Short (~900 letras)
    "veo_segundo": 0.10,                  # un segundo de vídeo con IA (Veo 3.1 Fast)
}
COMISION_PCT, COMISION_FIJA = 0.05, 0.50   # lo que se queda la pasarela de pago por cobro (aprox.)

PLANES: list[dict[str, Any]] = [
    {"id": "gratis", "nombre": "Gratis", "precio": 0, "gancho": "Para probar", "canales": 1, "marca_agua": True,
     "cupos": {"short": 3, "largo": 0, "imagen": 5, "voz_premium": 0, "veo_segundo": 0},
     "extra": ["Sin límite si conectas tu clave gratis de Google"]},
    {"id": "creador", "nombre": "Creador", "precio": 9, "gancho": "Para empezar a publicar", "canales": 2,
     "cupos": {"short": 30, "largo": 4, "imagen": 30, "voz_premium": 0, "veo_segundo": 0}},
    {"id": "pro", "nombre": "Pro", "precio": 29, "gancho": "El más elegido", "destacado": True, "canales": 5,
     "cupos": {"short": 80, "largo": 15, "imagen": 120, "voz_premium": 15, "veo_segundo": 0},
     "extra": ["Subtítulos en 4 idiomas", "Radar de tendencias por canal"]},
    {"id": "studio", "nombre": "Studio", "precio": 99, "gancho": "Para varios canales", "canales": 15,
     "cupos": {"short": 200, "largo": 40, "imagen": 300, "voz_premium": 40, "veo_segundo": 90},
     "extra": ["Vídeo con IA (Veo)", "Soporte prioritario"]},
    {"id": "claves", "nombre": "Con tus claves", "precio": 5, "gancho": "Ya pagas tu IA", "canales": 15, "propias": True,
     "cupos": {"short": 0, "largo": 0, "imagen": 0, "voz_premium": 0, "veo_segundo": 0},
     "extra": ["Todo Studio sin cupos: la IA la pagas tú en tus cuentas", "Sin marca de agua"]},
]

NOMBRES = {"short": "Shorts al mes", "largo": "vídeos largos al mes", "imagen": "imágenes con IA",
           "voz_premium": "Shorts con voz premium", "veo_segundo": "segundos de vídeo con IA"}


def coste_maximo(plan: dict[str, Any]) -> float:
    return round(sum(COSTES[k] * n for k, n in plan["cupos"].items()), 2)


def comision(plan: dict[str, Any]) -> float:
    return round(plan["precio"] * COMISION_PCT + COMISION_FIJA, 2) if plan["precio"] else 0.0


def margen(plan: dict[str, Any]) -> float:
    """Lo que queda de cada cobro si el cliente gasta TODO su cupo (en la práctica, más)."""
    if not plan["precio"]:
        return 0.0
    return round((plan["precio"] - coste_maximo(plan) - comision(plan)) / plan["precio"], 2)


def para_clientes() -> list[dict[str, Any]]:
    """Lo que ve un cliente: precio y qué incluye (nunca los costes ni los márgenes)."""
    salida = []
    for p in PLANES:
        puntos = [f"{p['canales']} canal{'es' if p['canales'] > 1 else ''}"]
        puntos += [f"{n} {NOMBRES[k]}" for k, n in p["cupos"].items() if n]
        puntos += p.get("extra", [])
        puntos.append("Marca de agua Studio 4" if p.get("marca_agua") else "Sin marca de agua")
        puntos.append("Subtítulos, 3 formatos y miniaturas incluidos")
        salida.append({"id": p["id"], "nombre": p["nombre"], "precio": f"{p['precio']} $/mes" if p["precio"] else "0 $",
                       "gancho": p["gancho"], "destacado": bool(p.get("destacado")), "puntos": puntos})
    return salida


def para_el_dueno() -> list[dict[str, Any]]:
    """Las cuentas de cada plan (solo para ti): coste máximo, comisión y margen."""
    return [{"plan": p["nombre"], "precio": p["precio"], "coste_maximo": coste_maximo(p), "comision": comision(p),
             "margen": margen(p)} for p in PLANES]
