"""Los formatos del conteo diario de FourLevel sin abrir el panel: arrastra el vídeo del día (16:9) sobre
«Formatos FourLevel» del escritorio y salen a su lado:

    <nombre> - 9x16.mp4        vertical con el cuadro entero sobre su imagen desenfocada
    <nombre> - 9x16 zoom.mp4   vertical que en la escena central se acerca al texto («26 DÍAS…») para leerlo grande
    <nombre> - 1x1.mp4         cuadrado para el feed
    <nombre> - textos YouTube.txt   título (16:9 y Short), descripción y etiquetas, con el día sacado del nombre

Si el vídeo trae negro al final (la pista de audio más larga que la imagen al exportar), se recorta solo.
La escena central se detecta por los cortes de plano (logo → cuenta atrás → redes).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FONDO = "gblur=sigma=32,eq=brightness=-0.14:saturation=1.15"


def _ff(*args: str) -> str:
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", *args], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return r.stderr


def duracion(v: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(v)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def fin_de_imagen(v: Path) -> float:
    """Donde acaba la imagen: si hay negro hasta el final, ahí se corta."""
    total = duracion(v)
    log = _ff("-i", str(v), "-an", "-vf", "blackdetect=d=0.5:pix_th=0.08", "-f", "null", "-")
    for ini, fin in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log):
        if float(fin) >= total - 0.5 and float(ini) > 1:
            return float(ini)
    return total


def cortes(v: Path, hasta: float) -> list[float]:
    log = _ff("-t", f"{hasta:.3f}", "-i", str(v), "-an", "-vf", "scale=320:-1,select='gt(scene,0.3)',showinfo", "-f", "null", "-")
    salida: list[float] = []
    for t in (float(x) for x in re.findall(r"pts_time:([\d.]+)", log)):
        if not salida or t - salida[-1] > 0.5:   # dos cortes pegados son el mismo
            salida.append(t)
    return salida


def encajar(etq: str, w: int, h: int) -> str:
    """El cuadro entero centrado sobre su versión desenfocada."""
    return (f"split=2[{etq}a][{etq}b];[{etq}a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{FONDO}[{etq}f];"
            f"[{etq}b]scale={w}:{h}:force_original_aspect_ratio=decrease[{etq}c];[{etq}f][{etq}c]overlay=(W-w)/2:(H-h)/2,setsar=1")


def acercar(etq: str) -> str:
    """Vertical con zoom a la mitad derecha del cuadro (donde va el texto de la cuenta atrás)."""
    return (f"split=2[{etq}a][{etq}b];[{etq}a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,{FONDO}[{etq}f];"
            f"[{etq}b]scale=2160:1215,crop=1080:1215:1060:0[{etq}c];[{etq}f][{etq}c]overlay=(W-w)/2:(H-h)/2,setsar=1")


def render(v: Path, filtro: str, destino: Path, fin: float) -> None:
    _ff("-y", "-t", f"{fin:.3f}", "-i", str(v), "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-af", f"afade=t=out:st={max(0, fin - 0.45):.3f}:d=0.4", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destino))


LANZAMIENTO = "19 de noviembre de 2026"
HASHTAGS = "#GTA6 #GTAVI #GrandTheftAuto6 #ViceCity #CuentaAtras #FourLevel #Rockstar"
ETIQUETAS = ("gta 6, gta vi, grand theft auto 6, gta 6 cuenta atras, cuanto falta para gta 6, gta 6 lanzamiento, "
             "gta 6 fecha de salida, vice city, rockstar games, gta 6 noticias, gta 6 español, fourlevel")


def textos(v: Path) -> str:
    """Título, descripción y etiquetas listos para pegar en YouTube. El día sale del nombre («conteo dia 26»)."""
    m = re.search(r"d[ií]a\s*(\d+)", v.stem, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        dias = "1 DÍA" if n == 1 else f"{n} DÍAS"
        largo = f"GTA 6: {'falta' if n == 1 else 'faltan'} {dias} para el lanzamiento 🔥 | Cuenta atrás FourLevel"
        corto = f"¡Solo {dias.lower()} para GTA 6! ⏳ #Shorts"
        gancho = f"⏳ {'Falta' if n == 1 else 'Faltan'} {dias.lower()} para el lanzamiento de Grand Theft Auto VI ({LANZAMIENTO})."
    else:
        largo = f"{v.stem} | FourLevel"
        corto = f"{v.stem} #Shorts"
        gancho = f"{v.stem}."
    descripcion = (f"{gancho}\nCada día, una nueva cuenta atrás hasta que vuelvas a Vice City. ¿Lo vas a jugar el primer día? "
                   "Te leo en los comentarios 👇\n\n🔔 Suscríbete y activa la campana para no perderte ningún día del conteo.\n\n"
                   "📲 Sígueme en todas mis redes: @FourLevel\nYouTube · Twitch · TikTok · Instagram · X · Discord\n\n" + HASHTAGS)
    return (f"TÍTULO (vídeo 16:9)\n{largo}\n\nTÍTULO (Short / Reel 9:16)\n{corto}\n\nDESCRIPCIÓN\n{descripcion}\n\n"
            f"ETIQUETAS\n{ETIQUETAS}\n\nCONSEJO: mete el vídeo en la lista «Cuenta atrás GTA 6».\n")


def hacer(v: Path) -> list[Path]:
    fin = fin_de_imagen(v)
    base = v.with_suffix("")
    hechos = []
    render(v, f"[0:v]fps=30,{encajar('x', 1080, 1920)}[v]", Path(f"{base} - 9x16.mp4"), fin); hechos.append(Path(f"{base} - 9x16.mp4"))
    render(v, f"[0:v]fps=30,{encajar('x', 1080, 1080)}[v]", Path(f"{base} - 1x1.mp4"), fin); hechos.append(Path(f"{base} - 1x1.mp4"))
    c = [t for t in cortes(v, fin) if 0.5 < t < fin - 0.5]
    if len(c) >= 2:   # logo → cuenta atrás → redes: zoom solo en la escena central
        a, b = c[0], c[1]
        filtro = (f"[0:v]fps=30,split=3[p][q][r];"
                  f"[p]trim=0:{a:.4f},setpts=PTS-STARTPTS,{encajar('s1', 1080, 1920)}[s1];"
                  f"[q]trim={a:.4f}:{b:.4f},setpts=PTS-STARTPTS,{acercar('s2')}[s2];"
                  f"[r]trim={b:.4f},setpts=PTS-STARTPTS,{encajar('s3', 1080, 1920)}[s3];"
                  f"[s1][s2][s3]concat=n=3:v=1:a=0[v]")
        render(v, filtro, Path(f"{base} - 9x16 zoom.mp4"), fin)
        hechos.append(Path(f"{base} - 9x16 zoom.mp4"))
    txt = Path(f"{base} - textos YouTube.txt")
    txt.write_text(textos(v), encoding="utf-8")
    hechos.append(txt)
    return hechos


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        input("Arrastra un vídeo sobre el icono. Pulsa Enter para salir.")
        sys.exit(1)
    for arg in sys.argv[1:]:
        video = Path(arg)
        print(f"→ {video.name}: preparando formatos…")
        try:
            for h in hacer(video):
                print(f"   listo: {h.name}")
        except Exception as e:  # noqa: BLE001 - se ve en la ventana
            print(f"   no se pudo: {e}")
    input("Terminado. Pulsa Enter para cerrar.")
