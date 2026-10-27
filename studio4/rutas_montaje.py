"""Rutas del panel nuevo (montaje 16:9 en 5 pasos), separadas del panel clásico.

servidor.py solo les pasa las peticiones y responde lo que devuelven. El panel nuevo NO carga el código del estudio
antiguo (produccion, flow, director, render…): una prueba lo vigila. Con el clásico comparte solo datos de lectura
(ideas del día, biblioteca, tendencias y canales), por las rutas que ya existían.

Cada función devuelve:  None (la ruta no es del panel nuevo) · ("json", datos) · ("archivo", ruta_en_disco).
"""

from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from . import canales, escaleta, escenas, extractor, linea, montaje, musica, radar

MEDIOS = re.compile(r"^(previa\.mp4|final_16x9\.mp4|short_9x16\.mp4|cuadrado_1x1\.mp4|miniatura(_c\d)?\.jpg|voz\.wav|voz_propia\.wav|subtitulos(\.[a-z]{2,8})?\.srt|storyboard\.jpg)$")


class NoExiste(Exception):
    """Se responde 404."""


def get(ruta: str, query: dict[str, list[str]]) -> tuple[str, Any] | None:
    q = lambda k: (query.get(k) or [""])[0]  # noqa: E731
    if ruta == "/api/m":
        activo = canales.activo()
        # solo los vídeos del canal activo (los antiguos sin canal son de FourLevel): cada canal, lo suyo
        suyos = [v for v in montaje.listar() if (v.get("canal") or "fourlevel") == activo["id"]]
        return "json", {"videos": suyos, "canal": activo,
                        "banco": [{k: f[k] for k in ("id", "nombre", "titulo", "url")} | {"planos": len(f["planos"])}
                                  for f in montaje.banco()]}
    if ruta == "/api/m/musica":   # tu música de la Biblioteca de audio de YouTube, catalogada
        return "json", {"carpeta": str(musica.carpeta()), "pistas": musica.catalogo(), "animos": list(musica.ANIMOS)}
    m = re.fullmatch(r"/api/m/voces-guardadas/([0-9a-f]{16})\.wav", ruta)   # escuchar una voz de tu biblioteca
    if m:
        return "archivo", montaje.archivo_voz_guardada(m.group(1))
    if ruta == "/api/m/subs-vista":   # un fotograma con los subtítulos como quedarían (antes de aplicarlos)
        cambios = {k: q(k) for k in ("estilo", "posicion", "tamano") if q(k)}
        if q("activos"):
            cambios["activos"] = q("activos") in ("1", "true")
        return "archivo", montaje.vista_subtitulos(q("id"), cambios, q("formato") or "16x9")
    m = re.fullmatch(r"/m/([\w-]+)/adjuntos/([0-9a-f]{12}\.jpg)", ruta)   # las imágenes adjuntas en el chat
    if m:
        return "archivo", montaje.adjunto(m.group(1), m.group(2))
    if ruta == "/api/m/biblioteca-chat":   # la Biblioteca con chat: conversación, ideas guardadas y bases
        from . import buscador
        cid = canales.activo()["id"]
        return "json", {**buscador.leer(cid), "bases": buscador.bases(cid), "canal": canales.activo()["nombre"]}
    if ruta == "/api/m/inicio-chat":   # el chat de la portada del canal activo
        from . import asistente
        return "json", {"chat": asistente.leer(canales.activo()["id"]), "canal": canales.activo()["nombre"]}
    if ruta == "/api/m/estilos":   # los estilos de producción: quién los hace, modelos recomendados y coste
        from . import estilos
        return "json", {"estilos": estilos.catalogo(), "canal": canales.activo().get("estilo", "")}
    if ruta == "/api/m/planes":   # las suscripciones, sacadas de lo que cuesta producir (sin costes ni márgenes)
        from . import planes
        return "json", {"planes": planes.para_clientes(), "prueba": planes.prueba()}
    if ruta == "/api/m/nube":   # la copia en la nube: si está conectada y cuándo se subió por última vez
        from . import nube
        return "json", {"conectada": nube.disponible(), **nube.estado}
    if ruta == "/api/m/musica/cama":   # escuchar el fondo suave del Studio antes de elegirlo
        return "archivo", montaje.muestra_cama()
    m = re.fullmatch(r"/musica/(.+)", ruta)   # escuchar una pista (solo archivos de tu carpeta de música)
    if m:
        f = musica.ruta(urllib.parse.unquote(m.group(1)))
        if not f:
            raise NoExiste(ruta)
        return "archivo", f
    if ruta == "/api/m/flow":   # el enlace de tu herramienta de Google Flow
        return "json", {"enlace": escaleta.herramienta()}
    if ruta == "/api/m/radar":   # juegos/temas en tendencia ahora (varias webs de juegos + GTA Wiki)
        return "json", radar.para_panel(canales.activo()["id"])
    if ruta == "/api/m/conexiones":   # qué APIs del estudio están conectadas (nunca las claves)
        return "json", {"conexiones": montaje.conexiones()}
    if ruta == "/api/m/mantenimiento":   # espacio en disco y versión del descargador
        return "json", {"espacio": montaje.espacio(), "descargador": extractor.descargador()}
    if ruta == "/api/m/linea":   # la línea de tiempo por pistas del vídeo (validada)
        p = montaje.cargar(q("id"))
        tl = linea.desde_montaje(p, {fid: montaje.fuente(fid) for fid in p["fuentes"]})
        return "json", {"linea": tl, "errores": linea.validar(tl)}
    if ruta == "/api/m/ver":
        p = montaje.cargar(q("id"))
        elegida = musica.elegir(p)
        idx = escenas.indice(red=False)
        return "json", {"video": p, "paso": montaje.paso_actual(p), "fuentes": {fid: montaje.fuente(fid) for fid in p["fuentes"]},
                        "escenas": {fid: len(escenas.de_fuente(montaje.fuente(fid), idx)) for fid in p["fuentes"]},
                        "voces": montaje.opciones_voz(), "voces_guardadas": montaje.voces_guardadas(), "coste_voz": montaje.coste_voz(p), "resumen": montaje.resumen(p),
                        "musica": {"modo": p.get("musica") or musica.AUTO, "elegida": elegida["titulo"] if elegida else "",
                                   "pistas": [{"archivo": x["archivo"], "titulo": x["titulo"], "artista": x["artista"],
                                               "animo": x["animo"]} for x in musica.catalogo()]}}
    m = re.fullmatch(r"/m/([\w-]+)/([\w.]+)", ruta)   # los vídeos, la previa, el Short, la miniatura y la voz
    if m:
        if not MEDIOS.match(m.group(2)):
            raise NoExiste(ruta)
        return "archivo", montaje.carpeta(m.group(1)) / m.group(2)
    m = re.fullmatch(r"/m/([\w-]+)/imagenes/(\d{3}_[0-9a-f]{8}\.jpg)", ruta)   # las imágenes puestas en las frases
    if m:
        f = montaje.carpeta(m.group(1)) / "imagenes" / m.group(2)
        if not f.exists():
            raise NoExiste(ruta)
        return "archivo", f
    m = re.fullmatch(r"/canal/([\w-]+)/logo\.png", ruta)   # el logo del canal (en círculo)
    if m:
        logo = montaje.logo_de(m.group(1))
        if not logo:
            raise NoExiste(ruta)
        return "archivo", logo
    m = re.fullmatch(r"/fv/([\w.-]+)/(\d{3})\.jpg", ruta)   # miniaturas de los planos del banco de clips
    if m:
        return "archivo", extractor.CACHE / f"{m.group(1)}_planos" / f"{m.group(2)}.jpg"
    return None


def post(ruta: str, d: dict[str, Any]) -> tuple[str, Any]:
    mid = str(d.get("id", ""))
    num = lambda k: float(d[k]) if d.get(k) not in (None, "") else None  # noqa: E731
    if ruta == "/api/m/desde-biblioteca":   # un guion de la Biblioteca → vídeo nuevo
        return "json", {"ok": True, "id": montaje.desde_biblioteca(str(d.get("item", "")))}
    if ruta == "/api/m/entregar":   # vídeo traído → 16:9, 9:16 y 1:1 (+ subtítulos opcionales y miniatura), sin guion
        from . import entrega
        entrega.entregar(mid, d.get("opciones") or {})
        return "json", {"ok": True}
    if ruta == "/api/m/chat":   # el chat del vídeo: DeepSeek elige acciones del estudio y se ejecutan
        from . import chat
        return "json", chat.responder(mid, str(d.get("mensaje", "")))
    if ruta in ("/api/m/inicio-chat", "/api/m/inicio-chat/limpiar"):   # empezar hablando: nicho, ideas, tendencias o vídeo
        from . import asistente
        cid = canales.activo()["id"]
        if ruta.endswith("/limpiar"):
            asistente.limpiar(cid)
            return "json", {"ok": True}
        return "json", asistente.responder(cid, str(d.get("mensaje", "")))
    if ruta.startswith("/api/m/biblioteca/"):   # chat de la Biblioteca: buscar guiones en las bases y usarlos
        from . import buscador
        cid = canales.activo()["id"]
        accion = ruta.rsplit("/", 1)[1]
        if accion == "chat":
            return "json", buscador.conversar(cid, str(d.get("mensaje", "")))
        if accion == "guardar":
            buscador.guardar_idea(cid, str(d.get("idea", "")))
        elif accion == "quitar":
            buscador.quitar_idea(cid, str(d.get("idea", "")))
        elif accion == "crear":
            return "json", {"ok": True, "id": buscador.crear_video(cid, str(d.get("idea", "")))}
        elif accion == "bases":
            return "json", {"ok": True, "fuentes": buscador.guardar_bases(cid, list(d.get("fuentes") or []))}
        else:
            raise NoExiste(ruta)
        return "json", {"ok": True}
    if ruta == "/api/m/crear-ia":   # idea + duración/formato/tono → la IA busca material, escribe y pone planos
        return "json", {"ok": True, "id": montaje.crear_con_ia(str(d.get("tema", "")), d.get("opciones") or {})}
    if ruta == "/api/m/guion-ia":   # un vídeo con material y sin guion → la IA lo escribe
        montaje.guion_con_ia(mid, d.get("opciones") or {})
        return "json", {"ok": True}
    if ruta == "/api/m/desde-url":   # pega un enlace → vídeo nuevo con ese material bajándose
        return "json", {"ok": True, "id": montaje.desde_url(str(d.get("url", "")))}
    if ruta == "/api/m/desde-idea":   # una idea del día → Studio escribe el guion
        return "json", {"ok": True, "id": montaje.desde_idea(int(d.get("n", -1)))}
    if ruta == "/api/m/nube/sincronizar":   # subir ya a la nube (además de cada 30 min)
        from . import nube
        return "json", {"ok": True, "subidos": nube.sincronizar()}
    if ruta == "/api/m/archivar":   # un vídeo a medias que no se va a terminar sale de la lista
        montaje.archivar(str(d.get("id", "")))
        return "json", {"ok": True}
    if ruta == "/api/m/liberar":
        return "json", {"ok": True, "liberado": montaje.liberar()}
    if ruta == "/api/m/actualizar-descargador":
        return "json", {"ok": True, "version": extractor.actualizar_descargador()}
    if ruta == "/api/m/nuevo":
        return "json", {"ok": True, "id": montaje.crear(str(d.get("titulo", "")), str(d.get("guion", "")))}
    if ruta == "/api/m/planos-escenas":   # el plano del tráiler donde ocurre lo que dice cada frase (GTA Wiki)
        montaje.planos_por_escenas(mid, bool(d.get("todas")))
        return "json", {"ok": True}
    if ruta == "/api/m/proponer":
        return "json", {"ok": True, "propuestas": montaje.proponer(mid)}
    if ruta == "/api/m/musica/etiquetar":
        return "json", {"ok": True, "pista": musica.etiquetar(str(d.get("archivo", "")), d.get("animo"), d.get("atribucion"),
                                                               d.get("titulo"), d.get("artista"))}
    if ruta == "/api/m/musica/carpeta":
        os.startfile(str(musica.carpeta()))  # noqa: S606 - el Explorador en tu PC
        return "json", {"ok": True}
    if ruta == "/api/m/imagen":   # una imagen para una frase: enlace o archivo (base64)
        return "json", {"ok": True, "imagen": montaje.poner_imagen(mid, int(d.get("n", 0)), str(d.get("url", "")).strip(),
                                                                    str(d.get("datos", "")), str(d.get("credito", "")))}
    if ruta == "/api/m/imagen/quitar":
        montaje.quitar_imagen(mid, int(d.get("n", 0)))
        return "json", {"ok": True}
    if ruta == "/api/m/imagenes/buscar":
        return "json", {"ok": True, "imagenes": montaje.buscar_imagenes(mid, str(d.get("consulta", "")))}
    if ruta == "/api/m/storyboard":   # la hoja para aprobar el montaje (se hace en segundos)
        montaje.storyboard(mid)
        return "json", {"ok": True, "url": f"/m/{mid}/storyboard.jpg"}
    if ruta == "/api/m/escaleta":   # la escaleta para pegar en tu herramienta de Google Flow
        return "json", {"ok": True, "escaleta": escaleta.exportar(mid, str(d.get("estilo") or escaleta.ESTILO), d.get("con_ia", True) is not False)}
    if ruta == "/api/m/importar-flow":   # el paquete que exporta la herramienta → fuente del vídeo
        return "json", {"ok": True, **escaleta.importar(mid, str(d["origen"]) if d.get("origen") else None)}
    if ruta == "/api/m/flow/enlace":
        return "json", {"ok": True, "enlace": escaleta.guardar_herramienta(str(d.get("enlace", "")))}
    if ruta == "/api/m/flow/carpeta":
        os.startfile(str(escaleta.carpeta_importar()))  # noqa: S606 - el Explorador en tu PC
        return "json", {"ok": True}
    if ruta == "/api/m/textos":
        return "json", {"ok": True, "textos": montaje.hacer_textos(mid)}
    acciones = {
        "/api/m/guion": lambda: montaje.cambiar_guion(mid, str(d.get("guion", ""))),
        "/api/m/fuente": lambda: montaje.anadir_fuente(mid, str(d.get("url", "")).strip(), num("desde"), num("hasta"),
                                                       str(d.get("nombre", ""))),
        "/api/m/usar-fuente": lambda: montaje.usar_fuente(mid, str(d.get("fuente", ""))),
        "/api/m/material/buscar": lambda: montaje.buscar_material(mid),
        "/api/m/mover": lambda: montaje.mover_frase(mid, int(d.get("n", 0)), int(d.get("direccion", 0))),
        "/api/m/quitar-clip": lambda: montaje.quitar_clip(mid, int(d.get("n", 0))),
        "/api/m/asignar": lambda: montaje.asignar(mid, int(d.get("n", 0)), str(d.get("fuente", "")), int(d.get("plano", 0) or 0),
                                                  d.get("rotulo"), d.get("panel"), list(d.get("mas") or [])),
        "/api/m/previa": lambda: montaje.previa(mid),
        "/api/m/voz": lambda: montaje.elegir_voz(mid, str(d.get("proveedor", "")), str(d.get("nombre", ""))),
        "/api/m/musica/elegir": lambda: montaje.elegir_musica(mid, str(d.get("musica", ""))),
        "/api/m/voz-guardada": lambda: montaje.usar_voz_guardada(mid, str(d.get("voz", ""))),
        "/api/m/subtitulos-rapido": lambda: montaje.subtitulos_rapido(mid, d.get("cambios") or {}),
        "/api/m/corregir-subtitulo": lambda: montaje.corregir_subtitulo(mid, str(d.get("de", "")), str(d.get("a", ""))),
        "/api/m/miniaturas": lambda: montaje.candidatos_miniatura(mid, str(d.get("texto", ""))),
        "/api/m/miniatura/elegir": lambda: montaje.elegir_miniatura(mid, str(d.get("archivo", ""))),
        "/api/m/adjunto/frase": lambda: montaje.imagen_adjunta_en_frase(mid, int(d.get("n", 0)), str(d.get("archivo", ""))),
        "/api/m/velocidad": lambda: montaje.elegir_velocidad(mid, float(d.get("velocidad", 1.0))),
        "/api/m/final": lambda: montaje.montar_final(mid),
        "/api/m/automatico": lambda: montaje.automatico(mid, bool(d.get("pago_ok"))),
        "/api/m/render-basico": lambda: montaje.render_basico(mid, d.get("opciones") or {}),
        "/api/m/cuadrado": lambda: montaje.montar_cuadrado(mid, float(d.get("desde", 0)), float(d.get("hasta", 0))),
        "/api/m/short": lambda: montaje.montar_short(mid, float(d.get("desde", 0)), float(d.get("hasta", 0))),
        "/api/m/miniatura": lambda: montaje.miniatura(mid, str(d.get("texto", ""))[:40], list(d.get("fotos") or [])),
        "/api/m/carpeta": lambda: os.startfile(str(montaje.carpeta(mid))),  # noqa: S606 - el Explorador en tu PC
    }
    if ruta not in acciones:
        raise NoExiste(ruta)
    acciones[ruta]()
    return "json", {"ok": True}


def es_archivo(x: Any) -> bool:
    return isinstance(x, Path)
