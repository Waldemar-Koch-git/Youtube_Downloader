#!/bin/bash

echo ""
echo "========================================"
echo "   yt-dlp Paketmanager - Update & Pruefung"
echo "========================================"
echo ""
echo "[INFO] Pruefe Python-Umgebung..."
echo ""

# Python-Befehl ermitteln (python3 bevorzugen)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[FEHLER] Python ist nicht installiert oder nicht im Pfad!"
    echo ""
    echo "Bitte Python von https://www.python.org/ installieren."
    echo "Unter Linux/macOS: python3 oder python."
    exit 1
fi

# Python-Version anzeigen
PYTHON_VER=$($PYTHON_CMD --version 2>&1)
echo "[OK] $PYTHON_VER gefunden"
echo ""

# pip-Verfügbarkeit prüfen
$PYTHON_CMD -m pip --version &> /dev/null
if [ $? -ne 0 ]; then
    echo "[FEHLER] pip ist nicht verfuegbar!"
    echo ""
    echo "Bitte pip installieren: $PYTHON_CMD -m ensurepip --upgrade"
    exit 1
fi
echo "[OK] pip ist verfuegbar"
echo ""

# Definierte Pakete
# Hinweis: FFmpeg wird NICHT mehr separat installiert.
# static-ffmpeg laedt und cached die aktuelle FFmpeg-Binary automatisch
# beim ersten Start des Downloaders.
PAKETE=("yt-dlp[default]" "static-ffmpeg" "mutagen")

MISSING=""
HAS_UPDATES=0

# Prüfen, welche Pakete fehlen
echo "[INFO] Pruefe installierte Pakete..."
echo ""

for PAKET in "${PAKETE[@]}"; do
    # Basispaketnamen ohne [default] extrahieren
    if [[ "$PAKET" == *"[default]"* ]]; then
        BASIS="${PAKET%\[default\]}"
    else
        BASIS="$PAKET"
    fi

    $PYTHON_CMD -c "import pkg_resources; pkg_resources.get_distribution('$BASIS')" &> /dev/null
    if [ $? -ne 0 ]; then
        echo "[FEHLT] $PAKET"
        MISSING="$MISSING $PAKET"
    else
        VERSION=$($PYTHON_CMD -c "import pkg_resources; print(pkg_resources.get_distribution('$BASIS').version)" 2>&1)
        echo "[VORHANDEN] $PAKET (Version: $VERSION)"
    fi
done

echo ""

# Prüfen auf verfügbare Updates
echo "[INFO] Pruefe auf verfuegbare Updates..."
echo ""

for PAKET in "${PAKETE[@]}"; do
    if [[ "$PAKET" == *"[default]"* ]]; then
        BASIS="${PAKET%\[default\]}"
    else
        BASIS="$PAKET"
    fi

    # Aktuelle Version ermitteln
    CURRENT=$($PYTHON_CMD -c "import pkg_resources; print(pkg_resources.get_distribution('$BASIS').version)" 2>/dev/null)
    # Prüfen, ob eine neuere Version auf PyPI existiert
    OUTDATED=$($PYTHON_CMD -m pip list --outdated --format=columns | grep "^$BASIS " | awk '{print $2}')
    if [ -n "$OUTDATED" ]; then
        echo "[UPDATE] Update verfuegbar fuer $PAKET (aktuell $CURRENT -> $OUTDATED)"
        HAS_UPDATES=1
    else
        echo "[AKTUELL] $PAKET ist auf dem neuesten Stand ($CURRENT)"
    fi
done

echo ""

# Fehlende Pakete installieren
if [ -n "$MISSING" ]; then
    echo "[AKTION] Fehlende Pakete werden installiert..."
    echo ""
    $PYTHON_CMD -m pip install $MISSING
    if [ $? -ne 0 ]; then
        echo "[FEHLER] Installation fehlgeschlagen!"
        exit 1
    fi
    echo "[ERFOLG] Fehlende Pakete wurden installiert"
    echo ""
fi

# Updates durchführen
if [ $HAS_UPDATES -eq 1 ]; then
    echo "[AKTION] Updates werden installiert..."
    echo ""
    $PYTHON_CMD -m pip install --upgrade yt-dlp[default] static-ffmpeg mutagen
    if [ $? -ne 0 ]; then
        echo "[FEHLER] Update fehlgeschlagen!"
        exit 1
    fi
    echo "[ERFOLG] Alle Pakete wurden aktualisiert"
    echo ""
else
    if [ -z "$MISSING" ]; then
        echo "[OK] Alle Pakete sind vorhanden und aktuell!"
        echo ""
    fi
fi

# Abschluss
echo "========================================"
echo "  Aktuelle Installation:"
echo "========================================"
echo ""

# yt-dlp Version anzeigen
if command -v yt-dlp &> /dev/null; then
    YTDLP_VER=$(yt-dlp --version 2>&1)
    echo "yt-dlp: Version $YTDLP_VER"
else
    echo "yt-dlp: nicht im Pfad oder nicht verfuegbar"
fi

# static-ffmpeg prüfen
$PYTHON_CMD -c "import static_ffmpeg; print('static-ffmpeg: installiert (FFmpeg wird beim ersten Programmstart automatisch geladen)')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "static-ffmpeg: nicht verfuegbar"
fi

# mutagen prüfen
$PYTHON_CMD -c "import mutagen; print(f'mutagen: Version {mutagen.__version__}')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "mutagen: nicht verfuegbar"
fi

echo ""
echo "[FERTIG] Alle Pruefungen abgeschlossen!"
echo ""