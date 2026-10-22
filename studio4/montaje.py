"""Montaje 16:9 con material real: el flujo con el que se hizo el primer vídeo, en 5 pasos y en orden.

1. GUION     el guion del autor (o de la Biblioteca) se parte en bloques (párrafos) y frases.
2. MATERIAL  enlaces de fuentes seguras (tráilers oficiales, gameplay sin comentario): se bajan en BAJA calidad
             solo para ver sus planos; el banco de clips guarda todo para otros vídeos.
3. MONTAJE   cada frase lleva un plano (Studio propone, el autor cambia) y, si quiere, un rótulo.
4. PREVIA    vídeo en silencio con los efectos, rápido y gratis, para revisar antes de gastar nada.
5. FINAL     voz del canal → los planos elegidos se bajan en ALTA (1080p, solo esos segundos) → 16:9 a
             pantalla completa, rejilla con tarjetas SOLO entre bloques, subtítulos, logo, efectos y música →
             Short vertical sacado del 16:9 → textos para publicar y miniatura.

Calidad: el gameplay va directo de la fuente a FFmpeg (sin capturas de pantalla); el navegador solo dibuja la
rejilla de las transiciones, los paneles de texto y la miniatura.
"""

from __future__ import annotations

import array
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import animacion, calidad, canales, config, extractor, medios, musica, sonido, subtitulos, voz

logger = logging.getLogger("studio4.montaje")

ANCHO, ALTO = 1920, 1080
ANCHO_PREVIA, ALTO_PREVIA = 960, 540
TRANSICION = 1.6        # segundos del cambio de bloque: el vídeo se encoge, entra la tarjeta nueva y crece
ENTRADA = 0.25          # respiro antes de la primera palabra
PAUSA_FRASE = 0.35      # silencio que se añade a la voz al acabar una oración (la voz de Google casi no respira)
PAUSA_BLOQUE = 0.9      # y al cambiar de bloque, donde entra la transición
PALABRAS_MAX = 14       # una oración más larga se parte en una coma: cada parte lleva su plano
PALABRAS_POR_SEGUNDO = 2.5
ESTILO_VOZ = ("Narra en español latino neutro, con acento latinoamericano (nunca de España), como un youtuber de "
              "videojuegos: cercano, con energía y ritmo ágil, dando datos con seguridad")
_lock = threading.RLock()
# Un trabajo pesado a la vez (render, voz, descargas en alta): el PC no tiene tarjeta gráfica y dos montajes a la
# par se ahogan. Los demás esperan su turno y el panel lo dice.
_turno = threading.Lock()
PESADOS = {"Previa", "Vídeo final", "Short", "Automático"}


# --- Guardado -----------------------------------------------------------------------------------------------------
def raiz() -> Path:
    return config.PRODUCCIONES / "_montajes"


def carpeta(mid: str) -> Path:
    if not re.fullmatch(r"[\w-]{3,80}", mid or ""):
        raise ValueError("Montaje desconocido.")
    return raiz() / mid


def cargar(mid: str) -> dict[str, Any]:
    ruta = carpeta(mid) / "proyecto.json"
    if not ruta.exists():
        raise ValueError("Ese vídeo ya no existe.")
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar(p: dict[str, Any]) -> None:
    ruta = carpeta(p["id"]) / "proyecto.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    p["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def modificar(mid: str, cambio: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    with _lock:
        p = cargar(mid)
        cambio(p)
        guardar(p)
        return p


def listar() -> list[dict[str, Any]]:
    salida = []
    for f in sorted(raiz().glob("*/proyecto.json"), reverse=True) if raiz().exists() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        salida.append({"id": p["id"], "titulo": p["titulo"], "creado": p["creado"], "paso": paso_actual(p),
                       "frases": len(p["frases"]), "con_clip": sum(1 for x in p["frases"] if con_imagen(x)),
                       "final": bool(p.get("final"))})
    return salida


def con_imagen(f: dict[str, Any]) -> bool:
    """La frase ya tiene qué enseñar: un plano de vídeo, un panel de texto o una imagen."""
    return bool(f.get("clip") or f.get("panel") or f.get("imagen"))


def paso_actual(p: dict[str, Any]) -> int:
    """En qué paso va el vídeo (1 a 5), para la lista y para abrir el panel donde toca."""
    if not p["frases"]:
        return 1
    if not p["fuentes"]:
        return 2
    if any(not con_imagen(x) for x in p["frases"]):
        return 3
    if not p.get("previa"):
        return 4
    return 5


def cobertura(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Las frases cuyo plano (con sus «mas») no da para lo que dura la frase: {n, necesita, hay, congela}.
    «congela» = ni estirándolo llega (se quedaría quieto el final): hay que añadir un plano o cambiarlo."""
    t = _tiempos_estimados(p)
    tramos = [(0.0 if k == 0 else a, t[k + 1][0] if k + 1 < len(t) else b + 1.2) for k, (a, b) in enumerate(t)]
    salida = []
    for k, (f, (a, b)) in enumerate(zip(p["frases"], tramos)):
        if f.get("panel") or not f.get("clip"):
            continue
        try:
            meta = fuente(f["clip"]["fuente"])
        except ValueError:
            continue
        nums = [x for x in [f["clip"]["plano"], *f["clip"].get("mas", [])] if 1 <= x <= len(meta["planos"])]
        hay = sum(meta["planos"][x - 1]["fin"] - meta["planos"][x - 1]["ini"] for x in nums)
        nuevo = k > 0 and f["bloque"] != p["frases"][k - 1]["bloque"]
        necesita = (b - a) - (TRANSICION if nuevo and (b - a) > TRANSICION + 0.8 else 0)
        if hay < necesita:
            salida.append({"n": f["n"], "necesita": round(necesita, 1), "hay": round(hay, 1),
                           "congela": hay * LENTO_MAX < necesita})
    return salida


def resumen(p: dict[str, Any]) -> dict[str, Any]:
    """Lo que se ve al pegar el guion: duración, capítulos (bloques), escenas (frases) y cómo va el material."""
    t = (p.get("voz") or {}).get("pausas", {}).get("tiempos") or _tiempos_estimados(p)
    total = (t[-1][1] + 1.2) if t else 0.0
    return {"duracion": round(total, 1), "estimada": not (p.get("voz") or {}).get("pausas"),
            "capitulos": len({f["bloque"] for f in p["frases"]}), "frases": len(p["frases"]),
            "paneles": sum(1 for f in p["frases"] if f.get("panel")),
            "con_imagen": sum(1 for f in p["frases"] if con_imagen(f)),
            "cobertura": cobertura(p) if p["fuentes"] else []}


def storyboard(mid: str) -> Path:
    """Una hoja con cada frase y su imagen (o su panel), por bloques, para aprobar el montaje en segundos antes
    de la previa. Marca en rojo las frases cuyo plano no da para lo que dura la frase."""
    from PIL import Image, ImageDraw, ImageFont
    p = cargar(mid)
    letra = lambda tam, negrita=False: ImageFont.truetype("arialbd.ttf" if negrita else "arial.ttf", tam)  # noqa: E731
    cortos = {c["n"]: c for c in cobertura(p)}
    col, ancho_c, alto_img, alto_txt = 4, 420, 236, 118
    filas = -(-len(p["frases"]) // col)
    lienzo = Image.new("RGB", (col * ancho_c + 20, filas * (alto_img + alto_txt + 14) + 90), (10, 12, 14))
    d = ImageDraw.Draw(lienzo)
    d.text((20, 22), f"Storyboard · {p['titulo']}", fill=(240, 240, 240), font=letra(34, True))
    r = resumen(p)
    d.text((20, 62), f"{r['frases']} frases · {r['capitulos']} bloques · {r['paneles']} paneles · ≈{int(r['duracion'] // 60)}:"
                     f"{int(r['duracion'] % 60):02d} min", fill=(150, 160, 160), font=letra(18))
    acento = (57, 255, 136)
    for k, f in enumerate(p["frases"]):
        x, y = 10 + (k % col) * ancho_c, 90 + (k // col) * (alto_img + alto_txt + 14)
        caja = (x + 6, y, x + ancho_c - 6, y + alto_img + alto_txt)
        d.rounded_rectangle(caja, radius=14, fill=(22, 26, 28), outline=(255, 70, 70) if f["n"] in cortos else (45, 52, 56), width=2)
        img_box = (x + 12, y + 6, x + ancho_c - 12, y + alto_img)
        if f.get("panel"):
            d.rounded_rectangle(img_box, radius=10, fill=(14, 30, 22), outline=acento, width=2)
            d.text((img_box[0] + 16, img_box[1] + 14), f["panel"].get("titulo", "Panel"), fill=(255, 255, 255), font=letra(22, True))
            for j, item in enumerate(f["panel"].get("items", [])[:5]):
                d.text((img_box[0] + 22, img_box[1] + 52 + j * 30), f"● {item}"[:44], fill=acento, font=letra(17))
        elif f.get("imagen"):
            im = Image.open(carpeta_imagenes(mid) / f["imagen"]["archivo"]).convert("RGB")
            im.thumbnail((img_box[2] - img_box[0], img_box[3] - img_box[1]))
            lienzo.paste(im, (img_box[0] + (img_box[2] - img_box[0] - im.width) // 2, img_box[1] + (img_box[3] - img_box[1] - im.height) // 2))
            d.text((img_box[0] + 8, img_box[1] + 6), "IMAGEN", fill=(46, 230, 255), font=letra(14, True))
        elif f.get("clip"):
            nums = [f["clip"]["plano"], *f["clip"].get("mas", [])]
            w = (img_box[2] - img_box[0]) // len(nums)
            for j, n in enumerate(nums):
                mini = extractor.CACHE / f"{f['clip']['fuente']}_planos" / f"{n:03d}.jpg"
                if mini.exists():
                    im = Image.open(mini).convert("RGB")
                    im = im.resize((w - 2, int((w - 2) * im.height / im.width)))
                    alto_m = img_box[3] - img_box[1]
                    if im.height > alto_m:
                        im = im.crop((0, (im.height - alto_m) // 2, im.width, (im.height - alto_m) // 2 + alto_m))
                    lienzo.paste(im, (img_box[0] + j * w, img_box[1] + (alto_m - im.height) // 2))
        else:
            d.rounded_rectangle(img_box, radius=10, fill=(40, 20, 20))
            d.text((img_box[0] + 20, img_box[1] + 100), "SIN IMAGEN", fill=(255, 90, 90), font=letra(24, True))
        if f.get("rotulo"):
            d.rounded_rectangle((img_box[0] + 8, img_box[3] - 36, img_box[0] + 18 + 11 * len(f["rotulo"]), img_box[3] - 8),
                                radius=12, fill=(0, 0, 0), outline=(46, 230, 255), width=2)
            d.text((img_box[0] + 16, img_box[3] - 33), f["rotulo"], fill=(46, 230, 255), font=letra(17, True))
        nuevo = k == 0 or f["bloque"] != p["frases"][k - 1]["bloque"]
        cab = f"{f['n']}" + (f" · BLOQUE {f['bloque'] + 1}" if nuevo else "")
        d.text((x + 16, y + alto_img + 6), cab, fill=acento if nuevo else (150, 160, 160), font=letra(16, True))
        palabras, lineas, linea = f["texto"].split(), [], ""
        for w_ in palabras:
            if len(linea) + len(w_) > 44:
                lineas.append(linea)
                linea = w_
            else:
                linea = f"{linea} {w_}".strip()
        lineas.append(linea)
        for j, l in enumerate(lineas[:4]):
            d.text((x + 16, y + alto_img + 28 + j * 21), l, fill=(225, 228, 228), font=letra(16))
        if f["n"] in cortos:
            c = cortos[f["n"]]
            d.text((x + ancho_c - 210, y + alto_img + 6), f"{'SE CONGELA' if c['congela'] else 'se estira'}: {c['hay']}/{c['necesita']} s",
                   fill=(255, 90, 90), font=letra(14, True))
    destino = carpeta(mid) / "storyboard.jpg"
    lienzo.save(destino, quality=88)
    return destino


# --- 1 · Guion ----------------------------------------------------------------------------------------------------
def partir(guion: str) -> list[dict[str, Any]]:
    """Bloques = párrafos; frases = oraciones (las de menos de 6 palabras se juntan con la siguiente).
    Cada frase es lo que se ve con un mismo plano."""
    frases = []
    bloques = [b.strip() for b in re.split(r"\n\s*\n", (guion or "").replace("\r\n", "\n")) if b.strip()]
    for nb, bloque in enumerate(bloques):
        oraciones = [t for o in re.split(r"(?<=[.!?…])\s+", " ".join(bloque.split())) if o.strip() for t in _trocear(o.strip())]
        pendiente = ""
        for o in oraciones:
            pendiente = f"{pendiente} {o}".strip()
            if len(pendiente.split()) >= 6:
                frases.append({"bloque": nb, "texto": pendiente})
                pendiente = ""
        if pendiente:
            if frases and frases[-1]["bloque"] == nb:
                frases[-1]["texto"] += " " + pendiente
            else:
                frases.append({"bloque": nb, "texto": pendiente})
    if len(bloques) == 1 and len(frases) > 8:
        for k, f in enumerate(frases):
            f["bloque"] = k // 4
    for k, f in enumerate(frases):
        f["n"] = k + 1
    return frases


def _trocear(oracion: str) -> list[str]:
    """Una oración larga se parte en la coma (o dos puntos) más cercana a la mitad, si deja dos partes de 5+ palabras."""
    palabras = oracion.split()
    if len(palabras) <= PALABRAS_MAX:
        return [oracion]
    sitios = [k + 1 for k, w in enumerate(palabras) if w.endswith((",", ":", ";")) and 5 <= k + 1 <= len(palabras) - 5]
    if not sitios:
        return [oracion]
    k = min(sitios, key=lambda x: abs(x - len(palabras) / 2))
    return _trocear(" ".join(palabras[:k])) + _trocear(" ".join(palabras[k:]))


def _pausa(frases: list[dict[str, Any]], k: int) -> float:
    """El silencio que va después de la frase k: ninguno si se partió en una coma (la voz ya respira ahí)."""
    if k + 1 >= len(frases) or not frases[k]["texto"].rstrip().endswith((".", "!", "?", "…")):
        return 0.0
    return PAUSA_BLOQUE if frases[k + 1]["bloque"] != frases[k]["bloque"] else PAUSA_FRASE


def revisar(guion: str) -> list[str]:
    """Avisos gratis antes de montar: frases que suenan a IA y datos de GTA 6 que deberían ir como avance."""
    from .guion import frases_prohibidas
    avisos = [f"Suena a IA: «{x}»" for x in frases_prohibidas(guion)]
    if re.search(r"GTA\s*(6|VI)", guion, re.I) and not re.search(r"(seg[uú]n|avance|tr[aá]iler|rumor|filtraci)", guion, re.I):
        avisos.append("Habla de GTA 6 sin decir de dónde sale el dato (tráiler, avances): todavía no se puede jugar.")
    return avisos


def crear(titulo: str, guion: str, canal: str = "", sin_guion: bool = False) -> str:
    """`sin_guion`: el vídeo nace vacío porque Studio está escribiendo su guion (desde una idea del día)."""
    frases = partir(guion)
    if not frases and not sin_guion:
        raise ValueError("Pega el guion (lo que dirá la voz).")
    base = re.sub(r"[^a-z0-9]+", "-", titulo.lower())[:40].strip("-") or "video"
    mid = f"{time.strftime('%Y%m%d-%H%M%S')}-{base}"
    with _lock:
        while (raiz() / mid).exists():
            mid += "-b"
        c = canales.obtener(canal) if canal else canales.activo()
        guardar({"id": mid, "titulo": titulo.strip()[:120] or "Vídeo sin título", "canal": c["id"],
                 "creado": time.strftime("%Y-%m-%d %H:%M"), "guion": guion.strip(), "frases": frases,
                 "avisos": revisar(guion), "fuentes": [], "voz_nombre": c.get("voz_nombre") or "Sadaltager",
                 "previa": "", "final": None, "short": None, "textos": None, "miniatura": "",
                 "trabajo": {"ocupado": False, "fase": "", "progreso": 0, "error": ""}})
    return mid


def desde_biblioteca(item_id: str) -> str:
    """Un guion de la Biblioteca (los de Agron) → un vídeo nuevo con su título, descripción y hashtags."""
    from . import biblioteca
    cid = canales.activo()["id"]
    item = next((x for x in biblioteca.leer(cid) if x["id"] == item_id), None)
    if not item:
        raise ValueError("Ese guion ya no está en la biblioteca.")
    mid = crear(item.get("titulo") or item["guion"][:60], item["guion"], cid)
    modificar(mid, lambda p: p.update(textos_autor={"titulo": item.get("titulo", ""), "descripcion": item.get("descripcion", ""),
                                                    "hashtags": item.get("hashtags", [])}, biblioteca=item_id))
    biblioteca.marcar(cid, item_id, mid)
    return mid


def desde_idea(n: int) -> str:
    """Una idea del día → vídeo nuevo; Studio investiga (fuentes del canal + web) y escribe el guion de ~5 min con la
    metodología del estudio. El vídeo se abre ya y el guion aparece en el paso 1 al terminar."""
    from . import fuentes as fuentes_web
    from . import guion as guionista
    from . import ideas, investigacion
    cid = canales.activo()["id"]
    lista = ideas.diarias(cid).get("ideas") or []
    if not 0 <= n < len(lista):
        raise ValueError("Esa idea ya no está.")
    idea = lista[n]
    mid = crear(idea["idea"][:90], "", cid, sin_guion=True)

    def fase():
        _avisar(mid, "Investigando el tema", 10)
        dossier = investigacion.investigar(idea["idea"], produccion=mid)
        propias = canales.obtener(cid).get("fuentes") or []
        if propias:
            _avisar(mid, "Leyendo tus fuentes de confianza", 35)
            try:
                extra = fuentes_web.investigar(idea["idea"], propias, produccion=mid)
                if extra["texto"]:
                    dossier["dossier"] = f"DE TUS FUENTES DE CONFIANZA:\n{extra['texto']}\n\n" + dossier.get("dossier", "")
            except Exception as e:  # noqa: BLE001 - sin sus fuentes el guion sale igual
                logger.warning("Fuentes del canal: %s", e)
        _avisar(mid, "Escribiendo el guion", 60)
        escrito = guionista.escribir(idea["idea"], dossier.get("dossier", ""), {"largo": 300}, produccion=mid,
                                     referencias=idea.get("texto", ""), identidad=guionista.identidad_del_canal(canales.obtener(cid)))
        cambiar_guion(mid, escrito["largo"]["guion"])
        modificar(mid, lambda p: p.update(titulo=escrito.get("titulo_provisional") or p["titulo"]))
    _en_fondo(mid, "Guion", fase)
    return mid


PROVEEDORES_VOZ = ("gemini", "fal")


def opciones_voz() -> dict[str, Any]:
    """Las voces que el panel ofrece: las de Google (gratis) y, si hay clave de fal, las de ElevenLabs (de pago)."""
    return {"gemini": {"nombre": "Google · gratis", "voces": config.VOCES_GEMINI, "disponible": bool(config.GEMINI_API_KEY)},
            "fal": {"nombre": "ElevenLabs por fal · de pago", "voces": voz.VOCES_FAL, "disponible": bool(config.FAL_KEY) and not config.SIN_PAGO,
                    "por_mil": voz.FAL_TTS_POR_MIL}}


def coste_voz(p: dict[str, Any]) -> float:
    """Lo que costará la voz de este guion con la voz elegida (0 si es gratis)."""
    return voz.coste_voz([f["texto"] for f in p["frases"]], p.get("voz_proveedor", "gemini"))


def elegir_voz(mid: str, proveedor: str, nombre: str) -> None:
    if proveedor not in PROVEEDORES_VOZ:
        raise ValueError("Voz desconocida.")
    voces = config.VOCES_GEMINI if proveedor == "gemini" else voz.VOCES_FAL
    if nombre not in voces:
        raise ValueError(f"La voz «{nombre}» no existe.")
    modificar(mid, lambda p: p.update(voz_proveedor=proveedor, voz_nombre=nombre, final=None, short=None))


def conexiones() -> list[dict[str, Any]]:
    """Qué APIs están conectadas (sin enseñar nunca las claves), para qué sirven y si cuestan."""
    from . import youtube
    return [
        {"api": "Google (Gemini)", "conectada": bool(config.GEMINI_API_KEY), "pago": False, "uso": "Voz gratis, investigación y textos de reserva"},
        {"api": "DeepSeek", "conectada": bool(config.DEEPSEEK_API_KEY), "pago": True, "uso": "Guiones, textos para publicar (céntimos por vídeo)"},
        {"api": "YouTube", "conectada": youtube.disponible(), "pago": False, "uso": "Estadísticas, tendencias e ideas del día (cupo diario gratis)"},
        {"api": "fal (ElevenLabs)", "conectada": bool(config.FAL_KEY) and not config.SIN_PAGO, "pago": True, "uso": "Voz de pago, plan B (≈0,10 $ cada 1.000 letras)"},
        {"api": "ElevenLabs directo", "conectada": bool(config.ELEVENLABS_API_KEY), "pago": True, "uso": "Voz con tu cuenta de ElevenLabs"},
        {"api": "Xiaomi MiMo", "conectada": bool(config.XIAOMIMIMO_API_KEY), "pago": False, "uso": "Voz: no se usa, en español suena mal"},
        {"api": "Descargador (yt-dlp)", "conectada": True, "pago": False, "uso": "Material: tráilers y gameplay"},
    ]


def cambiar_guion(mid: str, guion: str) -> None:
    """Un guion nuevo conserva los planos de las frases que no cambiaron."""
    nuevas = partir(guion)

    def cambio(p):
        viejas = {f["texto"]: f for f in p["frases"]}
        for f in nuevas:
            v = viejas.get(f["texto"])
            if v:
                f.update({k: v[k] for k in ("clip", "rotulo", "panel") if v.get(k)})
        p.update(guion=guion.strip(), frases=nuevas, avisos=revisar(guion), previa="", final=None, short=None)
    modificar(mid, cambio)


# --- 2 · Material -------------------------------------------------------------------------------------------------
def _fid(url: str, desde: float | None, hasta: float | None) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", url)
    base = m.group(1) if m else re.sub(r"[^\w-]+", "_", url)[-40:]
    return f"{base}_{int(desde)}-{int(hasta)}" if desde is not None and hasta is not None else base


def preparar_fuente(url: str, desde: float | None = None, hasta: float | None = None, nombre: str = "",
                    avisar: Callable[[str, int], None] = lambda *_: None) -> dict[str, Any]:
    """Una fuente en el banco de clips: su versión en baja (para ver), sus planos y una miniatura por plano.
    Si ya estaba, no se vuelve a bajar nada."""
    fid = _fid(url, desde, hasta)
    meta_ruta = extractor.CACHE / f"{fid}.banco.json"
    if meta_ruta.exists():
        return json.loads(meta_ruta.read_text(encoding="utf-8"))
    avisar("Bajando en baja calidad para ver sus planos", 10)
    import yt_dlp
    with yt_dlp.YoutubeDL(extractor.opciones_ytdlp(skip_download=True)) as y:
        info = y.extract_info(url, download=False)
    ini = float(desde or 0)
    fin = float(hasta) if hasta is not None else float(info.get("duration") or 0)
    if fin - ini > 45 * 60:
        raise ValueError("Es muy largo: indica el tramo que te interesa (desde y hasta, como mucho 45 min), "
                         "por ejemplo el capítulo de la misión.")
    baja = extractor.descargar_tramo(info["webpage_url"], ini, fin, alto=360, nombre=f"{fid}_360p")
    avisar("Buscando los cambios de plano", 60)
    planos = extractor.planos(baja)
    if len(planos) < max(3, (fin - ini) / 30):   # gameplay sin cortes: tramos fijos de 6 s
        tot = medios.duracion(baja)
        planos = [(round(a, 2), round(min(a + 6, tot), 2)) for a in [i * 6.0 for i in range(int(tot // 6))]]
    miniaturas = extractor.CACHE / f"{fid}_planos"
    miniaturas.mkdir(exist_ok=True)
    for k, (a, b) in enumerate(planos):
        medios.ffmpeg("-ss", f"{(a + b) / 2:.2f}", "-i", str(baja), "-frames:v", "1", "-vf", "scale=320:180",
                      str(miniaturas / f"{k + 1:03d}.jpg"))
        if k % 10 == 0:
            avisar(f"Miniaturas de los planos: {k + 1} de {len(planos)}", 60 + int(35 * k / len(planos)))
    meta = {"id": fid, "url": info["webpage_url"], "titulo": info.get("title", ""), "nombre": nombre or info.get("title", "")[:60],
            "canal": info.get("channel") or info.get("uploader", ""), "desde": ini, "hasta": fin, "baja": baja.name,
            "planos": [{"n": k + 1, "ini": a, "fin": b} for k, (a, b) in enumerate(planos)],
            "fecha": time.strftime("%Y-%m-%d")}
    _marcar_pobres(meta)
    meta_ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def _marcar_pobres(meta: dict[str, Any]) -> dict[str, Any]:
    """Marca los planos que no sirven como imagen: negros, fundidos, lisos (rótulos de clasificación, logos sobre
    negro) o de menos de 0,8 s. La propuesta automática se los salta; el autor aún puede elegirlos a mano."""
    from PIL import Image, ImageStat
    carpeta_m = extractor.CACHE / f"{meta['id']}_planos"
    for pl in meta["planos"]:
        if "pobre" in pl:
            continue
        try:
            st = ImageStat.Stat(Image.open(carpeta_m / f"{pl['n']:03d}.jpg").convert("L"))
            media, desv = st.mean[0], st.stddev[0]
        except OSError:   # sin miniatura no se puede juzgar la imagen: solo cuenta la duración
            media, desv = 255.0, 255.0
        pl["pobre"] = media < 28 or desv < 22 or (pl["fin"] - pl["ini"]) < 0.8
    if meta["planos"] and meta["hasta"] - meta["desde"] < 600:   # tráilers: clasificación de edad al principio, logo al final
        if meta["planos"][0]["fin"] - meta["planos"][0]["ini"] < 4:
            meta["planos"][0]["pobre"] = True
        meta["planos"][-1]["pobre"] = True
    return meta


def banco() -> list[dict[str, Any]]:
    """Todas las fuentes ya preparadas (para reutilizarlas en otros vídeos)."""
    salida = []
    for f in sorted(extractor.CACHE.glob("*.banco.json")) if extractor.CACHE.exists() else []:
        try:
            salida.append(json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return salida


def fuente(fid: str) -> dict[str, Any]:
    ruta = extractor.CACHE / f"{fid}.banco.json"
    if not re.fullmatch(r"[\w.-]{3,120}", fid or "") or not ruta.exists():
        raise ValueError("Esa fuente no está en el banco.")
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    if any("pobre" not in pl for pl in meta["planos"]):   # fuentes preparadas antes de esta marca
        _marcar_pobres(meta)
        ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def anadir_fuente(mid: str, url: str, desde: float | None = None, hasta: float | None = None, nombre: str = "") -> None:
    def fase():
        meta = preparar_fuente(url, desde, hasta, nombre, avisar=lambda f, n: _avisar(mid, f, n))
        modificar(mid, lambda p: p["fuentes"].append(meta["id"]) if meta["id"] not in p["fuentes"] else None)
    _en_fondo(mid, "Material", fase)


def usar_fuente(mid: str, fid: str) -> None:
    """Una fuente del banco en este vídeo (sin bajar nada)."""
    fuente(fid)
    modificar(mid, lambda p: p["fuentes"].append(fid) if fid not in p["fuentes"] else None)


# --- 3 · Montaje --------------------------------------------------------------------------------------------------
def asignar(mid: str, n: int, fid: str = "", plano: int = 0, rotulo: str | None = None,
            panel: dict[str, Any] | None = None, mas: list[int] | None = None) -> None:
    """El plano de una frase (o un panel de texto en su lugar) y su rótulo. `mas`: otros planos de la misma fuente
    elegidos a propósito para la misma frase (se corta a ellos en una pausa de la voz)."""
    mas = [int(x) for x in (mas or [])][:3]
    if fid:
        meta = fuente(fid)
        if not all(1 <= x <= len(meta["planos"]) for x in [plano, *mas]):
            raise ValueError("Ese plano no existe.")

    def cambio(p):
        f = next((x for x in p["frases"] if x["n"] == n), None)
        if not f:
            raise ValueError("Esa frase no existe.")
        if fid:
            f["clip"] = {"fuente": fid, "plano": plano, **({"mas": mas} if mas else {})}
            f.pop("panel", None)
            f.pop("imagen", None)
        if panel is not None:
            items = [str(i).strip()[:80] for i in panel.get("items", []) if str(i).strip()][:5]
            # iconos elegidos a mano (si no, la animación los deduce del texto de cada punto)
            iconos = [str(x) if str(x) in animacion.ICONOS_NOMBRES else "" for x in panel.get("iconos", [])][:len(items)]
            f["panel"] = {"titulo": str(panel.get("titulo", ""))[:60], "items": items, "nota": str(panel.get("nota", ""))[:90],
                          **({"iconos": iconos} if any(iconos) else {})} if items or panel.get("titulo") else None
            if not f["panel"]:
                f.pop("panel")
            else:
                f.pop("imagen", None)
        if rotulo is not None:
            f["rotulo"] = rotulo.strip()[:40]
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)


def carpeta_imagenes(mid: str) -> Path:
    c = carpeta(mid) / "imagenes"
    c.mkdir(exist_ok=True)
    return c


def poner_imagen(mid: str, n: int, url: str = "", datos_b64: str = "", credito: str = "") -> dict[str, Any]:
    """Una imagen (arte oficial, captura, foto de un producto) para una frase: desde un enlace o un archivo tuyo.
    Se guarda en el vídeo como JPG; en el montaje lleva movimiento lento y, si no es apaisada, va como tarjeta."""
    import base64
    import io

    from PIL import Image
    if datos_b64:
        crudo = base64.b64decode(datos_b64.split(",", 1)[-1])
    elif url.startswith(("http://", "https://")):
        import requests
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Studio4"})
        r.raise_for_status()
        crudo = r.content
    else:
        raise ValueError("Pega el enlace de una imagen (https://…) o elige un archivo.")
    try:
        im = Image.open(io.BytesIO(crudo))
        im.load()
    except OSError as e:
        raise ValueError("Eso no es una imagen que se pueda abrir (prueba con JPG, PNG o WEBP).") from e
    if min(im.size) < 360:
        raise ValueError(f"La imagen es muy pequeña ({im.width}x{im.height}): a pantalla completa se vería mal.")
    im = im.convert("RGB")
    im.thumbnail((3840, 3840))
    nombre = f"{n:03d}_{hashlib.sha1(crudo).hexdigest()[:8]}.jpg"
    im.save(carpeta_imagenes(mid) / nombre, quality=92)
    imagen = {"archivo": nombre, "ancho": im.width, "alto": im.height, "url": url if not datos_b64 else "",
              "credito": credito.strip()[:160]}

    def cambio(p):
        f = next((x for x in p["frases"] if x["n"] == n), None)
        if not f:
            raise ValueError("Esa frase no existe.")
        f["imagen"] = imagen
        f.pop("clip", None)
        f.pop("panel", None)
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)
    return imagen


def quitar_imagen(mid: str, n: int) -> None:
    def cambio(p):
        for f in p["frases"]:
            if f["n"] == n:
                f.pop("imagen", None)
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)


def buscar_imagenes(mid: str, consulta: str) -> list[dict[str, Any]]:
    """Imágenes reales en las fuentes de confianza del canal (las mismas del panel clásico)."""
    from . import galeria
    if len(consulta.strip()) < 3:
        raise ValueError("Escribe qué imagen buscas (por ejemplo: «Rockstar Toronto logo»).")
    p = cargar(mid)
    return [{"url": galeria.grande(i["url"]), "miniatura": i["url"], "descripcion": i.get("descripcion", ""),
             "pagina": i.get("pagina", "")} for i in galeria.buscar(p["canal"], consulta, n=24, produccion=mid, sitio_entero=True)]


def _segmento_imagen(imagen: Path, d: float, ancho: int, alto: int, destino: Path) -> None:
    """Una imagen durante `d` s con un acercamiento lento. Apaisada: a pantalla completa. Si no (una caja, un
    cartel vertical, un producto): como tarjeta sobre la misma imagen desenfocada, sin bandas negras."""
    from PIL import Image
    with Image.open(imagen) as im:
        w, h = im.size
    cuadros = max(1, round(d * config.FPS))
    acerca = (f"scale={ancho * 2}:{alto * 2}:flags=bicubic,zoompan=z='1+{ACERCA * 1.5}*on/{cuadros}'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={ancho}x{alto}:fps={config.FPS},setsar=1")
    if 1.55 <= w / h <= 1.95:
        filtro = ["-vf", f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},{acerca}"]
    else:
        filtro = ["-filter_complex",
                  f"[0:v]split=2[a][b];[a]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
                  f"gblur=sigma={max(8, int(40 * ancho / 1920))},eq=brightness=-0.22[fondo];"
                  f"[b]scale={int(ancho * 0.84)}:{int(alto * 0.84)}:force_original_aspect_ratio=decrease[frente];"
                  f"[fondo][frente]overlay=(W-w)/2:(H-h)/2,{acerca}[v]", "-map", "[v]"]
    medios.ffmpeg("-loop", "1", "-framerate", str(config.FPS), "-t", f"{d:.3f}", "-i", str(imagen), *filtro,
                  "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(destino))


def proponer(mid: str) -> int:
    """A cada frase sin plano, el siguiente plano sin usar de las fuentes del vídeo (por turnos entre fuentes).
    Es un punto de partida: el autor cambia los que no encajen. Devuelve cuántas propuso."""
    p = cargar(mid)
    if not p["fuentes"]:
        raise ValueError("Primero añade material (paso 2).")
    usados = {(f["clip"]["fuente"], f["clip"]["plano"]) for f in p["frases"] if f.get("clip")}
    colas = {fid: [pl["n"] for pl in fuente(fid)["planos"] if (fid, pl["n"]) not in usados and not pl.get("pobre")]
             for fid in p["fuentes"]}
    hechas, turno = 0, 0

    def cambio(q):
        nonlocal hechas, turno
        for f in q["frases"]:
            if con_imagen(f):
                continue
            for _ in range(len(q["fuentes"])):
                fid = q["fuentes"][turno % len(q["fuentes"])]
                turno += 1
                if colas[fid]:
                    f["clip"] = {"fuente": fid, "plano": colas[fid].pop(0)}
                    hechas += 1
                    break
        q.update(previa="", final=None, short=None)
    modificar(mid, cambio)
    return hechas


# --- Trabajo en segundo plano ---------------------------------------------------------------------------------------
def _avisar(mid: str, fase: str, progreso: int) -> None:
    modificar(mid, lambda p: p["trabajo"].update(fase=fase, progreso=max(0, min(100, progreso))))


def _despierto(si: bool) -> None:
    """Mientras se monta, Windows no suspende el PC por inactividad: un montaje de media hora se cortaba de noche
    (FFmpeg «tardaba» las horas que el PC estuvo dormido). Solo pide no dormir; no impide cerrar la tapa ni apagar."""
    if os.name != "nt":
        return
    import ctypes
    continuo, sistema = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(continuo | (sistema if si else 0))


def _en_fondo(mid: str, nombre: str, fn: Callable[[], None]) -> None:
    with _lock:
        p = cargar(mid)
        if p["trabajo"].get("ocupado"):
            raise RuntimeError(f"Este vídeo ya está trabajando: {p['trabajo'].get('fase')}")
        p["trabajo"] = {"ocupado": True, "nombre": nombre, "fase": nombre, "progreso": 0, "error": ""}
        guardar(p)

    def correr():
        _despierto(True)
        try:
            if nombre in PESADOS:
                if not _turno.acquire(blocking=False):
                    _avisar(mid, "En cola: espera a que termine el otro vídeo", 0)
                    _turno.acquire()
                try:
                    fn()
                finally:
                    _turno.release()
            else:
                fn()
        except Exception as e:  # noqa: BLE001 - el motivo se ve en el panel
            logger.exception("%s falló", nombre)
            modificar(mid, lambda p: p["trabajo"].update(ocupado=False, error=f"{nombre}: {str(e)[:300]}"))
        else:
            modificar(mid, lambda p: p["trabajo"].update(ocupado=False, error="", progreso=100, fase=f"{nombre}: listo"))
        finally:
            _despierto(False)
    threading.Thread(target=correr, name=f"montaje-{nombre}", daemon=True).start()


def _tamano(ruta: Path) -> int:
    return sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file()) if ruta.exists() else 0


def espacio() -> dict[str, Any]:
    """Cuánto ocupa cada cosa y cuánto se puede liberar sin perder nada que se vea en el panel."""
    temporales = sum(_tamano(d) for pat in ("*/render_previa", "*/render_miniatura", "*/cache", "*/cache_previa") for d in raiz().glob(pat)) \
        + sum(f.stat().st_size for d in raiz().glob("*/render") for f in d.glob("*") if f.is_file() and f.name not in ("cuerpo.mp4", "subs.ass"))
    return {"montajes": _tamano(raiz()), "banco": _tamano(extractor.CACHE), "papelera": _tamano(config.PRODUCCIONES / "_papelera"),
            "liberable": temporales}


def liberar() -> int:
    """Borra solo lo temporal de los renders (trozos ya unidos). El vídeo final, la previa, el Short, la miniatura,
    la voz y lo necesario para rehacer el Short se quedan. Devuelve los bytes liberados."""
    antes = espacio()["liberable"]
    # (la caché de trozos solo acelera volver a montar: se rehace sola si hace falta)
    for pat in ("*/render_previa", "*/render_miniatura", "*/cache", "*/cache_previa"):
        for d in raiz().glob(pat):
            shutil.rmtree(d, ignore_errors=True)
    for d in raiz().glob("*/render"):
        for f in d.glob("*"):
            if f.is_file() and f.name not in ("cuerpo.mp4", "subs.ass"):
                f.unlink(missing_ok=True)
    return antes


def recuperar_colgados() -> None:
    """Al arrancar el servidor ningún montaje puede seguir «trabajando»: se libera para poder repetirlo."""
    for f in raiz().glob("*/proyecto.json") if raiz().exists() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if p["trabajo"].get("ocupado"):
                p["trabajo"].update(ocupado=False, error=f"{p['trabajo'].get('nombre', 'Trabajo')}: se cortó al cerrar Studio 4; vuelve a pulsarlo.")
                guardar(p)
        except (ValueError, KeyError, OSError):
            continue


# --- 4 y 5 · Render -------------------------------------------------------------------------------------------------
def _tiempos_estimados(p: dict[str, Any]) -> list[tuple[float, float]]:
    t, salida = ENTRADA, []
    for k, f in enumerate(p["frases"]):
        d = max(1.6, len(f["texto"].split()) / PALABRAS_POR_SEGUNDO)
        salida.append((t, t + d))
        t += d + _pausa(p["frases"], k)
    return salida


def _silencio_cerca(muestras: array.array, hz: int, t: float, margen: float = 0.45) -> float:
    """El punto más callado (ventanas de 30 ms) a menos de `margen` s de t: ahí se puede cortar la voz sin partir
    una palabra. Los tiempos de cada frase son aproximados; el silencio real entre oraciones es este."""
    paso, ventana = int(hz * 0.01), int(hz * 0.03)
    mejor, mejor_t = None, t
    for i in range(max(0, int((t - margen) * hz)), min(len(muestras) - ventana, int((t + margen) * hz)), paso):
        energia = sum(x * x for x in muestras[i:i + ventana:4])
        if mejor is None or energia < mejor or (energia == mejor and abs(i / hz - t) < abs(mejor_t - t)):
            mejor, mejor_t = energia, (i + ventana / 2) / hz
    return mejor_t


def _respirar(wav: Path, tiempos: list[tuple[float, float]], palabras: list[dict[str, Any]],
              frases: list[dict[str, Any]], destino: Path) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    """La voz con silencios entre oraciones y entre bloques: se corta en el silencio real entre dos frases (nunca a
    mitad de palabra), con un fundido de 10 ms para que no chasquee, y se mete la pausa.
    Devuelve los tiempos y las palabras movidos a su sitio nuevo."""
    hz = 16000
    crudo = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", str(hz), "-f", "s16le", "-"],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=120).stdout
    muestras = array.array("h")
    muestras.frombytes(crudo[:len(crudo) // 2 * 2])
    cortes = [_silencio_cerca(muestras, hz, (tiempos[k][1] + tiempos[k + 1][0]) / 2 - ENTRADA) + ENTRADA
              for k in range(len(tiempos) - 1)]   # en la línea (con ENTRADA)
    pausas = [_pausa(frases, k) for k in range(len(tiempos))]
    bordes = [0.0, *[c - ENTRADA for c in cortes], medios.duracion(wav) + 1]
    filtros = [f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,"
               f"areverse,afade=t=in:d=0.01,areverse,apad=pad_dur={pausas[k]:.3f}[p{k}]"
               for k, (a, b) in enumerate(zip(bordes, bordes[1:]))]
    filtros.append("".join(f"[p{k}]" for k in range(len(tiempos))) + f"concat=n={len(tiempos)}:v=0:a=1[a]")
    medios.ffmpeg("-i", str(wav), "-filter_complex", ";".join(filtros), "-map", "[a]", str(destino))
    desplaza = [sum(pausas[:k]) for k in range(len(tiempos))]

    def tramo(w: dict[str, Any]) -> int:
        # por el centro de la palabra: sus tiempos vienen algo adelantados y una palabra que empieza justo en el corte
        # («Según») se quedaba del lado anterior y salía en pantalla en plena pausa, antes de oírse
        centro = (w["ini"] + w["fin"]) / 2
        return sum(1 for c in cortes if centro >= c)
    return ([(a + desplaza[k], b + desplaza[k]) for k, (a, b) in enumerate(tiempos)],
            [{**w, "ini": w["ini"] + desplaza[tramo(w)], "fin": w["fin"] + desplaza[tramo(w)]} for w in palabras])


def _segmento(fuente_video: Path, ini: float, fin: float, d: float, ancho: int, alto: int, destino: Path) -> None:
    """Un plano a pantalla completa durante `d` s: si el plano es más corto, va algo más lento (hasta ×1,35; más se
    nota a tirones) y después se queda en su último fotograma. Nunca se cuela el plano siguiente del vídeo de origen."""
    largo = max(0.3, min(fin, medios.duracion(fuente_video)) - ini)   # lo que de verdad hay en el archivo
    lento = min(LENTO_MAX, max(1.0, d / largo))
    # más lento sin repetir cuadros (eso se ve a tirones): se inventan los cuadros intermedios siguiendo el movimiento
    interpola = (f",minterpolate=fps={config.FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" if lento > 1.01 else "")
    # y un acercamiento lento (+6 % en todo el plano): aunque el juego esté quieto (un menú, el minijuego), la imagen
    # nunca se ve parada. Se hace al doble de tamaño para que el movimiento sea fino, sin temblores.
    cuadros = max(1, round(d * config.FPS))
    acerca = (f",scale={ancho * 2}:{alto * 2}:flags=bicubic,zoompan=z='1+{ACERCA}*on/{cuadros}'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={ancho}x{alto}:fps={config.FPS}")
    vf = (f"setpts={lento:.4f}*PTS,scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto}"
          f"{interpola},fps={config.FPS},tpad=stop_mode=clone:stop_duration={d + 1:.3f},trim=duration={d:.3f}{acerca},setsar=1")
    medios.ffmpeg("-ss", f"{ini:.3f}", "-t", f"{largo:.3f}", "-i", str(fuente_video), "-an", "-vf", vf,
                  "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(destino))


def _segmentos(fuente_video: Path, ini: float, fin: float, partes: list[tuple[float, Path]], ancho: int, alto: int) -> None:
    """Un plano montado de una sola vez (misma velocidad de principio a fin) y partido en trozos seguidos: así el
    arranque que va dentro de una tarjeta, el plano a pantalla completa y la cola de la tarjeta siguiente son el
    mismo movimiento, sin saltos de velocidad ni de sentido en las uniones."""
    if len(partes) == 1:
        _segmento(fuente_video, ini, fin, partes[0][0], ancho, alto, partes[0][1])
        return
    entero = partes[0][1].with_name(partes[0][1].stem + "_entero.mp4")
    _segmento(fuente_video, ini, fin, sum(d for d, _ in partes), ancho, alto, entero)
    desde = 0.0
    for d, destino in partes:
        medios.ffmpeg("-i", str(entero), "-an", "-vf", f"trim=start={desde:.4f}:duration={d:.4f},setpts=PTS-STARTPTS",
                      "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(destino))
        desde += d
    entero.unlink(missing_ok=True)


LENTO_MAX = 1.35   # un plano corto se estira como mucho esto
ACERCA = 0.06      # cuánto se acerca la cámara a lo largo de un plano (nunca una imagen quieta)
RESERVA = 0.8      # segundos del mismo plano que van dentro de la tarjeta de un panel o de un cambio de bloque
CACHE_VERSION = 1  # súbelo si cambia cómo se monta un trozo: la caché vieja deja de valer
ANIMACION_VERSION = hashlib.sha1(animacion.PLANTILLA.encode("utf-8")).hexdigest()[:12]   # cambia la página → se redibuja


def _cadena(meta: dict[str, Any], clip: dict[str, Any], d: float, pausas: list[float] | None = None
            ) -> list[tuple[dict[str, Any], float]]:
    """Los planos de una frase: el elegido y los de `clip["mas"]`, nunca uno que nadie eligió (el plano siguiente de
    un tráiler suele ser otra escena y el salto se nota). Cada corte cae en la pausa entre palabras más cercana
    (`pausas`, segundos desde el inicio de la frase), así nunca se corta a mitad de palabra."""
    planos = [meta["planos"][x - 1] for x in [clip["plano"], *clip.get("mas", [])] if 1 <= x <= len(meta["planos"])]
    if len(planos) == 1:
        return [(planos[0], d)]
    largos = [pl["fin"] - pl["ini"] for pl in planos]
    bordes, acum = [0.0], 0.0
    for largo in largos[:-1]:   # reparto según lo que dura cada plano
        acum += largo
        ideal = d * acum / sum(largos)
        cerca = [c for c in (pausas or []) if abs(c - ideal) <= 0.8 and bordes[-1] + 0.8 <= c <= d - 0.8]
        marca = min(cerca, key=lambda c: abs(c - ideal)) if cerca else ideal
        if bordes[-1] + 0.8 <= marca <= d - 0.8:
            bordes.append(marca)
    bordes.append(d)
    return [(pl, b - a) for pl, (a, b) in zip(planos, zip(bordes, bordes[1:]))]


def _rotulo_png(texto: str, color: str, destino: Path, escala: float) -> Path:
    """El rótulo neón (pastilla) como PNG transparente, para superponerlo sin tocar la calidad del plano."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    fuente_ttf = ImageFont.truetype("arialbd.ttf", int(46 * escala))
    caja = fuente_ttf.getbbox(texto)
    w, h = caja[2] - caja[0] + int(80 * escala), caja[3] - caja[1] + int(44 * escala)
    img = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    brillo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(brillo).rounded_rectangle([30, 30, 30 + w, 30 + h], radius=h // 2, outline=color, width=int(10 * escala))
    img.alpha_composite(brillo.filter(ImageFilter.GaussianBlur(10 * escala)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([30, 30, 30 + w, 30 + h], radius=h // 2, fill=(5, 5, 8, 215), outline=color, width=int(4 * escala))
    d.text((30 + w / 2, 30 + h / 2), texto, fill=color, font=fuente_ttf, anchor="mm")
    img.save(destino)
    return destino


def _render(mid: str, final: bool, avisar: Callable[[str, int], None]) -> Path:
    p = cargar(mid)
    base = carpeta(mid)
    ancho, alto = (ANCHO, ALTO) if final else (ANCHO_PREVIA, ALTO_PREVIA)
    escala = ancho / ANCHO
    trabajo = base / ("render" if final else "render_previa")
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir(parents=True)
    # Los trozos ya montados se guardan por su huella (todo lo que los define): si una frase no cambia, su trozo
    # no se vuelve a montar. Cambiar un plano rehace ese plano y los paneles que lo tocan, no el vídeo entero.
    cache = base / ("cache" if final else "cache_previa")
    cache.mkdir(exist_ok=True)
    en_uso: set[Path] = set()

    def huella(*partes: Any) -> str:
        datos = [CACHE_VERSION, final, ancho, alto, ACERCA, LENTO_MAX, RESERVA, TRANSICION, config.FPS, *partes]
        return hashlib.sha1(json.dumps(datos, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    if final:
        segmentos = [f["texto"] for f in p["frases"]]
        wav = base / "voz.wav"
        proveedor = p.get("voz_proveedor", "gemini")
        firma_voz = hashlib.sha1(json.dumps([segmentos, proveedor, p["voz_nombre"], ESTILO_VOZ]).encode("utf-8")).hexdigest()
        previa_voz = p.get("voz") or {}
        if previa_voz.get("firma") == firma_voz and wav.exists():   # mismo texto y misma voz: no se regraba
            avisar("Voz ya grabada (mismo guion)", 10)
            tiempos, palabras = [tuple(x) for x in previa_voz["tiempos"]], previa_voz["palabras"]
        else:
            avisar("Grabando la voz", 5)
            t = voz.locutar(segmentos, wav, proveedor, produccion=mid, voz_nombre=p["voz_nombre"], estilo_voz=ESTILO_VOZ,
                            voice_id=p["voz_nombre"] if proveedor == "fal" else None)
            tiempos = [(e["ini"] + ENTRADA, e["fin"] + ENTRADA) for e in t["escenas"]]
            palabras = [{**w, "ini": w["ini"] + ENTRADA, "fin": w["fin"] + ENTRADA} for w in t["palabras"]]
            modificar(mid, lambda q: q.update(voz={"archivo": "voz.wav", "duracion": t["duracion"], "palabras": palabras,
                                                   "tiempos": tiempos, "firma": firma_voz}))
        avisar("Pausas de la voz", 12)
        voz_montaje = trabajo / "voz_pausas.wav"
        tiempos, palabras = _respirar(wav, tiempos, palabras, p["frases"], voz_montaje)
        modificar(mid, lambda q: q["voz"].update(pausas={"tiempos": tiempos, "palabras": palabras}))
    else:
        tiempos = _tiempos_estimados(p)
    # cada frase dura desde su inicio hasta el inicio de la siguiente (sin huecos); la primera empieza en 0
    tramos = [(0.0 if k == 0 else a, tiempos[k + 1][0] if k + 1 < len(tiempos) else b + 1.2) for k, (a, b) in enumerate(tiempos)]
    piezas: list[Path] = []
    # paneles y cambios de bloque: se dibujan al final, cuando ya existen sus vecinos (sus puentes con el vídeo)
    animadas: dict[Path, tuple[dict[str, Any], float]] = {}
    # las tarjetas de los puentes van en movimiento: lo que sigue del plano anterior (cola) y el arranque del siguiente
    colas: dict[Path, Path] = {}                        # pieza → lo que sigue de su plano (dentro de la tarjeta)
    arranques: dict[Path, Path] = {}                    # animación → los primeros segundos del plano que viene
    eventos: list[tuple[float, str, float]] = [(0.1, "impacto", 0.9)]   # (segundo, efecto, volumen)
    usados: list[dict[str, Any]] = []
    fuentes_ok = {fid: fuente(fid) for fid in p["fuentes"]}
    colores = {fid: list(animacion.COLORES.values())[k % len(animacion.COLORES)] for k, fid in enumerate(p["fuentes"])}
    cursor = 0.0
    for k, (f, (a, b)) in enumerate(zip(p["frases"], tramos)):
        avisar(f"Plano {k + 1} de {len(p['frases'])}", 15 + int(60 * k / len(p["frases"])))
        d = b - a
        nuevo_bloque = k > 0 and f["bloque"] != p["frases"][k - 1]["bloque"]
        seg = trabajo / f"s{k:03d}.mp4"
        if f.get("panel"):   # un panel de cristal sobre el propio vídeo desenfocado, dibujado en el navegador
            animadas[seg] = ({"ini": 0, "fin": d, "panel": f["panel"]}, d)
            eventos += [(cursor + 0.05, "whoosh", 0.45), (cursor + 0.3, "impacto", 0.7), (cursor + d - 0.62, "whoosh", 0.4)]
            if nuevo_bloque:   # la pausa larga antes del panel no queda vacía
                eventos.append((cursor - 0.9, "subida", 0.5))
            eventos += [(cursor + 0.8 + j * 0.42, "pop", 0.9) for j in range(len(f["panel"].get("items", [])))]
        elif f.get("imagen"):   # una imagen (arte, captura, producto) con movimiento lento
            seg = cache / f"{huella('imagen', f['imagen']['archivo'], round(d, 3))}.mp4"
            if not seg.exists():
                _segmento_imagen(carpeta_imagenes(mid) / f["imagen"]["archivo"], d, ancho, alto, seg)
            en_uso.add(seg)
            usados.append({"frase": f["n"], "fuente": f["imagen"].get("credito") or "Imagen", "canal": "",
                           "url": f["imagen"].get("url", ""), "imagen": True})
            eventos.append((cursor + 0.05, "whoosh", 0.25))
        else:
            clip = f["clip"]
            meta = fuentes_ok[clip["fuente"]]
            con_transicion = nuevo_bloque and d > TRANSICION + 0.8
            inicio_plano = a + (TRANSICION if con_transicion else 0)
            pausas = [(x["fin"] + y["ini"]) / 2 - inicio_plano for x, y in zip(palabras, palabras[1:])
                      if inicio_plano < x["fin"] < b] if final else []
            cadena = _cadena(meta, clip, d - (TRANSICION if con_transicion else 0), pausas)
            for c, _dur in cadena:
                usados.append({"frase": f["n"], "fuente": meta["titulo"], "canal": meta.get("canal", ""), "url": meta["url"],
                               "desde": round(meta["desde"] + c["ini"], 2), "hasta": round(meta["desde"] + c["fin"], 2)})

            def de(c: dict[str, Any]) -> tuple[Path, float]:
                """El vídeo de donde sale el plano y su segundo 0. En el final, solo los segundos de ese plano en alta
                (cada plano por separado: los elegidos pueden estar en cualquier orden del vídeo de origen)."""
                if final and meta.get("alta"):   # escenas propias (Google Flow): ya están en alta en el banco
                    return extractor.CACHE / meta["alta"], 0.0
                if final:
                    return extractor.descargar_tramo(meta["url"], meta["desde"] + c["ini"], meta["desde"] + c["fin"], alto=1080), c["ini"]
                return extractor.CACHE / meta["baja"], 0.0
            if con_transicion:
                # cambio de bloque: el vídeo se encoge a tarjeta, entra la del bloque nuevo con su rótulo y crece
                tr = trabajo / f"t{k:03d}.mp4"
                animadas[tr] = ({"ini": 0, "fin": TRANSICION, "etiqueta": f.get("rotulo", ""),
                                 "color": colores[clip["fuente"]]}, TRANSICION)
                piezas.append(tr)
                # subida antes, cruce de lado a lado al entrar la tarjeta, impacto al llegar y whoosh al crecer
                eventos += [(cursor - 1.5, "subida", 0.6), (cursor, "cruce", 0.8), (cursor + 0.5, "impacto", 1.0),
                            (cursor + TRANSICION - 0.62, "whoosh", 0.45)]
                cursor += TRANSICION
                d -= TRANSICION
            # Con una animación delante, su tarjeta final ya reproduce el arranque de este plano; con una detrás, la
            # tarjeta que se encoge sigue este mismo plano. Las tres partes salen de una sola pasada: mismo movimiento.
            previo = piezas[-1] if piezas else None
            visible = (animadas[previo][1] - (0.9 if "panel" in animadas[previo][0] else 0.25)) if previo in animadas else 0.0
            sig = p["frases"][k + 1] if k + 1 < len(p["frases"]) else None
            antes_de_animacion = bool(sig) and bool(sig.get("panel") or (
                sig["bloque"] != f["bloque"] and tramos[k + 1][1] - tramos[k + 1][0] > TRANSICION + 0.8))
            cola_frase = None
            trozos = []
            t_frase = 0.0
            for j, (c, dur) in enumerate(cadena):   # un trozo por plano elegido
                origen, base_t = de(c)
                ini_l, fin_l = c["ini"] - base_t, min(c["fin"] - base_t, medios.duracion(origen))
                # las tarjetas solo se llevan imagen que sobre (estirando como mucho LENTO_MAX): si no, el plano se
                # quedaría corto a pantalla completa y se congelaría
                sobra = max(0.0, (fin_l - ini_l) * LENTO_MAX - dur)
                d_arranque = min(RESERVA, visible, sobra) if j == 0 and min(RESERVA, visible, sobra) >= 0.3 else 0.0
                sobra -= d_arranque
                d_cola = (min(RESERVA, sobra) if j == len(cadena) - 1 and antes_de_animacion and min(RESERVA, sobra) >= 0.3
                          else 0.0)
                clave = huella("trozo", meta["url"] or meta["id"], meta.get("importada", ""), meta["desde"], c["ini"], c["fin"], round(dur, 3),
                               round(d_arranque, 3), round(d_cola, 3), round(fin_l - ini_l, 2))
                trozo = cache / f"{clave}.mp4"
                partes = []
                if d_arranque:
                    arranques[previo] = cache / f"{clave}_a.mp4"
                    partes.append((d_arranque, arranques[previo]))
                partes.append((dur, trozo))
                if d_cola:
                    cola_frase = cache / f"{clave}_c.mp4"
                    partes.append((d_cola, cola_frase))
                if not all(x.exists() for _, x in partes):
                    _segmentos(origen, ini_l, fin_l, partes, ancho, alto)
                en_uso.update(x for _, x in partes)
                trozos.append(trozo)
                if j:
                    eventos.append((cursor + t_frase, "whoosh", 0.18))   # un roce suave en cada corte
                t_frase += dur
            seg = cache / f"{huella('frase', [x.name for x in trozos], f.get('rotulo', ''), colores[clip['fuente']], round(d, 3))}.mp4"
            if len(trozos) == 1 and not f.get("rotulo"):
                seg = trozos[0]   # un solo plano sin rótulo: el trozo ya es la frase
            elif not seg.exists():
                if len(trozos) == 1:
                    unido = trozos[0]
                else:
                    unido = trabajo / f"s{k:03d}.mp4"
                    lista_f = trabajo / f"s{k:03d}.txt"
                    lista_f.write_text("".join(f"file '{x.as_posix()}'\n" for x in trozos), encoding="utf-8")
                    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista_f), "-c", "copy", str(unido))
                if f.get("rotulo"):   # rótulo neón abajo a la izquierda los primeros segundos
                    png = _rotulo_png(f["rotulo"], colores[clip["fuente"]], trabajo / f"r{k:03d}.png", escala)
                    medios.ffmpeg("-i", str(unido), "-loop", "1", "-i", str(png), "-filter_complex",
                                  f"[1:v]format=rgba,fade=t=in:st=0.2:d=0.3:alpha=1,fade=t=out:st={min(3.2, d - 0.4):.2f}:d=0.3:alpha=1[r];"
                                  f"[0:v][r]overlay=x={int(70 * escala)}:y=H-h-{int(150 * escala)}:shortest=1",
                                  "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(seg))
                else:
                    shutil.copyfile(unido, seg)
            en_uso.add(seg)
            if f.get("rotulo"):
                eventos += [(cursor + 0.15, "impacto", 0.55), (cursor + 0.45, "pop", 0.9)]
            if cola_frase:
                colas[seg] = cola_frase
        piezas.append(seg)
        cursor += d
    for k, pieza in enumerate(piezas):   # las animaciones, con el último fotograma del anterior y el primero del siguiente
        if pieza not in animadas:
            continue
        avisar("Paneles y transiciones", 76)
        escena, dur = animadas.pop(pieza)
        siguiente = arranques.get(pieza) or (piezas[k + 1] if k + 1 < len(piezas) and piezas[k + 1] not in animadas else None)
        clave = huella("animacion", ANIMACION_VERSION, escena, round(dur, 3), piezas[k - 1].name if k > 0 else "",
                       colas[piezas[k - 1]].name if k > 0 and piezas[k - 1] in colas else "",
                       siguiente.name if siguiente else "")
        hecha = cache / f"{clave}.mp4"
        piezas[k] = hecha
        en_uso.add(hecha)
        if hecha.exists():
            continue
        pieza = trabajo / pieza.name   # los fotogramas de sus puentes, al lado
        if k > 0:
            escena["entra"] = str(_fotograma(piezas[k - 1], trabajo / f"{pieza.stem}_entra.png", ultimo=True))
            if piezas[k - 1] in colas:   # lo que sigue del plano anterior, al mismo ritmo
                escena["entra_video"] = str(colas[piezas[k - 1]])
        if k + 1 < len(piezas) and piezas[k + 1] not in animadas:
            if pieza in arranques:   # el arranque del plano siguiente: acaba justo donde sigue a pantalla completa
                escena["sale"] = str(_fotograma(arranques[pieza], trabajo / f"{pieza.stem}_sale.png", ultimo=False))
                escena["sale_video"] = str(arranques[pieza])
            else:
                escena["sale"] = str(_fotograma(piezas[k + 1], trabajo / f"{pieza.stem}_sale.png", ultimo=False))
        animacion.renderizar([escena], dur, hecha, ancho, alto)
    for viejo in cache.iterdir():   # lo que ya no usa este vídeo (planos cambiados) se borra
        if viejo not in en_uso:
            viejo.unlink(missing_ok=True)
    pista = musica.elegir(p)   # la canción de la Biblioteca de audio de YouTube (o ninguna: cama suave o nada)
    cancion = musica.ruta(pista["archivo"]) if pista else None
    if final:   # «Fuentes y créditos»: cada fragmento con su segundo exacto, por si hay una reclamación
        _creditos(base, p, usados, pista)
        if pista:
            musica.apuntar_uso(pista["archivo"], mid)
    avisar("Uniendo los planos", 78)
    lista = trabajo / "lista.txt"
    lista.write_text("".join(f"file '{x.as_posix()}'\n" for x in piezas), encoding="utf-8")
    cuerpo = trabajo / "cuerpo.mp4"
    medios.ffmpeg("-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(cuerpo))
    total = medios.duracion(cuerpo)
    avisar("Diseño de sonido", 82)
    fx = sonido.pista(eventos, total, trabajo / "fx.wav")
    if cancion:
        lecho = cancion
    elif p.get("musica") == musica.NADA:   # sin fondo (por ejemplo, si la música se pone después en YouTube)
        lecho = sonido.silencio(total, trabajo / "silencio.wav")
    else:
        lecho = sonido.cama(total, trabajo / "cama.wav")   # el fondo suave propio: nunca silencio
    logo = logo_de(p["canal"])
    destino = base / ("final_16x9.mp4" if final else "previa.mp4")
    # En dos pasos: primero el sonido a un archivo y luego la imagen con ese sonido. Todo en una sola orden, FFmpeg se
    # quedaba atascado a mitad del vídeo (esperando audio y vídeo a la vez) y no terminaba nunca.
    avisar("Subtítulos, voz y efectos" if final else "Efectos y fondo", 88)
    # una canción se iguala a las demás y se baja; la cama suave sostiene las pausas de la voz
    vol_lecho = config.VOLUMEN_MUSICA * musica.ganancia(pista) if cancion else 1.4
    # el vídeo no se corta en seco: los últimos 0,8 s funden a negro y el sonido se apaga con él
    cierre_a = f"afade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8"
    cierre_v = f"fade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8"
    entradas_a = ["-i", str(fx), *(["-stream_loop", "-1"] if cancion else []), "-i", str(lecho)]
    lecho_f = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={vol_lecho},"
               f"afade=t=out:st={max(0, total - 2):.3f}:d=2")
    if final:
        entradas_a += ["-i", str(voz_montaje)]
        voz_f = f"[2:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(ENTRADA * 1000)}:all=1,apad"
        if cancion:   # una canción sí baja suave cuando habla la voz (sidechain lento); la cama suave no lo necesita
            audio = (f"{voz_f},asplit=2[voz][llave];[0:a]volume=0.6[fx];{lecho_f}[l0];"
                     "[l0][llave]sidechaincompress=threshold=0.03:ratio=2.5:attack=60:release=700[lecho];")
        else:
            audio = f"{voz_f}[voz];[0:a]volume=0.6[fx];{lecho_f}[lecho];"
        audio += f"[voz][fx][lecho]amix=inputs=3:duration=longest:normalize=0,{sonido.LIMITE},apad,atrim=0:{total:.3f}[a]"
    else:   # la previa ya suena: efectos y lecho (sin voz), con el mismo volumen final
        audio = f"[0:a]volume=0.6[fx];{lecho_f}[l];[fx][l]amix=inputs=2:normalize=0,{sonido.LIMITE},apad,atrim=0:{total:.3f}[a]"
    premezcla, mezcla = trabajo / "premezcla.wav", trabajo / "mezcla.wav"
    # apad en la voz: el lecho sigue sonando después de la última palabra; -t corta justo en la duración del vídeo
    medios.ffmpeg(*entradas_a, "-filter_complex", audio, "-map", "[a]", "-t", f"{total:.3f}", "-ar", "48000", str(premezcla))
    sonido.masterizar(premezcla, mezcla, cierre_a)

    entradas = ["-i", str(cuerpo), "-i", str(mezcla)]
    filtros, mezcla_v = [], "[0:v]"
    if logo:   # el logo del canal, discreto arriba a la derecha en todo el vídeo
        entradas += ["-loop", "1", "-i", str(logo)]
        lado = int(130 * escala)
        filtros.append(f"[2:v]scale={lado}:{lado},format=rgba,colorchannelmixer=aa=0.55[logo];"
                       f"{mezcla_v}[logo]overlay=W-w-{int(40 * escala)}:{int(36 * escala)}:shortest=1[v1]")
        mezcla_v = "[v1]"
    if final:
        ass = subtitulos.construir(palabras, trabajo / "subs.ass", ancho, alto, {"posicion": "abajo"})
        filtros.append(f"{mezcla_v}ass={ass.name},{cierre_v}[v]")
    else:
        filtros.append(f"{mezcla_v}{cierre_v}[v]")
    medios.ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "1:a", "-t", f"{total:.3f}",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "17" if final else "23", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(destino), cwd=trabajo)
    return destino


def logo_de(canal: str) -> Path | None:
    """El logo del canal recortado en círculo con fondo transparente (el PNG original trae un cuadrado negro).
    Se prepara una vez y se reutiliza."""
    from PIL import Image, ImageDraw
    base = config.PRODUCCIONES / "_canales" / canal
    original, redondo = base / "logo.png", base / "logo_redondo.png"
    if not original.exists():
        return None
    if not redondo.exists() or redondo.stat().st_mtime < original.stat().st_mtime:
        im = Image.open(original).convert("RGBA")
        lado = min(im.size)
        im = im.crop(((im.width - lado) // 2, (im.height - lado) // 2, (im.width + lado) // 2, (im.height + lado) // 2))
        mascara = Image.new("L", (lado * 4, lado * 4), 0)
        ImageDraw.Draw(mascara).ellipse([8, 8, lado * 4 - 8, lado * 4 - 8], fill=255)   # borde suave: se dibuja a 4x
        im.putalpha(mascara.resize((lado, lado), Image.LANCZOS))
        im.save(redondo)
    return redondo


def _creditos(base: Path, p: dict[str, Any], usados: list[dict[str, Any]], pista: dict[str, Any] | None = None) -> None:
    reloj = lambda s: f"{int(s) // 3600}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}"  # noqa: E731
    lineas = [f"Fuentes y créditos · {p['titulo']}", "Fragmentos cortos, sin su audio, con comentario y edición propios.", ""]
    lineas += [f"Frase {u['frase']}: imagen · {u['fuente']}" + (f" · {u['url']}" if u["url"] else "") if u.get("imagen")
               else f"Frase {u['frase']}: {u['fuente']} ({u['canal']}) · {reloj(u['desde'])}–{reloj(u['hasta'])} · {u['url']}"
               for u in usados]
    credito_musica = musica.credito(pista) if pista else ""
    if credito_musica:
        lineas += ["", credito_musica]
    (base / "Fuentes y créditos.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    modificar(p["id"], lambda q: q.update(creditos=usados, musica_credito=credito_musica))


def _fotograma(video: Path, destino: Path, ultimo: bool) -> Path:
    """El primer o el último fotograma de un plano ya montado, sin comprimir (PNG): la tarjeta que sale de él o
    vuelve a él tiene exactamente la misma imagen y la misma calidad, y el paso no se nota."""
    if ultimo:   # se escriben los últimos cuadros encima del mismo archivo: queda el último
        medios.ffmpeg("-sseof", "-0.3", "-i", str(video), "-update", "1", "-c:v", "png", str(destino))
    else:
        medios.ffmpeg("-i", str(video), "-frames:v", "1", "-c:v", "png", str(destino))
    return destino


def elegir_musica(mid: str, modo: str) -> None:
    """La música del vídeo: «auto» (por el ánimo del guion), «cama» (el fondo suave), «nada» o una pista concreta."""
    if modo not in (musica.AUTO, musica.CAMA, musica.NADA) and not musica.ruta(modo):
        raise ValueError("Esa pista no está en tu carpeta de música.")
    modificar(mid, lambda p: p.update(musica=modo))


def _musica(p: dict[str, Any]) -> Path | None:
    """El archivo de la canción del vídeo (None si va con la cama suave o sin fondo)."""
    pista = musica.elegir(p)
    return musica.ruta(pista["archivo"]) if pista else None


def _revisar(mid: str, video: Path, final: bool) -> dict[str, Any]:
    """La revisión de calidad al terminar (congelados, huecos, subtítulos, volumen): se ve en el panel."""
    _avisar(mid, "Revisión de calidad", 98)
    p = cargar(mid)
    v = p.get("voz") or {}
    palabras = (v.get("pausas") or v).get("palabras") if final else None
    r = calidad.revisar(video, palabras, carpeta(mid) / "render" / "voz_pausas.wav" if final else None)
    r["hecha"] = time.strftime("%Y-%m-%d %H:%M")
    modificar(mid, lambda q: q.setdefault("calidad", {}).update({"final" if final else "previa": r}))
    return r


def _hacer_previa(mid: str) -> None:
    destino = _render(mid, False, lambda f, n: _avisar(mid, f, n))
    modificar(mid, lambda p: p.update(previa=destino.name))
    _revisar(mid, destino, final=False)


def previa(mid: str) -> None:
    _en_fondo(mid, "Previa", lambda: _hacer_previa(mid))


def montar_final(mid: str) -> None:
    _en_fondo(mid, "Vídeo final", lambda: _hacer_final(mid))


def _hacer_final(mid: str) -> None:
    destino = _render(mid, True, lambda f, n: _avisar(mid, f, n))
    modificar(mid, lambda p: p.update(final={"archivo": destino.name, "hecho": time.strftime("%Y-%m-%d %H:%M")}))
    from . import linea   # la línea de tiempo por pistas, junto al vídeo (para abrirla en otro editor o revisarla)
    q = cargar(mid)
    (carpeta(mid) / "linea_de_tiempo.json").write_text(
        json.dumps(linea.desde_montaje(q, {fid: fuente(fid) for fid in q["fuentes"]}), ensure_ascii=False, indent=1), encoding="utf-8")
    v = q.get("voz") or {}   # los subtítulos aparte, para subirlos a YouTube
    subtitulos.srt((v.get("pausas") or v).get("palabras") or [], carpeta(mid) / "subtitulos.srt")
    _avisar(mid, "Textos para publicar", 96)
    try:
        hacer_textos(mid)
    except Exception as e:  # noqa: BLE001 - el vídeo ya está; los textos se pueden repetir
        logger.warning("Textos: %s", e)
    _revisar(mid, destino, final=True)


# --- Short vertical sacado del 16:9 ---------------------------------------------------------------------------------
def montar_short(mid: str, desde: float, hasta: float) -> None:
    """Un tramo del vídeo final (≤ 60 s) en vertical: el 16:9 entero en el centro sobre su versión desenfocada,
    con sus subtítulos rehechos para el formato vertical. No se recorta el gameplay."""
    p = cargar(mid)
    if not p.get("final"):
        raise ValueError("Primero monta el vídeo final.")
    if not 5 <= hasta - desde <= 60:
        raise ValueError("Un Short dura entre 5 y 60 segundos.")
    _en_fondo(mid, "Short", lambda: _hacer_short(mid, desde, hasta))


def _hacer_short(mid: str, desde: float, hasta: float) -> None:
    q = cargar(mid)
    base = carpeta(mid)
    trabajo = base / "render_short"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir()
    _avisar(mid, "Encuadrando en vertical", 20)
    # el vídeo final ya lleva subtítulos horizontales: se parte del cuerpo sin subtítulos + la misma mezcla
    palabras = [{**w, "ini": w["ini"] - desde, "fin": w["fin"] - desde}
                for w in (q["voz"].get("pausas") or q["voz"])["palabras"]
                if desde <= w["ini"] < hasta]
    ass = subtitulos.construir(palabras, trabajo / "subs.ass", 1080, 1920, {"posicion": "abajo"})
    medios.ffmpeg("-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / "render" / "cuerpo.mp4"),
                  "-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / q["final"]["archivo"]),
                  "-filter_complex",
                  "[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  "gblur=sigma=30,eq=brightness=-0.12[fondo];[b]scale=1080:-2[centro];"
                  f"[fondo][centro]overlay=0:(H-h)/2-120,ass={ass.name}[v]",
                  "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                  str(base / "short_9x16.mp4"), cwd=trabajo)
    modificar(mid, lambda r: r.update(short={"archivo": "short_9x16.mp4", "desde": desde, "hasta": hasta}))


def tramo_short(p: dict[str, Any], maximo: float = 58.0) -> tuple[float, float]:
    """El Short automático: desde el principio (el gancho) hasta el final de la frase más cercana a `maximo` s."""
    tiempos = (p.get("voz") or {}).get("pausas", {}).get("tiempos") or _tiempos_estimados(p)
    fin = max((b for _a, b in tiempos if b + 0.4 <= maximo), default=min(maximo, tiempos[-1][1] if tiempos else maximo))
    return 0.0, round(max(5.0, fin + 0.4), 2)


def automatico(mid: str, pago_ok: bool = False) -> None:
    """Con todas las frases con imagen: storyboard → vídeo final (voz, subtítulos, música, textos, .srt y
    revisión) → Short → miniatura, sin pararse. Una voz de pago solo con «pago_ok» (el sí explícito del autor)."""
    p = cargar(mid)
    if not p["frases"] or any(not con_imagen(f) for f in p["frases"]):
        raise ValueError("Antes de hacerlo todo, cada frase necesita su imagen o su panel (paso 3).")
    if coste_voz(p) > 0 and not pago_ok:
        raise ValueError(f"La voz {p['voz_nombre']} es de pago (≈{coste_voz(p):.2f} $): confírmalo o elige una gratis.")

    def fase():
        _avisar(mid, "Storyboard", 2)
        storyboard(mid)
        _hacer_final(mid)
        q = cargar(mid)
        desde, hasta = tramo_short(q)
        _avisar(mid, "Short vertical", 99)
        _hacer_short(mid, desde, hasta)
        con_imagen = [f["clip"] for f in q["frases"] if f.get("clip")]
        if con_imagen:
            _avisar(mid, "Miniatura", 99)
            texto = ((q.get("textos") or {}).get("texto_miniatura") or q["titulo"])[:40]
            fotos = [con_imagen[0], con_imagen[len(con_imagen) // 2]] if len(con_imagen) > 1 else con_imagen
            try:
                miniatura(mid, texto, fotos)
            except Exception as e:  # noqa: BLE001 - el vídeo y el Short ya están; la miniatura se rehace a mano
                logger.warning("Miniatura automática: %s", e)
    _en_fondo(mid, "Automático", fase)


# --- Textos para publicar y miniatura -------------------------------------------------------------------------------
SISTEMA_TEXTOS = """Eres editor de un canal de YouTube de videojuegos en español latino. Con el guion de un vídeo
escribe lo necesario para publicarlo. Reglas: nada de clickbait engañoso; lo no confirmado se presenta como avance
o rumor; nunca menciones a otros youtubers ni canales. Devuelve JSON:
{"titulos": ["3 títulos de máx. 70 caracteres, distintos"], "descripcion": "3-5 frases, primera línea con gancho",
 "hashtags": ["5 a 8, con #"], "texto_miniatura": "2 a 4 palabras en mayúsculas para la miniatura"}"""


def hacer_textos(mid: str) -> dict[str, Any]:
    from . import deepseek
    p = cargar(mid)
    d = deepseek.generar_json(SISTEMA_TEXTOS, f"Título de trabajo: {p['titulo']}\n\nGUION:\n{p['guion']}",
                              temperatura=0.6, detalle="textos para publicar", produccion=mid)
    capitulos = []
    if p.get("voz"):   # un capítulo por bloque, en el minuto en que empieza (la primera línea siempre 0:00)
        vistos = set()
        for f, (a, _b) in zip(p["frases"], p["voz"]["tiempos"]):
            if f["bloque"] not in vistos:
                vistos.add(f["bloque"])
                seg = 0 if not capitulos else int(a)
                capitulos.append(f"{seg // 60}:{seg % 60:02d} {' '.join(f['texto'].split()[:6]).rstrip('.,:;')}")
    creditos = sorted({fuente(fid)["titulo"] for fid in p["fuentes"] if fid})
    textos = {"titulos": [str(t)[:100] for t in d.get("titulos", [])][:3], "descripcion": str(d.get("descripcion", "")),
              "hashtags": [h for h in d.get("hashtags", []) if str(h).startswith("#")][:8],
              "texto_miniatura": str(d.get("texto_miniatura", ""))[:40], "capitulos": capitulos,
              "creditos": "\n".join(x for x in (
                  "Escenas generadas con IA (Google Flow · Veo), con guion, voz y edición propios." if p.get("ia")
                  else "Imágenes de los juegos con comentario y edición propios.", p.get("musica_credito", "")) if x)}
    modificar(mid, lambda q: q.update(textos=textos, fuentes_titulos=creditos))
    return textos


def miniatura(mid: str, texto: str, fotos: list[dict[str, Any]]) -> Path:
    """Miniatura 1280×720: una o dos imágenes de los planos (pantalla dividida) y el texto grande, con el logo."""
    from playwright.sync_api import sync_playwright
    p = cargar(mid)
    base = carpeta(mid)
    trabajo = base / "render_miniatura"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir()
    imgs = []
    for k, ft in enumerate(fotos[:2]):
        meta = fuente(ft["fuente"])
        pl = meta["planos"][int(ft["plano"]) - 1]
        if meta.get("alta"):   # escenas propias (Google Flow), ya en alta en el banco
            origen, medio = extractor.CACHE / meta["alta"], pl["ini"] + (pl["fin"] - pl["ini"]) / 2
        else:
            origen = extractor.descargar_tramo(meta["url"], meta["desde"] + pl["ini"], meta["desde"] + pl["fin"], alto=1080)
            medio = (pl["fin"] - pl["ini"]) / 2
        medios.ffmpeg("-ss", f"{medio:.2f}", "-i", str(origen), "-frames:v", "1", str(trabajo / f"m{k}.jpg"))
        imgs.append(f"m{k}.jpg")
    logo = logo_de(p["canal"])
    if logo:
        shutil.copy(logo, trabajo / "logo.png")
    shutil.copy(animacion.FUENTES / "geist-latin-wght-normal.woff2", trabajo / "geist.woff2")
    paneles = "".join(f'<div class="f" style="background-image:url({i})"></div>' for i in imgs)
    html = f"""<!doctype html><meta charset="utf-8"><style>
@font-face {{ font-family: S4; src: url(geist.woff2); font-weight: 100 900; }}
body {{ margin: 0; width: 1280px; height: 720px; overflow: hidden; background: #050508; font-family: S4, sans-serif; }}
.fotos {{ position: absolute; inset: 0; display: flex; gap: 10px; }}
.f {{ flex: 1; background-size: cover; background-position: center; filter: saturate(1.25) contrast(1.08); }}
.velo {{ position: absolute; inset: 0; background: linear-gradient(to top, rgba(0,0,0,.85), rgba(0,0,0,.05) 55%); }}
h1 {{ position: absolute; left: 0; right: 0; bottom: 36px; margin: 0; text-align: center; color: #fff; font-size: 118px;
  font-weight: 900; line-height: .95; letter-spacing: -.02em; text-shadow: 0 0 30px #ff3ea5, 0 8px 0 #000; padding: 0 40px; }}
.logo {{ position: absolute; top: 22px; right: 22px; width: 120px; opacity: .9; }}
</style><div class="fotos">{paneles}</div><div class="velo"></div><h1>{texto}</h1>
{'<img class="logo" src="logo.png">' if logo else ''}"""
    (trabajo / "m.html").write_text(html, encoding="utf-8")
    destino = base / "miniatura.jpg"
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": 1280, "height": 720})
        pag.goto((trabajo / "m.html").as_uri())
        pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
        pag.screenshot(path=str(destino), type="jpeg", quality=92)
        nav.close()
    modificar(mid, lambda q: q.update(miniatura=destino.name))
    return destino
