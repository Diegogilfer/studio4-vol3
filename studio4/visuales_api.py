"""Imágenes y vídeo por la API de Google (DE PAGO, fuera de tu suscripción): la alternativa a Flow cuando
no quieres generar a mano. Siempre con un presupuesto: antes de cada llamada se comprueba que el gasto
acumulado no lo supere, y si fuera a pasarse, se para.

- Personajes: primero un retrato de cada uno con su ficha; ese retrato va como referencia en cada escena donde
  sale, para que la cara y la ropa no cambien.
- Imágenes: gemini-3.1-flash-image (~0,02-0,04 $ por imagen; se reserva 0,04 para no pasarse nunca).
- Vídeo: veo-3.1-lite a 720p (0,05 $/s), arrancando de la imagen de su escena, con la duración de su voz (4, 6 u 8 s).
Precios de septiembre de 2026 (ai.google.dev/gemini-api/docs/pricing): cámbialos aquí si Google los cambia.

Con FAL_KEY en .env se usa fal.ai en su lugar (saldo prepagado, sin la facturación de Google):
- Imágenes: fal-ai/nano-banana (0,0398 $), y con referencias de personajes fal-ai/nano-banana/edit.
- Vídeo: fal-ai/veo3.1/fast/image-to-video, 720p, sin audio. fal no publica el precio en la ficha:
  se reservan 0,15 $/s (prudente), así el tope nunca se supera.
"""

from __future__ import annotations

import base64
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import requests
from google.genai import types
from pydantic import BaseModel, Field

from . import config, gemini, registro

logger = logging.getLogger("studio4.visuales_api")

MODELO_IMAGEN = "gemini-3.1-flash-image"
MODELO_VIDEO = "veo-3.1-lite-generate-preview"
PRECIO_IMAGEN = 0.04           # $ por imagen (reserva prudente: el precio real está entre 0,02 y 0,04)
PRECIO_VIDEO_SEGUNDO = 0.05    # $ por segundo, 720p
SEGUNDOS_VIDEO = 8
FAL = "https://queue.fal.run"
FAL_IMAGEN, FAL_IMAGEN_REFS = "fal-ai/nano-banana", "fal-ai/nano-banana/edit"
FAL_VIDEO = "fal-ai/veo3.1/fast/image-to-video"
FAL_PRECIO_IMAGEN, FAL_PRECIO_VIDEO_SEGUNDO = 0.04, 0.15


def con_fal() -> bool:
    return bool(config.FAL_KEY) and not config.SIN_PAGO


def precios() -> tuple[float, float]:
    """(imagen, segundo de vídeo) del proveedor que se va a usar."""
    return (FAL_PRECIO_IMAGEN, FAL_PRECIO_VIDEO_SEGUNDO) if con_fal() else (PRECIO_IMAGEN, PRECIO_VIDEO_SEGUNDO)


def _fal_pedir(url: str, cuerpo: Optional[dict] = None) -> dict:
    cab = {"Authorization": f"Key {config.FAL_KEY}"}
    r = requests.post(url, json=cuerpo, headers=cab, timeout=120) if cuerpo is not None else requests.get(url, headers=cab, timeout=60)
    if r.status_code >= 400:
        texto = r.text[:300].replace(config.FAL_KEY, "***")
        if r.status_code == 402 or "balance" in texto.lower() or "locked" in texto.lower():
            raise SinFacturacion("fal.ai no tiene saldo: recárgalo en fal.ai/dashboard/billing.")
        if r.status_code in (401, 403):
            raise SinFacturacion(f"fal.ai rechazó la clave ({r.status_code}): revisa FAL_KEY en .env.")
        if "content_policy_violation" in texto:
            raise Moderada("el filtro de contenido de fal rechazó el plano")
        raise RuntimeError(f"fal.ai respondió {r.status_code}: {texto}")
    return r.json() if r.text else {}


def _fal(modelo: str, cuerpo: dict, limite_s: int = 600) -> dict:
    """Cola de fal: se envía, se pregunta cada pocos segundos (gratis) y se devuelve el resultado."""
    tarea = _fal_pedir(f"{FAL}/{modelo}", cuerpo)
    if not tarea.get("status_url"):
        raise RuntimeError(f"fal.ai no aceptó la petición: {str(tarea)[:200]}")
    fin, espera = time.time() + limite_s, 3.0
    while time.time() < fin:
        estado = str(_fal_pedir(tarea["status_url"]).get("status", "")).upper()
        if estado == "COMPLETED":
            return _fal_pedir(tarea["response_url"])
        if estado in ("FAILED", "ERROR", "CANCELLED"):
            raise RuntimeError(f"fal.ai falló ({estado})")
        time.sleep(espera)
        espera = min(espera * 1.3, 8.0)
    raise RuntimeError(f"fal.ai no terminó en {limite_s // 60} minutos.")


def _data_uri(ruta: Path) -> str:
    mime = "image/jpeg" if ruta.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{base64.b64encode(ruta.read_bytes()).decode('ascii')}"


def quitar_franjas(ruta: Path) -> bool:
    """Algunas imágenes llegan con franjas negras (formato cine dentro del vertical): se recortan para que el
    montaje no las amplíe. Devuelve True si había franjas."""
    from PIL import Image
    im = Image.open(ruta).convert("RGB")
    gris = im.convert("L").point(lambda v: 255 if v > 18 else 0)
    caja = gris.getbbox()
    if not caja or (caja[2] - caja[0]) * (caja[3] - caja[1]) > 0.97 * im.width * im.height:
        return False
    im.crop(caja).save(ruta)
    return True


def _bajar(url: str, destino: Path) -> Path:
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    if len(r.content) < 2000:
        raise RuntimeError("fal.ai devolvió un archivo vacío")
    destino.write_bytes(r.content)
    return destino


def segundos_clip(segundos: float) -> int:
    """Veo genera clips de 4, 6 u 8 s: el más corto que cubre la voz de la escena."""
    return next((s for s in (4, 6, 8) if s >= (segundos or 8) - 0.25), 8)


class Presupuesto:
    def __init__(self, limite_usd: float):
        self.limite = float(limite_usd)
        self.gastado = 0.0

    def reservar(self, coste: float, que: str) -> None:
        if self.gastado + coste > self.limite + 1e-9:
            raise PresupuestoAgotado(f"{que} costaría {coste:.3f} $ y ya van {self.gastado:.3f} $ de {self.limite:.2f} $.")
        self.gastado += coste

    def devolver(self, coste: float) -> None:
        """Una llamada que falla no se cobra: lo reservado vuelve al presupuesto."""
        self.gastado = max(0.0, self.gastado - coste)


class PresupuestoAgotado(RuntimeError):
    pass


class SinFacturacion(RuntimeError):
    pass


class Moderada(RuntimeError):
    """El filtro de contenido del proveedor rechazó el prompt (no se cobra; repetirlo igual no sirve)."""


# Si el filtro rechaza un plano (armas apuntando, violencia), se pide la misma escena contada sin lo explícito.
SUAVIZAR = ("\nSafe framing: no weapon pointed at the camera or at anyone (weapon lowered, holstered or out of frame); "
            "convey the tension through expression, posture, light and setting.")


def estimar(escenas: list[dict], personajes: int = 0) -> dict:
    """Lo que costaría rellenar las escenas que aún no tienen clip: todo como recomienda el plan, o solo imágenes."""
    pendientes = [e for e in escenas if e.get("elegida") is None]
    videos = [e for e in pendientes if e.get("tipo_clip") == "video"]
    seg = sum(segundos_clip(e.get("segundos") or 8) for e in videos)
    precio_imagen, precio_segundo = precios()
    base = (len(pendientes) + personajes) * precio_imagen
    return {"escenas": len(pendientes), "videos": len(videos), "segundos_video": seg, "personajes": personajes,
            "coste_todo": round(base + seg * precio_segundo, 2), "coste_imagenes": round(base, 2)}


def imagen(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, referencia: Optional[Path] = None,
           produccion: str = "", referencias: Optional[list[Path]] = None) -> Path:
    if config.SIN_PAGO:
        raise SinFacturacion("STUDIO4_SIN_PAGO=1 está activo: las imágenes y vídeos por API de pago están apagados.")
    refs = [r for r in ([referencia] if referencia else []) + list(referencias or []) if r and r.exists()][:3]
    if con_fal():
        return _imagen_fal(prompt, aspecto, destino, presupuesto, refs, produccion)
    presupuesto.reservar(PRECIO_IMAGEN, "Una imagen")
    contenido: list = []
    if refs:
        contenido += [types.Part.from_bytes(data=r.read_bytes(), mime_type="image/png") for r in refs]
        contenido.append("Use the image(s) above only as references for the characters' faces, hair and clothes, and for "
                         "the lighting and art style. Do NOT copy their pose or framing. Create a NEW frame for this shot:")
    contenido.append(f"{prompt}\nSingle cinematic still frame, no text, no letters, no watermark.")
    cfg = types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio=aspecto))
    for intento in range(2):
        try:
            r = gemini.cliente().models.generate_content(model=MODELO_IMAGEN, contents=contenido, config=cfg)
            datos = next((p.inline_data.data for p in r.candidates[0].content.parts if p.inline_data and p.inline_data.data), None)
            if datos:
                destino.write_bytes(datos)
                registro.apuntar("Google · imágenes (API de pago)", f"{MODELO_IMAGEN}", cantidad=1, unidad="imágenes",
                                 produccion=produccion, usd=PRECIO_IMAGEN)
                return destino
            raise RuntimeError("la respuesta no trae imagen (¿filtro de seguridad?)")
        except Exception as e:  # noqa: BLE001
            logger.warning("Imagen (intento %d): %s", intento + 1, e)
            if "429" in str(e) and "limit: 0" in str(e):
                presupuesto.devolver(PRECIO_IMAGEN)
                raise SinFacturacion("Tu clave de Gemini está en el nivel gratuito: generar imágenes o vídeo por API "
                                     "exige activar la facturación en Google AI Studio (Configurar facturación).") from e
            if intento:
                presupuesto.devolver(PRECIO_IMAGEN)
                raise RuntimeError(f"No se pudo generar la imagen: {e}") from e
            time.sleep(3)
    raise RuntimeError("No se pudo generar la imagen")


_REFERENCIAS = ("Use the reference image(s) only for the characters' faces, hair and clothes, and for the lighting and "
                "art style. Do NOT copy their pose or framing. Create a NEW frame for this shot: ")


def _imagen_fal(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, refs: list[Path], produccion: str) -> Path:
    presupuesto.reservar(FAL_PRECIO_IMAGEN, "Una imagen")
    cuerpo = {"prompt": f"{_REFERENCIAS if refs else ''}{prompt}\nSingle cinematic still frame, no text, no letters, no watermark.",
              "num_images": 1, "aspect_ratio": aspecto, "output_format": "png"}
    if refs:
        cuerpo["image_urls"] = [_data_uri(r) for r in refs]
    for intento in range(2):
        try:
            res = _fal(FAL_IMAGEN_REFS if refs else FAL_IMAGEN, cuerpo, limite_s=240)
            url = ((res.get("images") or [{}])[0]).get("url")
            if not url:
                raise RuntimeError("la respuesta no trae imagen (¿filtro de seguridad?)")
            _bajar(url, destino)
            quitar_franjas(destino)
            registro.apuntar("fal.ai · imágenes", FAL_IMAGEN_REFS if refs else FAL_IMAGEN, cantidad=1, unidad="imágenes",
                             produccion=produccion, usd=FAL_PRECIO_IMAGEN)
            return destino
        except (SinFacturacion, Moderada):
            presupuesto.devolver(FAL_PRECIO_IMAGEN)
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("Imagen fal (intento %d): %s", intento + 1, e)
            if intento:
                presupuesto.devolver(FAL_PRECIO_IMAGEN)
                raise RuntimeError(f"No se pudo generar la imagen: {e}") from e
            time.sleep(3)
    raise RuntimeError("No se pudo generar la imagen")


def _video_fal(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, imagen_inicial: Optional[Path],
               produccion: str, segundos: int) -> Path:
    if not imagen_inicial or not imagen_inicial.exists():
        raise RuntimeError("Veo por fal necesita la imagen de la escena para arrancar.")
    coste = segundos * FAL_PRECIO_VIDEO_SEGUNDO
    presupuesto.reservar(coste, "Un clip de vídeo")
    try:
        res = _fal(FAL_VIDEO, {"prompt": prompt[:1400], "image_url": _data_uri(imagen_inicial), "duration": f"{segundos}s",
                               "resolution": "720p", "aspect_ratio": aspecto if aspecto in ("16:9", "9:16") else "auto",
                               "generate_audio": False}, limite_s=900)
    except SinFacturacion:
        presupuesto.devolver(coste)
        raise
    url = (res.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai terminó sin vídeo: {str(res)[:160]}")
    _bajar(url, destino)
    registro.apuntar("fal.ai · vídeo Veo 3.1 Fast", f"{FAL_VIDEO} · {segundos} s 720p", cantidad=segundos, unidad="segundos",
                     produccion=produccion, usd=coste)
    return destino


def video(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, imagen_inicial: Optional[Path] = None,
          produccion: str = "", segundos: int = SEGUNDOS_VIDEO) -> Path:
    if config.SIN_PAGO:
        raise SinFacturacion("STUDIO4_SIN_PAGO=1 está activo: las imágenes y vídeos por API de pago están apagados.")
    if con_fal():
        return _video_fal(prompt, aspecto, destino, presupuesto, imagen_inicial, produccion, segundos)
    coste = segundos * PRECIO_VIDEO_SEGUNDO
    presupuesto.reservar(coste, "Un clip de vídeo")
    cliente = gemini.cliente()
    kwargs = {}
    if imagen_inicial and imagen_inicial.exists():
        kwargs["image"] = types.Image(image_bytes=imagen_inicial.read_bytes(), mime_type="image/png")
    try:
        op = cliente.models.generate_videos(
            model=MODELO_VIDEO, prompt=prompt,
            config=types.GenerateVideosConfig(aspect_ratio=aspecto, resolution="720p", duration_seconds=segundos,
                                              number_of_videos=1, generate_audio=False),
            **kwargs)
    except Exception:
        presupuesto.devolver(coste)
        raise
    fin = time.time() + 600
    while not op.done:
        if time.time() > fin:
            raise RuntimeError("Veo tardó más de 10 minutos.")
        time.sleep(10)
        op = cliente.operations.get(op)
    if getattr(op, "error", None):
        raise RuntimeError(f"Veo devolvió un error: {op.error}")
    generado = op.response.generated_videos[0].video
    cliente.files.download(file=generado)
    generado.save(str(destino))
    registro.apuntar("Google · vídeo Veo (API de pago)", f"{MODELO_VIDEO} · {segundos} s 720p",
                     cantidad=segundos, unidad="segundos", produccion=produccion, usd=coste)
    return destino


class Revision(BaseModel):
    personaje_ok: bool = Field(description="¿La persona de la escena es la MISMA del retrato (cara, pelo, ropa)? true si no hay retrato.")
    escena_ok: bool = Field(description="¿La imagen muestra lo que describe el plano y encaja con lo que dice la voz?")
    motivo: str = Field(description="Si algo falla, qué corregir, en inglés y en una frase (p. ej. «hair must be long and wavy»). Vacío si todo encaja.")


def revisar(foto: Path, retratos: list[Path], prompt: str, voz: str, produccion: str = "") -> dict:
    """Gemini (gratis) mira la imagen junto a los retratos: ¿es el mismo personaje y cuenta lo que dice el guion?
    Si Gemini no responde, no bloquea: la imagen se da por buena y queda anotado que no se revisó."""
    try:
        adjuntos = [(r.read_bytes(), "image/png") for r in retratos] + [(foto.read_bytes(), "image/png")]
        crudo = gemini.generar(
            (f"Las {len(retratos)} primeras imágenes son los retratos de referencia de los personajes; la última es una escena "
             if retratos else "La imagen es una escena ") +
            f"de un vídeo.\nPlano pedido: {prompt}\nLo que dice la voz en esa escena: «{voz}»\n"
            "Revisa con criterio estricto si el personaje es el mismo y si la escena cuenta lo pedido.",
            esquema=Revision, temperatura=0.1, detalle="revisión de imagen", produccion=produccion, archivos=adjuntos)
        r = Revision.model_validate_json(crudo).model_dump()
        return {**r, "ok": r["personaje_ok"] and r["escena_ok"], "revisada": True}
    except Exception as e:  # noqa: BLE001
        logger.warning("Revisión de %s no disponible: %s", foto.name, e)
        return {"ok": True, "revisada": False, "personaje_ok": True, "escena_ok": True, "motivo": ""}


def generar_escenas(escenas: list[dict], aspecto: str, presupuesto: Presupuesto, recibir: Callable[[Path, str, int], None],
                    con_video: set[int] = frozenset(), produccion: str = "",
                    avisar: Callable[[str, int], None] = lambda *_: None, fichas: Optional[list[dict]] = None,
                    retratos: Optional[Path] = None) -> dict:
    """Genera lo que falta en cada escena y lo entrega con `recibir(archivo, mime, orden)` (la misma vía que Flow).
    Primero los retratos de los personajes (se guardan en `retratos` y se reutilizan si ya estaban)."""
    hechas, estilo, revisiones = [], None, []
    trabajo = Path(tempfile.mkdtemp(prefix="studio4_api_", dir=config.PRODUCCIONES))
    caras: dict[str, Path] = {}
    pendientes = [e for e in escenas if e.get("elegida") is None]
    # Solo los personajes que salen en lo que falta: los de escenas ya resueltas no se pagan.
    for f in [f for f in fichas or [] if any(f"{f['nombre'].upper()} is" in e["prompt_flow"] for e in pendientes)]:
        destino = (retratos or trabajo) / f"retrato_{f['nombre'].lower()}.png"
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            avisar(f"Retrato de {f['nombre']} ({presupuesto.gastado:.2f} $ de {presupuesto.limite:.2f} $)", 3)
            imagen(f["prompt"], "3:4", destino, presupuesto, produccion=produccion)
        caras[f["nombre"].upper()] = destino
    fallidas: list[dict] = []
    try:
        for i, e in enumerate(pendientes):
            avisar(f"Escena {e['orden']}: {'vídeo' if e['orden'] in con_video else 'imagen'} "
                   f"({presupuesto.gastado:.2f} $ de {presupuesto.limite:.2f} $)", 5 + int(90 * i / max(1, len(pendientes))))
            try:
                rev, tipo = _una_escena(e, aspecto, presupuesto, recibir, trabajo, caras, estilo, e["orden"] in con_video,
                                        produccion, lambda f: avisar(f, 5 + int(90 * i / max(1, len(pendientes)))))
            except (PresupuestoAgotado, SinFacturacion):
                raise
            except Exception as err:  # noqa: BLE001 - una escena que falla no tumba el lote: se queda como estaba
                logger.warning("Escena %d sin imagen: %s", e["orden"], err)
                fallidas.append({"orden": e["orden"], "motivo": str(err)[:200]})
                continue
            estilo = estilo or trabajo / f"escena_{e['orden']:02d}.png"   # sin personajes, la primera marca luz y estilo
            revisiones.append({"orden": e["orden"], **rev})
            hechas.append((e["orden"], tipo))
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
    return {"hechas": hechas, "gastado": round(presupuesto.gastado, 4), "revisiones": revisiones, "fallidas": fallidas}


def _una_escena(e: dict, aspecto: str, presupuesto: Presupuesto, recibir: Callable[[Path, str, int], None], trabajo: Path,
                caras: dict[str, Path], estilo: Optional[Path], con_video: bool, produccion: str,
                avisar: Callable[[str], None]) -> tuple[dict, str]:
    n, prompt = e["orden"], e["prompt_flow"]
    foto = trabajo / f"escena_{n:02d}.png"
    salen = [caras[c] for c in caras if f"{c} is" in prompt]
    refs = salen or ([estilo] if estilo else [])
    try:
        imagen(prompt, aspecto, foto, presupuesto, referencias=refs, produccion=produccion)
    except Moderada:
        avisar(f"Escena {n}: el filtro la rechazó, la cuento sin lo explícito")
        prompt += SUAVIZAR
        imagen(prompt, aspecto, foto, presupuesto, referencias=refs, produccion=produccion)
    rev = revisar(foto, salen, prompt, e.get("texto_voz", ""), produccion)
    if not rev["ok"]:   # una segunda oportunidad, diciéndole qué corregir; si tampoco, se queda la mejor que hay
        avisar(f"Escena {n}: rehaciendo ({rev['motivo'][:60]})")
        otra = foto.with_name(foto.stem + "_b.png")
        try:
            imagen(f"{prompt}\nIMPORTANT FIX: {rev['motivo']}", aspecto, otra, presupuesto, referencias=refs, produccion=produccion)
            rev = {**revisar(otra, salen, prompt, e.get("texto_voz", ""), produccion), "rehecha": True}
            shutil.move(str(otra), str(foto))
        except (PresupuestoAgotado, Moderada):
            rev["rehecha"] = False
    if con_video:
        clip = trabajo / f"escena_{n:02d}.mp4"
        try:
            video(prompt, aspecto, clip, presupuesto, imagen_inicial=foto, produccion=produccion,
                  segundos=segundos_clip(e.get("segundos") or SEGUNDOS_VIDEO))
            recibir(clip, "video/mp4", n)
            return rev, "video"
        except (PresupuestoAgotado, SinFacturacion):
            raise
        except Exception as err:  # noqa: BLE001 - si Veo falla, la escena se queda con su imagen
            logger.warning("Vídeo de la escena %d falló (%s): uso la imagen.", n, err)
    copia = foto.with_name(foto.stem + "_envio.png")   # recibir() se queda el archivo; la foto sigue de referencia
    shutil.copy(foto, copia)
    recibir(copia, "image/png", n)
    return rev, "imagen"
