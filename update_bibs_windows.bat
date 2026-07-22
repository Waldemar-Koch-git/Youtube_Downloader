@echo off
setlocal enabledelayedexpansion

echo.
echo ========================================
echo    yt-dlp Package Manager - Update ^& Check
echo ========================================
echo.
echo [INFO] Checking Python environment...
echo.

:: 1. Check Python availability
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not on PATH or not installed!
    echo.
    echo Please install Python from https://www.python.org/
    echo Important: check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] %PYTHON_VER% found
echo.

:: 2. Check pip availability
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available!
    echo.
    echo Please install pip: python -m ensurepip --upgrade
    pause
    exit /b 1
)
echo [OK] pip is available
echo.

:: 3. Defined packages
::    Note: FFmpeg is NOT installed separately anymore.
::    static-ffmpeg downloads and caches the current FFmpeg binary
::    automatically on first start of the downloader.
set "PACKAGES[0]=yt-dlp[default]"
set "PACKAGES[1]=static-ffmpeg"
set "PACKAGES[2]=mutagen"

set "MISSING="

:: 4. Check which packages are missing
::    Uses importlib.metadata (Python standard library) instead of the
::    deprecated pkg_resources / setuptools, which is not guaranteed to
::    be installed on every Python setup (e.g. some virtual environments).
echo [INFO] Checking installed packages...
echo.

for /l %%i in (0,1,2) do (
    set "package=!PACKAGES[%%i]!"
    set "base=!package:[default]=!"
    if "!base!"=="" set "base=!package!"

    python -c "import importlib.metadata as m; m.version('!base!')" >nul 2>&1
    if errorlevel 1 (
        echo [MISSING] !package!
        set "MISSING=!MISSING! !package!"
    ) else (
        for /f "tokens=*" %%v in ('python -c "import importlib.metadata as m; print(m.version('!base!'))" 2^>^&1') do set "version=%%v"
        echo [FOUND] !package! (version: !version!)
    )
)

echo.

:: 5. Check for available updates
echo [INFO] Checking for available updates...
echo.

set "HAS_UPDATES=0"
python -m pip list --outdated --format=columns > "%TEMP%\ytdlp_outdated.txt" 2>nul

for /l %%i in (0,1,2) do (
    set "package=!PACKAGES[%%i]!"
    set "base=!package:[default]=!"
    if "!base!"=="" set "base=!package!"

    findstr /b /i "!base! " "%TEMP%\ytdlp_outdated.txt" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [UPDATE] Update available for !package!
        set "HAS_UPDATES=1"
    ) else (
        echo [CURRENT] !package! is up to date
    )
)

del "%TEMP%\ytdlp_outdated.txt" >nul 2>&1
echo.

:: 6. If packages are missing or updates are available
if not "%MISSING%"=="" (
    echo [ACTION] Installing missing packages...
    echo.
    call :PipInstall install %MISSING%

    if not "!PIPSTATUS!"=="0" (
        echo [ERROR] Installation failed!
        pause
        exit /b 1
    )
    echo [SUCCESS] Missing packages have been installed
    echo.
)

if "%HAS_UPDATES%"=="1" (
    echo [ACTION] Installing updates...
    echo.
    call :PipInstall upgrade yt-dlp[default] static-ffmpeg mutagen

    if not "!PIPSTATUS!"=="0" (
        echo [ERROR] Update failed!
        pause
        exit /b 1
    )
    echo [SUCCESS] All packages have been updated
    echo.
) else (
    if "%MISSING%"=="" (
        echo [OK] All packages are present and up to date!
        echo.
    )
)

:: 7. Summary
echo ========================================
echo   Current installation:
echo ========================================
echo.

yt-dlp --version 2>nul
if errorlevel 1 (
    echo yt-dlp: not on PATH or not available
) else (
    for /f "tokens=*" %%v in ('yt-dlp --version 2^>^&1') do echo yt-dlp: version %%v
)

python -c "import static_ffmpeg; print('static-ffmpeg: installed (FFmpeg is downloaded automatically on first program start)')" 2>nul
if errorlevel 1 echo static-ffmpeg: not available

python -c "import importlib.metadata as m; print(f'mutagen: version {m.version(\"mutagen\")}')" 2>nul
if errorlevel 1 echo mutagen: not available

echo.
echo [DONE] All checks completed!
echo.
pause
