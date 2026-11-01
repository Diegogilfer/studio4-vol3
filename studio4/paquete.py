"""El paquete de entrega de un vídeo terminado: UNA carpeta ordenada con todo (y un .zip para descargarla), para saber
qué es cada cosa y dónde subirla.

    Vídeos\\STUDIO 4\\<Canal>\\<fecha> · <título>\\
        1 Vídeo final · YouTube (16x9).mp4
        2 Short · YouTube Shorts, TikTok y Reels (9x16).mp4
        3 Cuadrado · Instagram y Facebook (1x1).mp4
        Miniaturas\\            la elegida y las demás opciones
        Subtítulos\\            .srt para subir a YouTube
        Textos para publicar.txt   títulos, descripción con capítulos, hashtags, etiquetas, créditos y fuentes
        Proyecto (para reeditar)\\   guion, voz, línea de tiempo y proyecto.json
        LÉEME.txt
"""

from __future__ import annotations

import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from . import canales, carpetas, montaje

FORMATOS = (("final_16x9.mp4", "1 Vídeo final · YouTube (16x9).mp4"),
            ("short_9x16.mp4", "2 Short · YouTube Shorts, TikTok y Reels (9x16).mp4"),
            ("cuadrado_1x1.mp4", "3 Cuadrado · Instagram y Facebook (1x1).mp4"))

LEEME = """«{titulo}» · {canal} · entregado el {fecha}

QUÉ SUBIR Y DÓNDE
· 1 Vídeo final (16x9)  → YouTube (vídeo normal). Pega los textos de «Textos para publicar.txt».
· 2 Short (9x16)        → YouTube Shorts, TikTok e Instagram Reels.
· 3 Cuadrado (1x1)      → publicaciones de Instagram y Facebook.
· Miniaturas            → en YouTube, «Miniatura» → sube «miniatura elegida.jpg» si ya elegiste una, o la opción que prefieras.
· Subtítulos            → en YouTube, «Subtítulos» → «Subir archivo» → el .srt (con tiempos).

PARA REEDITAR
· «Proyecto (para reeditar)» guarda el guion, la voz y la línea de tiempo. En Studio 4 el vídeo sigue abierto
  con todo su trabajo: lo que cambies allí se rehace sin empezar de cero.

ANTES DE PUBLICAR
· Revisa el vídeo entero. Si lleva escenas generadas con IA que parezcan reales, marca en YouTube
  «Contenido alterado o sintético».
"""


def _nombre_limpio(texto: str, n: int = 70) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "", texto).strip()[:n].rstrip(" .")


def textos_para_publicar(p: dict[str, Any], base: Path) -> str:
    t = p.get("textos") or {}
    rev = (t.get("revision") or {}).get("titulos") or []
    partes = ["TÍTULO (elige uno; nota del empaque entre paréntesis)"]
    partes += [f"- {x}" + (f" ({rev[k]['nota']}/100)" if k < len(rev) else "") for k, x in enumerate(t.get("titulos") or [p["titulo"]])]
    partes += ["", "DESCRIPCIÓN", t.get("descripcion", "")]
    if t.get("capitulos"):
        partes += ["", "⏱️ Capítulos:", *t["capitulos"]]
    if t.get("hashtags"):
        partes += ["", " ".join(t["hashtags"])]
    creditos = base / "Fuentes y créditos.txt"
    if creditos.exists():
        partes += ["", creditos.read_text(encoding="utf-8").strip()]
    elif t.get("creditos"):
        partes += ["", t["creditos"]]
    return "\n".join(partes).strip() + "\n"


SISTEMA_FLOW = """Escribe UN prompt en inglés para generar la miniatura de un vídeo de YouTube con Google Flow (imagen).
Reglas: 16:9, un sujeto claro y grande, fondo con profundidad, iluminación de alto contraste, colores vivos, deja
espacio libre a un lado para el texto (no escribas el texto en la imagen). Nada de logos, marcas ni personajes con
derechos de autor (ni de videojuegos ni de películas): estética propia que lo evoque. Máximo 80 palabras.
Devuelve solo JSON: {"prompt": "..."}"""


def prompt_miniatura_flow(p: dict[str, Any]) -> str:
    """El prompt para hacer la miniatura en Google Flow (a mano, con tu suscripción) y el texto que va encima."""
    t = p.get("textos") or {}
    texto = (t.get("texto_miniatura") or p["titulo"])[:40]
    base = (f"Cinematic YouTube thumbnail, 16:9, about: {p['titulo']}. One big clear subject, dramatic high-contrast lighting, "
            "vivid colors, depth of field, empty space on the right for a headline. No text, no logos, no copyrighted characters.")
    try:
        from . import deepseek
        if deepseek.disponible():
            base = str(deepseek.generar_json(SISTEMA_FLOW, f"TÍTULO: {p['titulo']}\nGUION (inicio): {(p.get('guion') or '')[:1500]}",
                                             temperatura=0.6, detalle="prompt de miniatura (Flow)", produccion=p["id"]).get("prompt") or base)
    except Exception:  # noqa: BLE001 - sin IA, el prompt base ya sirve
        pass
    return (f"PROMPT PARA GOOGLE FLOW (pégalo tal cual, formato 16:9):\n\n{base}\n\n"
            f"TEXTO PARA PONER ENCIMA (en mayúsculas, 2-4 palabras): {texto.upper()}\n\n"
            "Después: descarga la imagen, ponle el texto y súbela como miniatura en YouTube.\n")


def preparar(mid: str) -> Path:
    """Crea (o rehace) la carpeta de entrega del vídeo y su .zip. Devuelve la carpeta."""
    p = montaje.cargar(mid)
    if not p.get("final"):
        raise ValueError("El vídeo aún no está terminado: primero el montaje final.")
    base = montaje.carpeta(mid)
    try:
        canal = canales.obtener(p.get("canal") or "fourlevel")["nombre"]
    except ValueError:
        canal = "Canal"
    fecha = time.strftime("%Y-%m-%d")
    destino = carpetas.RAIZ_USUARIO / _nombre_limpio(canal, 40) / f"{fecha} · {_nombre_limpio(p['titulo'])}"
    if destino.exists():
        shutil.rmtree(destino, ignore_errors=True)
    (destino / "Miniaturas").mkdir(parents=True)
    (destino / "Subtítulos").mkdir()
    (destino / "Proyecto (para reeditar)").mkdir()
    for origen, nombre in FORMATOS:
        if (base / origen).exists():
            shutil.copy2(base / origen, destino / nombre)
    if (base / "miniatura.jpg").exists():
        shutil.copy2(base / "miniatura.jpg", destino / "Miniaturas" / "miniatura elegida.jpg")
    for k, c in enumerate(p.get("miniatura_candidatos") or [], 1):
        if (base / c["archivo"]).exists():
            shutil.copy2(base / c["archivo"], destino / "Miniaturas" / f"opción {k}.jpg")
    for srt in base.glob("subtitulos*.srt"):
        idioma = srt.stem.split(".", 1)[1] if "." in srt.stem else "es"
        shutil.copy2(srt, destino / "Subtítulos" / f"subtítulos.{idioma}.srt")
    (destino / "Textos para publicar.txt").write_text(textos_para_publicar(p, base), encoding="utf-8")
    (destino / "Miniaturas" / "Prompt para Google Flow.txt").write_text(prompt_miniatura_flow(p), encoding="utf-8")
    proyecto = destino / "Proyecto (para reeditar)"
    (proyecto / "guion.txt").write_text(p.get("guion", ""), encoding="utf-8")
    for archivo in ("voz.wav", "linea_de_tiempo.json", "proyecto.json", "Fuentes y créditos.txt"):
        if (base / archivo).exists():
            shutil.copy2(base / archivo, proyecto / archivo)
    (destino / "LÉEME.txt").write_text(LEEME.format(titulo=p["titulo"], canal=canal, fecha=fecha), encoding="utf-8")
    zip_ = base / "paquete.zip"   # el .zip vive con el vídeo: el panel lo ofrece para descargar
    with zipfile.ZipFile(zip_, "w", compression=zipfile.ZIP_STORED) as z:   # los vídeos ya van comprimidos
        for f in destino.rglob("*"):
            if f.is_file():
                z.write(f, Path(destino.name) / f.relative_to(destino))
    montaje.modificar(mid, lambda q: q.update(paquete={"carpeta": str(destino), "zip": "paquete.zip", "hecho": time.strftime("%Y-%m-%d %H:%M")}))
    return destino


def terminar(mid: str) -> Path:
    """Cierra la edición: carpeta y .zip al día y el vídeo marcado como terminado (el panel invita a otro)."""
    destino = preparar(mid)
    montaje.modificar(mid, lambda q: q.update(terminado={"hecho": time.strftime("%Y-%m-%d %H:%M")}))
    subir_a_drive(mid)
    return destino


def subir_a_drive(mid: str) -> str:
    """Sube la carpeta de entrega a Drive si Google está conectado (si no, no hace nada). Devuelve el enlace."""
    from . import drive
    p = montaje.cargar(mid)
    carpeta_local = Path((p.get("paquete") or {}).get("carpeta", ""))
    if not drive.conectado() or not carpeta_local.is_dir():
        return ""
    try:
        canal = canales.obtener(p.get("canal") or "fourlevel")["nombre"]
    except ValueError:
        canal = "Canal"
    try:
        enlace = drive.subir_carpeta(carpeta_local, canal)
    except Exception as e:  # noqa: BLE001 - el vídeo ya está en tu PC: Drive se reintenta con su botón
        motivo = str(e)[:300]
        montaje.modificar(mid, lambda q: q.setdefault("paquete", {}).update(drive_error=motivo))
        return ""
    montaje.modificar(mid, lambda q: q.setdefault("paquete", {}).update(drive=enlace, drive_error="", drive_subido=time.strftime("%Y-%m-%d %H:%M")))
    return enlace


def reabrir(mid: str) -> None:
    """Seguir editando un vídeo ya cerrado: vuelve al paso 5 con todo su trabajo."""
    montaje.modificar(mid, lambda q: q.pop("terminado", None))
