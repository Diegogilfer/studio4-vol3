"""Diseño de sonido del panel nuevo, sacado de la ingeniería inversa de un vídeo profesional del nicho:
graves presentes (impactos y cama), nunca silencio, efectos que se mueven en estéreo y un volumen final de YouTube
(alrededor de −11 LUFS, comprimido). Todo se genera con FFmpeg: es nuestro, sin derechos de nadie.

Medidas de la referencia (4 min): −9,3 LUFS · graves (<120 Hz) −17,6 dB · agudos (>6 kHz) −24,8 dB · 0 silencios.
Las nuestras antes de esto: −13,9 LUFS · graves −32,4 dB · agudos −32,7 dB.
"""

from __future__ import annotations

from pathlib import Path

from . import medios

# Cadena final: compresión suave, techo y volumen de YouTube (YouTube baja lo que pase de −14; así llega lleno)
MASTER = ("acompressor=threshold=-18dB:ratio=3:attack=5:release=150:makeup=2,"
          "alimiter=limit=0.94:level=disabled,loudnorm=I=-11:TP=-1:LRA=7")
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
    """Fondo grave continuo para cuando no hay música: dos notas graves que respiran despacio y un poco de aire,
    con los canales levemente desfasados para que suene ancho. Nunca hay silencio."""
    expr = ("0.22*sin(2*PI*55*t)*(0.7+0.3*sin(2*PI*0.09*t))+0.12*sin(2*PI*82.4*t)*(0.6+0.4*sin(2*PI*0.06*t))"
            "+0.06*sin(2*PI*110*t)*(0.5+0.5*sin(2*PI*0.05*t))")
    medios.ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':d={total:.3f}:s=48000",
                  "-f", "lavfi", "-i", f"anoisesrc=d={total:.3f}:c=brown:a=0.25:r=48000",
                  "-filter_complex", "[1:a]lowpass=f=400[aire];[0:a][aire]amix=inputs=2:normalize=0,"
                  "aformat=channel_layouts=stereo,adelay=0|12,afade=t=in:d=2,"
                  f"afade=t=out:st={max(0.0, total - 2.5):.3f}:d=2.5",
                  "-ar", "48000", "-ac", "2", str(destino))
    return destino


def pista(eventos: list[tuple[float, str, float]], total: float, destino: Path) -> Path:
    """Todos los efectos en su sitio [(segundo, efecto, volumen)], con reverberación de sala."""
    fx = biblioteca(destino.parent / "_fx")
    eventos = [e for e in eventos if 0 <= e[0] < total]
    if not eventos:
        medios.ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{total:.3f}", str(destino))
        return destino
    entradas, filtros = [], []
    for k, (t, tipo, vol) in enumerate(eventos):
        entradas += ["-i", str(fx[tipo])]
        filtros.append(f"[{k}:a]volume={vol:.2f},adelay={int(t * 1000)}:all=1[f{k}]")
    filtros.append("".join(f"[f{k}]" for k in range(len(eventos))) +
                   f"amix=inputs={len(eventos)}:normalize=0,{REVERB},apad,atrim=0:{total:.3f}[a]")
    medios.ffmpeg(*entradas, "-filter_complex", ";".join(filtros), "-map", "[a]", "-ar", "48000", str(destino))
    return destino
