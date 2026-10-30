"""El chat de Inicio: empiezas hablando, nunca pegando un guion. Le pides un nicho, ideas, tendencias o un vídeo y
el estudio lo hace: busca nichos con datos reales de YouTube, propone guiones con sus fuentes (Biblioteca), enseña
el radar del canal o crea el vídeo (pregunta antes el estilo). DeepSeek elige UNA acción de una lista cerrada y
Studio la valida y la ejecuta; lo de pago nunca se activa desde aquí.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from . import canales, config, deepseek, estilos

MAX_HISTORIA = 30
_cerrojo = threading.Lock()

SISTEMA = """Eres el productor de STUDIO 4 en la pantalla de inicio. Hablas en español, breve y cercano. El usuario
NUNCA necesita traer un guion: tú propones y Studio lo escribe. Elige UNA acción por mensaje:
- "nicho": analizar si unos temas están saturados en YouTube (args: temas = lista de 1-5 temas cortos en español).
- "ideas": proponer guiones con fuentes para el canal (args: pedido = qué ideas busca, en una frase).
- "tendencias": enseñar lo que es tendencia hoy en el canal (sin args).
- "estado": decir cómo van los vídeos que se están montando y los últimos terminados (sin args).
- "crear": crear el vídeo ya (args: tema, estilo, duracion en segundos 15|30|60|180|300|600, formato 16:9|9:16; y si
  el usuario los pide: gancho dato_imposible|pregunta|nadie_conto|contradiccion|final_primero|cuenta_atras,
  ritmo rapido|medio|lento, leyenda viral_dorado|viral_amarillo|viral_cian|viral_rosa|cine|minimal).
  Solo si el usuario ya eligió estilo; si no lo dijo, usa "preguntar_estilo".
- "preguntar_estilo": el usuario quiere un vídeo pero no dijo el estilo (args: tema, duracion).
- "responder": solo contestar (dudas, consejos), sin acción.
Los temas son sobre lo que trata el canal (los juegos, los casos, los mitos), no sobre creadores reales poco conocidos.
Estilos válidos (id: nombre): {estilos}
Devuelve solo JSON: {{"respuesta": "lo que le dices", "accion": "nombre", "args": {{...}}}}"""


def _archivo(cid: str):
    c = config.PRODUCCIONES / "_canales" / cid
    c.mkdir(parents=True, exist_ok=True)
    return c / "inicio_chat.json"


def leer(cid: str) -> list[dict[str, Any]]:
    f = _archivo(cid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _guardar(cid: str, mensajes: list[dict[str, Any]]) -> None:
    _archivo(cid).write_text(json.dumps(mensajes[-MAX_HISTORIA:], ensure_ascii=False, indent=1), encoding="utf-8")


def _pensar(canal: dict[str, Any], historia: list[dict[str, Any]], mensaje: str) -> dict[str, Any]:
    lista = ", ".join(f"{k}: {e['nombre']}" for k, e in estilos.ESTILOS.items())
    previos = "\n".join(f"{m['quien']}: {m['texto']}" for m in historia[-8:])
    contexto = (f"CANAL: {canal['nombre']} · nicho: {canal.get('nicho', '')} · estilo por defecto: "
                f"{canal.get('estilo', '') or 'ninguno'}\n\nCONVERSACIÓN:\n{previos}\n\nUSUARIO: {mensaje}")
    return deepseek.generar_json(SISTEMA.format(estilos=lista), contexto, temperatura=0.4, detalle="chat de inicio")


def _ejecutar(cid: str, accion: str, args: dict[str, Any]) -> dict[str, Any]:
    """La acción elegida, validada. Devuelve lo que pinta el panel bajo la respuesta."""
    if accion == "nicho":
        from . import nichos
        temas = [str(t) for t in (args.get("temas") or []) if str(t).strip()][:nichos.MAX_TEMAS]
        if not temas:
            raise ValueError("Dime sobre qué temas quieres que mire la saturación.")
        resultado = nichos.analizar(temas)
        try:   # además de si está saturado, historias reales con fuente para empezar (si no, el análisis sigue valiendo)
            historias = nichos.historias_reales(temas, canales.obtener(cid))
        except Exception:  # noqa: BLE001 - sin historias, el análisis de saturación sigue valiendo
            historias = {}
        for n in resultado:
            n["historias"] = historias.get(n["tema"]) or next((v for k, v in historias.items() if k.lower() in n["tema"].lower()
                                                               or n["tema"].lower() in k.lower()), [])
        return {"tipo": "nicho", "nichos": resultado}
    if accion == "ideas":
        from . import buscador
        r = buscador.conversar(cid, str(args.get("pedido") or "ideas para el canal"))
        return {"tipo": "ideas", "ideas": r["ideas"]}
    if accion == "estado":   # «¿cómo va el vídeo?»: lo que se monta ahora y lo último terminado
        from . import montaje
        en_curso, hechos = [], []
        for v in montaje.listar()[:30]:
            t = montaje.cargar(v["id"])["trabajo"]
            if t.get("ocupado"):
                en_curso.append({"titulo": v["titulo"], "fase": t.get("fase", ""), "progreso": t.get("progreso", 0)})
            elif v["final"] and len(hechos) < 3:
                hechos.append(v["titulo"])
        return {"tipo": "estado", "en_curso": en_curso, "terminados": hechos}
    if accion == "tendencias":
        from . import radar
        return {"tipo": "tendencias", "senales": radar.guardadas(12, cid)}
    if accion in ("crear", "preguntar_estilo"):
        tema = str(args.get("tema") or "").strip()
        if len(tema) < 4:
            raise ValueError("Dime de qué va el vídeo.")
        duracion = int(args.get("duracion") or 60)
        if accion == "preguntar_estilo" or args.get("estilo") not in estilos.ESTILOS:
            return {"tipo": "estilo", "tema": tema, "duracion": duracion, "estilos": estilos.catalogo()}
        from . import montaje
        mid = montaje.crear_con_ia(tema, {"estilo": args["estilo"], "duracion": duracion, "formato": str(args.get("formato") or "16:9"),
                                          **{k: args[k] for k in ("gancho", "ritmo", "leyenda") if args.get(k)}})
        return {"tipo": "video", "id": mid, "estilo": estilos.ESTILOS[args["estilo"]]["nombre"]}
    return {"tipo": "texto"}


def responder(cid: str, mensaje: str, pensar=_pensar) -> dict[str, Any]:
    mensaje = (mensaje or "").strip()[:1500]
    if not mensaje:
        raise ValueError("Escribe qué vídeo quieres hacer.")
    if not deepseek.disponible():
        raise ValueError("El chat necesita DeepSeek conectado.")
    canal = canales.obtener(cid)
    historia = leer(cid)
    d = pensar(canal, historia, mensaje)
    accion = str(d.get("accion") or "responder")
    try:
        resultado = _ejecutar(cid, accion, d.get("args") if isinstance(d.get("args"), dict) else {})
        error = ""
    except (ValueError, RuntimeError) as e:
        resultado, error = {"tipo": "texto"}, str(e)
    respuesta = str(d.get("respuesta") or "").strip() or "Hecho."
    ahora = time.strftime("%H:%M")
    with _cerrojo:
        _guardar(cid, leer(cid) + [{"quien": "tú", "texto": mensaje, "hora": ahora},
                                   {"quien": "IA", "texto": respuesta, "hora": ahora, "resultado": resultado, "error": error}])
    return {"respuesta": respuesta, "resultado": resultado, "error": error}


def limpiar(cid: str) -> None:
    _guardar(cid, [])

