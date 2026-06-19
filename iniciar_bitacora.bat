@echo off
setlocal
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw "%~dp0bitacora.pyw"
    exit /b 0
)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0bitacora.pyw"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%~dp0bitacora.pyw"
    exit /b 0
)

echo No se encontro Python para iniciar Bitacora.
echo Instala Python 3 desde https://www.python.org/downloads/ y vuelve a intentarlo.
pause
