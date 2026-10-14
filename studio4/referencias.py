"""Referencias que aporta el autor al crear un vídeo: fotos, documentos (PDF o texto), enlaces y datos obligatorios.

1. Se suben antes de que exista la producción: quedan en producciones/_referencias/ con un id.
2. Al crear la producción se copian a producciones/<id>/referencias/.
3. Gemini (gratis) las estudia una vez: describe cada foto (quién o qué aparece, aspecto, lugar, época, texto
   visible) y saca de cada documento o enlace los hechos, nombres, fechas y cifras.
4. El guion las usa como material prioritario y el plan de escenas copia el aspecto de las fotos, para que los
   prompts de Flow se parezcan a lo que el autor enseñó.
"""

from __future__ import annotations

import html
import io
import logging
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

import urllib.parse

import requests

from . import config, gemini

logger = logging.getLogger("studio4.referencias")

FOTOS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
DOCUMENTOS = {"application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md"}
MAX_FOTO, MAX_DOC = 15 * 1024 * 1024, 20 * 1024 * 1024
LIMITES = {"foto": 6, "documento": 2, "enlace": 3}


def _espera() -> Path:
    return config.PRODUCCIONES / "_referencias"


def subir(tmp: Path, nombre: str, mime: str) -> dict[str, Any]:
    """Guarda una foto o un documento a la espera de que se cree la producción."""
    mime = mime.split(";")[0].strip().lower()
    if mime in FOTOS:
        tipo, ext, tope = "foto", FOTOS[mime], MAX_FOTO
    elif mime in DOCUMENTOS or Path(nombre).suffix.lower() in (".txt", ".md", ".pdf"):
        tipo, tope = "documento", MAX_DOC
        ext = DOCUMENTOS.get(mime) or Path(nombre).suffix.lower()
    else:
        raise ValueError("Solo fotos (JPG, PNG, WEBP) o documentos (PDF, TXT).")
    if tmp.stat().st_size > tope:
        raise ValueError(f"«{nombre}» es demasiado grande (máx. {tope // (1024 * 1024)} MB).")
    rid = secrets.token_hex(8)
    _espera().mkdir(parents=True, exist_ok=True)
    shutil.copy(tmp, _espera() / f"{rid}{ext}")
    return {"id": rid, "tipo": tipo, "nombre": Path(nombre).name[:80] or f"{tipo}{ext}"}


def _archivo_en_espera(rid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", rid or ""):
        raise ValueError("Referencia no válida")
    hallados = list(_espera().glob(f"{rid}.*"))
    if not hallados:
        raise ValueError("La referencia ya no está: vuelve a subirla.")
    return hallados[0]


def borrar(rid: str) -> None:
    _archivo_en_espera(rid).unlink(missing_ok=True)


def limpiar_espera(horas: int = 24) -> None:
    """Las subidas que nunca llegaron a una producción se borran al día."""
    if not _espera().is_dir():
        return
    for f in _espera().iterdir():
        if time.time() - f.stat().st_mtime > horas * 3600:
            f.unlink(missing_ok=True)


def preparar(datos: dict[str, Any] | None, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Valida lo que manda el panel. `items` son las subidas ({id, tipo, nombre})."""
    datos = datos or {}
    for i in items:
        _archivo_en_espera(i["id"])   # antes de crear nada: cada subida tiene que seguir ahí
    enlaces = [e.strip() for e in datos.get("enlaces") or [] if re.match(r"https?://\S+$", str(e).strip())]
    for tipo, tope in LIMITES.items():
        n = len(enlaces) if tipo == "enlace" else sum(i["tipo"] == tipo for i in items)
        if n > tope:
            raise ValueError(f"Como mucho {tope} referencias de tipo {tipo}.")
    return {"items": items, "enlaces": enlaces[:LIMITES["enlace"]], "datos": str(datos.get("datos") or "").strip()[:2000],
            "material": None}


def copiar_a(carpeta: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copia las subidas a la carpeta de la producción y devuelve los items con su archivo."""
    destino = carpeta / "referencias"
    destino.mkdir(exist_ok=True)
    salida = []
    for i in items:
        origen = _archivo_en_espera(i["id"])
        shutil.copy(origen, destino / origen.name)
        salida.append({**i, "archivo": f"referencias/{origen.name}"})
    return salida


def soltar_espera(items: list[dict[str, Any]]) -> None:
    for i in items:
        try:
            borrar(i["id"])
        except ValueError:
            pass


# --- Estudio con Gemini ---------------------------------------------------------------------------
FOTO = """Describe esta foto para un guionista y para un generador de imágenes. En español, 3 a 5 frases:
quién o qué aparece y su IDENTIDAD (edad, rasgos del rostro, pelo, ojos, complexión, ropa con colores), el lugar y
la época, la luz, y el texto legible si hay. No describas la pose, el gesto ni el encuadre: eso cambia en cada escena.
Solo lo que se ve; no inventes nombres."""
DOCUMENTO = """Extrae de este material lo útil para un guion de vídeo de divulgación: hechos, nombres, fechas, cifras
y citas textuales importantes. En español, en viñetas breves, máximo 15. No añadas nada que no esté en el material."""


def _jpeg(ruta: Path) -> bytes:
    from PIL import Image
    with Image.open(ruta) as im:
        im = im.convert("RGB")
        im.thumbnail((1600, 1600))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue()


def _texto_web(url: str) -> str:
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (STUDIO 4)"})
    r.raise_for_status()
    t = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", r.text)
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()[:15000]


def es_maps(url: str) -> bool:
    return bool(re.match(r"https?://(maps\.app\.goo\.gl|goo\.gl/maps|(www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)/", url))


def lugar_de_maps(url: str) -> dict[str, Any]:
    """Nombre y coordenadas del sitio, leídos del enlace. Los enlaces cortos (maps.app.goo.gl) solo se siguen
    hasta la dirección completa: no se descarga ni se lee la página de Google Maps."""
    largo = url
    if "goo.gl" in url:
        largo = requests.head(url, allow_redirects=True, timeout=15).url
    ruta = urllib.parse.unquote_plus(urllib.parse.urlparse(largo).path)
    nombre = re.search(r"/place/([^/]+)", ruta)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(largo).query).get("q", [""])[0]
    coords = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", largo) or re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", largo)
    salida = {"nombre": (nombre.group(1) if nombre else q).strip(), "url": largo}
    if coords:
        salida.update(lat=float(coords.group(1)), lng=float(coords.group(2)))
    if not salida["nombre"] and not coords:
        raise ValueError("No encuentro el sitio en ese enlace de Google Maps.")
    return salida


def video_de_youtube(url: str) -> dict[str, Any] | None:
    """Título, canal, descripción y etiquetas de un vídeo de YouTube (API oficial, solo lectura).
    La página de YouTube apenas tiene texto: sin esto, el enlace no aportaría nada al guion."""
    m = re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/))([\w-]{11})", url)
    if not m:
        return None
    from . import youtube   # aquí: youtube importa canales y no hace falta cargarlo para subir fotos
    d = youtube._get("videos", part="snippet", id=m.group(1))
    if not d.get("items"):
        raise ValueError("Ese vídeo de YouTube no existe o es privado.")
    s = d["items"][0]["snippet"]
    return {"titulo": s["title"], "canal": s["channelTitle"], "descripcion": s.get("description", "")[:5000],
            "etiquetas": s.get("tags", [])[:20]}


def _limpio(texto: str) -> str:
    return re.sub(r"\*\*|__|^#+\s*", "", texto.strip(), flags=re.M)


def estudiar(carpeta: Path, refs: dict[str, Any], produccion: str = "") -> list[dict[str, Any]]:
    """Una entrada por referencia: {tipo, nombre, resumen}. Si una falla, se anota y se sigue con las demás."""
    material = []
    for i in refs.get("items", []):
        ruta = carpeta / i["archivo"]
        try:
            if i["tipo"] == "foto":
                resumen = gemini.generar(FOTO, imagenes=[_jpeg(ruta)], temperatura=0.2, detalle="referencia: foto",
                                         produccion=produccion)
            elif ruta.suffix.lower() == ".pdf":
                resumen = gemini.generar(DOCUMENTO, archivos=[(ruta.read_bytes(), "application/pdf")], temperatura=0.2,
                                         detalle="referencia: documento", produccion=produccion)
            else:
                texto = ruta.read_text(encoding="utf-8", errors="replace")[:15000]
                resumen = gemini.generar(f"{DOCUMENTO}\n\n--- MATERIAL ---\n{texto}", temperatura=0.2,
                                         detalle="referencia: texto", produccion=produccion)
            material.append({"tipo": i["tipo"], "nombre": i["nombre"], "resumen": _limpio(resumen)})
        except Exception as e:  # noqa: BLE001 - una referencia mala no frena al resto
            logger.warning("No pude estudiar «%s»: %s", i["nombre"], e)
    for url in refs.get("enlaces", []):
        try:
            if es_maps(url):
                sitio = lugar_de_maps(url)
                donde = f" Ubicación: {sitio['lat']:.5f}, {sitio['lng']:.5f}." if "lat" in sitio else ""
                material.append({"tipo": "lugar", "nombre": sitio["nombre"] or "Sitio de Google Maps",
                                 "resumen": f"Lugar o negocio del vídeo: {sitio['nombre']}.{donde} (enlace de Google Maps del autor)"})
                continue
            yt = video_de_youtube(url)
            texto = (f"Vídeo de YouTube «{yt['titulo']}» ({yt['canal']}). Etiquetas: {', '.join(yt['etiquetas'])}.\n"
                     f"Descripción:\n{yt['descripcion']}") if yt else _texto_web(url)
            resumen = gemini.generar(f"{DOCUMENTO}\n\n--- MATERIAL ({url}) ---\n{texto}", temperatura=0.2,
                                     detalle="referencia: enlace", produccion=produccion)
            material.append({"tipo": "enlace", "nombre": url, "resumen": _limpio(resumen)})
        except Exception as e:  # noqa: BLE001
            logger.warning("No pude leer el enlace %s: %s", url, e)
    return material


def para_guion(refs: dict[str, Any] | None) -> str:
    """El bloque que recibe quien escribe el guion (vacío si no hay referencias)."""
    if not refs:
        return ""
    partes = []
    if refs.get("datos"):
        partes += ["DATOS QUE NO PUEDEN FALTAR:", refs["datos"]]
    for m in refs.get("material") or []:
        partes += [f"[{m['tipo'].upper()}: {m['nombre']}]", m["resumen"]]
    return "\n".join(partes)


def visuales(refs: dict[str, Any] | None) -> list[str]:
    """Las descripciones de las fotos, para que el plan de escenas copie su aspecto."""
    return [m["resumen"] for m in (refs or {}).get("material") or [] if m["tipo"] == "foto"]
