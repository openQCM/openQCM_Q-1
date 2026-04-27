"""
Build the openQCM Q-1 Windows release bundle.

After PyInstaller has produced `dist/openQCM_Q-1.exe`, run this script to
assemble the user-facing release folder under `dist/openQCM_Q-1_release/`:

    dist/openQCM_Q-1_release/
        openQCM_Q-1.exe          ← the standalone executable
        openQCM/                 ← runtime data directory
            PeakFrequencies.txt   (factory default — overwritten by Peak Detection)
            Calibration_5MHz.txt  (factory default)
            Calibration_10MHz.txt (factory default)
        logged_data/             ← empty, will fill with measurement CSV logs
        README.txt               ← first-run instructions

Usage:
    cd OPENQCM
    pyinstaller openQCM_Q-1.spec
    python tools/package_release.py

The factory-default calibration files are copied from the repository so that
the application can boot on first launch even before the user runs Peak
Detection. They will be overwritten the first time the user calibrates a
real sensor.
"""
import os
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent           # OPENQCM/
DIST_DIR = REPO_ROOT / "dist"
EXE_NAME = "openQCM_Q-1.exe"
RELEASE_DIR = DIST_DIR / "openQCM_Q-1_release"

# Factory-default runtime files (copied next to the .exe at packaging time).
RUNTIME_FILES = [
    REPO_ROOT / "openQCM" / "PeakFrequencies.txt",
    REPO_ROOT / "openQCM" / "Calibration_5MHz.txt",
    REPO_ROOT / "openQCM" / "Calibration_10MHz.txt",
]

README_CONTENT = """\
openQCM Q-1 — Standalone Windows build
======================================

First run
---------
1. Connect the openQCM Q-1 device via USB.
2. Double-click `openQCM_Q-1.exe`.
3. The application starts in Peak Detection mode by default.
4. Click START to calibrate the connected sensor — the calibration
   files in the `openQCM/` folder will be overwritten with the
   sensor's actual peak frequencies.
5. Once calibration completes, switch to Measurement mode from the
   sidebar and click START again to begin a real measurement run.

Measurement logs
----------------
Each acquisition is saved as a CSV file in the `logged_data/` folder
with the name `YYYY-MM-DD_hh-mm-ss_Fn.csv` (e.g.
`2026-04-27_15-30-00_F3.csv`).

Folder layout
-------------
openQCM_Q-1.exe          — the application
openQCM/                 — calibration files (auto-updated)
logged_data/             — measurement CSV logs (auto-created on each run)

Source code, documentation and updates
--------------------------------------
https://github.com/openQCM/openQCM_Q-1
https://openqcm.com/

License: GPLv3
"""


def main():
    # Locate the executable produced by PyInstaller
    exe_src = DIST_DIR / EXE_NAME
    if not exe_src.is_file():
        sys.exit(
            "ERROR: {} not found.\n"
            "Run `pyinstaller openQCM_Q-1.spec` first.".format(exe_src))

    # Wipe any previous release folder, recreate the layout
    if RELEASE_DIR.exists():
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True)
    (RELEASE_DIR / "openQCM").mkdir()
    (RELEASE_DIR / "logged_data").mkdir()

    # Copy the executable
    shutil.copy2(exe_src, RELEASE_DIR / EXE_NAME)
    print("Copied:", EXE_NAME)

    # Copy the factory-default runtime files
    missing = []
    for src in RUNTIME_FILES:
        if src.is_file():
            shutil.copy2(src, RELEASE_DIR / "openQCM" / src.name)
            print("Copied:", src.name)
        else:
            missing.append(src.name)
    if missing:
        print("WARNING: missing factory-default files:", ", ".join(missing))
        print("The release will still boot, but the user will need to run")
        print("Peak Detection before any Measurement is possible.")

    # Write the README
    (RELEASE_DIR / "README.txt").write_text(README_CONTENT, encoding="utf-8")
    print("Wrote:    README.txt")

    print()
    print("Release bundle ready:", RELEASE_DIR)


if __name__ == "__main__":
    main()
