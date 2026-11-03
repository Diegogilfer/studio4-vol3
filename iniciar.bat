@echo off
chcp 65001 >nul
title STUDIO 4
cd /d "%~dp0"

rem Un acceso directo por canal ("iniciar.bat fourlevel", "iniciar.bat arigab"): Studio 4 abre ya en ese canal.
if not "%~1"=="" (
  python -c "from studio4 import canales; canales.activar('%~1')" || (
    echo  No existe el canal "%~1". Revisa el acceso directo.
    pause
    exit /b 1
  )
  title STUDIO 4 · %~1
)

rem Si Studio 4 ya esta abierto, solo se abre el panel (antes se lanzaba otro y chocaba con el puerto).
curl.exe -s -o nul -m 2 http://127.0.0.1:8000/api/estado
if not errorlevel 1 (
  start "" http://127.0.0.1:8000
  exit /b 0
)

rem Pantalla de carga con el logo: espera al servidor y entra sola en el panel cuando responde
rem (antes el navegador se abria antes que el servidor y la primera carga daba error).
start "" "%~dp0web\arranque.html"
python servidor.py

echo.
echo  STUDIO 4 se ha cerrado. Si fue por un error, el detalle esta en producciones\servidor.log
pause
