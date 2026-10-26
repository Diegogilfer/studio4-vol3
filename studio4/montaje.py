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


def _reintentar(fn: Callable[[], Any], veces: int = 20) -> Any:
    """En Windows, leer proyecto.json justo cuando otro hilo lo reemplaza (o reemplazarlo mientras se lee) da
    PermissionError: el panel consulta el vídeo cada 1,5 s mientras un trabajo lo reescribe. Se reintenta un instante."""
    for k in range(veces):
        try:
            return fn()
        except PermissionError:
            if k == veces - 1:
                raise
            time.sleep(0.02 * (k + 1))


def cargar(mid: str) -> dict[str, Any]:
    ruta = carpeta(mid) / "proyecto.json"
    if not ruta.exists():
        raise ValueError("Ese vídeo ya no existe.")
    return _reintentar(lambda: json.loads(ruta.read_text(encoding="utf-8")))


def guardar(p: dict[str, Any]) -> None:
    ruta = carpeta(p["id"]) / "proyecto.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    p["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    _reintentar(lambda: tmp.replace(ruta))


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
    from . import material as materiales
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
        _avisar(mid, "Buscando el material real del tema", 50)   # el guion sale de donde salen las imágenes
        inv = materiales.inventario(idea["idea"], dossier.get("dossier", ""), produccion=mid)
        modificar(mid, lambda p: p.update(material_sugerido=inv))
        if hay := materiales.para_guion(inv):
            dossier["dossier"] = f"{hay}\n\n" + dossier.get("dossier", "")
        from . import escenas
        if indice := escenas.para_guion([{"url": v["url"], "nombre": v["titulo"]} for e in inv for v in e["videos"]]):
            dossier["dossier"] = f"{indice}\n\n" + dossier.get("dossier", "")
        _avisar(mid, "Escribiendo el guion", 60)
        # la duración la marca la idea: «corto» (Shorts, ~60 s o los segundos que diga) o largo (~5 min)
        version, segundos = ("corto", 60) if idea.get("formato") == "corto" else ("largo", 300)
        if version == "corto" and (m := re.search(r"(\d{2,3})\s*segundos", idea["idea"])) and 20 <= int(m.group(1)) <= 180:
            segundos = int(m.group(1))
        escrito = guionista.escribir(idea["idea"], dossier.get("dossier", ""), {version: segundos}, produccion=mid,
                                     referencias=idea.get("texto", ""), identidad=guionista.identidad_del_canal(canales.obtener(cid)))
        cambiar_guion(mid, escrito[version]["guion"])
        modificar(mid, lambda p: p.update(titulo=escrito.get("titulo_provisional") or p["titulo"]))
    _en_fondo(mid, "Guion", fase)
    return mid


PROVEEDORES_VOZ = ("gemini", "fal", "propia")   # «propia»: tu locución subida (voz_propia.wav)
VOZ_PROPIA = "voz_propia.wav"
AUDIO_PERMITIDO = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
VELOCIDADES = (0.9, 1.0, 1.1, 1.2, 1.3)   # velocidad de la voz (sin cambiar el tono)


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
    if proveedor == "propia":
        if not (carpeta(mid) / VOZ_PROPIA).exists():
            raise ValueError("Primero sube tu voz con «Examinar».")
        modificar(mid, lambda p: p.update(voz_proveedor="propia", voz_nombre="Tu voz", final=None, short=None))
        return
    voces = config.VOCES_GEMINI if proveedor == "gemini" else voz.VOCES_FAL
    if nombre not in voces:
        raise ValueError(f"La voz «{nombre}» no existe.")
    modificar(mid, lambda p: p.update(voz_proveedor=proveedor, voz_nombre=nombre, final=None, short=None))


def subir_voz(mid: str, tmp: Path, nombre: str) -> None:
    """Tu locución (grabada por ti) en vez de una voz de IA: se guarda en WAV y queda elegida. Al montar, Whisper la
    escucha en tu PC (gratis) para saber en qué segundo empieza cada frase del guion."""
    try:
        if Path(nombre).suffix.lower() not in AUDIO_PERMITIDO:
            raise ValueError(f"Sube un audio ({', '.join(AUDIO_PERMITIDO)}).")
        cargar(mid)
        medios.ffmpeg("-i", str(tmp), "-vn", "-ac", "1", "-ar", "24000", str(carpeta(mid) / VOZ_PROPIA))
        huella = hashlib.sha1((carpeta(mid) / VOZ_PROPIA).read_bytes()).hexdigest()[:16]
    finally:
        tmp.unlink(missing_ok=True)
    _guardar_en_biblioteca(carpeta(mid) / VOZ_PROPIA, huella, Path(nombre).stem[:60])
    modificar(mid, lambda p: p.update(voz_proveedor="propia", voz_nombre="Tu voz", final=None, short=None,
                                      voz_propia={"archivo": Path(nombre).name[:80], "huella": huella}))


def _biblioteca_voces() -> Path:
    c = config.PRODUCCIONES / "_voces" / "propias"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _guardar_en_biblioteca(wav: Path, huella: str, nombre: str) -> None:
    """Cada voz subida queda guardada para los demás vídeos (la misma voz dos veces es una sola)."""
    c = _biblioteca_voces()
    if not (c / f"{huella}.wav").exists():
        shutil.copyfile(wav, c / f"{huella}.wav")
    indice = c / "voces.json"
    voces = json.loads(indice.read_text(encoding="utf-8")) if indice.exists() else []
    if not any(x["id"] == huella for x in voces):
        voces.append({"id": huella, "nombre": nombre or "Mi voz", "duracion": round(medios.duracion(wav), 1),
                      "fecha": time.strftime("%Y-%m-%d")})
        indice.write_text(json.dumps(voces, ensure_ascii=False, indent=1), encoding="utf-8")


def voces_guardadas() -> list[dict[str, Any]]:
    indice = _biblioteca_voces() / "voces.json"
    voces = json.loads(indice.read_text(encoding="utf-8")) if indice.exists() else []
    return [x for x in voces if (_biblioteca_voces() / f"{x['id']}.wav").exists()]


def archivo_voz_guardada(vid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", vid or "") or not (f := _biblioteca_voces() / f"{vid}.wav").exists():
        raise ValueError("Esa voz guardada no existe.")
    return f


def usar_voz_guardada(mid: str, vid: str) -> None:
    """Una voz de tu biblioteca en este vídeo."""
    origen = archivo_voz_guardada(vid)
    nombre = next((x["nombre"] for x in voces_guardadas() if x["id"] == vid), "Mi voz")
    cargar(mid)
    shutil.copyfile(origen, carpeta(mid) / VOZ_PROPIA)
    modificar(mid, lambda p: p.update(voz_proveedor="propia", voz_nombre="Tu voz", final=None, short=None,
                                      voz_propia={"archivo": nombre, "huella": vid}))


def elegir_velocidad(mid: str, velocidad: float) -> None:
    velocidad = round(float(velocidad), 2)
    if velocidad not in VELOCIDADES:
        raise ValueError(f"Velocidad: {', '.join(str(v) for v in VELOCIDADES)}.")
    modificar(mid, lambda p: p.update(voz_velocidad=velocidad, final=None, short=None))


def _normal(palabra: str) -> str:
    import unicodedata
    p = unicodedata.normalize("NFD", palabra.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in p if unicodedata.category(c) != "Mn"))


def alinear_voz(segmentos: list[str], oidas: list[dict[str, Any]], duracion: float) -> dict[str, Any]:
    """Las palabras del guion con los tiempos de lo que Whisper oyó en tu locución (aunque oiga alguna palabra
    distinta): las que coinciden fijan el tiempo y las demás se reparten entre sus vecinas. Mismo formato que
    voz.locutar, y los subtítulos salen con el texto del guion, sin faltas de oído."""
    import difflib
    guion = [(k, w) for k, seg in enumerate(segmentos) for w in seg.split()]
    if not oidas or not guion:
        raise ValueError("No se oye voz en tu audio.")
    a, b = [_normal(w) for _, w in guion], [_normal(w["palabra"]) for w in oidas]
    fijo: dict[int, tuple[float, float]] = {}
    for blq in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for j in range(blq.size):
            fijo[blq.a + j] = (oidas[blq.b + j]["ini"], oidas[blq.b + j]["fin"])
    if not fijo:   # nada coincide (otro idioma u otro texto): lo oído se reparte en proporción
        n, m = len(guion), len(oidas)
        fijo = {i: (oidas[min(m - 1, i * m // n)]["ini"], oidas[min(m - 1, i * m // n)]["fin"]) for i in range(n)}
    claves = sorted(fijo)
    palabras = []
    for i, (_k, w) in enumerate(guion):
        if i in fijo:
            ini, fin = fijo[i]
        else:   # entre la coincidencia anterior y la siguiente, a partes iguales
            ant = max((c for c in claves if c < i), default=None)
            sig = min((c for c in claves if c > i), default=None)
            t0 = fijo[ant][1] if ant is not None else 0.0
            t1 = fijo[sig][0] if sig is not None else duracion
            ia, ib = (ant if ant is not None else -1), (sig if sig is not None else len(guion))
            paso = max(0.0, t1 - t0) / (ib - ia)
            ini, fin = t0 + paso * (i - ia - 1), t0 + paso * (i - ia)
        palabras.append({"palabra": w, "ini": round(ini, 3), "fin": round(max(fin, ini + 0.05), 3)})
    escenas: list[dict[str, float]] = []
    for k in range(len(segmentos)):
        suyas = [pw for (kk, _w), pw in zip(guion, palabras) if kk == k]
        previo = escenas[-1]["fin"] if escenas else 0.0
        escenas.append({"ini": suyas[0]["ini"], "fin": suyas[-1]["fin"]} if suyas else {"ini": previo, "fin": previo})
    return {"duracion": duracion, "escenas": escenas, "palabras": palabras}


def _locutar_propia(mid: str, segmentos: list[str], wav: Path, trabajo: Path) -> dict[str, Any]:
    from . import entrega
    shutil.copyfile(carpeta(mid) / VOZ_PROPIA, wav)
    oidas, _idioma = entrega._transcribir(wav, trabajo)
    return alinear_voz(segmentos, oidas, medios.duracion(wav))


def subir_musica(tmp: Path, nombre: str, mid: str = "") -> str:
    """Una canción tuya (con «Examinar») a tu carpeta de música; con `mid`, queda elegida para ese vídeo."""
    try:
        nombre = re.sub(r"[^\w .()-]", "", Path(nombre or "").name)[:90].strip()
        if Path(nombre).suffix.lower() not in AUDIO_PERMITIDO:
            raise ValueError(f"Sube un audio ({', '.join(AUDIO_PERMITIDO)}).")
        shutil.copyfile(tmp, musica.carpeta() / nombre)
    finally:
        tmp.unlink(missing_ok=True)
    musica.catalogo()
    if mid:
        elegir_musica(mid, nombre)
    return nombre


def muestra_cama() -> Path:
    """20 s del fondo suave del Studio, para escucharlo antes de elegirlo (se hace una vez)."""
    from . import sonido
    destino = config.PRODUCCIONES / "_voces" / "cama_muestra.wav"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        sonido.cama(20.0, destino)
    return destino


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


# --- Crea con IA: idea → material real → guion → planos (como el creador de CapCut, con nuestro motor) -----------
OPCIONES_IA = {"duracion": 60, "formato": "16:9", "tono": "", "modo": "buscar"}
DURACIONES_IA = (15, 30, 60, 180, 300, 600)


def crear_con_ia(tema: str, opciones: dict[str, Any] | None = None) -> str:
    """Escribes la idea y eliges duración, formato y tono: Studio investiga, busca material real (tráilers y gameplay
    sin comentario), escribe el guion con DeepSeek y pone un plano en cada frase. El vídeo se abre ya; todo llega solo."""
    tema = (tema or "").strip()
    if len(tema) < 4:
        raise ValueError("Escribe la idea del vídeo.")
    o = _opciones_ia(opciones)
    mid = crear(tema[:90], "", canales.activo()["id"], sin_guion=True)
    modificar(mid, lambda p: p.update(ia_opciones=o, formato_principal=o["formato"]))
    _en_fondo(mid, "Guion", lambda: _fase_ia(mid, tema, o, buscar_material=True))
    return mid


def guion_con_ia(mid: str, opciones: dict[str, Any] | None = None) -> None:
    """Un vídeo que ya tiene material (subido o por enlace) pero no guion: la IA lo escribe a partir de ese material."""
    p = cargar(mid)
    o = _opciones_ia(opciones or p.get("ia_opciones"))
    tema = p["titulo"] + ("" if not p["fuentes"] else " · " + ", ".join(fuente(f)["titulo"] for f in p["fuentes"]))
    modificar(mid, lambda q: q.update(ia_opciones=o, formato_principal=o["formato"]))
    _en_fondo(mid, "Guion", lambda: _fase_ia(mid, tema, o, buscar_material=not p["fuentes"]))


def _opciones_ia(opciones: dict[str, Any] | None) -> dict[str, Any]:
    o = {**OPCIONES_IA, **{k: v for k, v in (opciones or {}).items() if v not in (None, "")}}
    o["duracion"] = min(DURACIONES_IA, key=lambda d: abs(d - int(float(o["duracion"]))))
    o["formato"] = "9:16" if str(o["formato"]) == "9:16" else "16:9"
    o["modo"] = "inventar" if o["modo"] == "inventar" else "buscar"
    o["tono"] = str(o["tono"])[:80]
    return o


def _fase_ia(mid: str, tema: str, o: dict[str, Any], buscar_material: bool) -> None:
    from . import escenas, investigacion
    from . import guion as guionista
    from . import material as materiales
    _avisar(mid, "Investigando el tema", 8)
    dossier = investigacion.investigar(tema, produccion=mid).get("dossier", "")
    metas = [fuente(f) for f in cargar(mid)["fuentes"]]
    if metas:
        dossier = "MATERIAL QUE YA TIENE EL VÍDEO (escribe sobre lo que se ve en él): " + "; ".join(
            m["titulo"] for m in metas) + "\n\n" + dossier
    inv: list[dict[str, Any]] = []
    if buscar_material:
        _avisar(mid, "Buscando material real del tema", 30)
        inv = materiales.inventario(tema, dossier, produccion=mid)
        modificar(mid, lambda q: q.update(material_sugerido=inv))
        if hay := materiales.para_guion(inv):
            dossier = f"{hay}\n\n{dossier}"
    if indice := escenas.para_guion(metas + [{"url": v["url"], "nombre": v["titulo"]} for e in inv for v in e["videos"]]):
        dossier = f"{indice}\n\n{dossier}"
    if o["modo"] == "inventar":
        dossier = ("MODO HISTORIA: puedes contar una historia inventada (dilo: «imaginen…»), pero sobre juegos, lugares y "
                   "momentos de los que hay material real arriba.\n\n" + dossier)
    seg = int(o["duracion"])
    version = "corto" if seg <= 60 else "largo"
    _avisar(mid, "Escribiendo el guion", 55)
    cid = cargar(mid)["canal"]
    escrito = guionista.escribir(tema, dossier, {version: seg}, produccion=mid, tono=o.get("tono", ""),
                                 identidad=guionista.identidad_del_canal(canales.obtener(cid)))
    cambiar_guion(mid, escrito[version]["guion"])
    ganchos = escrito[version].get("ganchos") or []
    if buscar_material and inv:
        _avisar(mid, "Bajando el mejor material", 72)
        candidatos = sorted((v for e in inv for v in e["videos"] if 20 <= (v.get("duracion") or 0) <= 15 * 60),
                            key=lambda v: -materiales.puntos(v))[:2]
        for v in candidatos:
            try:
                meta = preparar_fuente(v["url"], nombre=v["titulo"][:60], avisar=lambda f, n: _avisar(mid, f, n))
                modificar(mid, lambda q, i=meta["id"]: q["fuentes"].append(i) if i not in q["fuentes"] else None)
            except Exception as e:  # noqa: BLE001 - un vídeo que no baja no frena el resto
                logger.warning("Material automático (%s): %s", v.get("url"), e)
    if cargar(mid)["fuentes"]:
        _avisar(mid, "Poniendo un plano en cada frase", 92)
        proponer(mid)
    p = cargar(mid)
    modificar(mid, lambda q: q.update(
        titulo=escrito.get("titulo_provisional") or q["titulo"],
        resumen_ia={"tema": tema[:200], "gancho": ganchos[0] if ganchos else "", "duracion": seg, "formato": o["formato"],
                    "tono": o.get("tono") or "el del canal", "modo": o["modo"], "voz": p.get("voz_nombre", ""),
                    "musica": p.get("musica") or "automática", "subtitulos": "karaoke",
                    "material": len(p["fuentes"]), "plataforma": "YouTube Shorts" if seg <= 60 else "YouTube"}))


VIDEO_PERMITIDO = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


def preparar_fuente_local(archivo: Path, nombre: str = "", avisar: Callable[[str, int], None] = lambda *_: None
                          ) -> dict[str, Any]:
    """Un vídeo de tu PC como fuente del banco: en alta (1080p, para el montaje final, sin volver a bajar nada), en
    baja (360p, para ver) y con sus planos. El mismo archivo dos veces es la misma fuente (por su huella)."""
    h = hashlib.sha1()
    with archivo.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    fid = f"local_{h.hexdigest()[:12]}"
    meta_ruta = extractor.CACHE / f"{fid}.banco.json"
    if meta_ruta.exists():
        return json.loads(meta_ruta.read_text(encoding="utf-8"))
    try:
        total = medios.duracion(archivo)
    except Exception as e:  # noqa: BLE001 - lo que no lee FFmpeg no es un vídeo
        raise ValueError("Ese archivo no es un vídeo que se pueda leer (prueba con MP4, MOV, MKV o WEBM).") from e
    if total > 45 * 60:
        raise ValueError("Es muy largo (más de 45 min): recórtalo antes o sube solo la parte que te interesa.")
    extractor.CACHE.mkdir(parents=True, exist_ok=True)
    alta, baja = extractor.CACHE / f"{fid}_1080p.mp4", extractor.CACHE / f"{fid}_360p.mp4"
    avisar("Preparando el vídeo en alta calidad", 10)
    medios.ffmpeg("-i", str(archivo), "-vf", f"scale=-2:'min(1080,ih)',fps={config.FPS},setsar=1", "-c:v", "libx264",
                  "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(alta))
    avisar("Versión ligera para ver los planos", 40)
    medios.ffmpeg("-i", str(alta), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                  "-an", str(baja))
    avisar("Buscando los cambios de plano", 60)
    planos = extractor.planos(baja)
    if len(planos) < max(3, total / 30):   # sin cortes (gameplay grabado): tramos fijos de 6 s
        tot = medios.duracion(baja)
        planos = [(round(a, 2), round(min(a + 6, tot), 2)) for a in [i * 6.0 for i in range(max(1, int(tot // 6)))]]
    miniaturas = extractor.CACHE / f"{fid}_planos"
    miniaturas.mkdir(exist_ok=True)
    for k, (a, b) in enumerate(planos):
        medios.ffmpeg("-ss", f"{(a + b) / 2:.2f}", "-i", str(baja), "-frames:v", "1", "-vf", "scale=320:180",
                      str(miniaturas / f"{k + 1:03d}.jpg"))
    meta = {"id": fid, "url": "", "titulo": nombre or "Vídeo subido", "nombre": (nombre or "Vídeo subido")[:60],
            "canal": "Subido desde tu PC", "desde": 0.0, "hasta": round(total, 3), "baja": baja.name, "alta": alta.name,
            "local": True, "planos": [{"n": k + 1, "ini": a, "fin": b} for k, (a, b) in enumerate(planos)],
            "fecha": time.strftime("%Y-%m-%d")}
    _marcar_pobres(meta)
    meta_ruta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def subir_video(tmp: Path, nombre: str, mid: str = "") -> str:
    """Un vídeo arrastrado o elegido con «Examinar» → material. Con `mid`, se añade a ese vídeo; sin él, vídeo nuevo.
    La preparación (alta, baja, planos) va en segundo plano; el archivo temporal se borra al terminar."""
    nombre = Path(nombre or "video.mp4").name
    if Path(nombre).suffix.lower() not in VIDEO_PERMITIDO:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"Sube un vídeo ({', '.join(VIDEO_PERMITIDO)}).")
    if not mid:
        mid = crear(Path(nombre).stem[:80] or "Vídeo subido", "", canales.activo()["id"], sin_guion=True)

    def fase():
        try:
            meta = preparar_fuente_local(tmp, Path(nombre).stem[:60], avisar=lambda f, n: _avisar(mid, f, n))
        finally:
            tmp.unlink(missing_ok=True)
        modificar(mid, lambda p: p["fuentes"].append(meta["id"]) if meta["id"] not in p["fuentes"] else None)
    _en_fondo(mid, "Material", fase)
    return mid


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


def desde_url(url: str, cid: str = "") -> str:
    """Pega un enlace de vídeo → vídeo nuevo con ese material ya bajándose. Para editar directamente desde él
    (la «magia de la URL»): se abre el vídeo y, cuando el material está, eliges planos o montas los 3 formatos."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Pega un enlace de vídeo (https://…).")
    mid = crear("Vídeo desde URL", "", cid or canales.activo()["id"], sin_guion=True)
    anadir_fuente(mid, url)   # se descarga en segundo plano como material del vídeo
    return mid


def buscar_material(mid: str) -> None:
    """El material real que existe para el tema del vídeo (tráilers oficiales y gameplay sin comentario), para
    añadirlo con un clic. Mira el título y el guion: así se ve también si el guion pide algo que no hay."""
    from . import material as materiales

    def fase():
        p = cargar(mid)
        _avisar(mid, "Buscando el material real del tema", 20)
        inv = materiales.inventario(p["titulo"], p.get("guion", ""), produccion=mid)
        modificar(mid, lambda q: q.update(material_sugerido=inv))
    _en_fondo(mid, "Buscar material", fase)


def usar_fuente(mid: str, fid: str) -> None:
    """Una fuente del banco en este vídeo (sin bajar nada)."""
    fuente(fid)
    modificar(mid, lambda p: p["fuentes"].append(fid) if fid not in p["fuentes"] else None)


# --- 3 · Montaje --------------------------------------------------------------------------------------------------
# --- Editor de línea de tiempo (básico): reordenar escenas y quitar clips -----------------------------------------
def mover_frase(mid: str, n: int, direccion: int) -> None:
    """Mueve una escena (frase) una posición arriba (-1) o abajo (+1) en la línea de tiempo. Reordena también su
    narración, así que invalida la previa y el final (hay que volver a montar)."""
    def cambio(p):
        frases = p["frases"]
        i = next((k for k, f in enumerate(frases) if f["n"] == n), None)
        if i is None:
            raise ValueError("Esa escena no existe.")
        j = i + (1 if direccion > 0 else -1)
        if not 0 <= j < len(frases):
            return   # ya está en un extremo
        # se intercambian también los bloques: la estructura (dónde entra cada transición) se queda en su sitio
        frases[i]["bloque"], frases[j]["bloque"] = frases[j]["bloque"], frases[i]["bloque"]
        frases[i], frases[j] = frases[j], frases[i]
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)


def quitar_clip(mid: str, n: int) -> None:
    """Deja la escena sin clip (vuelve a «elegir plano»). No borra la frase ni su texto."""
    def cambio(p):
        f = next((x for x in p["frases"] if x["n"] == n), None)
        if not f:
            raise ValueError("Esa escena no existe.")
        f.pop("clip", None)
        p.update(previa="", final=None, short=None)
    modificar(mid, cambio)


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


ESCENAS_SISTEMA = """Eres montador de vídeo. Te doy las frases de un guion (en español) y las escenas de los tráilers
oficiales que hay como material, cada una con su id, qué se ve y qué se dice (en inglés). Para cada frase elige la
escena que MEJOR enseña lo que dice la frase (mismo personaje, lugar, coche, acción o diálogo). Si ninguna encaja, no
la pongas. No repitas la misma escena en dos frases seguidas. Solo JSON: {"asignaciones": [{"n": 1, "escena": "E12"}]}"""


def planos_por_escenas(mid: str, todas: bool = False) -> None:
    """Cada frase recibe el plano del tráiler oficial donde ocurre lo que dice, con el índice de escenas de GTA Wiki.
    `todas`: también las que ya tienen plano (las de imagen o panel nunca se tocan)."""
    from . import escenas, gemini
    p = cargar(mid)
    idx = escenas.indice()
    lista = [{**e, "fuente": fid, "id": ""} for fid in p["fuentes"] for e in escenas.de_fuente(fuente(fid), idx) if e["plano"]]
    if not lista:
        raise ValueError("Ninguna fuente de este vídeo es un tráiler con escenas en GTA Wiki (Tráiler 1, 2 o de lanzamiento).")
    for k, e in enumerate(lista, 1):
        e["id"] = f"E{k}"
    frases = [f for f in p["frases"] if not con_imagen(f) and not f.get("panel") and (todas or not f.get("clip"))]
    if not frases:
        raise ValueError("No hay frases sin plano (marca «también las que ya tienen» para rehacerlas).")

    def fase():
        _avisar(mid, "Leyendo las escenas de los tráileres", 20)
        texto = ("FRASES:\n" + "\n".join(f"{f['n']}. {f['texto']}" for f in frases) + "\n\nESCENAS:\n"
                 + "\n".join(f"{e['id']} [{fuente(e['fuente'])['nombre']} {int(e['t']) // 60}:{int(e['t']) % 60:02d}] {e['que']}"
                              + (f" | {e['quien']}: {e['dice']}" if e["dice"] else "") for e in lista)
                 + "\n\nResponde solo con el JSON.")
        crudo = gemini.generar(texto, sistema=ESCENAS_SISTEMA, temperatura=0.2, detalle="planos por escenas", produccion=mid)
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        elegidas = {int(a["n"]): a["escena"] for a in json.loads(m.group(0) if m else crudo).get("asignaciones", [])
                    if isinstance(a, dict) and str(a.get("n", "")).isdigit()}
        por_id = {e["id"]: e for e in lista}
        _avisar(mid, "Poniendo cada plano en su frase", 80)

        def cambio(q):
            previo = None
            for f in q["frases"]:
                e = por_id.get(elegidas.get(f["n"], ""))
                if e and any(x["n"] == f["n"] for x in frases) and (e["fuente"], e["plano"]) != previo:
                    f["clip"] = {"fuente": e["fuente"], "plano": e["plano"]}
                    f.pop("imagen", None)
                if f.get("clip"):
                    previo = (f["clip"]["fuente"], f["clip"]["plano"])
            q.update(previa="", final=None, short=None, escenas_wiki=True)
        modificar(mid, cambio)
    _en_fondo(mid, "Planos por escenas", fase)


# --- Trabajo en segundo plano ---------------------------------------------------------------------------------------
def _avisar(mid: str, fase: str, progreso: int) -> None:
    modificar(mid, lambda p: p["trabajo"].update(fase=fase, progreso=max(0, min(100, progreso))))


def _despierto(si: bool) -> None:
    """Mientras se monta, Windows no suspende el PC por inactividad: un montaje de media hora se cortaba de noche
    (FFmpeg «tardaba» las horas que el PC estuvo dormido). Solo pide no dormir; no impide cerrar la tapa ni apagar.
    En portátiles con «espera moderna» (S0) no basta con el sistema: al apagarse la pantalla entran en espera y todo
    se congela (08:41 → 17:46 un día entero), así que mientras se monta también se pide la pantalla encendida."""
    if os.name != "nt":
        return
    import ctypes
    continuo, sistema, pantalla = 0x80000000, 0x00000001, 0x00000002
    ctypes.windll.kernel32.SetThreadExecutionState(continuo | ((sistema | pantalla) if si else 0))


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
        firma_voz = hashlib.sha1(json.dumps([segmentos, proveedor, p["voz_nombre"], ESTILO_VOZ,
                                             (p.get("voz_propia") or {}).get("huella", "") if proveedor == "propia" else "",
                                             p.get("voz_velocidad", 1.0)]
                                            ).encode("utf-8")).hexdigest()
        previa_voz = p.get("voz") or {}
        if previa_voz.get("firma") == firma_voz and wav.exists():   # mismo texto y misma voz: no se regraba
            avisar("Voz ya grabada (mismo guion)", 10)
            tiempos, palabras = [tuple(x) for x in previa_voz["tiempos"]], previa_voz["palabras"]
        else:
            avisar("Escuchando tu voz para sincronizarla" if proveedor == "propia" else "Grabando la voz", 5)
            vel = float(p.get("voz_velocidad", 1.0))
            t = _locutar_propia(mid, segmentos, wav, trabajo) if proveedor == "propia" else voz.locutar(segmentos, wav, proveedor, produccion=mid, voz_nombre=p["voz_nombre"], estilo_voz=ESTILO_VOZ,
                            voice_id=p["voz_nombre"] if proveedor == "fal" else None)
            if abs(vel - 1.0) > 0.01:
                voz.acelerar(wav, vel)
                t = {"duracion": t["duracion"] / vel, "escenas": [{"ini": e["ini"] / vel, "fin": e["fin"] / vel} for e in t["escenas"]],
                     "palabras": [{**w, "ini": w["ini"] / vel, "fin": w["fin"] / vel} for w in t["palabras"]]}
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
    destino = base / ("final_16x9.mp4" if final else "previa.mp4")
    # En dos pasos: primero el sonido a un archivo y luego la imagen con ese sonido. Todo en una sola orden, FFmpeg se
    # quedaba atascado a mitad del vídeo (esperando audio y vídeo a la vez) y no terminaba nunca.
    avisar("Subtítulos, voz y efectos" if final else "Efectos y fondo", 88)
    # una canción se iguala a las demás y se baja; la cama suave sostiene las pausas de la voz
    vol_lecho = config.VOLUMEN_MUSICA * musica.ganancia(pista) if cancion else 1.4
    # el vídeo no se corta en seco: los últimos 0,8 s funden a negro y el sonido se apaga con él
    cierre_a = f"afade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8"
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

    _pasada_imagen(p, trabajo, cuerpo, mezcla, destino, palabras if final else [], ancho, alto, escala, total, final)
    return destino


def _pasada_imagen(p: dict[str, Any], trabajo: Path, cuerpo: Path, mezcla: Path, destino: Path,
                   palabras: list[dict[str, Any]], ancho: int, alto: int, escala: float, total: float, final: bool) -> None:
    """La última pasada del vídeo: el cuerpo ya montado + el sonido ya mezclado + la marca 4L + los subtítulos. Va
    aparte para poder rehacerla sola (cambiar o corregir subtítulos en segundos, sin montar todo otra vez)."""
    logo = logo_de(p["canal"])
    cierre_v = f"fade=t=out:st={max(0.0, total - 0.8):.3f}:d=0.8"
    entradas = ["-i", str(cuerpo), "-i", str(mezcla)]
    filtros, mezcla_v = [], "[0:v]"
    if logo:   # el logo del canal, discreto arriba a la derecha en todo el vídeo
        entradas += ["-loop", "1", "-i", str(logo)]
        lado = int(130 * escala)
        filtros.append(f"[2:v]scale={lado}:{lado},format=rgba,colorchannelmixer=aa={OPACIDAD_MARCA}[logo];"
                       f"{mezcla_v}[logo]overlay=W-w-{int(40 * escala)}:{int(36 * escala)}:shortest=1[v1]")
        mezcla_v = "[v1]"
    subs = {**SUBS_POR_DEFECTO, **(p.get("subtitulos") or {})}
    if final and subs.get("activos", True):
        ass = subtitulos.construir(palabras, trabajo / "subs.ass", ancho, alto,
                                   {"estilo": subs["estilo"], "posicion": subs["posicion"], "tamano": subs["tamano"]})
        filtros.append(f"{mezcla_v}ass={ass.name},{cierre_v}[v]")
    else:
        filtros.append(f"{mezcla_v}{cierre_v}[v]")
    medios.ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "1:a", "-t", f"{total:.3f}",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "17" if final else "23", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(destino), cwd=trabajo)


def rehacer_subtitulos(mid: str) -> None:
    """Subtítulos nuevos (estilo, posición, tamaño o una palabra corregida) en el 16:9, el Short y el cuadrado, sin
    volver a montar: se reutilizan el cuerpo y la mezcla del último montaje."""
    p = cargar(mid)
    trabajo = carpeta(mid) / "render"
    if not p.get("final") or not (trabajo / "cuerpo.mp4").exists() or not (trabajo / "mezcla.wav").exists():
        raise ValueError("Primero monta el vídeo final.")

    def fase() -> None:
        q = cargar(mid)
        cuerpo = trabajo / "cuerpo.mp4"
        _avisar(mid, "Subtítulos nuevos en el vídeo", 20)
        palabras = ((q.get("voz") or {}).get("pausas") or q.get("voz") or {}).get("palabras") or []
        _pasada_imagen(q, trabajo, cuerpo, trabajo / "mezcla.wav", carpeta(mid) / q["final"]["archivo"], palabras,
                       ANCHO, ALTO, 1.0, medios.duracion(cuerpo), True)
        subtitulos.srt(palabras, carpeta(mid) / "subtitulos.srt")
        if q.get("short"):
            _avisar(mid, "Subtítulos nuevos en el Short", 60)
            _hacer_short(mid, q["short"]["desde"], q["short"]["hasta"])
        if q.get("cuadrado"):
            _avisar(mid, "Subtítulos nuevos en el cuadrado", 85)
            _hacer_cuadrado(mid, q["cuadrado"]["desde"], q["cuadrado"]["hasta"])
        modificar(mid, lambda r: r["final"].update(hecho=time.strftime("%Y-%m-%d %H:%M")))
    _en_fondo(mid, "Subtítulos", fase)


def _validar_subs(cambios: dict[str, Any]) -> dict[str, Any]:
    c = {k: cambios[k] for k in ("activos", "estilo", "posicion", "tamano") if k in cambios}
    if "estilo" in c and c["estilo"] not in ("viral", "cine"):
        raise ValueError("Estilo de subtítulos: viral o cine.")
    if "posicion" in c and c["posicion"] not in ("abajo", "arriba", "centro"):
        raise ValueError("Posición: abajo, arriba o centro.")
    if "tamano" in c and c["tamano"] not in ("pequeno", "normal", "grande"):
        raise ValueError("Tamaño: pequeño, normal o grande.")
    if "activos" in c:
        c["activos"] = bool(c["activos"])
    return c


def subtitulos_rapido(mid: str, cambios: dict[str, Any]) -> None:
    """Cambia los subtítulos; si el vídeo ya está montado, solo se rehace su última pasada."""
    c = _validar_subs(cambios)
    hay_final = bool(cargar(mid).get("final"))
    modificar(mid, lambda p: p.update(subtitulos={**SUBS_POR_DEFECTO, **(p.get("subtitulos") or {}), **c}, previa=""))
    if hay_final:
        rehacer_subtitulos(mid)


def corregir_subtitulo(mid: str, de: str, a: str) -> int:
    """Corrige una palabra en todos los subtítulos («Lucia» → «Lucía»), conservando su puntuación, y los rehace."""
    de, a = (de or "").strip(), (a or "").strip()
    if not de or not a or " " in de:
        raise ValueError("Escribe la palabra que está mal y cómo debe quedar.")
    patron = re.compile(rf"^(\W*){re.escape(de)}(\W*)$", re.IGNORECASE)
    cuenta = 0

    def cambio(p: dict[str, Any]) -> None:
        nonlocal cuenta
        v = p.get("voz") or {}
        for lista in (v.get("palabras") or [], (v.get("pausas") or {}).get("palabras") or []):
            for w in lista:
                m = patron.match(w["palabra"])
                if m:
                    w["palabra"] = f"{m.group(1)}{a}{m.group(2)}"
                    cuenta += 1
    modificar(mid, cambio)
    if not cuenta:
        raise ValueError(f"«{de}» no aparece en los subtítulos.")
    if cargar(mid).get("final"):
        rehacer_subtitulos(mid)
    return cuenta


def vista_subtitulos(mid: str, cambios: dict[str, Any], formato: str = "16x9") -> Path:
    """Un fotograma del vídeo con los subtítulos como quedarían, para verlos antes de aplicarlos."""
    p = cargar(mid)
    c = {**SUBS_POR_DEFECTO, **(p.get("subtitulos") or {}), **_validar_subs(cambios)}
    trabajo = carpeta(mid) / "render"
    cuerpo = trabajo / "cuerpo.mp4"
    if not cuerpo.exists():
        raise ValueError("Primero monta el vídeo final.")
    palabras = ((p.get("voz") or {}).get("pausas") or p.get("voz") or {}).get("palabras") or []
    if not palabras:
        raise ValueError("Este vídeo aún no tiene voz.")
    t = palabras[min(len(palabras) - 1, len(palabras) // 3)]["ini"] + 0.05
    cerca = [{**w, "ini": w["ini"] - t + 2, "fin": w["fin"] - t + 2} for w in palabras if t - 4 < w["ini"] < t + 4]
    vista = carpeta(mid) / "render_vista"
    vista.mkdir(exist_ok=True)
    ancho, alto = (1080, 1920) if formato == "9x16" else (ANCHO, ALTO)
    ass = subtitulos.construir(cerca, vista / "v.ass", ancho, alto, {k: c[k] for k in ("estilo", "posicion", "tamano")})
    subs = f",ass={ass.name}" if c.get("activos", True) else ""
    if formato == "9x16":
        filtro = ("split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=30,"
                  f"eq=brightness=-0.12[f];[b]scale=1080:-2[c];[f][c]overlay=0:(H-h)/2-120,setpts=PTS+2/TB{subs}")
    else:
        filtro = f"scale={ancho}:{alto},setpts=PTS+2/TB{subs}"
    destino = vista / f"subs_{formato}.jpg"
    medios.ffmpeg("-ss", f"{max(0.0, t - 0.0):.3f}", "-i", str(cuerpo), "-frames:v", "1", "-vf", filtro, "-q:v", "3",
                  str(destino), cwd=vista)
    return destino


# --- adjuntos del chat y miniaturas para elegir --------------------------------------------------------------------
IMAGEN_PERMITIDA = (".jpg", ".jpeg", ".png", ".webp")


def adjuntar_imagen(mid: str, tmp: Path, nombre: str) -> str:
    """Una imagen soltada en el chat: queda en el vídeo (adjuntos/) para la miniatura o para una frase."""
    from PIL import Image
    try:
        if Path(nombre).suffix.lower() not in IMAGEN_PERMITIDA:
            raise ValueError("Adjunta una imagen JPG, PNG o WEBP (los vídeos van como material y los .txt como guion).")
        cargar(mid)
        carpeta_a = carpeta(mid) / "adjuntos"
        carpeta_a.mkdir(exist_ok=True)
        archivo = f"{hashlib.sha1(tmp.read_bytes()).hexdigest()[:12]}.jpg"
        Image.open(tmp).convert("RGB").save(carpeta_a / archivo, quality=92)
    finally:
        tmp.unlink(missing_ok=True)
    modificar(mid, lambda p: p.update(adjuntos=[x for x in (p.get("adjuntos") or []) if x["archivo"] != archivo]
                                      + [{"archivo": archivo, "nombre": Path(nombre).name[:80]}]))
    return archivo


def adjunto(mid: str, archivo: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}\.jpg", archivo or "") or not (f := carpeta(mid) / "adjuntos" / archivo).exists():
        raise ValueError("Ese adjunto no existe.")
    return f


def imagen_adjunta_en_frase(mid: str, n: int, archivo: str) -> None:
    import base64
    poner_imagen(mid, n, datos_b64=base64.b64encode(adjunto(mid, archivo).read_bytes()).decode(), credito="Imagen propia")


def candidatos_miniatura(mid: str, texto: str = "") -> None:
    """3 o 4 miniaturas distintas (planos y textos) para VERLAS y elegir, en segundo plano."""
    p = cargar(mid)
    con_plano = [f["clip"] for f in p["frases"] if f.get("clip")]
    adj = p.get("adjuntos") or []
    if not con_plano and not adj:
        raise ValueError("Este vídeo aún no tiene planos ni imágenes para la miniatura.")
    t = (p.get("textos") or {})
    base_txt = (texto or t.get("texto_miniatura") or p["titulo"]).strip()[:40].upper()
    alt = f"{base_txt} {emoji_de(base_txt) or '🔥'}"   # la misma idea con su emoji (el navegador lo pinta a color)
    n = len(con_plano)
    variantes = []
    if n:
        variantes.append((base_txt, [con_plano[n // 3], con_plano[(2 * n) // 3]] if n > 1 else con_plano[:1]))
        variantes.append((base_txt, [con_plano[n // 2]]))
        variantes.append((alt or base_txt, [con_plano[0], con_plano[-1]] if n > 1 else con_plano[:1]))
    if adj:
        variantes.append((base_txt, [{"adjunto": adj[-1]["archivo"]}]))

    def fase() -> None:
        hechas = []
        for k, (txt, fotos) in enumerate(variantes[:4], 1):
            _avisar(mid, f"Miniatura {k} de {len(variantes[:4])}", int(100 * k / (len(variantes[:4]) + 1)))
            miniatura(mid, txt, fotos, destino_nombre=f"miniatura_c{k}.jpg")
            hechas.append({"archivo": f"miniatura_c{k}.jpg", "texto": txt})
        modificar(mid, lambda q: q.update(miniatura_candidatos=hechas))
    _en_fondo(mid, "Miniaturas", fase)


def elegir_miniatura(mid: str, archivo: str) -> None:
    if not re.fullmatch(r"miniatura_c\d\.jpg", archivo or "") or not (carpeta(mid) / archivo).exists():
        raise ValueError("Esa miniatura no existe.")
    shutil.copyfile(carpeta(mid) / archivo, carpeta(mid) / "miniatura.jpg")
    modificar(mid, lambda q: q.update(miniatura="miniatura.jpg"))


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
    if p.get("escenas_wiki"):
        from . import escenas
        lineas += ["", escenas.CREDITO]
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
    subs = {**SUBS_POR_DEFECTO, **(q.get("subtitulos") or {})}
    puestos = ""
    if subs.get("activos", True):
        ass = subtitulos.construir(palabras, trabajo / "subs.ass", 1080, 1920,
                                   {"estilo": subs["estilo"], "posicion": subs["posicion"], "tamano": subs["tamano"]})
        puestos = f",ass={ass.name}"
    capas, marca = _capas_marca(q, desde, hasta, 1080, 1920, "[base]", 2, emojis=True)
    medios.ffmpeg("-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / "render" / "cuerpo.mp4"),
                  "-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / q["final"]["archivo"]),
                  *capas,
                  "-filter_complex",
                  "[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  "gblur=sigma=30,eq=brightness=-0.12[fondo];[b]scale=1080:-2[centro];"
                  f"[fondo][centro]overlay=0:(H-h)/2-120{puestos}[base];{marca}",
                  "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                  str(base / "short_9x16.mp4"), cwd=trabajo)
    modificar(mid, lambda r: r.update(short={"archivo": "short_9x16.mp4", "desde": desde, "hasta": hasta}))


def montar_cuadrado(mid: str, desde: float, hasta: float) -> None:
    """Un tramo del vídeo final (≤ 60 s) en 1:1 para el feed de Instagram/Facebook."""
    p = cargar(mid)
    if not p.get("final"):
        raise ValueError("Primero monta el vídeo final.")
    if not 5 <= hasta - desde <= 60:
        raise ValueError("Un clip de feed dura entre 5 y 60 segundos.")
    _en_fondo(mid, "Cuadrado", lambda: _hacer_cuadrado(mid, desde, hasta))


def _hacer_cuadrado(mid: str, desde: float, hasta: float) -> None:
    """1:1 (1080x1080): el 16:9 centrado sobre su versión desenfocada, con subtítulos propios. Mismo método que el Short."""
    q = cargar(mid)
    base = carpeta(mid)
    trabajo = base / "render_cuadrado"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir()
    _avisar(mid, "Encuadrando en 1:1", 20)
    palabras = [{**w, "ini": w["ini"] - desde, "fin": w["fin"] - desde}
                for w in (q["voz"].get("pausas") or q["voz"])["palabras"]
                if desde <= w["ini"] < hasta]
    subs = {**SUBS_POR_DEFECTO, **(q.get("subtitulos") or {})}
    puestos = ""
    if subs.get("activos", True):
        ass = subtitulos.construir(palabras, trabajo / "subs.ass", 1080, 1080,
                                   {"estilo": subs["estilo"], "posicion": subs["posicion"], "tamano": subs["tamano"]})
        puestos = f",ass={ass.name}"
    capas, marca = _capas_marca(q, desde, hasta, 1080, 1080, "[base]", 2, emojis=False)
    medios.ffmpeg("-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / "render" / "cuerpo.mp4"),
                  "-ss", f"{desde:.3f}", "-t", f"{hasta - desde:.3f}", "-i", str(base / q["final"]["archivo"]),
                  *capas,
                  "-filter_complex",
                  "[0:v]split=2[a][b];[a]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,"
                  "gblur=sigma=28,eq=brightness=-0.12[fondo];[b]scale=1080:-2[centro];"
                  f"[fondo][centro]overlay=0:(H-h)/2{puestos}[base];{marca}",
                  "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                  str(base / "cuadrado_1x1.mp4"), cwd=trabajo)
    modificar(mid, lambda r: r.update(cuadrado={"archivo": "cuadrado_1x1.mp4", "desde": desde, "hasta": hasta}))


OPACIDAD_MARCA = 0.85
# el emoji de cada frase del Short, por lo que dice (la primera regla que encaja); sin regla, sin emoji
EMOJIS = (
    (r"\b(faltan?|d[ií]as?|cuenta atr[aá]s|fecha|noviembre|diciembre|enero|semanas?)\b", "⏳"),
    (r"(d[oó]lares|euros|precio|cuesta|\$|pagar|gratis)", "💰"),
    (r"\b(disco|f[ií]sicas?|caja|copias?|c[oó]digo de descarga)\b", "💿"),
    (r"\b(m[uú]sica|[aá]lbum|canci[oó]n|banda sonora|vinilo|cd|tocadiscos|temas)\b", "🎵"),
    (r"\b(playstation|xbox|ps5|consolas?|pc|switch)\b", "🎮"),
    (r"\b(sale|salida|lanzamiento|llega|estreno)\b", "🚀"),
    (r"\b(coches?|autos?|carros?|motos?|veh[ií]culos?)\b", "🚗"),
    (r"\b(armas?|pistolas?|disparos?|tiroteos?)\b", "🔫"),
    (r"\b(confirm\w*|oficial\w*)\b", "✅"),
    (r"\b(secreto|oculto|misterio|filtra\w*|rumor\w*)\b", "👀"),
    (r"\b(pero|ojo|cuidado|sin embargo)\b", "⚠️"),
    (r"\b(primera?|nuevos?|nunca|r[eé]cord|hist[oó]ric\w*|incluso)\b", "🔥"),
    (r"\b(ciudad|vice city|leonida|mapa|florida|estado)\b", "🌴"),
    (r"\b(protagonistas?|personajes?|pareja)\b", "⭐"),
)


def emoji_de(texto: str) -> str:
    t = texto.lower()
    return next((e for patron, e in EMOJIS if re.search(patron, t)), "")


def _png_emoji(emoji: str) -> Path:
    """El emoji a color en PNG transparente (FFmpeg los pinta en blanco y negro): lo dibuja el navegador, una vez."""
    from playwright.sync_api import sync_playwright
    destino = config.PRODUCCIONES / "_emojis" / f"{'-'.join(f'{ord(c):x}' for c in emoji)}.png"
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pagina = nav.new_page(device_scale_factor=1)
        pagina.set_content('<html><body style="margin:0;background:transparent"><span id="e" style="display:inline-block;'
                           "padding:12px;font:220px/1 'Segoe UI Emoji','Noto Color Emoji',sans-serif\">" + emoji + "</span></body></html>")
        pagina.locator("#e").screenshot(path=str(destino), omit_background=True)
        nav.close()
    return destino


def _capas_marca(q: dict[str, Any], desde: float, hasta: float, ancho: int, alto: int, entrada: str,
                 n_entrada: int, emojis: bool) -> tuple[list[str], str]:
    """La marca 4L (y, en el Short, un emoji por frase) sobre `entrada`. Devuelve las entradas extra de FFmpeg y la
    cadena de filtros que termina en [v]."""
    entradas: list[str] = []
    cadena, actual, k = "", entrada, n_entrada
    logo = logo_de(q["canal"])
    if logo:
        lado, x, y = (150, 48, 150) if alto > ancho else (110, ancho - 140, 30)   # vertical: arriba a la izquierda (libre de la interfaz)
        entradas += ["-loop", "1", "-i", str(logo)]
        cadena += (f"[{k}:v]scale={lado}:{lado},format=rgba,colorchannelmixer=aa={OPACIDAD_MARCA}[m{k}];"
                   f"{actual}[m{k}]overlay={x}:{y}:shortest=1[c{k}];")
        actual, k = f"[c{k}]", k + 1
    if emojis:
        tiempos = (q.get("voz") or {}).get("pausas", {}).get("tiempos") or (q.get("voz") or {}).get("tiempos") or []
        previo = ""
        # cada emoji se queda hasta que empieza la frase siguiente (sin parpadeo en las pausas)
        tiempos = [(a, tiempos[k + 1][0] if k + 1 < len(tiempos) else b) for k, (a, b) in enumerate(tiempos)]
        for f, (a, b) in zip(q["frases"], tiempos):
            e = emoji_de(f["texto"])
            if not e or e == previo or b <= desde or a >= hasta:
                previo = e or previo
                continue
            previo = e
            a, b = max(0.0, a - desde), min(hasta - desde, b - desde)
            try:
                png = _png_emoji(e)
            except Exception as err:  # noqa: BLE001 - sin navegador, el Short sale igual (sin emojis)
                logger.warning("Emoji %s: %s", e, err)
                break
            entradas += ["-loop", "1", "-t", f"{hasta - desde:.3f}", "-i", str(png)]
            cadena += (f"[{k}:v]scale=230:-1,format=rgba,fade=t=in:st={a:.2f}:d=0.18:alpha=1,"
                       f"fade=t=out:st={max(a, b - 0.2):.2f}:d=0.2:alpha=1[e{k}];"
                       f"{actual}[e{k}]overlay=(W-w)/2:{int(alto * 0.13)}:enable='between(t,{a:.2f},{b:.2f})'[c{k}];")
            actual, k = f"[c{k}]", k + 1
    return entradas, cadena + f"{actual}null[v]"


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
        _avisar(mid, "Short vertical", 98)
        _hacer_short(mid, desde, hasta)
        if q.get("formatos", {}).get("cuadrado", True):   # el 1:1 para el feed (por defecto sí; el render básico lo decide)
            _avisar(mid, "Clip 1:1 para el feed", 99)
            _hacer_cuadrado(mid, desde, hasta)
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


SUBS_POR_DEFECTO = {"activos": True, "estilo": "viral", "posicion": "abajo", "tamano": "normal"}


def render_basico(mid: str, opciones: dict[str, Any] | None = None) -> None:
    """Un solo paso: aplica lo esencial (voz, subtítulos, música, qué formatos, sonido original del vídeo) y entrega
    el 16:9, el 9:16, el 1:1 y la miniatura, sin más opciones. Rellena los planos que falten para no pararse."""
    o = opciones or {}
    if o.get("voz_proveedor") and o.get("voz_nombre"):
        elegir_voz(mid, str(o["voz_proveedor"]), str(o["voz_nombre"]))
    if o.get("musica"):
        elegir_musica(mid, str(o["musica"]))
    subs = {**SUBS_POR_DEFECTO, **(o.get("subtitulos") or {})}
    modificar(mid, lambda p: p.update(subtitulos=subs, formatos={"cuadrado": bool(o.get("cuadrado", True))},
                                      voz_original=bool(o.get("voz_original", False))))
    p = cargar(mid)
    if p["fuentes"] and any(not con_imagen(f) and not f.get("panel") for f in p["frases"]):
        proponer(mid)   # cada frase vacía recibe un plano, para poder hacerlo todo
    automatico(mid, pago_ok=bool(o.get("pago_ok")))


# --- Textos para publicar y miniatura -------------------------------------------------------------------------------
SISTEMA_TEXTOS = """Eres editor de un canal de YouTube de videojuegos en español latino. Con el guion de un vídeo
escribe lo necesario para publicarlo. Reglas: nada de clickbait engañoso; lo no confirmado se presenta como avance
o rumor; nunca menciones a otros youtubers ni canales. Para que llamen más la atención, pon 1 o 2 emojis o símbolos (🔥 ⏳ 💰 ⚠️ ✅ ➡️ 🎮) en cada título y en la descripción, sin
llenarlo todo. Devuelve JSON:
{"titulos": ["3 títulos de máx. 70 caracteres, distintos"], "titulo_short": "título del Short, máx. 60 caracteres, con emojis y #Shorts", "descripcion": "3-5 frases, primera línea con gancho",
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
              "titulo_short": str(d.get("titulo_short", ""))[:100],
              "hashtags": [h for h in d.get("hashtags", []) if str(h).startswith("#")][:8],
              "texto_miniatura": str(d.get("texto_miniatura", ""))[:40], "capitulos": capitulos,
              "creditos": "\n".join(x for x in (
                  "Escenas generadas con IA (Google Flow · Veo), con guion, voz y edición propios." if p.get("ia")
                  else "Imágenes de los juegos con comentario y edición propios.", p.get("musica_credito", "")) if x)}
    from . import empaque   # título + miniatura como pareja, capítulos que YouTube acepte y el gancho
    duracion = (p.get("voz") or {}).get("duracion") or 0
    revision = empaque.revisar(textos, p["frases"][0]["texto"] if p["frases"] else "", duracion or 9999)
    textos["capitulos"] = revision.pop("capitulos")
    textos["revision"] = revision
    modificar(mid, lambda q: q.update(textos=textos, fuentes_titulos=creditos))
    return textos


def miniatura(mid: str, texto: str, fotos: list[dict[str, Any]], destino_nombre: str = "miniatura.jpg") -> Path:
    """Miniatura 1280×720: una o dos imágenes de los planos (pantalla dividida) y el texto grande, con el logo."""
    from playwright.sync_api import sync_playwright
    p = cargar(mid)
    base = carpeta(mid)
    trabajo = base / "render_miniatura"
    shutil.rmtree(trabajo, ignore_errors=True)
    trabajo.mkdir()
    imgs = []
    for k, ft in enumerate(fotos[:2]):
        if ft.get("adjunto"):   # una imagen tuya soltada en el chat
            shutil.copyfile(adjunto(mid, str(ft["adjunto"])), trabajo / f"m{k}.jpg")
            imgs.append(f"m{k}.jpg")
            continue
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
    destino = base / destino_nombre
    with sync_playwright() as pw:
        nav = pw.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": 1280, "height": 720})
        pag.goto((trabajo / "m.html").as_uri())
        pag.wait_for_function("document.fonts.ready.then(() => [...document.images].every(i => i.complete))")
        pag.screenshot(path=str(destino), type="jpeg", quality=92)
        nav.close()
    if destino_nombre == "miniatura.jpg":
        modificar(mid, lambda q: q.update(miniatura=destino.name))
    return destino
