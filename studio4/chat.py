"""El chat del vídeo: le pides cambios en lenguaje normal y el estudio los HACE (no solo los recomienda).

DeepSeek (o Gemini de reserva) recibe el estado real del vídeo y una lista cerrada de acciones que sabe hacer el
estudio; devuelve su respuesta y las acciones a ejecutar. Studio valida cada una contra la lista y la ejecuta con las
mismas funciones que los botones del panel. Nada de comandos sueltos ni de inventar operaciones. Lo de pago (voz de
ElevenLabs) nunca se confirma desde aquí: eso exige tu clic en el panel.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

from . import config, deepseek, gemini, montaje, musica

logger = logging.getLogger("studio4.chat")

MAX_HISTORIA = 40


def _voz(mid: str, a: dict[str, Any]) -> str:
    nombre = str(a.get("nombre", ""))
    if nombre not in config.VOCES_GEMINI:
        raise ValueError(f"Esa voz no existe. Gratis: {', '.join(config.VOCES_GEMINI)}.")
    montaje.elegir_voz(mid, "gemini", nombre)
    return f"Voz cambiada a {nombre} (gratis)."


def _subtitulos(mid: str, a: dict[str, Any]) -> str:
    """Si el vídeo ya está montado, solo se rehacen los subtítulos (segundos), no el vídeo entero."""
    hay_final = bool(montaje.cargar(mid).get("final"))
    montaje.subtitulos_rapido(mid, a)
    return "Subtítulos nuevos en los 3 formatos…" if hay_final else "Subtítulos ajustados."


def _musica(mid: str, a: dict[str, Any]) -> str:
    modo = str(a.get("modo", ""))
    montaje.elegir_musica(mid, modo)
    return f"Música: {modo}."


# acción → (qué hace, argumentos, función). «fondo»: lanza un trabajo (uno solo por mensaje)
ACCIONES: dict[str, dict[str, Any]] = {
    "generar_guion": {"desc": "Escribe (o rehace) el guion con IA investigando el tema", "args": "duracion (15|30|60|180|300|600), formato (16:9|9:16), tono, modo (buscar|inventar)",
                      "fondo": True, "fn": lambda mid, a: (montaje.guion_con_ia(mid, a), "Escribiendo el guion con IA…")[1]},
    "cambiar_guion": {"desc": "Reemplaza el guion por el texto dado (solo lo que dirá la voz)", "args": "guion",
                      "fn": lambda mid, a: (montaje.cambiar_guion(mid, str(a.get("guion", ""))), "Guion actualizado.")[1]},
    "buscar_material": {"desc": "Busca tráilers oficiales y gameplay sin comentario del tema", "args": "", "fondo": True,
                        "fn": lambda mid, a: (montaje.buscar_material(mid), "Buscando material real…")[1]},
    "anadir_material": {"desc": "Añade como material el vídeo de un enlace", "args": "url", "fondo": True,
                        "fn": lambda mid, a: (montaje.anadir_fuente(mid, str(a.get("url", ""))), "Bajando ese material…")[1]},
    "proponer_planos": {"desc": "Pone un plano a cada frase vacía", "args": "",
                        "fn": lambda mid, a: f"Planos puestos en {montaje.proponer(mid)} frases."},
    "planos_por_escenas": {"desc": "Elige el plano del tráiler donde ocurre lo que dice cada frase", "args": "todas (true|false)", "fondo": True,
                           "fn": lambda mid, a: (montaje.planos_por_escenas(mid, bool(a.get("todas"))), "Buscando la escena de cada frase…")[1]},
    "mover_escena": {"desc": "Sube (-1) o baja (+1) una escena", "args": "n, direccion",
                     "fn": lambda mid, a: (montaje.mover_frase(mid, int(a["n"]), int(a["direccion"])), f"Escena {a['n']} movida.")[1]},
    "quitar_clip": {"desc": "Deja una escena sin plano", "args": "n",
                    "fn": lambda mid, a: (montaje.quitar_clip(mid, int(a["n"])), f"Escena {a['n']} sin plano.")[1]},
    "cambiar_voz": {"desc": "Cambia la voz por otra gratis de Google", "args": "nombre", "fn": _voz},
    "cambiar_musica": {"desc": "Música: auto, cama (fondo suave) o nada", "args": "modo (auto|cama|nada)", "fn": _musica},
    "subtitulos": {"desc": "Ajusta los subtítulos", "args": "activos (true|false), estilo (viral|cine), posicion (abajo|arriba|centro), tamano (pequeno|normal|grande)",
                   "fn": _subtitulos},
    "corregir_subtitulo": {"desc": "Corrige una palabra mal escrita en los subtítulos (sin volver a montar)", "args": "de, a", "fondo": True,
                           "fn": lambda mid, a: f"Corregida en {montaje.corregir_subtitulo(mid, str(a.get('de', '')), str(a.get('a', '')))} sitios."},
    "miniaturas": {"desc": "Hace 3 o 4 miniaturas distintas para elegir (opcional: texto grande)", "args": "texto", "fondo": True,
                   "fn": lambda mid, a: (montaje.candidatos_miniatura(mid, str(a.get("texto", ""))), "Haciendo miniaturas para elegir…")[1]},
    "imagen_en_miniatura": {"desc": "Hace la miniatura con una imagen adjunta en el chat", "args": "archivo (de adjuntos), texto", "fondo": True,
                            "fn": lambda mid, a: (montaje._en_fondo(mid, "Miniatura", lambda: montaje.miniatura(
                                mid, str(a.get("texto") or (montaje.cargar(mid).get("textos") or {}).get("texto_miniatura") or "")[:40].upper(),
                                [{"adjunto": str(a.get("archivo", ""))}])), "Miniatura con tu imagen…")[1]},
    "imagen_en_frase": {"desc": "Pone una imagen adjunta en el chat como plano de una frase", "args": "n, archivo (de adjuntos)",
                        "fn": lambda mid, a: (montaje.imagen_adjunta_en_frase(mid, int(a["n"]), str(a.get("archivo", ""))), f"Imagen puesta en la frase {a['n']}.")[1]},
    "ilustrar_isometrico": {"desc": "Pone una maqueta isométrica 3D (hecha con código, gratis) en cada frase sin imagen", "args": "todas (true|false)",
                            "fondo": True, "fn": lambda mid, a: (montaje.ilustrar_isometrico(mid, bool(a.get("todas"))), "Dibujando las maquetas isométricas…")[1]},
    "hacer_previa": {"desc": "Monta la previa rápida para revisar", "args": "", "fondo": True,
                     "fn": lambda mid, a: (montaje.previa(mid), "Montando la previa…")[1]},
    "entregar_formatos": {"desc": "Vídeo traído (sin guion): entrega 16:9, 9:16 y 1:1 con miniatura y, si se pide, subtítulos",
                          "args": "subtitulos (true|false), idioma (original|es|en|zh|ja)", "fondo": True,
                          "fn": lambda mid, a: (__import__("studio4.entrega", fromlist=["x"]).entregar(mid, a), "Entregando los 3 formatos…")[1]},
    "hacerlo_todo": {"desc": "Render completo: vídeo 16:9, Short 9:16, clip 1:1 y miniatura", "args": "", "fondo": True,
                     "fn": lambda mid, a: (montaje.render_basico(mid, {}), "Render completo en marcha (los 3 formatos)…")[1]},
}

SISTEMA = """Eres el asistente de edición de STUDIO #4 dentro de un vídeo concreto. Hablas en español, breve y claro.
Te doy el ESTADO del vídeo y la lista de ACCIONES que el estudio sabe hacer. Si lo que pide el usuario se resuelve con
acciones, elígelas; si es una pregunta, contéstala con el estado. Nunca inventes acciones ni digas que hiciste algo que
no está en tu lista. Como mucho UNA acción que trabaje en segundo plano por mensaje. Lo que cuesta dinero (voz de
pago) no lo activas tú: dile al usuario que lo confirme en el panel.
Devuelve solo JSON: {"respuesta": "lo que le dices", "acciones": [{"accion": "nombre", "args": {...}}]}"""


def _estado(p: dict[str, Any]) -> str:
    t = p.get("trabajo") or {}
    frases = p["frases"]
    return json.dumps({
        "titulo": p["titulo"], "frases": len(frases), "con_plano": sum(1 for f in frases if f.get("clip")),
        "guion_inicio": (p.get("guion") or "")[:1200], "escenas": [{"n": f["n"], "texto": f["texto"][:90], "plano": bool(f.get("clip"))} for f in frases[:40]],
        "material": [montaje.fuente(fid)["titulo"][:60] for fid in p["fuentes"]], "voz": p.get("voz_nombre"),
        "musica": p.get("musica") or musica.AUTO, "subtitulos": p.get("subtitulos") or montaje.SUBS_POR_DEFECTO,
        "formato": p.get("formato_principal", "16:9"), "trabajando": t.get("fase") if t.get("ocupado") else "",
        "previa": bool(p.get("previa")), "final": bool(p.get("final")),
        "adjuntos": [{"archivo": x["archivo"], "nombre": x["nombre"]} for x in (p.get("adjuntos") or [])],
        "miniaturas_para_elegir": [x["archivo"] for x in (p.get("miniatura_candidatos") or [])],
    }, ensure_ascii=False)


def _pensar(p: dict[str, Any], mensaje: str, mid: str) -> dict[str, Any]:
    catalogo = "\n".join(f"- {k}: {v['desc']}" + (f" (args: {v['args']})" if v["args"] else "") for k, v in ACCIONES.items())
    historia = "\n".join(f"{m['quien']}: {m['texto']}" for m in (p.get("chat") or [])[-8:])
    prompt = f"ESTADO:\n{_estado(p)}\n\nACCIONES:\n{catalogo}\n\nCONVERSACIÓN:\n{historia}\n\nUSUARIO: {mensaje}"
    if deepseek.disponible():
        try:
            return deepseek.generar_json(SISTEMA, prompt, temperatura=0.3, detalle="chat del vídeo", produccion=mid)
        except RuntimeError as e:
            logger.warning("Chat: DeepSeek no respondió (%s); contesta Gemini.", e)
    crudo = gemini.generar(prompt + "\n\nResponde solo con el JSON.", sistema=SISTEMA, temperatura=0.3,
                           detalle="chat del vídeo (reserva)", produccion=mid, reserva=False)
    m = re.search(r"\{.*\}", crudo, re.DOTALL)
    return json.loads(m.group(0) if m else crudo)


def responder(mid: str, mensaje: str, pensar: Callable[[dict[str, Any], str, str], dict[str, Any]] = _pensar) -> dict[str, Any]:
    mensaje = (mensaje or "").strip()[:2000]
    if not mensaje:
        raise ValueError("Escribe qué quieres hacer con el vídeo.")
    p = montaje.cargar(mid)
    d = pensar(p, mensaje, mid)
    hechas, errores, en_fondo = [], [], False
    for a in (d.get("acciones") or [])[:5]:
        nombre, args = str((a or {}).get("accion", "")), (a or {}).get("args") or {}
        accion = ACCIONES.get(nombre)
        if not accion:
            errores.append(f"«{nombre}» no es una acción del estudio.")
            continue
        if accion.get("fondo"):
            if en_fondo or montaje.cargar(mid)["trabajo"].get("ocupado"):
                errores.append(f"{nombre}: espera a que termine el trabajo en marcha.")
                continue
            en_fondo = True
        try:
            hechas.append(accion["fn"](mid, args if isinstance(args, dict) else {}))
        except (ValueError, RuntimeError, KeyError, TypeError) as e:
            errores.append(f"{nombre}: {e}")
    respuesta = str(d.get("respuesta") or "").strip() or ("Hecho." if hechas else "No entendí qué hacer.")
    ahora = time.strftime("%H:%M")
    montaje.modificar(mid, lambda q: q.update(chat=((q.get("chat") or []) + [
        {"quien": "tú", "texto": mensaje, "hora": ahora},
        {"quien": "IA", "texto": respuesta, "hora": ahora, "hechas": hechas, "errores": errores}])[-MAX_HISTORIA:]))
    return {"respuesta": respuesta, "hechas": hechas, "errores": errores}
