"""STUDIO 4 · vídeos con Google: Gemini (guion, escenas, voz) + Flow (clips) + FFmpeg (render)."""

import subprocess as _sp
import sys as _sys

if _sys.platform == "win32":   # sin esto, cada FFmpeg/yt-dlp abre y cierra una ventana de consola
    _popen_init = _sp.Popen.__init__

    def _sin_ventana(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    _sp.Popen.__init__ = _sin_ventana
