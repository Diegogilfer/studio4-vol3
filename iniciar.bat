@echo off
chcp 65001 >nul
title STUDIO 4
cd /d "%~dp0"

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
