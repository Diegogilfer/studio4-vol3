"""La carpeta de cada producción, a la vista en tu PC (Vídeos\\STUDIO 4\\«fecha · título»):

  1 Clips de Flow     → dejas aquí cada clip que bajes de Flow, con el número de su escena en el nombre
                        («escena 3.mp4», «07.png»…): STUDIO lo coloca solo en su escena.
  2 Guion y escenas   → el guion y la lista de escenas (qué generar, vídeo o imagen, y su prompt).
  3 Entregas          → vídeo completo, Reels, Shorts, miniaturas y las descripciones para publicar.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from . import canales, config

logger = logging.getLogger("studio4.carpetas")

RAIZ_USUARIO = Path(os.getenv("STUDIO4_CARPETA", str(Path.home() / "Videos" / "STUDIO 4")))
# Subcarpetas: llevan delante el nombre del vídeo (ver subcarpeta()).
CLIPS, GUION, ENTREGAS = "1 Clips de Flow", "2 Guion y escenas", "3 Entregas"
MATERIAL = "4 Voz y material"   # la voz y lo que se usó en cada escena, guardado aunque se borre la producción
EXTENSIONES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
               ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
VERSION = {"corto": "Corto", "largo": "Largo", "propio": "Guion propio", "importado": "Importado"}

LEEME = """«{titulo}» · clips de Google Flow

Guarda aquí cada clip que descargues de Flow con el nombre del vídeo y el NÚMERO DE SU ESCENA:

    {corto} - escena 01.mp4
    {corto} - escena 02.png
    {corto} - escena 14 (toma 2).mp4

STUDIO 4 lo detecta en unos segundos y lo coloca en su escena (vídeo o imagen, como te recomendó).
Si dejas varios para la misma escena, se guardan todos como tomas y eliges la mejor en el panel.
"""


def _limpio(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)).strip().rstrip(".")


def _recortar(texto: str, n: int) -> str:
    """Como mucho `n` letras, cortando en una palabra entera (Windows no admite rutas de más de 260 letras y el
    nombre del vídeo se repite en la carpeta, la subcarpeta y cada archivo)."""
    if len(texto) <= n:
        return texto
    corte = texto[:n].rsplit(" ", 1)[0]
    palabras = (corte if len(corte) > n // 2 else texto[:n]).rstrip(" ,;:-·").split(" ")
    while len(palabras) > 2 and palabras[-1].lower() in SUELTAS:   # que no acabe en «y el», «de la»…
        palabras.pop()
    return " ".join(palabras).rstrip(" ,;:-·")


SUELTAS = {"y", "e", "o", "u", "el", "la", "los", "las", "lo", "de", "del", "al", "a", "en", "con", "por", "para", "un", "una",
           "su", "sus", "que", "the", "of", "and", "to", "in"}


def _titulo(p: dict[str, Any]) -> str:
    """El título para nombrar carpetas: si tiene dos partes («Bonnie nunca disparó: lo que…»), la primera."""
    t = (p.get("titulo") or p.get("tema") or "Producción").strip()
    antes = t.split(":")[0].strip()
    return _limpio(antes if len(antes) >= 12 else t)


def nombre(p: dict[str, Any]) -> str:
    titulo = _recortar(_titulo(p), 44)
    version = VERSION.get(p.get("version", ""), "")
    return f"{p['creado'][:10]} · {titulo}" + (f" ({version})" if version else "")


def corto(p: dict[str, Any]) -> str:
    """El nombre del vídeo para ponerlo delante de cada archivo y subcarpeta."""
    return _recortar(_titulo(p), 32)


def subcarpeta(p: dict[str, Any], cual: str) -> str:
    return f"{cual} · {corto(p)}"


def ruta(p: dict[str, Any]) -> Path:
    """Vídeos/STUDIO 4/<canal>/<fecha · título>. Las carpetas de antes de los canales (sin la del canal) se mueven."""
    if p.get("carpeta") and Path(p["carpeta"]).parent != RAIZ_USUARIO:
        return Path(p["carpeta"])
    return RAIZ_USUARIO / _limpio(canales.de_produccion(p)["nombre"]) / nombre(p)


def preparar(p: dict[str, Any]) -> Path:
    """Crea (o completa) la carpeta y escribe el guion y la lista de escenas, todo con el nombre del vídeo."""
    base = ruta(p)
    vieja_raiz = Path(p["carpeta"]) if p.get("carpeta") else None
    if vieja_raiz and vieja_raiz != base and vieja_raiz.is_dir() and not base.exists():
        base.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(vieja_raiz), str(base))   # a la carpeta de su canal
    c = corto(p)
    for cual in (CLIPS, GUION, ENTREGAS):
        nueva = base / subcarpeta(p, cual)
        viejas = [base / cual] + sorted(base.glob(f"{cual} · *"))   # sin el nombre del vídeo, o con uno más largo
        vieja = next((v for v in viejas if v.is_dir() and v != nueva), None)
        if vieja and not nueva.exists():
            vieja.rename(nueva)
        nueva.mkdir(parents=True, exist_ok=True)
    clips, guion = base / subcarpeta(p, CLIPS), base / subcarpeta(p, GUION)
    for viejo in (clips / "LEEME.txt", guion / "Guion.txt", guion / "Escenas para Flow.txt"):
        viejo.unlink(missing_ok=True)
    (clips / f"{c} - LEEME.txt").write_text(LEEME.format(titulo=p.get("titulo") or p.get("tema", ""), corto=c), encoding="utf-8")
    if p.get("guion"):
        (guion / f"{c} - Guion.txt").write_text(f"«{p.get('titulo') or p['tema']}» · Guion\n\n{p['guion']}\n", encoding="utf-8")
    if p.get("escenas"):
        lineas = [f"«{p.get('titulo') or p['tema']}» · Escenas para Google Flow",
                  f"Guarda cada clip en «{subcarpeta(p, CLIPS)}» como: {c} - escena 01.mp4", ""]
        for e in p["escenas"]:
            tipo = "IMAGEN" if e.get("tipo_clip") == "imagen" else "VÍDEO"
            lineas += [f"{c} · ESCENA {e['orden']:02d} · hazla como {tipo}" + (f" — {e['motivo_tipo']}" if e.get("motivo_tipo") else ""),
                       f"Guárdala como: {c} - escena {e['orden']:02d}{'.png' if tipo == 'IMAGEN' else '.mp4'}",
                       f"Voz: {e['texto_voz']}", f"Prompt para Flow: {e['prompt_flow']}", ""]
        (guion / f"{c} - Escenas para Flow.txt").write_text("\n".join(lineas), encoding="utf-8")
    return base


def numero_de_escena(p: dict[str, Any], nombre_archivo: str) -> int:
    """«Título 2 - escena 07.mp4» → 7. Primero busca «escena N»; si no, el primer número que no sea del título."""
    stem = Path(nombre_archivo).stem
    m = re.search(r"escena\s*0*(\d+)", stem, re.IGNORECASE)
    if m:
        return int(m.group(1))
    resto = stem.replace(corto(p), " ")
    m = re.search(r"(\d+)", resto)
    return int(m.group(1)) if m else 0


def estado(p: dict[str, Any]) -> dict[str, Any]:
    """Lo que hay en «1 Clips de Flow»: la ruta, cuántos clips hay y a cuántas escenas corresponden."""
    carpeta = ruta(p) / subcarpeta(p, CLIPS)
    total = len(p.get("escenas") or [])
    archivos = [f for f in carpeta.iterdir() if f.is_file() and f.suffix.lower() in EXTENSIONES] if carpeta.is_dir() else []
    con_escena = {numero_de_escena(p, f.name) for f in archivos} & set(range(1, total + 1))
    return {"ruta": str(carpeta), "archivos": len(archivos), "escenas_en_carpeta": len(con_escena),
            "escenas_con_clip": sum(1 for e in p.get("escenas") or [] if e.get("elegida") is not None), "total": total}


def importar(p: dict[str, Any], recibir) -> list[str]:
    """Mira «1 Clips de Flow» y entrega a su escena lo que aún no se había importado. Devuelve las claves nuevas."""
    carpeta = ruta(p) / subcarpeta(p, CLIPS)
    if not carpeta.is_dir():
        return []
    ya = set(p.get("importados", []))
    nuevas = []
    for f in sorted(carpeta.iterdir()):
        mime = EXTENSIONES.get(f.suffix.lower())
        if not mime or not f.is_file():
            continue
        clave = f"{f.name}|{f.stat().st_size}|{int(f.stat().st_mtime)}"
        if clave in ya:
            continue
        n = numero_de_escena(p, f.name)
        if not 1 <= n <= len(p.get("escenas", [])):
            logger.warning("«%s»: no sé a qué escena va (pon el número de escena en el nombre).", f.name)
            nuevas.append(clave)   # no se vuelve a intentar hasta que cambie el archivo
            continue
        fd, tmp = tempfile.mkstemp(prefix="studio4_", suffix=f.suffix, dir=config.PRODUCCIONES)
        os.close(fd)
        shutil.copy(f, tmp)
        try:
            recibir(Path(tmp), mime, n)
            nuevas.append(clave)
        except Exception as e:  # noqa: BLE001 - un archivo malo no frena a los demás
            logger.warning("No pude importar «%s»: %s", f.name, e)
            nuevas.append(clave)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return nuevas


def _copiar(origen: Path, destino: Path) -> bool:
    """Copia si falta o cambió (un vídeo largo no vuelve a copiar 100 imágenes iguales al montarse otra vez)."""
    if not origen.is_file():
        return False
    if destino.is_file() and destino.stat().st_size == origen.stat().st_size:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    return True


def guardar_material(p: dict[str, Any], base_produccion: Path) -> Path:
    """«4 Voz y material»: la voz, la imagen o el clip de cada escena (y su original a sangre), los retratos y de
    dónde salió cada cosa. De un vídeo importado no se copian los trozos del original (ya tienes el vídeo)."""
    destino = ruta(p) / subcarpeta(p, MATERIAL)
    destino.mkdir(parents=True, exist_ok=True)
    c = corto(p)
    voz = p.get("voz") or {}
    if voz.get("archivo") and voz.get("proveedor") != "original":
        _copiar(base_produccion / voz["archivo"], destino / f"{c} - Voz{Path(voz['archivo']).suffix}")
    creditos = [f"«{p.get('titulo') or p.get('tema', '')}» · voz, material y fuentes", ""]
    if voz:
        creditos.append(f"Voz: {voz.get('proveedor', '')} {voz.get('voz_nombre', '')} · {voz.get('duracion', 0)} s".rstrip())
    for e in p.get("escenas") or []:
        if e.get("elegida") is None:
            continue
        t = e["tomas"][e["elegida"]]
        origen = t.get("origen", "")
        linea = f"Escena {e['orden']:02d} · {origen or t.get('tipo', '')}"
        if t.get("fuente") or t.get("url"):
            linea += f" · {t.get('url') or ''} {('(' + t['fuente'] + ')') if t.get('fuente') else ''}".rstrip()
        creditos.append(linea)
        if origen == "original":
            continue
        archivo = base_produccion / t["archivo"]
        _copiar(archivo, destino / "Escenas" / f"{c} - escena {e['orden']:02d}{archivo.suffix}")
        if t.get("original"):
            o = base_produccion / t["original"]
            _copiar(o, destino / "Escenas" / f"{c} - escena {e['orden']:02d} - original{o.suffix}")
    for retrato in sorted((base_produccion / "retratos").glob("*.png")):
        _copiar(retrato, destino / "Retratos" / retrato.name)
    paginas = [f.get("url", "") for f in ((p.get("investigacion") or {}).get("fuentes") or []) if f.get("url")]
    if paginas:
        creditos += ["", "Páginas investigadas:"] + [f"- {u}" for u in paginas]
    (destino / f"{c} - Fuentes y créditos.txt").write_text("\n".join(creditos) + "\n", encoding="utf-8")
    return destino


def exportar(p: dict[str, Any], archivos: list[tuple[Path, str]], textos: str) -> Path:
    """Copia las entregas con nombres claros a «3 Entregas» y deja las descripciones listas para publicar."""
    destino = ruta(p) / subcarpeta(p, ENTREGAS)
    destino.mkdir(parents=True, exist_ok=True)
    c = corto(p)
    for origen, nombre_final in archivos:
        if origen.exists():
            shutil.copy(origen, destino / f"{c} - {_limpio(nombre_final)}")
    (destino / f"{c} - Descripciones para publicar.txt").write_text(f"«{p.get('titulo') or p['tema']}»\n\n{textos}", encoding="utf-8")
    return destino


EXTENSIONES_MATERIAL = {".wav", ".mp3", ".jpg", ".jpeg", ".png", ".webp", ".mp4"}


def _tipo_material(ext: str) -> str:
    if ext in (".wav", ".mp3"):
        return "voz"
    return "clip" if ext == ".mp4" else "imagen"


def _etiqueta_item(nombre_archivo: str, tipo: str, sub: str) -> str:
    if tipo == "voz":
        return "Voz"
    if sub.lower() == "retratos":
        return f"Retrato · {Path(nombre_archivo).stem.removeprefix('retrato_').capitalize()}"
    m = re.search(r"escena\s*0*(\d+)", nombre_archivo, re.IGNORECASE)
    if m:
        es_orig = "original" in nombre_archivo.lower()
        return f"Escena {int(m.group(1)):02d}" + (" · original" if es_orig else "")
    return Path(nombre_archivo).stem


def _creditos_de(carpeta_mat: Path) -> dict[int, str]:
    """De dónde salió cada escena según «Fuentes y créditos.txt», para distinguir si dos escenas usaron la misma foto."""
    txt = next(carpeta_mat.glob("* - Fuentes y créditos.txt"), None)
    if not txt or not txt.is_file():
        return {}
    origenes: dict[int, str] = {}
    for linea in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^Escena\s+0*(\d+)\s*·\s*(.+)$", linea.strip())
        if m:
            origenes[int(m.group(1))] = m.group(2).strip()
    return origenes


def archivo_material(relativo: str) -> Path:
    """Resuelve un archivo dentro de RAIZ_USUARIO; rechaza cualquier intento de salir o extensión no permitida."""
    if not relativo or Path(relativo).is_absolute() or "\\" in relativo.lstrip("\\") and ":" in relativo:
        raise FileNotFoundError("Ruta no permitida")
    base = RAIZ_USUARIO.resolve()
    destino = (base / relativo).resolve()
    if not destino.is_relative_to(base) or destino.suffix.lower() not in EXTENSIONES_MATERIAL or not destino.is_file():
        raise FileNotFoundError("No existe")
    return destino


def carpeta_material(cid: str, video: str) -> Path:
    """Calcula la carpeta «4 Voz y material» de un vídeo del canal sin aceptar rutas libres."""
    if not video or "/" in video or "\\" in video or ".." in video:
        raise FileNotFoundError("Carpeta no válida")
    canal_dir = (RAIZ_USUARIO / _limpio(canales.obtener(cid)["nombre"])).resolve()
    base_video = (canal_dir / video).resolve()
    if not base_video.is_relative_to(canal_dir) or not base_video.is_dir():
        raise FileNotFoundError("No existe la carpeta del vídeo")
    mat = next((d for d in sorted(base_video.glob(f"{MATERIAL}*")) if d.is_dir()), base_video)
    return mat


def listar_material(cid: str) -> list[dict[str, Any]]:
    """Todo el material guardado del canal en «4 Voz y material» (voces, imágenes y clips), con sus repeticiones."""
    canal_dir = RAIZ_USUARIO / _limpio(canales.obtener(cid)["nombre"])
    if not canal_dir.is_dir():
        return []
    base_raiz = RAIZ_USUARIO.resolve()
    items: list[dict[str, Any]] = []
    for dir_video in sorted((d for d in canal_dir.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True):
        partes = dir_video.name.split(" · ", 1)
        fecha_v = partes[0] if len(partes) > 1 else ""
        titulo_v = partes[1] if len(partes) > 1 else dir_video.name
        for dir_mat in sorted(d for d in dir_video.glob(f"{MATERIAL}*") if d.is_dir()):
            creditos = _creditos_de(dir_mat)
            archivos = sorted((f for f in dir_mat.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONES_MATERIAL),
                              key=lambda f: f.name)
            for f in archivos:
                if " - original." in f.name.lower():
                    continue   # la versión recortada ya representa a la escena en la galería
                res = f.resolve()
                if not res.is_relative_to(base_raiz):
                    continue
                ext = f.suffix.lower()
                tipo = _tipo_material(ext)
                sub = f.parent.name if f.parent != dir_mat else ""
                m_esc = re.search(r"escena\s*0*(\d+)", f.name, re.IGNORECASE)
                n_esc = int(m_esc.group(1)) if m_esc else 0
                credito = creditos.get(n_esc, "")
                url_fuente = next((u for u in re.findall(r"https?://\S+", credito)), "")
                import hashlib
                huella = (url_fuente or f"{ext}:{hashlib.sha1(res.read_bytes()).hexdigest()}"
                          if tipo != "voz" else f"voz:{res.as_posix()}")
                items.append({
                    "ruta": res.relative_to(base_raiz).as_posix(),
                    "tipo": tipo,
                    "etiqueta": _etiqueta_item(f.name, tipo, sub),
                    "video": dir_video.name,
                    "titulo": titulo_v,
                    "fecha": fecha_v,
                    "fuente": url_fuente.rsplit("/", 1)[-1][:50] if url_fuente else credito.split("·")[0].strip(),
                    "_huella": huella,
                })
    # Contar en cuántos vídeos o escenas aparece cada pieza para destacar «Lo más usado».
    usos: dict[str, int] = {}
    videos_por_huella: dict[str, list[str]] = {}
    for it in items:
        h = it.pop("_huella")
        usos[h] = usos.get(h, 0) + 1
        if it["titulo"] not in videos_por_huella.setdefault(h, []):
            videos_por_huella[h].append(it["titulo"])
        it["_h"] = h
    for it in items:
        h = it.pop("_h")
        it["usos"] = usos[h]
        it["videos_usado"] = len(videos_por_huella[h])
    return items

