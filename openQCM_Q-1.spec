# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the openQCM Q-1 Windows executable.

Mode:
    onefile — produces a single self-contained .exe in `dist/`.
    Console window kept visible for the first beta builds (set
    `CONSOLE = False` once the GUI is stable to hide the DOS prompt).

Build:
    cd OPENQCM
    pyinstaller openQCM_Q-1.spec

Output:
    dist/openQCM_Q-1.exe

Runtime data files (NOT bundled — stay next to the .exe so they remain
writable across runs):
    logged_data/                    — measurement CSV logs
    openQCM/Calibration_5MHz.txt    — calibration sweeps (written by Peak
    openQCM/Calibration_10MHz.txt     Detection)
    openQCM/PeakFrequencies.txt     — detected peak frequencies

`openQCM/common/resources.py:get_data_path()` resolves these paths next
to the executable when running frozen, and next to OPENQCM/ in dev mode.
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------- Build options ----------
APP_NAME = 'openQCM_Q-1'
MAIN_SCRIPT = 'run.py'
CONSOLE = False         # Hide the Windows console window (release mode)
ONEFILE = True          # Single-file executable (False → onedir)

spec_dir = os.path.dirname(os.path.abspath(SPEC))

# Note: cleanup of previous `build/` and `dist/` folders cannot be done here.
# PyInstaller creates its working directory `build/<APP_NAME>/` BEFORE parsing
# the spec, so any rmtree at this point would race with PyInstaller and break
# the build. Use the wrapper `tools/build_release.bat` (Windows) or pass
# `pyinstaller --clean openQCM_Q-1.spec` to clear the PyInstaller cache.


# ---------- Analysis: dependency discovery ----------
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[spec_dir],
    binaries=[],
    datas=[
        # Resource files bundled inside the executable. At runtime they are
        # extracted to sys._MEIPASS and accessed via get_resource_path().
        ('icons/favicon.ico', 'icons'),
        ('icons/favicon.png', 'icons'),
        ('icons/openqcm-logo.png', 'icons'),
        ('icons/start_icon.ico', 'icons'),
        ('icons/clear_icon.ico', 'icons'),
        ('icons/download_icon.ico', 'icons'),
    ],
    hiddenimports=[
        # PyQt5 — fonts / styles / image plugins are picked up automatically
        # by PyInstaller's PyQt5 hook (no manual handling needed).
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # pyqtgraph
        'pyqtgraph',
        # NumPy / SciPy
        'numpy',
        'scipy',
        'scipy.signal',
        'scipy.interpolate',
        'scipy.stats',                # explicit — used for trim_mean
        # Serial communication
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        # Console progress widgets used by Serial / Calibration processes
        'progressbar',
        # Standard library modules referenced at runtime
        'urllib',
        'urllib.request',
        'csv',
        'logging',
        'multiprocessing',
        'webbrowser',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Excluded to shrink the bundle — none of these are needed at runtime.
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        # `pandas` is heavy (~150 MB) and only used by `get_web_info()` for
        # parsing the openQCM news HTML table. The function gracefully
        # disables itself if pandas is unavailable (see mainWindow.py).
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------- Splash screen ----------
# Shown by the PyInstaller bootloader while the onefile bundle is extracting
# and the Python interpreter / Qt are warming up. The image disappears as
# soon as MainWindow calls `pyi_splash.close()` from app.py.
#
# Text overlay disabled on purpose: with `text_pos` set, the PyInstaller
# bootloader (5.x) writes the name of every DLL it extracts on the splash
# label, which is visually noisy. Setting `text_pos=None` removes the
# label widget, so the bootloader has nowhere to write and the user sees
# the bare image — clean and professional.
# Side effect: `pyi_splash.update_text(...)` from app.py becomes a no-op
# (raises RuntimeError, swallowed by the helper).
splash = Splash(
    'icons/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    minify_script=True,
    always_on_top=False,                # do not steal focus from other windows
)


# ---------- EXE / COLLECT ----------
if ONEFILE:
    # Single-file executable: splash, binaries + zipfiles + datas in EXE,
    # no COLLECT.
    exe = EXE(
        pyz,
        a.scripts,
        splash,
        splash.binaries,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='icons/favicon.ico',
    )
else:
    # onedir: EXE references the binaries, COLLECT bundles them in a folder.
    exe = EXE(
        pyz,
        a.scripts,
        splash,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=CONSOLE,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='icons/favicon.ico',
    )
    coll = COLLECT(
        exe,
        splash.binaries,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )

# =============================================================================
# Build notes
# =============================================================================
# 1. Install PyInstaller in the project conda environment:
#        pip install pyinstaller
#
# 2. Build:
#        cd OPENQCM
#        pyinstaller openQCM_Q-1.spec
#
# 3. Distribute (Windows):
#        - Single file:    dist/openQCM_Q-1.exe
#        - Ship next to it: an empty `logged_data/` folder, and an
#          `openQCM/` folder where Peak Detection will write the
#          calibration files.
#
# 4. To hide the console window in release: set CONSOLE = False above.
#
# 5. To switch to onedir distribution: set ONEFILE = False above. The
#    output becomes `dist/openQCM_Q-1/` (folder with the exe + DLLs).
# =============================================================================
