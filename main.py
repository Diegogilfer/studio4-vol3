"""
main.py - Orquestador Principal de STUDIO 4 Vol. 3
Pipeline Automatizado de Generación de Video Audiovisual

Cadena de ejecución:
Claude (Guion) -> Gemini 2.5 Flash (Director Técnico) -> Google TTS + Pexels -> FFmpeg -> Final Video
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

# Asegurar codificación UTF-8 en stdout y stderr (evita errores en consolas Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

# Importar los módulos del pipeline
from writer import escribir_guion
from gemini_director import estructurar_produccion
from voice import generar_locucion
from video_maker import descargar_broll, ensamblar_video

# Cargar variables de entorno
load_dotenv()


class FormatterConsola:
    """Utilidad de presentación visual de fases y tiempos en consola."""

    AZUL = "\033[94m"
    VERDE = "\033[92m"
    AMARILLO = "\033[93m"
    ROJO = "\033[91m"
    CIAN = "\033[96m"
    MAGENTA = "\033[95m"
    NEGRITA = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def banner(cls, writer_provider: str = "gemini") -> None:
        print(f"\n{cls.CIAN}{cls.NEGRITA}{'=' * 70}")
        print("   🎬  STUDIO 4 Vol. 3  |  Automated AI Video Production Pipeline")
        print(f"   Guionista: {writer_provider.upper()} | Director: GEMINI 2.5 | TTS | Pexels | FFmpeg")
        print(f"{'=' * 70}{cls.RESET}\n")

    @classmethod
    def fase(cls, num: int, total: int, nombre: str, descripcion: str) -> None:
        print(
            f"\n{cls.AZUL}{cls.NEGRITA}[FASE {num}/{total}]{cls.RESET} "
            f"{cls.NEGRITA}{nombre}{cls.RESET} - {cls.AMARILLO}{descripcion}{cls.RESET}"
        )

    @classmethod
    def exito(cls, mensaje: str, duracion: float) -> None:
        print(
            f"{cls.VERDE}✔ {mensaje}{cls.RESET} "
            f"{cls.CIAN}({duracion:.2f}s){cls.RESET}"
        )

    @classmethod
    def alerta(cls, mensaje: str) -> None:
        print(f"{cls.AMARILLO}⚠ {mensaje}{cls.RESET}")

    @classmethod
    def error(cls, mensaje: str) -> None:
        print(f"{cls.ROJO}✖ {mensaje}{cls.RESET}")


def verificar_entorno(writer_provider: str = "gemini") -> list[str]:
    """Verifica la presencia de variables de entorno requeridas."""
    faltantes: list[str] = []
    if writer_provider == "claude" and not os.getenv("ANTHROPIC_API_KEY"):
        faltantes.append("ANTHROPIC_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        faltantes.append("GEMINI_API_KEY")
    if not os.getenv("PEXELS_API_KEY"):
        faltantes.append("PEXELS_API_KEY")
    # Para TTS sirve GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_API_KEY o GEMINI_API_KEY
    if not (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GEMINI_API_KEY")):
        faltantes.append("GOOGLE_APPLICATION_CREDENTIALS o GOOGLE_CLOUD_API_KEY")
    return faltantes


def ejecutar_pipeline(
    tema: str,
    target_seconds: int = 60,
    orientation: str = "landscape",
    voice_name: Optional[str] = None,
    writer_provider: str = "gemini",
    output_video: str = "output/video_final.mp4",
    temp_folder: str = "temp_clips",
) -> dict[str, Any]:
    """
    Ejecuta el ciclo de vida completo de generación de video.
    """
    FormatterConsola.banner(writer_provider=writer_provider)
    t_global_inicio = time.perf_counter()

    # Verificación preventiva de configuración
    faltantes = verificar_entorno(writer_provider=writer_provider)
    if faltantes:
        FormatterConsola.alerta(
            f"Atención: Faltan variables de entorno en .env: {', '.join(faltantes)}"
        )

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(temp_folder)
    temp_dir.mkdir(parents=True, exist_ok=True)

    print(f"📌 Tema del video: {FormatterConsola.NEGRITA}'{tema}'{FormatterConsola.RESET}")
    print(f"📐 Formato: {orientation.upper()} | Duración objetivo: ~{target_seconds}s")
    print(f"✍️  Guionista Creativo: {writer_provider.upper()}\n")

    # =========================================================================
    # FASE 1: GUIONISTA CREATIVO
    # =========================================================================
    label_guionista = f"Guionista Creativo ({writer_provider.capitalize()})"
    FormatterConsola.fase(
        1, 5, label_guionista, "Generando guion con gancho y alta retención"
    )
    t0 = time.perf_counter()
    try:
        guion = escribir_guion(tema=tema, target_seconds=target_seconds, provider=writer_provider)
    except Exception as e:
        FormatterConsola.error(f"Fallo en {label_guionista}: {e}")
        raise

    t_writer = time.perf_counter() - t0
    FormatterConsola.exito(f"Guion redactado ({len(guion.split())} palabras)", t_writer)

    # Guardar copia del guion
    script_file = out_dir / "script.txt"
    script_file.write_text(guion, encoding="utf-8")
    print(f"   📄 Guardado en: {script_file}")

    # =========================================================================
    # FASE 2: DIRECTOR TÉCNICO (GOOGLE GEMINI 2.5 FLASH)
    # =========================================================================
    FormatterConsola.fase(
        2, 5, "Director Técnico (Gemini 2.5)", "Estructurando escenas y términos de B-roll"
    )
    t0 = time.perf_counter()
    try:
        plan_produccion = estructurar_produccion(guion_claude=guion)
    except Exception as e:
        FormatterConsola.error(f"Fallo en Gemini: {e}")
        raise

    t_gemini = time.perf_counter() - t0
    scenes = plan_produccion.get("scenes", [])
    FormatterConsola.exito(
        f"Plan estructurado: '{plan_produccion.get('title')}' con {len(scenes)} escenas",
        t_gemini,
    )

    # Guardar copia del plan de producción
    plan_file = out_dir / "production_plan.json"
    plan_file.write_text(
        json.dumps(plan_produccion, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"   📋 Metadatos y desglose guardados en: {plan_file}")

    # =========================================================================
    # FASE 3: LOCUCIÓN PROFESIONAL (GOOGLE CLOUD TTS)
    # =========================================================================
    FormatterConsola.fase(
        3, 5, "Locución Profesional (Google TTS)", "Sintetizando voz comercial continua"
    )
    t0 = time.perf_counter()
    audio_path = str(out_dir / "audio.wav")
    try:
        kwargs_tts = {"texto_completo": guion, "output_path": audio_path}
        if voice_name:
            kwargs_tts["voice_name"] = voice_name
        generar_locucion(**kwargs_tts)
    except Exception as e:
        FormatterConsola.error(f"Fallo en Google Cloud TTS: {e}")
        raise

    t_voice = time.perf_counter() - t0
    FormatterConsola.exito("Pista de locución WAV masterizada", t_voice)
    print(f"   🎙  Audio guardado en: {audio_path}")

    # =========================================================================
    # FASE 4: METRAJE CINEMATOGRÁFICO (PEXELS API)
    # =========================================================================
    FormatterConsola.fase(
        4, 5, "Metraje Cinematográfico (Pexels)", f"Descargando {len(scenes)} clips HD de stock"
    )
    t0 = time.perf_counter()
    try:
        clips_descargados = descargar_broll(
            scenes=scenes,
            folder=str(temp_dir),
            orientation=orientation,
        )
    except Exception as e:
        FormatterConsola.error(f"Fallo en Pexels: {e}")
        raise

    t_broll = time.perf_counter() - t0
    FormatterConsola.exito(
        f"{len(clips_descargados)} clips HD descargados en '{temp_folder}'", t_broll
    )

    # =========================================================================
    # FASE 5: MONTAJE & MASTERIZACIÓN (FFMPEG)
    # =========================================================================
    FormatterConsola.fase(
        5, 5, "Montaje y Renderizado (FFmpeg)", "Normalizando, recortando y sincronizando con audio"
    )
    t0 = time.perf_counter()
    try:
        video_final = ensamblar_video(
            scenes=scenes,
            audio_path=audio_path,
            output_path=output_video,
            temp_folder=str(temp_dir),
            orientation=orientation,
        )
    except Exception as e:
        FormatterConsola.error(f"Fallo en FFmpeg: {e}")
        raise

    t_ffmpeg = time.perf_counter() - t0
    FormatterConsola.exito("Video ensamblado y exportado", t_ffmpeg)

    # =========================================================================
    # RESUMEN EJECUTIVO FINAL
    # =========================================================================
    t_total = time.perf_counter() - t_global_inicio

    print(f"\n{FormatterConsola.VERDE}{'=' * 70}")
    print(f"   🎉 PRODUCCIÓN COMPLETADA CON ÉXITO")
    print(f"{'=' * 70}{FormatterConsola.RESET}\n")
    print(f"📌 {FormatterConsola.NEGRITA}Título:{FormatterConsola.RESET} {plan_produccion.get('title')}")
    print(f"📝 {FormatterConsola.NEGRITA}Descripción SEO:{FormatterConsola.RESET}\n{plan_produccion.get('description')}\n")
    print(f"🎞  {FormatterConsola.NEGRITA}Video Final:{FormatterConsola.RESET} {video_final}")
    print(f"⏱  {FormatterConsola.NEGRITA}Tiempo Total:{FormatterConsola.RESET} {t_total:.2f}s "
          f"[Guion ({writer_provider}): {t_writer:.1f}s | Gemini Dir: {t_gemini:.1f}s | TTS: {t_voice:.1f}s | Pexels: {t_broll:.1f}s | FFmpeg: {t_ffmpeg:.1f}s]\n")

    return {
        "title": plan_produccion.get("title"),
        "description": plan_produccion.get("description"),
        "video_path": video_final,
        "audio_path": audio_path,
        "plan_path": str(plan_file),
        "total_seconds": t_total,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="STUDIO 4 Vol. 3 - Pipeline Automatizado de Video con Gemini / Claude, TTS, Pexels y FFmpeg"
    )
    parser.add_argument(
        "tema",
        type=str,
        nargs="?",
        default=None,
        help="Tema o premisa central del video a producir.",
    )
    parser.add_argument(
        "--writer",
        "-w",
        choices=["gemini", "claude"],
        default="gemini",
        help="Motor de IA para la redacción del guion creativo: 'gemini' (Google) o 'claude' (Anthropic). Por defecto: gemini.",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=60,
        help="Duración estimada del video en segundos (por defecto: 60).",
    )
    parser.add_argument(
        "--orientation",
        "-o",
        choices=["landscape", "portrait"],
        default="landscape",
        help="Orientación del video: landscape (16:9, YouTube estándar) o portrait (9:16, Shorts/Reels/TikTok).",
    )
    parser.add_argument(
        "--voice",
        "-v",
        type=str,
        default=None,
        help="Identificador de la voz de Google Cloud TTS (ej. es-US-Neural2-F, es-US-Journey-F).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/video_final.mp4",
        help="Ruta de salida del video final (por defecto: output/video_final.mp4).",
    )
    parser.add_argument(
        "--temp",
        type=str,
        default="temp_clips",
        help="Carpeta temporal para almacenamiento de metraje de stock.",
    )

    args = parser.parse_args()

    # Si no se pasó argumento en línea de comandos, solicitar interactivamente
    tema = args.tema
    if not tema:
        print(f"\n{FormatterConsola.CIAN}STUDIO 4 Vol. 3 - Modo Interactivo{FormatterConsola.RESET}")
        try:
            tema = input("Introduce el tema del video: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperación cancelada.")
            sys.exit(0)

    if not tema:
        print("Error: Se requiere un tema para comenzar la producción.")
        sys.exit(1)

    try:
        ejecutar_pipeline(
            tema=tema,
            target_seconds=args.duration,
            orientation=args.orientation,
            voice_name=args.voice,
            writer_provider=args.writer,
            output_video=args.output,
            temp_folder=args.temp,
        )
    except KeyboardInterrupt:
        print("\n\nProducción interrumpida por el usuario.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n{FormatterConsola.ROJO}Error crítico durante la producción: {exc}{FormatterConsola.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()

