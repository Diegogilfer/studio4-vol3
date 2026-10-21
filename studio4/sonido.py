"""Diseño de sonido del panel nuevo, sacado de la ingeniería inversa de un vídeo profesional del nicho:
graves presentes (impactos y cama), nunca silencio, efectos que se mueven en estéreo y un volumen final de YouTube
(alrededor de −11 LUFS, comprimido). Todo se genera con FFmpeg: es nuestro, sin derechos de nadie.

Medidas de la referencia (4 min): −9,3 LUFS · graves (<120 Hz) −17,6 dB · agudos (>6 kHz) −24,8 dB · 0 silencios.
Las nuestras antes de esto: −13,9 LUFS · graves −32,4 dB · agudos −32,7 dB.
"""

from __future__ import annotations

import array
import json
import wave
from pathlib import Path

from . import medios

# Volumen final de YouTube (−11 LUFS: YouTube baja lo que pase de −14, así llega lleno). Sin compresores que
# «respiren»: con ellos, al callarse la voz el fondo bajaba y volvía a subir y se oía como un corte. Primero solo se
# recortan los picos (LIMITE) y luego masterizar() mide el volumen y lo sube de forma pareja (dos pasadas).
LIMITE = "alimiter=limit=0.5:attack=5:release=80:level=disabled"
OBJETIVO = "loudnorm=I=-11:TP=-1:LRA=11"


def masterizar(entrada: Path, destino: Path, extra: str = "") -> Path:
    """El volumen final, parejo: se mide la mezcla y se aplica una sola ganancia (loudnorm lineal, sin bombeo)."""
    medida = medios.ffmpeg("-i", str(entrada), "-af", f"{OBJETIVO}:print_format=json", "-f", "null", "-")
    d = json.loads(medida[medida.rindex("{"):medida.rindex("}") + 1])
    af = (f"{OBJETIVO}:measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}:"
          f"measured_thresh={d['input_thresh']}:offset={d['target_offset']}:linear=true")
    medios.ffmpeg("-i", str(entrada), "-af", af + (f",{extra}" if extra else ""), "-ar", "48000", str(destino))
    return destino
REVERB = "aecho=0.8:0.55:60|130:0.22|0.12"   # una sala: los efectos no suenan «secos»


def biblioteca(carpeta: Path) -> dict[str, Path]:
    """Los efectos, generados una vez y reutilizados."""
    carpeta.mkdir(parents=True, exist_ok=True)
    fx = {n: carpeta / f"{n}.wav" for n in ("impacto", "subida", "whoosh", "cruce", "pop")}
    gen = {
        # golpe grave que cae de 120 a 40 Hz con un chasquido de ruido al principio
        "impacto": ["-f", "lavfi", "-i", "aevalsrc='0.95*sin(2*PI*(38+90*exp(-7*t))*t)*exp(-3.2*t)':d=1.4:s=48000",
                    "-f", "lavfi", "-i", "anoisesrc=d=0.12:c=brown:a=0.7:r=48000",
                    "-filter_complex", "[1:a]lowpass=f=900,afade=t=out:st=0:d=0.12[c];[0:a][c]amix=inputs=2:normalize=0,"
                    "aformat=channel_layouts=stereo,volume=1.2"],
        # subida: ruido que se abre y un tono que sube, para anunciar un bloque nuevo
        "subida": ["-f", "lavfi", "-i", "anoisesrc=d=1.6:c=white:a=0.35:r=48000",
                   "-f", "lavfi", "-i", "aevalsrc='0.22*sin(2*PI*(180+520*t*t)*t)':d=1.6:s=48000",
                   "-filter_complex", "[0:a]highpass=f=900,lowpass=f=9000[r];[r][1:a]amix=inputs=2:normalize=0,"
                   "afade=t=in:d=1.5:curve=exp,afade=t=out:st=1.5:d=0.1,aformat=channel_layouts=stereo"],
        "whoosh": ["-f", "lavfi", "-i", "anoisesrc=d=0.55:c=pink:a=0.9:r=48000",
                   "-af", "highpass=f=300,lowpass=f=5000,afade=t=in:d=0.22,afade=t=out:st=0.25:d=0.3,aformat=channel_layouts=stereo"],
        # whoosh que cruza de izquierda a derecha: el efecto «envolvente»
        "cruce": ["-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:a=0.95:r=48000",
                  "-af", "bandpass=f=1800:width_type=o:w=2.5,afade=t=in:d=0.3,afade=t=out:st=0.35:d=0.35,"
                  "aformat=channel_layouts=stereo,aeval='val(0)*(1-t/0.7)|val(1)*(t/0.7)':c=stereo"],
        "pop": ["-f", "lavfi", "-i", "sine=f=880:d=0.12:sample_rate=48000", "-af", "afade=t=out:st=0.02:d=0.1,volume=0.55,aformat=channel_layouts=stereo"],
    }
    for n, args in gen.items():
        if not fx[n].exists():
            medios.ffmpeg(*args, "-ar", "48000", "-ac", "2", str(fx[n]))
    return fx


def cama(total: float, destino: Path) -> Path:
    """Fondo suave para cuando no hay música en tu carpeta: un acorde cálido (la menor) de notas dobles algo
    desafinadas entre sí, que crecen y bajan despacio, con un grave discreto debajo. Sin ruido (el ruido grave sonaba
    áspero, «como el mar a centímetros»). Nunca hay silencio."""
    def nota(f: float, a: float, lfo: float, fase: float) -> str:
        return (f"{a}*(sin(2*PI*{f}*t)+sin(2*PI*{f * 1.003:.3f}*t))*(0.55+0.45*sin(2*PI*{lfo}*t+{fase}))")
    expr = "+".join([
        "0.05*sin(2*PI*55*t)",                 # grave discreto
        nota(110.0, 0.045, 0.05, 0.0),         # la
        nota(164.81, 0.032, 0.07, 1.3),        # mi
        nota(220.0, 0.022, 0.045, 2.1),        # la (octava)
        nota(261.63, 0.016, 0.06, 3.0),        # do: le da el color menor
    ])
    medios.ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':d={total:.3f}:s=48000",
                  "-af", "lowpass=f=900,aformat=channel_layouts=stereo,adelay=0|15,aecho=0.8:0.6:120|210:0.25|0.15,"
                  f"afade=t=in:d=2,afade=t=out:st={max(0.0, total - 2.5):.3f}:d=2.5,atrim=0:{total:.3f}",
                  "-ar", "48000", "-ac", "2", str(destino))
    return destino


def silencio(total: float, destino: Path) -> Path:
    """Un fondo vacío (para montar sin música ni cama, si la música se añade después)."""
    medios.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{total:.3f}", str(destino))
    return destino


MUESTRAS = 48000   # por segundo y canal; todos los efectos están en estéreo de 16 bits a 48 kHz


def _muestras(wav: Path) -> array.array:
    with wave.open(str(wav), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (MUESTRAS, 2, 2):
            raise ValueError(f"Efecto con formato inesperado: {wav.name}")
        datos = array.array("h")
        datos.frombytes(w.readframes(w.getnframes()))
    return datos


def pista(eventos: list[tuple[float, str, float]], total: float, destino: Path) -> Path:
    """Todos los efectos en su sitio [(segundo, efecto, volumen)], con reverberación de sala.
    Los efectos se colocan aquí, en Python, y FFmpeg solo recibe un archivo: con un FFmpeg de decenas de entradas
    (el mismo efecto abierto muchas veces) la mezcla se quedaba colgada de vez en cuando."""
    fx = biblioteca(destino.parent / "_fx")
    mezcla = array.array("f", bytes(4 * 2 * int(total * MUESTRAS)))
    cache: dict[str, array.array] = {}
    for t, tipo, vol in eventos:
        if not 0 <= t < total:
            continue
        datos = cache.setdefault(tipo, _muestras(fx[tipo]))
        ini = 2 * int(t * MUESTRAS)
        fin = min(len(mezcla), ini + len(datos))
        mezcla[ini:fin] = array.array("f", (a + b * vol for a, b in zip(mezcla[ini:fin], datos)))
    crudo = destino.with_name(destino.stem + "_seco.raw")   # muestras en coma flotante, tal cual (sin recorrerlas)
    crudo.write_bytes(mezcla.tobytes())
    medios.ffmpeg("-f", "f32le", "-ar", str(MUESTRAS), "-ac", "2", "-i", str(crudo),
                  "-af", f"volume={1 / 32768:.8f},{REVERB},apad,atrim=0:{total:.3f}", "-ar", str(MUESTRAS),
                  "-c:a", "pcm_s16le", str(destino))
    crudo.unlink(missing_ok=True)
    return destino
