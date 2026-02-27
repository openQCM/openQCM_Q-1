#!/bin/bash
# ============================================================================
# openQCM Q-1 - Environment Setup Script
# ============================================================================
# Creates a conda environment with the exact dependencies required to run
# the openQCM Q-1 application.
#
# Usage:
#   chmod +x setup_env.sh
#   ./setup_env.sh
#
# Requirements:
#   - Anaconda or Miniconda installed
#   - On Apple Silicon (M1/M2/M3): Rosetta 2 installed
# ============================================================================

set -e

ENV_NAME="openqcm"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Colors for output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Step 1: Find conda ---
info "Looking for conda..."
if command -v conda &>/dev/null; then
    CONDA_EXE="$(command -v conda)"
elif [ -f "$HOME/opt/anaconda3/bin/conda" ]; then
    CONDA_EXE="$HOME/opt/anaconda3/bin/conda"
elif [ -f "$HOME/anaconda3/bin/conda" ]; then
    CONDA_EXE="$HOME/anaconda3/bin/conda"
elif [ -f "$HOME/miniconda3/bin/conda" ]; then
    CONDA_EXE="$HOME/miniconda3/bin/conda"
elif [ -f "/opt/anaconda3/bin/conda" ]; then
    CONDA_EXE="/opt/anaconda3/bin/conda"
elif [ -f "/opt/miniconda3/bin/conda" ]; then
    CONDA_EXE="/opt/miniconda3/bin/conda"
else
    error "conda not found. Please install Anaconda or Miniconda first.
    Download from: https://docs.conda.io/en/latest/miniconda.html"
fi
info "Found conda at: $CONDA_EXE"

# --- Step 2: Detect platform and architecture ---
OS="$(uname -s)"
ARCH="$(uname -m)"
info "Detected platform: $OS ($ARCH)"

case "$OS" in
    Darwin)
        SUBDIR="osx-64"
        if [ "$ARCH" = "arm64" ]; then
            info "Apple Silicon detected — will use x86_64 packages via Rosetta 2"
            # Verify Rosetta 2 is available
            if ! /usr/bin/pgrep -x oahd >/dev/null 2>&1; then
                warn "Rosetta 2 does not appear to be installed."
                warn "Installing Rosetta 2..."
                softwareupdate --install-rosetta --agree-to-license 2>/dev/null || true
            fi
        fi
        ;;
    Linux)
        SUBDIR="linux-64"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        SUBDIR="win-64"
        ;;
    *)
        error "Unsupported operating system: $OS"
        ;;
esac

# --- Step 3: Check if environment already exists ---
if $CONDA_EXE env list 2>/dev/null | grep -q "^${ENV_NAME} "; then
    warn "Environment '$ENV_NAME' already exists."
    read -p "Do you want to remove it and recreate? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Removing existing environment..."
        $CONDA_EXE env remove -n "$ENV_NAME" -y
    else
        info "Keeping existing environment. Exiting."
        exit 0
    fi
fi

# --- Step 4: Create environment with correct platform ---
info "Creating conda environment '$ENV_NAME' (platform: $SUBDIR)..."
CONDA_SUBDIR="$SUBDIR" $CONDA_EXE create -n "$ENV_NAME" python=3.9.12 -y

# --- Step 5: Configure environment to always use correct platform ---
CONDA_PREFIX="$($CONDA_EXE info --base)/envs/$ENV_NAME"
echo "subdir: $SUBDIR" > "$CONDA_PREFIX/.condarc"
info "Environment configured for platform: $SUBDIR"

# --- Step 6: Install dependencies ---
info "Installing dependencies (this may take a few minutes)..."
CONDA_SUBDIR="$SUBDIR" $CONDA_EXE install -n "$ENV_NAME" \
    pyqt=5.9.2 \
    qt=5.9.7 \
    sip=4.19.13 \
    pyqtgraph=0.11.0 \
    numpy=1.21.5 \
    scipy=1.7.3 \
    pyserial=3.5 \
    pandas=1.4.2 \
    lxml \
    -y

# --- Step 7: Install pip dependencies ---
info "Installing pip dependencies..."
"$CONDA_PREFIX/bin/pip" install progressbar==2.5

# --- Step 8: Verify installation ---
info "Verifying installation..."
"$CONDA_PREFIX/bin/python" -c "
import sys
print(f'  Python:    {sys.version.split()[0]}')
from PyQt5 import QtGui, QtWidgets
print(f'  PyQt5:     OK')
import pyqtgraph
print(f'  pyqtgraph: {pyqtgraph.__version__}')
import numpy
print(f'  numpy:     {numpy.__version__}')
import scipy
print(f'  scipy:     {scipy.__version__}')
import serial
print(f'  pyserial:  OK')
import pandas
print(f'  pandas:    {pandas.__version__}')
import lxml
print(f'  lxml:      OK')
print()
print('  All dependencies verified successfully!')
"

# --- Done ---
echo ""
info "============================================"
info "  Environment '$ENV_NAME' is ready!"
info "============================================"
echo ""
echo "  To run the application:"
echo ""
echo "    Option 1 (direct):"
echo "      $CONDA_PREFIX/bin/python run.py"
echo ""
echo "    Option 2 (activate environment first):"
echo "      conda activate $ENV_NAME"
echo "      python run.py"
echo ""
