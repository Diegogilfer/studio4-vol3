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
    "video": 0.02 + 300 * 0.0005,         # un vídeo (hasta 5 min): guion + investigación + voz de Google  ≈ 0,17
    "imagen": 0.04,                       # una imagen con IA
    "voz_premium": 0.45,                  # ElevenLabs para un vídeo de 5 min (~4.500 letras)
    "veo_segundo": 0.10,                  # un segundo de vídeo con IA (Veo 3.1 Fast)
}
COMISION_PCT, COMISION_FIJA = 0.05, 0.50   # lo que se queda la pasarela de pago por cobro (aprox.)
USO_JUSTO_VIDEOS = 100                    # «ilimitado»: para el cálculo del peor caso se cuentan 100 vídeos al mes

# Los 3 planes de Diego. Cada vídeo sale en los 3 formatos (16:9, 9:16, 1:1) con subtítulos y miniaturas.
# Lo que se paga a terceros (imágenes, voz premium, vídeo con IA) va con un tope mensual; pasado el tope, sus claves.
PLANES: list[dict[str, Any]] = [
    {"id": "basico", "nombre": "Básico", "precio": 17, "gancho": "Para empezar", "canales": 2,
     "cupos": {"video": 5, "imagen": 100, "voz_premium": 0, "veo_segundo": 0}},
    {"id": "pro", "nombre": "Pro", "precio": 49, "gancho": "El más elegido", "destacado": True, "canales": 5,
     "cupos": {"video": 15, "imagen": 300, "voz_premium": 5, "veo_segundo": 30}},
    {"id": "ilimitado", "nombre": "Ilimitado", "precio": 100, "gancho": "Todo sin límites", "canales": None,
     "cupos": {"video": None, "imagen": 500, "voz_premium": 15, "veo_segundo": 60}},
]

# No hay plan gratis: prueba de 3 días del Básico, POTENCIADO con un adelanto del Pro (voz premium y vídeo con IA)
PRUEBA = {"dias": 3, "plan": "basico", "cupos": {"video": 3, "imagen": 30, "voz_premium": 1, "veo_segundo": 6}}

NOMBRES = {"video": "vídeos al mes en los 3 formatos", "imagen": "imágenes con IA al mes",
           "voz_premium": "vídeos con voz premium al mes", "veo_segundo": "segundos de vídeo con IA al mes"}


def coste_maximo(plan: dict[str, Any]) -> float:
    """Lo que costaría el plan si el cliente gasta todo (en «ilimitado», con el uso justo de vídeos)."""
    return round(sum(COSTES[k] * (USO_JUSTO_VIDEOS if n is None else n) for k, n in plan["cupos"].items()), 2)


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
        puntos = ["Canales ilimitados" if p["canales"] is None else f"{p['canales']} canales"]
        puntos += ["Vídeos ilimitados en los 3 formatos" if n is None and k == "video" else f"{n} {NOMBRES[k]}"
                   for k, n in p["cupos"].items() if n or n is None]
        puntos += ["Subtítulos en 4 idiomas, miniaturas para elegir y textos para YouTube",
                   "Estilos hechos por Claude (stickman, motion, collage…) incluidos",
                   "Pasado el tope de IA: usa tus claves o compra un paquete"]
        salida.append({"id": p["id"], "nombre": p["nombre"], "precio": f"{p['precio']} $/mes" if p["precio"] else "0 $",
                       "gancho": p["gancho"], "destacado": bool(p.get("destacado")), "puntos": puntos})
    return salida


def para_el_dueno() -> list[dict[str, Any]]:
    """Las cuentas de cada plan (solo para ti): coste máximo, comisión y margen."""
    return [{"plan": p["nombre"], "precio": p["precio"], "coste_maximo": coste_maximo(p), "comision": comision(p),
             "margen": margen(p)} for p in PLANES]


def prueba() -> dict[str, Any]:
    """La prueba de 3 días, tal como la ve el cliente (y su coste máximo, solo para el dueño)."""
    c = PRUEBA["cupos"]
    return {"dias": PRUEBA["dias"], "plan": next(p["nombre"] for p in PLANES if p["id"] == PRUEBA["plan"]),
            "puntos": [f"{c['video']} vídeos en los 3 formatos", f"{c['imagen']} imágenes con IA",
                       f"{c['voz_premium']} vídeo con voz premium", f"{c['veo_segundo']} segundos de vídeo con IA"]}


def coste_prueba() -> float:
    return round(sum(COSTES[k] * n for k, n in PRUEBA["cupos"].items()), 2)


# --- La cuenta del negocio entero: no solo la IA de cada cliente --------------------------------------------------
# Gastos fijos al mes (USD). Supuestos a confirmar por Diego; se cambian aquí y todo se recalcula.
FIJOS = {
    "Supabase Pro (sin pausas, copias, más espacio)": 25.0,
    "Dominio y correo profesional": 8.0,
    "Web de venta (hosting)": 20.0,
    "Claude para mantener y mejorar Studio": 100.0,
}
USO_ESPERADO = 0.5          # qué parte de la IA de pago gasta de media un cliente (el peor caso es 1,0)
VIDEOS_ESPERADOS_ILIMITADO = 40   # vídeos al mes de un cliente «ilimitado» medio (el peor caso es USO_JUSTO_VIDEOS)
CONVERSION_PRUEBA = 0.25    # de cada 4 pruebas de 3 días, 1 acaba pagando
MEZCLA = {"basico": 0.6, "pro": 0.3, "ilimitado": 0.1}   # cómo se reparten los clientes entre los planes


def coste_esperado(plan: dict[str, Any], uso: float = USO_ESPERADO) -> float:
    """Lo que cuesta de verdad un cliente medio: sus vídeos enteros + la parte de IA de pago que suele gastar."""
    videos = VIDEOS_ESPERADOS_ILIMITADO if plan["cupos"]["video"] is None else plan["cupos"]["video"]
    de_pago = sum(COSTES[k] * n for k, n in plan["cupos"].items() if k != "video" and n)
    return round(COSTES["video"] * videos + de_pago * uso, 2)


def contribucion(plan: dict[str, Any], uso: float = USO_ESPERADO) -> float:
    """Lo que deja un cliente al mes para pagar los gastos fijos: precio − su IA − la comisión del cobro."""
    return round(plan["precio"] - coste_esperado(plan, uso) - comision(plan), 2)


def coste_captacion() -> float:
    """Lo que cuestan las pruebas gratis por cada cliente que acaba pagando (pruebas fallidas incluidas)."""
    return round(coste_prueba() * USO_ESPERADO / CONVERSION_PRUEBA, 2)


def economia(clientes: int, mezcla: dict[str, float] | None = None, uso: float = USO_ESPERADO) -> dict[str, Any]:
    """El mes del negocio con N clientes de pago: ingresos, costes, comisiones, fijos, pruebas y beneficio."""
    mezcla = mezcla or MEZCLA
    por_id = {p["id"]: p for p in PLANES}
    n = {k: round(clientes * f) for k, f in mezcla.items()}
    ingresos = sum(por_id[k]["precio"] * c for k, c in n.items())
    ia = sum(coste_esperado(por_id[k], uso) * c for k, c in n.items())
    comisiones = sum(comision(por_id[k]) * c for k, c in n.items())
    fijos = sum(FIJOS.values())
    pruebas = coste_captacion() * clientes * 0.1   # se renueva ~10 % de clientes al mes: hay que captarlos con pruebas
    beneficio = ingresos - ia - comisiones - fijos - pruebas
    return {"clientes": n, "ingresos": round(ingresos, 2), "ia": round(ia, 2), "comisiones": round(comisiones, 2),
            "fijos": round(fijos, 2), "pruebas": round(pruebas, 2), "beneficio": round(beneficio, 2),
            "margen": round(beneficio / ingresos, 2) if ingresos else 0.0}


def equilibrio(mezcla: dict[str, float] | None = None, uso: float = USO_ESPERADO) -> int:
    """Cuántos clientes de pago hacen falta para no perder dinero."""
    for c in range(1, 10_000):
        if economia(c, mezcla, uso)["beneficio"] >= 0:
            return c
    return -1
