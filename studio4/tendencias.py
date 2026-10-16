"""Tendencias: qué se está viendo hoy en YouTube en español, y qué le conviene a cada canal.

1. YouTube (gratis, con la clave de solo lectura): lo más visto por país y categoría, y lo más visto de la última
   semana sobre el nicho del canal. De cada vídeo: duración, calidad (HD o no), vistas y vistas por hora.
2. Las cifras se calculan aquí (duraciones, % en HD, qué crece más rápido, etiquetas que se repiten).
3. Gemini (gratis) lo lee y lo convierte en pautas para el canal: nichos, ideas de vídeo, duración y calidad
   recomendadas, consejos y qué evitar.

El informe se guarda en producciones/tendencias/<canal>.json y el guion lo usa como contexto. STUDIO no publica nada.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field

from . import canales, config, gemini, registro, youtube

logger = logging.getLogger("studio4.tendencias")

REGIONES = {"ES": "España", "MX": "México", "AR": "Argentina", "CO": "Colombia"}
CATEGORIAS = {"": "General", "28": "Ciencia y tecnología", "27": "Educación", "24": "Entretenimiento"}
CADUCA_HORAS = 24
_estado: dict[str, dict[str, Any]] = {}      # canal → {"ocupado", "fase", "error"}
_lock = threading.Lock()


# --- 1. Recoger ---------------------------------------------------------------------------------
def _segundos(iso: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _video(v: dict[str, Any], origen: str) -> dict[str, Any]:
    publicado = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
    horas = max(1.0, (datetime.now(timezone.utc) - publicado).total_seconds() / 3600)
    vistas = int(v.get("statistics", {}).get("viewCount", 0))
    return {"id": v["id"], "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
            "categoria": v["snippet"].get("categoryId", ""), "etiquetas": v["snippet"].get("tags", [])[:15],
            "segundos": _segundos(v["contentDetails"].get("duration", "")),
            "hd": v["contentDetails"].get("definition") == "hd", "vistas": vistas,
            "vistas_hora": round(vistas / horas), "horas": round(horas), "origen": origen,
            "url": f"https://youtu.be/{v['id']}"}


def _populares(region: str, categoria: str) -> list[dict[str, Any]]:
    params = {"part": "snippet,contentDetails,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": 50}
    if categoria:
        params["videoCategoryId"] = categoria
    try:
        d = youtube._get("videos", **params)
    except RuntimeError as e:
        if " 404 " in str(e):   # esa categoría no tiene lista de populares en ese país
            return []
        raise
    origen = f"{REGIONES[region]} · {CATEGORIAS[categoria]}"
    return [_video(v, origen) for v in d.get("items", [])]


def _del_nicho(nicho: str) -> list[dict[str, Any]]:
    """Lo más visto de los últimos 7 días sobre el nicho (100 unidades de las 10.000 diarias)."""
    desde = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = youtube._get("search", part="snippet", q=nicho, type="video", order="viewCount", maxResults=25,
                     publishedAfter=desde, relevanceLanguage="es")
    ids = [i["id"]["videoId"] for i in d.get("items", [])]
    if not ids:
        return []
    v = youtube._get("videos", part="snippet,contentDetails,statistics", id=",".join(ids))
    return [_video(x, f"Nicho · {nicho}") for x in v.get("items", [])]


def _filtro_canal(usuario: str) -> dict[str, str]:
    return {"id": usuario} if usuario.startswith("UC") else {"forHandle": usuario}


def del_referente(usuario: str) -> dict[str, Any]:
    """Un canal que te inspira: sus datos y sus ~25 vídeos más recientes con vistas por hora (3 unidades de cupo)."""
    d = youtube._get("channels", part="snippet,statistics,contentDetails", **_filtro_canal(usuario))
    if not d.get("items"):
        raise ValueError(f"No encuentro el canal {usuario} en YouTube.")
    ch = d["items"][0]
    subidas = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    try:
        ids = [i["contentDetails"]["videoId"] for i in
               youtube._get("playlistItems", part="contentDetails", playlistId=subidas, maxResults=25).get("items", [])]
    except RuntimeError:
        ids = []
    nombre = ch["snippet"]["title"]
    videos = [_video(v, f"Referente · {nombre}") for v in youtube._get(
        "videos", part="snippet,contentDetails,statistics", id=",".join(ids)).get("items", [])] if ids else []
    return {"canal": nombre, "usuario": usuario, "suscriptores": int(ch["statistics"].get("subscriberCount", 0)),
            "videos": sorted(videos, key=lambda v: -v["vistas_hora"])}


def parecidos(canal: dict[str, Any], n: int = 8) -> list[dict[str, Any]]:
    """Canales de YouTube en español del mismo nicho, de más a menos suscriptores (101 unidades de cupo)."""
    tema = canal.get("nicho") or canal["nombre"]
    d = youtube._get("search", part="snippet", q=tema, type="channel", maxResults=25, relevanceLanguage="es")
    ids = [i["snippet"]["channelId"] for i in d.get("items", [])]
    if not ids:
        return []
    datos = youtube._get("channels", part="snippet,statistics", id=",".join(ids)).get("items", [])
    propios = {canal["redes"].get("youtube", "").lower()}
    salida = [{"canal": c["snippet"]["title"], "usuario": c["snippet"].get("customUrl") or c["id"],
               "suscriptores": int(c["statistics"].get("subscriberCount", 0)), "videos": int(c["statistics"].get("videoCount", 0)),
               "foto": c["snippet"]["thumbnails"].get("default", {}).get("url", "")}
              for c in datos if (c["snippet"].get("customUrl") or "").lower() not in propios]
    registro.apuntar("YouTube (lectura)", f"canales parecidos a {canal['nombre']}", unidad="consultas")
    return sorted(salida, key=lambda c: -c["suscriptores"])[:n]


def recoger(nicho: str = "", avisar=lambda _f: None) -> list[dict[str, Any]]:
    vistos: dict[str, dict[str, Any]] = {}
    for region in REGIONES:
        avisar(f"Lo más visto en {REGIONES[region]}")
        for categoria in CATEGORIAS:
            for v in _populares(region, categoria):
                vistos.setdefault(v["id"], v)
    if nicho:
        avisar(f"Lo más visto esta semana sobre «{nicho}»")
        for v in _del_nicho(nicho):
            vistos[v["id"]] = v
    registro.apuntar("YouTube (lectura)", "tendencias", unidad="consultas")
    return list(vistos.values())


# --- 2. Cifras ----------------------------------------------------------------------------------
TRAMOS = [("Hasta 1 min", 60), ("1 a 3 min", 180), ("3 a 10 min", 600), ("10 a 20 min", 1200), ("Más de 20 min", 10**9)]


def metricas(videos: list[dict[str, Any]]) -> dict[str, Any]:
    if not videos:
        return {"total": 0}
    n = len(videos)
    tramos = Counter(next(nombre for nombre, tope in TRAMOS if v["segundos"] <= tope) for v in videos)
    rapidos = sorted(videos, key=lambda v: -v["vistas_hora"])
    etiquetas = Counter(t.lower() for v in videos for t in v["etiquetas"] if 2 < len(t) < 30)
    titulos = [v["titulo"] for v in videos]
    return {
        "total": n,
        "hd": round(100 * sum(v["hd"] for v in videos) / n),
        "duracion_mediana": int(statistics.median(v["segundos"] for v in videos)),
        "duraciones": {nombre: round(100 * tramos[nombre] / n) for nombre, _ in TRAMOS},
        "duracion_mas_rapidos": int(statistics.median(v["segundos"] for v in rapidos[:20])),
        "titulos": {"con_pregunta": round(100 * sum("?" in t for t in titulos) / n),
                    "con_numero": round(100 * sum(bool(re.search(r"\d", t)) for t in titulos) / n),
                    "en_mayusculas": round(100 * sum(sum(c.isupper() for c in t) > len(t) * 0.5 for t in titulos) / n),
                    "largo_medio": round(sum(len(t) for t in titulos) / n)},
        "etiquetas": [t for t, _ in etiquetas.most_common(20)],
        # Para las gráficas del panel: recuentos y los que más crecen (sin enlaces, solo cifras).
        "etiquetas_cuenta": [[t, c] for t, c in etiquetas.most_common(12)],
        "por_pais": [[k, c] for k, c in Counter(v["origen"].split(" · ")[0] for v in videos
                                                  if not v["origen"].startswith("Nicho")).most_common()],
        "por_categoria": [[k, c] for k, c in Counter(v["origen"].split(" · ")[-1] for v in videos
                                                       if not v["origen"].startswith("Nicho")).most_common()],
        "mas_rapidos": [{"titulo": v["titulo"][:90], "canal": v["canal"], "vistas_hora": v["vistas_hora"],
                         "segundos": v["segundos"]} for v in rapidos[:10]],
        "vistas_hora_mediana": int(statistics.median(v["vistas_hora"] for v in videos)),
    }


# --- 3. Pautas con Gemini -----------------------------------------------------------------------
class Nicho(BaseModel):
    nombre: str
    por_que: str = Field(description="Por qué está funcionando ahora, con un dato de los vídeos.")
    ideas: list[str] = Field(description="2 o 3 ideas concretas de vídeo dentro de este nicho.")


class Idea(BaseModel):
    idea: str = Field(description="La idea tal como se escribiría en STUDIO: concreta, con nombre, lugar o hecho.")
    formato: str = Field(description="«corto» (Shorts/Reels) o «largo» (YouTube).")
    por_que: str


class Formula(BaseModel):
    canal: str = Field(description="Nombre del canal de referencia.")
    formula: str = Field(description="Qué repite en sus vídeos que más crecen: tipo de tema, duración, gancho y cómo titula. "
                                     "2 o 3 frases concretas.")
    ideas: list[Idea] = Field(description="2 o 3 ideas ORIGINALES para el canal del autor con esa misma fórmula "
                                          "(nunca sus títulos ni sus temas exactos).")


class Informe(BaseModel):
    resumen: str = Field(description="3 o 4 frases: qué se está viendo hoy y qué significa para este canal.")
    nichos: list[Nicho] = Field(description="3 a 5 nichos con tirón que encajan con el canal.")
    ideas: list[Idea] = Field(description="6 a 8 ideas de vídeo listas para crear.")
    duracion_corto: str = Field(description="Duración recomendada para el vídeo corto, con el porqué.")
    duracion_largo: str = Field(description="Duración recomendada para el vídeo largo, con el porqué.")
    calidad: str = Field(description="Calidad y formato de imagen que conviene (resolución, vertical/horizontal, ritmo).")
    titulos: str = Field(description="Cómo titular hoy: patrones que funcionan, con ejemplo.")
    consejos: list[str] = Field(description="5 a 7 consejos prácticos y concretos.")
    evitar: list[str] = Field(description="2 a 4 cosas que hoy no funcionan o saturan.")
    formulas: list[Formula] = Field(default_factory=list, description="Una por cada canal de referencia (si los hay).")


SISTEMA = """Eres estratega de contenido para canales de YouTube, Shorts, Reels y TikTok en español.
Te doy cifras reales de lo que se está viendo hoy (YouTube, España y Latinoamérica) y los vídeos que más rápido
crecen. Saca pautas útiles para ESTE canal: solo lo que se apoye en los datos, nada genérico. Las ideas deben
encajar con el canal y ser realizables con vídeo generado (Google Flow) y voz en off, sin presentador en cámara.
Las tendencias generales (música, gaming, tráileres…) sirven para el FORMATO (duración, ritmo, títulos, gancho);
los TEMAS e ideas deben quedarse dentro del nicho del canal y de los temas que ya trata. Nunca copies un título
ajeno: las ideas son originales. Español neutro, frases claras, sin emojis."""


def _temas_del_canal(cid: str) -> list[str]:
    from . import produccion   # aquí para no crear un ciclo de imports
    return list(dict.fromkeys(x["titulo"] or x["tema"] for x in produccion.listar(cid)))[:10]


def _texto_para_gemini(canal: dict[str, Any], m: dict[str, Any], videos: list[dict[str, Any]],
                       referentes: list[dict[str, Any]] | None = None) -> str:
    rapidos = sorted(videos, key=lambda v: -v["vistas_hora"])[:40]
    temas = _temas_del_canal(canal["id"])
    lineas = [f"CANAL: {canal['nombre']}" + (f" · nicho: {canal.get('nicho')}" if canal.get("nicho") else "")
              + (f" · tono: {canal.get('tono')}" if canal.get("tono") else "")
              + (f" · público: {canal.get('publico')}" if canal.get("publico") else ""),
              "TEMAS QUE YA TRATA EL CANAL: " + ("; ".join(temas) if temas else "(todavía ninguno)"),
              "", f"CIFRAS ({m['total']} vídeos populares hoy): {json.dumps(m, ensure_ascii=False)}",
              "", "LOS QUE MÁS RÁPIDO CRECEN (vistas por hora · duración · origen · título):"]
    lineas += [f"- {v['vistas_hora']:,}/h · {v['segundos'] // 60}:{v['segundos'] % 60:02d} · {v['origen']} · «{v['titulo']}»"
               .replace(",", ".") for v in rapidos]
    for r in referentes or []:
        lineas += ["", f"CANAL DE REFERENCIA «{r['canal']}» ({r['suscriptores']:,} suscriptores) · sus vídeos recientes que más crecen:".replace(",", ".")]
        lineas += [f"- {v['vistas_hora']:,}/h · {v['segundos'] // 60}:{v['segundos'] % 60:02d} · «{v['titulo']}»".replace(",", ".")
                   for v in r["videos"][:12]]
    if referentes:
        lineas += ["", "Para cada canal de referencia, explica su FÓRMULA y propone ideas originales para este canal con esa "
                       "fórmula: se replica la manera (duración, gancho, ritmo, forma de titular), nunca el contenido."]
    return "\n".join(lineas)


def _archivo(cid: str):
    return config.PRODUCCIONES / "tendencias" / f"{cid}.json"


def leer(cid: str) -> dict[str, Any] | None:
    try:
        return json.loads(_archivo(cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def actualizar(cid: str) -> dict[str, Any]:
    """Recoge, calcula y pide las pautas. Tarda ~30 s (lo lanza el panel en segundo plano)."""
    canal = canales.obtener(cid)
    avisar = lambda fase: _estado.setdefault(cid, {}).update(fase=fase)  # noqa: E731
    videos = recoger(canal.get("nicho", ""), avisar)
    if not videos:
        raise RuntimeError("YouTube no devolvió vídeos populares: revisa la clave de YouTube.")
    m = metricas(videos)
    referentes = []
    for usuario in canal.get("referentes") or []:
        avisar(f"Mirando a tu referente {usuario}")
        try:
            referentes.append(del_referente(usuario))
        except Exception as e:  # noqa: BLE001 - un referente que no se encuentra no frena el informe
            logger.warning("Referente %s: %s", usuario, e)
    avisar("Convirtiendo las cifras en pautas para el canal")
    crudo = gemini.generar(_texto_para_gemini(canal, m, videos, referentes), sistema=SISTEMA, esquema=Informe, temperatura=0.6,
                           detalle=f"tendencias · {canal['nombre']}")
    bloque = re.search(r"\{.*\}", crudo, re.DOTALL)
    informe = Informe.model_validate_json(bloque.group(0) if bloque else crudo).model_dump()
    datos = {"canal": cid, "fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "metricas": m, "informe": informe,
             "referentes": [{"canal": r["canal"], "suscriptores": r["suscriptores"],
                             "videos": [{k: v[k] for k in ("titulo", "vistas", "vistas_hora", "segundos")} for v in r["videos"][:8]]}
                            for r in referentes],
             "rapidos": sorted(videos, key=lambda v: -v["vistas_hora"])[:12]}
    ruta = _archivo(cid)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)
    return datos


def lanzar(cid: str) -> None:
    canales.obtener(cid)
    if not youtube.disponible():
        raise RuntimeError("Las tendencias salen de YouTube: falta YOUTUBE_API_KEY en .env.")
    with _lock:
        if _estado.get(cid, {}).get("ocupado"):
            return
        _estado[cid] = {"ocupado": True, "fase": "Empezando", "error": ""}

    def correr():
        try:
            actualizar(cid)
            _estado[cid].update(ocupado=False, fase="")
        except Exception as e:  # noqa: BLE001 - el error se muestra en el panel
            logger.exception("Tendencias de %s", cid)
            _estado[cid].update(ocupado=False, error=str(e))
    threading.Thread(target=correr, name=f"studio4-tendencias-{cid}", daemon=True).start()


def estado(cid: str) -> dict[str, Any]:
    datos = leer(cid)
    viejo = True
    if datos:
        viejo = time.time() - time.mktime(time.strptime(datos["fecha"], "%Y-%m-%d %H:%M:%S")) > CADUCA_HORAS * 3600
    return {"datos": datos, "caducado": viejo, **_estado.get(cid, {"ocupado": False, "fase": "", "error": ""})}


def para_guion(cid: str) -> dict[str, Any]:
    """Lo que el guion necesita saber de las tendencias del canal (si hay informe guardado; nunca consulta nada)."""
    datos = leer(cid)
    if not datos:
        return {}
    i = datos["informe"]
    return {"fecha": datos["fecha"][:10], "duracion_corto": i["duracion_corto"], "duracion_largo": i["duracion_largo"],
            "titulos": i["titulos"], "consejos": i["consejos"][:5], "evitar": i["evitar"]}
