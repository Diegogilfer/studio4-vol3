"""Imágenes y vídeo por la API de Google (DE PAGO, fuera de tu suscripción): la alternativa a Flow cuando
no quieres generar a mano. Siempre con un presupuesto: antes de cada llamada se comprueba que el gasto
acumulado no lo supere, y si fuera a pasarse, se para.

- Personajes: primero un retrato de cada uno con su ficha; ese retrato va como referencia en cada escena donde
  sale, para que la cara y la ropa no cambien.
- Imágenes: gemini-3.1-flash-image (~0,02-0,04 $ por imagen; se reserva 0,04 para no pasarse nunca).
- Vídeo: veo-3.1-lite a 720p (0,05 $/s), arrancando de la imagen de su escena, con la duración de su voz (4, 6 u 8 s).
Precios de septiembre de 2026 (ai.google.dev/gemini-api/docs/pricing): cámbialos aquí si Google los cambia.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from google.genai import types

from . import config, gemini, registro

logger = logging.getLogger("studio4.visuales_api")

MODELO_IMAGEN = "gemini-3.1-flash-image"
MODELO_VIDEO = "veo-3.1-lite-generate-preview"
PRECIO_IMAGEN = 0.04           # $ por imagen (reserva prudente: el precio real está entre 0,02 y 0,04)
PRECIO_VIDEO_SEGUNDO = 0.05    # $ por segundo, 720p
SEGUNDOS_VIDEO = 8


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


def estimar(escenas: list[dict], personajes: int = 0) -> dict:
    """Lo que costaría rellenar las escenas que aún no tienen clip: todo como recomienda el plan, o solo imágenes."""
    pendientes = [e for e in escenas if e.get("elegida") is None]
    videos = [e for e in pendientes if e.get("tipo_clip") == "video"]
    seg = sum(segundos_clip(e.get("segundos") or 8) for e in videos)
    base = (len(pendientes) + personajes) * PRECIO_IMAGEN
    return {"escenas": len(pendientes), "videos": len(videos), "segundos_video": seg, "personajes": personajes,
            "coste_todo": round(base + seg * PRECIO_VIDEO_SEGUNDO, 2), "coste_imagenes": round(base, 2)}


def imagen(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, referencia: Optional[Path] = None,
           produccion: str = "", referencias: Optional[list[Path]] = None) -> Path:
    presupuesto.reservar(PRECIO_IMAGEN, "Una imagen")
    contenido: list = []
    refs = [r for r in ([referencia] if referencia else []) + list(referencias or []) if r and r.exists()][:3]
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


def video(prompt: str, aspecto: str, destino: Path, presupuesto: Presupuesto, imagen_inicial: Optional[Path] = None,
          produccion: str = "", segundos: int = SEGUNDOS_VIDEO) -> Path:
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


def generar_escenas(escenas: list[dict], aspecto: str, presupuesto: Presupuesto, recibir: Callable[[Path, str, int], None],
                    con_video: set[int] = frozenset(), produccion: str = "",
                    avisar: Callable[[str, int], None] = lambda *_: None, fichas: Optional[list[dict]] = None,
                    retratos: Optional[Path] = None) -> dict:
    """Genera lo que falta en cada escena y lo entrega con `recibir(archivo, mime, orden)` (la misma vía que Flow).
    Primero los retratos de los personajes (se guardan en `retratos` y se reutilizan si ya estaban)."""
    hechas, estilo = [], None
    trabajo = Path(tempfile.mkdtemp(prefix="studio4_api_", dir=config.PRODUCCIONES))
    caras: dict[str, Path] = {}
    for f in fichas or []:
        destino = (retratos or trabajo) / f"retrato_{f['nombre'].lower()}.png"
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            avisar(f"Retrato de {f['nombre']} ({presupuesto.gastado:.2f} $ de {presupuesto.limite:.2f} $)", 3)
            imagen(f["prompt"], "3:4", destino, presupuesto, produccion=produccion)
        caras[f["nombre"].upper()] = destino
    pendientes = [e for e in escenas if e.get("elegida") is None]
    for i, e in enumerate(pendientes):
        n = e["orden"]
        avisar(f"Escena {n}: {'vídeo' if n in con_video else 'imagen'} ({presupuesto.gastado:.2f} $ de {presupuesto.limite:.2f} $)",
               5 + int(90 * i / max(1, len(pendientes))))
        foto = trabajo / f"escena_{n:02d}.png"
        salen = [caras[c] for c in caras if f"{c} is" in e["prompt_flow"]]
        imagen(e["prompt_flow"], aspecto, foto, presupuesto, referencias=salen or ([estilo] if estilo else []), produccion=produccion)
        estilo = estilo or foto      # sin personajes, la primera escena marca la luz y el estilo
        if n in con_video:
            clip = trabajo / f"escena_{n:02d}.mp4"
            try:
                video(e["prompt_flow"], aspecto, clip, presupuesto, imagen_inicial=foto, produccion=produccion,
                      segundos=segundos_clip(e.get("segundos") or SEGUNDOS_VIDEO))
                recibir(clip, "video/mp4", n)
                hechas.append((n, "video"))
                continue
            except (PresupuestoAgotado, SinFacturacion):
                raise
            except Exception as err:  # noqa: BLE001 - si Veo falla, la escena se queda con su imagen
                logger.warning("Vídeo de la escena %d falló (%s): uso la imagen.", n, err)
        copia = foto.with_name(foto.stem + "_envio.png")   # recibir() se queda el archivo; la foto sigue de referencia
        shutil.copy(foto, copia)
        recibir(copia, "image/png", n)
        hechas.append((n, "imagen"))
    shutil.rmtree(trabajo, ignore_errors=True)
    return {"hechas": hechas, "gastado": round(presupuesto.gastado, 4)}
