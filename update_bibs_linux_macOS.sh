#!/bin/bash

echo ""
echo "========================================"
echo "   yt-dlp Package Manager - Update & Check"
echo "========================================"
echo ""
echo "[INFO] Checking Python environment..."
echo ""

# Determine Python command (prefer python3)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python is not installed or not on PATH!"
    echo ""
    echo "Please install Python from https://www.python.org/"
    echo "On Linux/macOS: python3 or python."
    exit 1
fi

# Show Python version
PYTHON_VER=$($PYTHON_CMD --version 2>&1)
echo "[OK] $PYTHON_VER found"
echo ""

# Check pip availability
$PYTHON_CMD -m pip --version &> /dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] pip is not available!"
    echo ""
    echo "Please install pip: $PYTHON_CMD -m ensurepip --upgrade"
    exit 1
fi
echo "[OK] pip is available"
echo ""

# ─────────────────────────────────────────────────────────────────────────
# Helper: pip_install <upgrade|install> <package> [package ...]
#
# On many modern distros (Debian/Ubuntu system Python, Homebrew Python on
# macOS) pip refuses to install into the system Python at all and fails
# with "externally-managed-environment" (PEP 668). This helper detects
# that specific error and automatically retries once with
# --break-system-packages, which is safe here because this script only
# ever installs the three packages this app needs.
# ─────────────────────────────────────────────────────────────────────────
pip_install() {
    local action="$1"
    shift
    local extra_args=()
    if [ "$action" = "upgrade" ]; then
        extra_args+=(--upgrade)
    fi

    local output
    output=$($PYTHON_CMD -m pip install "${extra_args[@]}" "$@" 2>&1)
    local status=$?

    if [ $status -ne 0 ] && echo "$output" | grep -q "externally-managed-environment"; then
        echo "[INFO] This Python installation is externally managed (PEP 668 –"
        echo "       common on Debian/Ubuntu system Python and Homebrew Python)."
        echo "[INFO] Retrying with --break-system-packages (installs only the"
        echo "       3 packages this app needs, nothing else is touched)..."
        echo ""
        output=$($PYTHON_CMD -m pip install --break-system-packages "${extra_args[@]}" "$@" 2>&1)
        status=$?
    fi

    echo "$output"

    if [ $status -ne 0 ]; then
        echo ""
        echo "[HINT] If this still fails, consider a virtual environment instead:"
        echo "       $PYTHON_CMD -m venv ~/.venvs/yt-downloader"
        echo "       source ~/.venvs/yt-downloader/bin/activate"
        echo "       pip install \"yt-dlp[default]\" mutagen"
    fi

    return $status
}

# Defined packages
# Note: FFmpeg is NOT installed separately anymore.
# static-ffmpeg downloads and caches the current FFmpeg binary automatically
# on first start of the downloader (not needed at all on Linux/macOS, see README).
PACKAGES=("yt-dlp[default]" "static-ffmpeg" "mutagen")

MISSING=()
HAS_UPDATES=0

# Check which packages are missing
# Uses importlib.metadata (Python standard library) instead of the deprecated
# pkg_resources / setuptools, which is not guaranteed to be installed on every
# Python setup (e.g. a plain "python3 -m venv" on newer Python versions).
echo "[INFO] Checking installed packages..."
echo ""

for PACKAGE in "${PACKAGES[@]}"; do
    # Strip the "[default]" extra to get the base package name
    if [[ "$PACKAGE" == *"[default]"* ]]; then
        BASE="${PACKAGE%\[default\]}"
    else
        BASE="$PACKAGE"
    fi

    $PYTHON_CMD -c "import importlib.metadata as m; m.version('$BASE')" &> /dev/null
    if [ $? -ne 0 ]; then
        echo "[MISSING] $PACKAGE"
        MISSING+=("$PACKAGE")
    else
        VERSION=$($PYTHON_CMD -c "import importlib.metadata as m; print(m.version('$BASE'))" 2>&1)
        echo "[FOUND] $PACKAGE (version: $VERSION)"
    fi
done

echo ""

# Check for available updates
echo "[INFO] Checking for available updates..."
echo ""

OUTDATED_LIST=$($PYTHON_CMD -m pip list --outdated --format=columns 2>/dev/null)

for PACKAGE in "${PACKAGES[@]}"; do
    if [[ "$PACKAGE" == *"[default]"* ]]; then
        BASE="${PACKAGE%\[default\]}"
    else
        BASE="$PACKAGE"
    fi

    # Only consider packages that are actually installed (skip missing ones here,
    # they are handled by the install step below)
    CURRENT=$($PYTHON_CMD -c "import importlib.metadata as m; print(m.version('$BASE'))" 2>/dev/null)
    if [ -z "$CURRENT" ]; then
        continue
    fi

    OUTDATED=$(echo "$OUTDATED_LIST" | grep "^$BASE " | awk '{print $2}')
    if [ -n "$OUTDATED" ]; then
        echo "[UPDATE] Update available for $PACKAGE (current $CURRENT -> $OUTDATED)"
        HAS_UPDATES=1
    else
        echo "[CURRENT] $PACKAGE is up to date ($CURRENT)"
    fi
done

echo ""

# Install missing packages
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[ACTION] Installing missing packages..."
    echo ""
    pip_install install "${MISSING[@]}"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Installation failed!"
        exit 1
    fi
    echo "[SUCCESS] Missing packages have been installed"
    echo ""
fi

# Install updates
if [ $HAS_UPDATES -eq 1 ]; then
    echo "[ACTION] Installing updates..."
    echo ""
    pip_install upgrade "yt-dlp[default]" static-ffmpeg mutagen
    if [ $? -ne 0 ]; then
        echo "[ERROR] Update failed!"
        exit 1
    fi
    echo "[SUCCESS] All packages have been updated"
    echo ""
else
    if [ ${#MISSING[@]} -eq 0 ]; then
        echo "[OK] All packages are present and up to date!"
        echo ""
    fi
fi

# Summary
echo "========================================"
echo "  Current installation:"
echo "========================================"
echo ""

# Show yt-dlp version
if command -v yt-dlp &> /dev/null; then
    YTDLP_VER=$(yt-dlp --version 2>&1)
    echo "yt-dlp: version $YTDLP_VER"
else
    echo "yt-dlp: not on PATH or not available"
fi

# Check static-ffmpeg (optional on Linux/macOS)
$PYTHON_CMD -c "import static_ffmpeg; print('static-ffmpeg: installed (not required on Linux/macOS, system ffmpeg is used instead)')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "static-ffmpeg: not installed (fine on Linux/macOS as long as system ffmpeg is installed)"
fi

# Check mutagen
$PYTHON_CMD -c "import importlib.metadata as m; print(f'mutagen: version {m.version(\"mutagen\")}')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "mutagen: not available"
fi

echo ""
echo "[DONE] All checks completed!"
echo ""
