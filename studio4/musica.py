"""La música de fondo del panel nuevo: pistas de la Biblioteca de audio de YouTube (seguras para monetizar).

YouTube no deja descargar esa biblioteca de forma automática: el autor baja las pistas desde YouTube Studio →
Biblioteca de audio y las guarda en «Vídeos\\STUDIO 4\\Música». Aquí se catalogan solas (título y artista del
nombre del archivo, duración y volumen medido para igualarlas) y el autor les pone el ánimo y, si la pista lo
pide, el texto de atribución. Cada vídeo usa una pista elegida, la automática (por ánimo y la menos usada), el
fondo suave propio o ninguna. Nada se descarga de YouTube Music: esas canciones tienen Content ID.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from . import carpetas, config, medios

EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
ANIMOS = ("épica", "tensión", "misterio", "acción", "oscura", "tranquila", "nostalgia", "emotiva", "alegre", "inspiradora")
OBJETIVO_LUFS = -14.0          # cada pista se iguala a este volumen antes de bajarla con VOLUMEN_MUSICA
LICENCIA = "Biblioteca de audio de YouTube"
# Modos de un vídeo (p["musica"]): "auto", "cama" (el fondo suave propio), "nada" o el nombre de un archivo
AUTO, CAMA, NADA = "auto", "cama", "nada"
_cerrojo = threading.Lock()

# Palabras del guion que piden un ánimo (raíz de 5 letras: «misterio» y «misteriosa» cuentan igual)
PISTAS_ANIMO = {
    "épica": ("leyen", "histo", "épico", "épica", "grand", "legad", "heren", "revol"),
    "tensión": ("polic", "perse", "escap", "peli", "riesg", "alarm", "rastr", "robar", "robo ", "asalt"),
    "misterio": ("miste", "secre", "nadie", "confi", "oculto", "rumor", "teorí"),
    "acción": ("pelea", "golpe", "lucha", "carre", "dispa", "explo", "pandi"),
    "oscura": ("noche", "oscur", "crime", "muert", "calle"),
    "nostalgia": ("recue", "años ", "2005", "clási", "infan", "olvid", "ps2"),
    "emotiva": ("famil", "amor ", "perdi", "triste"),
    "alegre": ("diver", "graci", "risa ", "fiest"),
    "inspiradora": ("logro", "sueño", "futur", "nuevo"),
}


def carpeta() -> Path:
    c = carpetas.carpeta_musica()
    c.mkdir(parents=True, exist_ok=True)
    return c


def _ruta_catalogo() -> Path:
    return config.PRODUCCIONES / "_musica.json"


def _leer() -> dict[str, Any]:
    try:
        return json.loads(_ruta_catalogo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pistas": {}}


def _escribir(d: dict[str, Any]) -> None:
    ruta = _ruta_catalogo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ruta)


def _titulo_artista(stem: str) -> tuple[str, str]:
    """La Biblioteca de audio guarda «Título - Artista»; si no, el nombre entero es el título."""
    limpio = re.sub(r"[_]+", " ", stem).strip()
    if " - " in limpio:
        t, a = limpio.rsplit(" - ", 1)
        return t.strip(), a.strip()
    return limpio, ""


def _lufs(ruta: Path) -> float:
    log = medios.ffmpeg("-i", str(ruta), "-vn", "-af", "ebur128", "-f", "null", "-")
    valores = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    return float(valores[-1]) if valores else OBJETIVO_LUFS


def catalogo() -> list[dict[str, Any]]:
    """Las pistas de la carpeta, catalogadas (las nuevas se miden ahora; las que ya no están se olvidan)."""
    with _cerrojo:
        d = _leer()
        pistas = d.setdefault("pistas", {})
        en_carpeta = {f.name: f for f in sorted(carpeta().iterdir()) if f.is_file() and f.suffix.lower() in EXT}
        for nombre in list(pistas):
            if nombre not in en_carpeta:
                pistas.pop(nombre)
        for nombre, f in en_carpeta.items():
            huella = f"{f.stat().st_size}:{int(f.stat().st_mtime)}"
            p = pistas.get(nombre)
            if p and p.get("huella") == huella:
                continue
            titulo, artista = _titulo_artista(f.stem)
            try:
                duracion, lufs = round(medios.duracion(f), 1), round(_lufs(f), 1)
            except (ValueError, RuntimeError):
                continue   # un archivo que no es audio válido no entra
            viejo = p or {}
            pistas[nombre] = {"archivo": nombre, "titulo": viejo.get("titulo") or titulo, "artista": viejo.get("artista") or artista,
                              "duracion": duracion, "lufs": lufs, "huella": huella, "animo": viejo.get("animo", []),
                              "atribucion": viejo.get("atribucion", ""), "usos": viejo.get("usos", []), "licencia": LICENCIA}
        _escribir(d)
        return sorted(pistas.values(), key=lambda p: (p["titulo"].lower(), p["archivo"]))


def etiquetar(archivo: str, animo: list[str] | None = None, atribucion: str | None = None,
              titulo: str | None = None, artista: str | None = None) -> dict[str, Any]:
    catalogo()
    with _cerrojo:
        d = _leer()
        p = d["pistas"].get(archivo)
        if not p:
            raise ValueError("Esa pista no está en tu carpeta de música.")
        if animo is not None:
            p["animo"] = [a for a in ANIMOS if a in animo]
        if atribucion is not None:
            p["atribucion"] = atribucion.strip()[:400]
        if titulo is not None and titulo.strip():
            p["titulo"] = titulo.strip()[:120]
        if artista is not None:
            p["artista"] = artista.strip()[:80]
        _escribir(d)
        return p


def ruta(archivo: str) -> Path | None:
    """El archivo de una pista del catálogo (nunca una ruta suelta: solo nombres de la carpeta)."""
    if not archivo or "/" in archivo or "\\" in archivo:
        return None
    f = carpeta() / archivo
    return f if f.is_file() and f.suffix.lower() in EXT else None


def animos_de(texto: str) -> list[str]:
    """Los ánimos que pide un guion, del más claro al menos."""
    t = f" {texto.lower()} "
    cuenta = {a: sum(t.count(p) for p in pistas) for a, pistas in PISTAS_ANIMO.items()}
    return [a for a, n in sorted(cuenta.items(), key=lambda x: -x[1]) if n]


def elegir(p: dict[str, Any]) -> dict[str, Any] | None:
    """La pista de un vídeo según su modo. None = sin canción (el montaje usa la cama suave o nada)."""
    modo = p.get("musica") or AUTO
    if modo in (CAMA, NADA):
        return None
    pistas = catalogo()
    if not pistas:
        return None
    if modo != AUTO:
        return next((x for x in pistas if x["archivo"] == modo), None)
    pedidos = animos_de(f"{p.get('titulo', '')} {p.get('guion', '')}")
    peso = {a: len(pedidos) - k for k, a in enumerate(pedidos)}

    def puntos(x: dict[str, Any]) -> tuple:
        return (sum(peso.get(a, 0) for a in x.get("animo", [])), -len(x.get("usos", [])), x["archivo"])
    return max(pistas, key=puntos)


def ganancia(pista: dict[str, Any]) -> float:
    """Cuánto subir o bajar la pista para igualarla a las demás (entre ×0,25 y ×4)."""
    return max(0.25, min(4.0, 10 ** ((OBJETIVO_LUFS - float(pista.get("lufs", OBJETIVO_LUFS))) / 20)))


def apuntar_uso(archivo: str, video: str) -> None:
    with _cerrojo:
        d = _leer()
        p = d.get("pistas", {}).get(archivo)
        if p and video not in p.setdefault("usos", []):
            p["usos"].append(video)
            _escribir(d)


def credito(pista: dict[str, Any]) -> str:
    """La línea para «Fuentes y créditos» y la descripción (con la atribución si la pista la pide)."""
    nombre = pista["titulo"] + (f" — {pista['artista']}" if pista.get("artista") else "")
    return pista.get("atribucion") or f"Música: «{nombre}» ({LICENCIA})"
