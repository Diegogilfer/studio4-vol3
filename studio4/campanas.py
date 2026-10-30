"""Campañas: Studio 4 prepara el kit de una temporada de ventas (Black Friday, Cyber Monday, Navidad…) para el
producto del creador: anuncios en vídeo de 15 y 30 s (que se montan como cualquier vídeo), textos para redes,
correos y el calendario. Honesto por regla: nada de urgencias falsas, descuentos inflados ni promesas de
resultados; la oferta, las fechas y las plazas son las que pone el creador.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from . import canales, config, deepseek

_cerrojo = threading.Lock()
MAX_KITS = 20

SISTEMA = """Eres el director de marketing de un creador hispanohablante. Con su PRODUCTO, su OFERTA y sus FECHAS,
prepara el kit de campaña de la TEMPORADA. Reglas: honesto (nada de urgencias falsas, «últimas horas» que no lo son,
precios tachados inventados ni promesas de vistas o dinero); la oferta y las plazas son EXACTAMENTE las que te dan;
español latino neutro, frases cortas, gancho en la primera línea; 1-2 emojis como mucho por texto.
Anuncios: guion para voz en off; el de 15 s ~35 palabras, el de 30 s ~70; estructura gancho → problema → producto →
oferta con fechas → llamada a la acción. Párrafos separados por línea en blanco (cada párrafo = una escena).
Devuelve solo JSON:
{"titulo": "nombre corto de la campaña", "mensaje": "la promesa en una frase",
 "anuncios": [{"duracion": 15, "titulo": "...", "guion": "..."}, {"duracion": 30, "titulo": "...", "guion": "..."}],
 "publicaciones": [{"cuando": "fecha o momento", "red": "Instagram|TikTok|YouTube|X|Facebook", "texto": "...", "hashtags": ["#..."]}],
 "correos": [{"cuando": "...", "asunto": "...", "cuerpo": "..."}],
 "calendario": [{"cuando": "...", "que": "..."}]}
Entre 6 y 9 publicaciones, 3 correos (aviso, apertura, último día) y el calendario de principio a fin."""

TEMPORADAS = ("Black Friday", "Cyber Monday", "Navidad", "Rebajas de enero", "San Valentín", "Lanzamiento")


def _archivo(cid: str):
    c = config.PRODUCCIONES / "_canales" / cid
    c.mkdir(parents=True, exist_ok=True)
    return c / "campanas.json"


def leer(cid: str) -> list[dict[str, Any]]:
    f = _archivo(cid)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except ValueError:
        return []


def crear_kit(cid: str, producto: str, oferta: str = "", fechas: str = "", temporada: str = "Black Friday") -> dict[str, Any]:
    """El kit de campaña para un producto. Se guarda con el canal para volver a él."""
    producto = (producto or "").strip()[:600]
    if len(producto) < 4:
        raise ValueError("Dime qué vendes (tu curso, tu merch, tu app, tu canal…).")
    if not deepseek.disponible():
        raise ValueError("Las campañas necesitan DeepSeek conectado.")
    canal = canales.obtener(cid)
    temporada = temporada if temporada in TEMPORADAS else "Black Friday"
    prompt = (f"CANAL: {canal['nombre']} · {canal.get('nicho', '')} · público: {canal.get('publico', '')}\n"
              f"TEMPORADA: {temporada}\nPRODUCTO: {producto}\nOFERTA: {oferta.strip()[:300] or '(sin oferta: no inventes descuentos)'}\n"
              f"FECHAS: {fechas.strip()[:200] or '(usa las fechas habituales de la temporada)'}")
    d = deepseek.generar_json(SISTEMA, prompt, temperatura=0.7, detalle=f"campaña {temporada}")
    kit = {"id": f"c{int(time.time())}", "creado": time.strftime("%Y-%m-%d %H:%M"), "temporada": temporada,
           "producto": producto, "oferta": oferta.strip()[:300], "fechas": fechas.strip()[:200],
           "titulo": str(d.get("titulo") or f"{temporada}: {producto[:40]}")[:90], "mensaje": str(d.get("mensaje", ""))[:240],
           "anuncios": [{"duracion": int(a.get("duracion") or 30), "titulo": str(a.get("titulo", ""))[:90], "guion": str(a.get("guion", "")).strip()}
                        for a in d.get("anuncios") or [] if str(a.get("guion", "")).strip()][:4],
           "publicaciones": [{"cuando": str(p.get("cuando", ""))[:60], "red": str(p.get("red", ""))[:20], "texto": str(p.get("texto", ""))[:1200],
                              "hashtags": [str(h) for h in p.get("hashtags") or [] if str(h).startswith("#")][:8]}
                             for p in d.get("publicaciones") or [] if p.get("texto")][:12],
           "correos": [{"cuando": str(c.get("cuando", ""))[:60], "asunto": str(c.get("asunto", ""))[:120], "cuerpo": str(c.get("cuerpo", ""))[:3000]}
                       for c in d.get("correos") or [] if c.get("cuerpo")][:5],
           "calendario": [{"cuando": str(c.get("cuando", ""))[:60], "que": str(c.get("que", ""))[:200]} for c in d.get("calendario") or []][:15]}
    if not kit["anuncios"]:
        raise RuntimeError("No salieron anuncios: prueba otra vez con más detalle del producto.")
    with _cerrojo:
        _archivo(cid).write_text(json.dumps(([kit] + leer(cid))[:MAX_KITS], ensure_ascii=False, indent=1), encoding="utf-8")
    return kit


def video_de_anuncio(cid: str, kit_id: str, n: int) -> str:
    """Un anuncio del kit → vídeo nuevo listo para montar (con su guion ya partido en escenas)."""
    from . import montaje
    kit = next((k for k in leer(cid) if k["id"] == kit_id), None)
    if not kit or not 0 <= n < len(kit["anuncios"]):
        raise ValueError("Ese anuncio ya no está.")
    a = kit["anuncios"][n]
    mid = montaje.crear(f"Anuncio {a['duracion']} s · {a['titulo'] or kit['titulo']}"[:110], a["guion"], cid)
    montaje.modificar(mid, lambda p: p.update(campana={"kit": kit_id, "anuncio": n, "temporada": kit["temporada"]},
                                              formato_principal="9:16" if a["duracion"] <= 30 else "16:9"))
    return mid
