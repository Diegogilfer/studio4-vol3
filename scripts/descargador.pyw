"""Descargador de YouTube de Studio 4: vídeo (MP4 hasta 4K) o solo audio (MP3), con el mismo yt-dlp y FFmpeg del
estudio. Se abre con el acceso «Descargador YouTube» del escritorio.

Guarda en «Vídeos\\STUDIO 4\\Descargas\\Vídeo» y «…\\Audio». La música bajada de YouTube NO va a la carpeta Música del
estudio: esa es solo para la Biblioteca de audio de YouTube (Content ID detecta el resto en un vídeo monetizado).
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from studio4 import carpetas, extractor  # noqa: E402

DESCARGAS = carpetas.RAIZ_USUARIO / "Descargas"
CALIDADES = {"Mejor (hasta 4K)": 2160, "1080p": 1080, "720p": 720}
FONDO, CAJA, TEXTO, SUAVE, ROSA, CIAN = "#07070c", "#14141c", "#f2f2f7", "#a3a3b8", "#ff3ea5", "#2ee6ff"


class Descargador(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Studio 4 · Descargador de YouTube")
        self.geometry("720x520")
        self.minsize(620, 480)
        self.configure(bg=FONDO)
        self.eventos: queue.Queue = queue.Queue()
        self.trabajando = False
        self._estilos()
        self._pantalla()
        self.after(150, self._mirar)

    def _estilos(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=FONDO, foreground=TEXTO, font=("Segoe UI", 11))
        s.configure("TLabel", background=FONDO, foreground=TEXTO)
        s.configure("Suave.TLabel", foreground=SUAVE, font=("Segoe UI", 10))
        s.configure("Titulo.TLabel", font=("Segoe UI Semibold", 20))
        s.configure("TRadiobutton", background=FONDO, foreground=TEXTO, font=("Segoe UI", 11))
        s.map("TRadiobutton", background=[("active", FONDO)])
        s.configure("Primario.TButton", background=ROSA, foreground="#0b0b10", font=("Segoe UI Semibold", 12), padding=10, borderwidth=0)
        s.map("Primario.TButton", background=[("active", CIAN), ("disabled", "#3a3a48")])
        s.configure("TButton", background=CAJA, foreground=TEXTO, padding=8, borderwidth=0)
        s.map("TButton", background=[("active", "#22222e")])
        s.configure("Horizontal.TProgressbar", background=ROSA, troughcolor=CAJA, borderwidth=0, thickness=10)
        s.configure("TCombobox", fieldbackground=CAJA, background=CAJA, foreground=TEXTO)

    def _pantalla(self) -> None:
        m = ttk.Frame(self, padding=24)
        m.pack(fill="both", expand=True)
        ttk.Label(m, text="Descargador de YouTube", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(m, text="Pega el enlace de un vídeo (o de una lista) y elige vídeo o solo audio.", style="Suave.TLabel").pack(anchor="w", pady=(2, 14))

        self.url = tk.Entry(m, bg=CAJA, fg=TEXTO, insertbackground=TEXTO, relief="flat", font=("Segoe UI", 12))
        self.url.pack(fill="x", ipady=10)
        self.url.bind("<Return>", lambda _e: self._descargar())
        self.url.focus_set()

        fila = ttk.Frame(m)
        fila.pack(fill="x", pady=14)
        self.tipo = tk.StringVar(value="video")
        ttk.Radiobutton(fila, text="Vídeo (MP4)", value="video", variable=self.tipo).pack(side="left")
        ttk.Radiobutton(fila, text="Solo audio (MP3)", value="audio", variable=self.tipo).pack(side="left", padx=18)
        self.calidad = ttk.Combobox(fila, values=list(CALIDADES), state="readonly", width=16)
        self.calidad.set("Mejor (hasta 4K)")
        self.calidad.pack(side="left", padx=6)
        self.lista = tk.BooleanVar(value=False)
        ttk.Checkbutton(fila, text="Toda la lista", variable=self.lista).pack(side="left", padx=12)

        botones = ttk.Frame(m)
        botones.pack(fill="x")
        self.boton = ttk.Button(botones, text="Descargar", style="Primario.TButton", command=self._descargar)
        self.boton.pack(side="left")
        ttk.Button(botones, text="Abrir carpeta", command=self._abrir).pack(side="left", padx=10)
        ttk.Button(botones, text="Actualizar descargador", command=self._actualizar).pack(side="right")

        self.barra = ttk.Progressbar(m, mode="determinate", maximum=100)
        self.barra.pack(fill="x", pady=(18, 6))
        self.estado = ttk.Label(m, text="Listo.", style="Suave.TLabel")
        self.estado.pack(anchor="w")
        self.registro = tk.Text(m, height=9, bg=CAJA, fg=SUAVE, relief="flat", font=("Consolas", 10), wrap="word")
        self.registro.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(m, text="Para tus vídeos, la música sale de la Biblioteca de audio de YouTube (carpeta Música del estudio).",
                  style="Suave.TLabel").pack(anchor="w", pady=(8, 0))

    def _escribir(self, texto: str) -> None:
        self.registro.insert("end", texto + "\n")
        self.registro.see("end")

    def _abrir(self) -> None:
        carpeta = DESCARGAS / ("Audio" if self.tipo.get() == "audio" else "Vídeo")
        carpeta.mkdir(parents=True, exist_ok=True)
        os.startfile(carpeta)  # noqa: S606 - el Explorador en tu PC

    def _descargar(self) -> None:
        url = self.url.get().strip()
        if self.trabajando or not url.startswith(("http://", "https://")):
            if not self.trabajando:
                self.estado.configure(text="Pega un enlace de YouTube (https://…).")
            return
        self.trabajando = True
        self.boton.configure(state="disabled")
        self.barra.configure(value=0)
        self._escribir(f"→ {url}")
        threading.Thread(target=self._trabajo, args=(url, self.tipo.get(), CALIDADES[self.calidad.get()], self.lista.get()),
                         daemon=True).start()

    def _trabajo(self, url: str, tipo: str, alto: int, lista: bool) -> None:
        import yt_dlp
        carpeta = DESCARGAS / ("Audio" if tipo == "audio" else "Vídeo")
        carpeta.mkdir(parents=True, exist_ok=True)

        def progreso(d: dict) -> None:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                hecho = d.get("downloaded_bytes") or 0
                self.eventos.put(("progreso", (100 * hecho / total) if total else 0,
                                  f"Descargando {Path(d.get('filename', '')).stem[:60]}… {hecho / 1e6:.0f} MB"))
            elif d.get("status") == "finished":
                self.eventos.put(("progreso", 100, "Uniendo y convirtiendo…"))

        opciones = {"outtmpl": str(carpeta / "%(title)s.%(ext)s"), "noplaylist": not lista, "progress_hooks": [progreso],
                    "quiet": True, "no_warnings": True, "windowsfilenames": True}
        if tipo == "audio":
            opciones |= {"format": "bestaudio/best",
                         "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                                            {"key": "FFmpegMetadata"}]}
        else:
            opciones |= {"format": f"bv*[height<={alto}]+ba/b[height<={alto}]/b", "merge_output_format": "mp4"}
        try:
            with yt_dlp.YoutubeDL(extractor.opciones_ytdlp(**opciones)) as y:
                info = y.extract_info(url, download=True)
            n = len(info.get("entries") or []) or 1
            self.eventos.put(("fin", f"Listo: {n} archivo{'s' if n > 1 else ''} en {carpeta}"))
        except Exception as e:  # noqa: BLE001 - el motivo se ve en la ventana
            motivo = str(e)
            if "confirm your age" in motivo or "Sign in" in motivo:
                motivo = "YouTube pide iniciar sesión (vídeo con restricción de edad o privado): no se puede bajar así."
            self.eventos.put(("fin", f"No se pudo: {motivo[:300]}"))

    def _actualizar(self) -> None:
        self._escribir("Actualizando el descargador (yt-dlp)…")

        def correr():
            r = subprocess.run([sys.executable.replace("pythonw", "python"), "-m", "pip", "install", "-U", "yt-dlp"],
                               capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.eventos.put(("log", "Descargador al día." if r.returncode == 0 else f"No se pudo actualizar: {r.stderr[-300:]}"))
        threading.Thread(target=correr, daemon=True).start()

    def _mirar(self) -> None:
        try:
            while True:
                tipo, *datos = self.eventos.get_nowait()
                if tipo == "progreso":
                    self.barra.configure(value=datos[0])
                    self.estado.configure(text=datos[1])
                elif tipo == "log":
                    self._escribir(datos[0])
                elif tipo == "fin":
                    self._escribir(datos[0])
                    self.estado.configure(text=datos[0][:110])
                    self.trabajando = False
                    self.boton.configure(state="normal")
        except queue.Empty:
            pass
        self.after(150, self._mirar)


if __name__ == "__main__":
    Descargador().mainloop()
