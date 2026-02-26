# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec File for openQCM Q-1 Application

This spec file is configured to create a standalone executable that:
1. Bundles all Python dependencies
2. Includes resource files (icons, images)
3. Works correctly with the resources.py path helper

Usage:
    cd OPENQCM
    pyinstaller openQCM_Q-1.spec

Output:
    dist/openQCM_Q-1/  (folder with executable and dependencies)
    or
    dist/openQCM_Q-1   (single file executable if onefile=True)
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Application info
APP_NAME = 'openQCM_Q-1'
MAIN_SCRIPT = 'run.py'

# Get the spec file directory (OPENQCM folder)
spec_dir = os.path.dirname(os.path.abspath(SPEC))

# Analysis: collect all modules and dependencies
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[spec_dir],
    binaries=[],
    datas=[
        # Resource files (bundled with the app)
        ('icons/favicon.ico', 'icons'),
        ('icons/favicon.png', 'icons'),
        ('icons/openqcm-logo.png', 'icons'),
        ('icons/start_icon.ico', 'icons'),
        ('icons/clear_icon.ico', 'icons'),
        ('icons/download_icon.ico', 'icons'),
        # Calibration data (if needed to be bundled)
        # ('openQCM/Calibration_5MHz.txt', 'openQCM'),
        # ('openQCM/Calibration_10MHz.txt', 'openQCM'),
        # ('openQCM/PeakFrequencies.txt', 'openQCM'),
    ],
    hiddenimports=[
        # PyQt5 modules
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # pyqtgraph
        'pyqtgraph',
        # numpy and scipy
        'numpy',
        'scipy',
        'scipy.signal',
        'scipy.interpolate',
        # serial communication
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        # pandas for web info
        'pandas',
        # multiprocessing
        'multiprocessing',
        # other
        'csv',
        'logging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Create the PYZ archive
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create the executable
exe = EXE(
    pyz,
    a.scripts,
    [],  # Empty for onedir mode; use a.binaries + a.zipfiles + a.datas for onefile
    exclude_binaries=True,  # True for onedir, False for onefile
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Use UPX compression if available
    console=True,  # Set to False for GUI-only (no console window)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/favicon.ico',  # Application icon
)

# Collect files for distribution (onedir mode)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# =============================================================================
# NOTES FOR BUILDING
# =============================================================================
#
# 1. INSTALL PYINSTALLER:
#    pip install pyinstaller
#
# 2. BUILD THE APPLICATION:
#    cd OPENQCM
#    pyinstaller openQCM_Q-1.spec
#
# 3. OUTPUT LOCATION:
#    dist/openQCM_Q-1/
#
# 4. IMPORTANT FILES TO INCLUDE WITH DISTRIBUTION:
#    - logged_data/ folder (create empty if not exists)
#    - openQCM/ folder with calibration files:
#      - Calibration_5MHz.txt
#      - Calibration_10MHz.txt
#      - PeakFrequencies.txt
#
# 5. FOR SINGLE-FILE EXECUTABLE (optional):
#    Change exclude_binaries=False in EXE section
#    Remove COLLECT section
#    Add a.binaries + a.zipfiles + a.datas to EXE
#
# 6. FOR GUI-ONLY (no console window):
#    Change console=True to console=False in EXE section
#
# =============================================================================
