"""Una producción = una carpeta en producciones/<id>/ con su proyecto.json, la voz, las tomas de Flow y el vídeo final.

Secuencia:
  1. crear()  → Gemini escribe el guion y el plan de escenas, y en seguida se genera la voz.
  2. Flow     → tú generas cada escena en Flow; la extensión trae los clips (flow.py).
  3. render() → FFmpeg ajusta cada clip a su trozo de voz y monta el vídeo final.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Optional

from . import config, director, guion, miniaturas, render, subtitulos, voz

logger = logging.getLogger("studio4.produccion")
_lock = threading.RLock()
_ACTIVA = config.PRODUCCIONES / "activa.txt"


# --- Disco ------------------------------------------------------------------------------------
def carpeta(pid: str) -> Path:
    if not re.fullmatch(r"[\w-]+", pid or ""):
        raise ValueError("Identificador de producción no válido")
    return config.PRODUCCIONES / pid


def cargar(pid: str) -> dict[str, Any]:
    with _lock:
        return json.loads((carpeta(pid) / "proyecto.json").read_text(encoding="utf-8"))


def guardar(p: dict[str, Any]) -> None:
    with _lock:
        p["actualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
        destino = carpeta(p["id"]) / "proyecto.json"
        tmp = destino.with_suffix(".tmp")
        tmp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(destino)


def modificar(pid: str, cambio: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Lee, aplica `cambio` y guarda de forma atómica (los hilos de fondo y el servidor escriben a la vez)."""
    with _lock:
        p = cargar(pid)
        cambio(p)
        guardar(p)
        return p


def activa() -> Optional[str]:
    try:
        pid = _ACTIVA.read_text(encoding="utf-8").strip()
        return pid if (carpeta(pid) / "proyecto.json").exists() else None
    except (OSError, ValueError):
        return None


def activar(pid: str) -> None:
    carpeta(pid)
    _ACTIVA.write_text(pid, encoding="utf-8")


def listar() -> list[dict[str, Any]]:
    salida = []
    for f in sorted(config.PRODUCCIONES.glob("*/proyecto.json"), reverse=True):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            salida.append({"id": p["id"], "tema": p["tema"], "titulo": p.get("titulo", ""), "estado": p["estado"],
                           "creado": p["creado"], "formato": p["formato"]})
        except (OSError, ValueError, KeyError):
            continue
    return salida


def recuperar_trabajos_colgados() -> int:
    """Al arrancar, ninguna fase puede estar en marcha: si el servidor se cerró a mitad, se libera."""
    n = 0
    for f in config.PRODUCCIONES.glob("*/proyecto.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if p.get("trabajo", {}).get("ocupado"):
            p["trabajo"].update(ocupado=False, error=f"Se interrumpió «{p['trabajo'].get('fase', '')}» al cerrar STUDIO: vuelve a lanzarlo.")
            if p.get("estado") in ("escribiendo", "renderizando"):
                p["estado"] = "rodando" if p.get("escenas") else "error"
            guardar(p)
            n += 1
    return n


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "video"


# --- Trabajos en segundo plano ------------------------------------------------------------------
def _avisar(pid: str, fase: str, progreso: int) -> None:
    def cambio(p):
        p["trabajo"].update(fase=fase, progreso=progreso)
    modificar(pid, cambio)


def _en_fondo(pid: str, nombre: str, fn: Callable[[], None]) -> None:
    def correr():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - el error se muestra en el panel
            logger.exception("%s falló", nombre)
            modificar(pid, lambda p: p["trabajo"].update(ocupado=False, error=str(e), fase=f"{nombre}: error"))
        else:
            modificar(pid, lambda p: p["trabajo"].update(ocupado=False, error="", progreso=100))

    with _lock:
        p = cargar(pid)
        if p["trabajo"].get("ocupado"):
            raise RuntimeError(f"Esta producción está ocupada: {p['trabajo'].get('fase')}")
        p["trabajo"] = {"ocupado": True, "nombre": nombre, "fase": nombre, "progreso": 0, "error": ""}
        guardar(p)
    threading.Thread(target=correr, name=f"studio4-{nombre}", daemon=True).start()


# --- Fases ------------------------------------------------------------------------------------
def crear(tema: str, segundos: int, formato: str, estilo: str, proveedor_voz: str) -> str:
    if formato not in config.FORMATOS:
        raise ValueError(f"Formato desconocido: {formato}")
    if proveedor_voz not in voz.PROVEEDORES:
        raise ValueError(f"Voz desconocida: {proveedor_voz}")
    pid = f"{time.strftime('%Y%m%d-%H%M%S')}-{_slug(tema)}"
    carpeta(pid).mkdir(parents=True)
    guardar({
        "id": pid, "creado": time.strftime("%Y-%m-%d %H:%M:%S"), "tema": tema.strip(), "segundos": int(segundos),
        "formato": formato, "estilo": estilo, "proveedor_voz": proveedor_voz, "estado": "escribiendo",
        "trabajo": {}, "guion": "", "titulo": "", "descripcion": "", "hashtags": [], "biblia": {},
        "escenas": [], "escena_activa": 1, "voz": None, "subtitulos": dict(subtitulos.POR_DEFECTO), "final": None,
        "miniaturas": None, "recoger_para": "escenas",
    })
    activar(pid)

    def fases():
        _avisar(pid, "Gemini escribe el guion", 10)
        texto = guion.escribir(tema, int(segundos), produccion=pid)
        modificar(pid, lambda p: p.update(guion=texto))

        _avisar(pid, "Gemini planifica las escenas para Flow", 35)
        plan = director.planificar(texto, estilo, formato, produccion=pid)

        def aplicar(p):
            p.update(titulo=plan["titulo"], descripcion=plan["descripcion"], hashtags=plan["hashtags"],
                     biblia=plan["biblia"], estilo_en=plan["estilo_en"], estado="rodando", escena_activa=1)
            p["escenas"] = [{**e, "tomas": [], "elegida": None} for e in plan["escenas"]]
        modificar(pid, aplicar)
        _generar_voz(pid)

    _en_fondo(pid, "Guion y escenas", fases)
    return pid


def _generar_voz(pid: str) -> None:
    p = cargar(pid)
    _avisar(pid, f"Locución con {voz.PROVEEDORES[p['proveedor_voz']]}", 70)
    segmentos = [e["texto_voz"] for e in p["escenas"]]
    try:
        tiempos = voz.locutar(segmentos, carpeta(pid) / "voz.wav", p["proveedor_voz"], produccion=pid)
    except RuntimeError as e:
        # Cupo diario de Gemini TTS agotado (o ElevenLabs sin créditos): se prueba con la otra voz si existe.
        otra = voz.reserva(p["proveedor_voz"])
        if not otra:
            raise
        logger.warning("Voz %s falló (%s); probando %s", p["proveedor_voz"], e, otra)
        _avisar(pid, f"{voz.PROVEEDORES[p['proveedor_voz']]} falló; uso {voz.PROVEEDORES[otra]}", 75)
        tiempos = voz.locutar(segmentos, carpeta(pid) / "voz.wav", otra, produccion=pid)
    modificar(pid, lambda q: q.update(voz={**tiempos, "archivo": "voz.wav", "generada": time.strftime("%H:%M:%S")}))


def rehacer_voz(pid: str, proveedor: str) -> None:
    if proveedor not in voz.PROVEEDORES:
        raise ValueError(f"Voz desconocida: {proveedor}")
    modificar(pid, lambda p: p.update(proveedor_voz=proveedor))
    _en_fondo(pid, "Voz", lambda: _generar_voz(pid))


def renderizar(pid: str) -> None:
    def fase():
        p = cargar(pid)
        modificar(pid, lambda q: q.update(estado="renderizando"))
        try:
            final = render.renderizar(p, carpeta(pid), avisar=lambda f, n: _avisar(pid, f, n))
        except Exception:
            modificar(pid, lambda q: q.update(estado="rodando"))
            raise
        modificar(pid, lambda q: q.update(estado="terminado", final={
            "archivo": final.name, "renderizado": time.strftime("%Y-%m-%d %H:%M:%S")}))
    _en_fondo(pid, "Render", fase)


# --- Miniaturas --------------------------------------------------------------------------------
def generar_miniaturas(pid: str) -> None:
    def fase():
        p = cargar(pid)
        base = carpeta(pid)
        _avisar(pid, "Sacando fotogramas de tus clips", 15)
        candidatos = miniaturas.extraer_candidatos(p, base)
        # Las imágenes que subiste o generaste en Flow para la miniatura siguen siendo candidatas.
        previas = [c for c in (p.get("miniaturas") or {}).get("candidatos", []) if c.get("origen")]
        candidatos += [c for c in previas if (base / c["archivo"]).exists()]
        _avisar(pid, "Gemini elige el fotograma y escribe el texto", 45)
        e = miniaturas.analizar(p, base, candidatos)
        _avisar(pid, "Componiendo las miniaturas", 85)

        def aplicar(q):
            q["miniaturas"] = {"candidatos": candidatos, "elegido": e["mejor"], "texto": e["texto"],
                               "resalte": e["resalte"], "alternativas": e["alternativas"],
                               "prompt_flow": e["prompt_flow_en"], "foco_x": e["foco_x"], "foco_y": e["foco_y"]}
            miniaturas.componer_todas(q, base)
        modificar(pid, aplicar)
    _en_fondo(pid, "Miniaturas", fase)


def ajustar_miniatura(pid: str, datos: dict[str, Any]) -> dict[str, Any]:
    def cambio(p):
        m = p.get("miniaturas")
        if not m:
            raise ValueError("Primero genera las miniaturas")
        if "elegido" in datos:
            i = int(datos["elegido"])
            if not 0 <= i < len(m["candidatos"]):
                raise ValueError("Esa imagen no existe")
            if i != m["elegido"]:
                m.update(elegido=i, foco_x=0.5, foco_y=0.5)
        if "texto" in datos:
            m["texto"] = " ".join(str(datos["texto"]).split())[:60]
        if "resalte" in datos:
            m["resalte"] = str(datos["resalte"]).strip()[:30]
        for k in ("foco_x", "foco_y"):
            if k in datos:
                m[k] = min(max(float(datos[k]), 0.0), 1.0)
        miniaturas.componer_todas(p, carpeta(pid))
    return modificar(pid, cambio)


def anadir_fuente_miniatura(pid: str, archivo: str, origen: str) -> None:
    """Una imagen subida o generada en Flow para la miniatura: pasa a ser la elegida."""
    def cambio(p):
        m = p.get("miniaturas") or {"candidatos": [], "texto": " ".join((p.get("titulo") or p["tema"]).split()[:3]),
                                    "resalte": "", "alternativas": [], "prompt_flow": ""}
        m["candidatos"].append({"archivo": archivo, "escena": 0, "origen": origen})
        m.update(elegido=len(m["candidatos"]) - 1, foco_x=0.5, foco_y=0.5)
        p["miniaturas"] = m
        miniaturas.componer_todas(p, carpeta(pid))
    modificar(pid, cambio)


# --- Ediciones desde el panel -------------------------------------------------------------------
def editar_escena(pid: str, orden: int, datos: dict[str, Any]) -> dict[str, Any]:
    def cambio(p):
        if not 1 <= orden <= len(p["escenas"]):
            raise ValueError(f"No existe la escena {orden}")
        esc = p["escenas"][orden - 1]
        if "prompt_flow" in datos:
            esc["prompt_flow"] = str(datos["prompt_flow"]).strip()
        if "texto_pantalla" in datos:
            esc["texto_pantalla"] = str(datos["texto_pantalla"]).strip()[:60]
        if "texto_voz" in datos and str(datos["texto_voz"]).strip() != esc["texto_voz"]:
            esc["texto_voz"] = " ".join(str(datos["texto_voz"]).split())
            p["voz"] = None  # la locución ya no corresponde: hay que rehacerla
        if "elegida" in datos:
            i = int(datos["elegida"])
            if not 0 <= i < len(esc["tomas"]):
                raise ValueError("Esa toma no existe")
            esc["elegida"] = i
        if "borrar_toma" in datos:
            i = int(datos["borrar_toma"])
            if not 0 <= i < len(esc["tomas"]):
                raise ValueError("Esa toma no existe")
            toma = esc["tomas"].pop(i)
            (carpeta(pid) / toma["archivo"]).unlink(missing_ok=True)
            if esc["elegida"] is not None:
                esc["elegida"] = None if not esc["tomas"] else min(esc["elegida"] - (esc["elegida"] > i), len(esc["tomas"]) - 1)
    return modificar(pid, cambio)


def ajustar_subtitulos(pid: str, ajustes: dict[str, Any]) -> dict[str, Any]:
    validos = {k: v for k, v in ajustes.items() if k in subtitulos.POR_DEFECTO}
    return modificar(pid, lambda p: p["subtitulos"].update(validos))
