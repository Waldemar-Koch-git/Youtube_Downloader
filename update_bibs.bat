@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo    yt-dlp Paketmanager - Update ^& Pruefung
echo ========================================
echo.
echo [INFO] Pruefe Python-Umgebung...
echo.

:: 1. Python-Verfuegbarkeit pruefen
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python ist nicht im Pfad oder nicht installiert!
    echo.
    echo Bitte Python von https://www.python.org/ installieren.
    echo Wichtig: Haken bei "Add Python to PATH" setzen!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] %PYTHON_VER% gefunden
echo.

:: 2. pip-Verfuegbarkeit pruefen
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] pip ist nicht verfuegbar!
    echo.
    echo Bitte pip installieren: python -m ensurepip --upgrade
    pause
    exit /b 1
)
echo [OK] pip ist verfuegbar
echo.

:: 3. Definierte Pakete
::    Hinweis: FFmpeg wird NICHT mehr separat installiert.
::    static-ffmpeg laedt und cached die aktuelle FFmpeg-Binary automatisch
::    beim ersten Start des Downloaders.
set "PAKETE[0]=yt-dlp[default]"
set "PAKETE[1]=static-ffmpeg"
set "PAKETE[2]=mutagen"

set "MISSING="

:: 4. Pruefen, welche Pakete fehlen
echo [INFO] Pruefe installierte Pakete...
echo.

for /l %%i in (0,1,2) do (
    set "paket=!PAKETE[%%i]!"
    set "basis=!paket:[default]=!"
    if "!basis!"=="" set "basis=!paket!"

    python -c "import pkg_resources; pkg_resources.get_distribution('!basis!')" >nul 2>&1
    if errorlevel 1 (
        echo [FEHLT] !paket!
        set "MISSING=!MISSING! !paket!"
    ) else (
        for /f "tokens=*" %%v in ('python -c "import pkg_resources; print(pkg_resources.get_distribution('!basis!').version)" 2^>^&1') do set "version=%%v"
        echo [VORHANDEN] !paket! (Version: !version!)
    )
)

echo.

:: 5. Pruefen auf verfuegbare Updates
echo [INFO] Pruefe auf verfuegbare Updates...
echo.

set "HAS_UPDATES=0"
for /l %%i in (0,1,2) do (
    set "paket=!PAKETE[%%i]!"
    set "basis=!paket:[default]=!"
    if "!basis!"=="" set "basis=!paket!"

    python -c "import pkg_resources; import subprocess; current=pkg_resources.get_distribution('!basis!').version; result=subprocess.run(['python', '-m', 'pip', 'index', 'versions', '!basis!'], capture_output=True, text=True); print('UPDATE' if current not in result.stdout else 'CURRENT')" 2>nul | findstr "UPDATE" >nul
    if !errorlevel! equ 0 (
        echo [UPDATE] Update verfuegbar fuer !paket!
        set "HAS_UPDATES=1"
    ) else (
        echo [AKTUELL] !paket! ist auf dem neuesten Stand
    )
)

echo.

:: 6. Falls Pakete fehlen oder Updates verfuegbar sind
if not "%MISSING%"=="" (
    echo [AKTION] Fehlende Pakete werden installiert...
    echo.
    python -m pip install %MISSING%

    if errorlevel 1 (
        echo [FEHLER] Installation fehlgeschlagen!
        pause
        exit /b 1
    )
    echo [ERFOLG] Fehlende Pakete wurden installiert
    echo.
)

if "%HAS_UPDATES%"=="1" (
    echo [AKTION] Updates werden installiert...
    echo.
    python -m pip install --upgrade yt-dlp[default] static-ffmpeg mutagen

    if errorlevel 1 (
        echo [FEHLER] Update fehlgeschlagen!
        pause
        exit /b 1
    )
    echo [ERFOLG] Alle Pakete wurden aktualisiert
    echo.
) else (
    if "%MISSING%"=="" (
        echo [OK] Alle Pakete sind vorhanden und aktuell!
        echo.
    )
)

:: 7. Abschluss
echo ========================================
echo   Aktuelle Installation:
echo ========================================
echo.

yt-dlp --version 2>nul
if errorlevel 1 (
    echo yt-dlp: nicht im Pfad oder nicht verfuegbar
) else (
    for /f "tokens=*" %%v in ('yt-dlp --version 2^>^&1') do echo yt-dlp: Version %%v
)

python -c "import static_ffmpeg; print('static-ffmpeg: installiert (FFmpeg wird beim ersten Programmstart automatisch geladen)')" 2>nul
if errorlevel 1 echo static-ffmpeg: nicht verfuegbar

python -c "import mutagen; print(f'mutagen: Version {mutagen.__version__}')" 2>nul
if errorlevel 1 echo mutagen: nicht verfuegbar

echo.
echo [FERTIG] Alle Pruefungen abgeschlossen!
echo.
pause
