# openQCM Q-1

**Real-time GUI software for the openQCM Q-1 quartz crystal microbalance**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.6+](https://img.shields.io/badge/Python-3.6%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

An open-source Python application to display, process, and store data in real-time from the [openQCM Q-1](https://openqcm.com/) device. The software monitors resonance frequency and dissipation variations of a quartz crystal microbalance through real-time analysis of the resonance curve.

---

## Features

### Real-Time Data Acquisition
- Serial port connection to the openQCM Q-1 device with automatic port detection
- Multiprocessing architecture for non-blocking acquisition and UI rendering
- Support for **5 MHz** and **10 MHz** quartz crystal sensors
- Configurable sampling with multiple overtones (Fundamental, 3rd, 5th, 7th)

### Dual Operating Modes
- **Measurement Mode** — Continuous frequency sweep acquisition with real-time resonance frequency and dissipation tracking
- **Peak Detection Mode** — Automatic identification of resonance peaks across the full frequency spectrum

### Real-Time Plotting
- **Amplitude / Phase** sweep (dual Y-axis)
- **Resonance Frequency / Dissipation** time series (dual Y-axis)
- **Temperature** monitoring
- Interactive zoom, pan, auto-scale, and measurement cursors

### Data Analysis Tools
- **Raw Data View** — Live visualization of the current frequency sweep with:
  - SG-filtered data points (scatter)
  - Spline interpolation fit (smooth curve)
  - Peak maximum marker
  - -3 dB bandwidth region highlighting (dissipation measurement)
  - Real-time Q-factor and dissipation readout
- **Log Data View** — Load and visualize previously recorded CSV data files
- **Measurement Cursors** — Dual draggable cursors with delta readout for frequency and dissipation

### Auto-Tracking
Automatically recalculates the sweep frequency window when the resonance frequency drifts beyond a configurable threshold, ensuring the peak remains centered in the measurement range.

### Data Logging
- Automatic CSV export with millisecond-precision timestamps
- Columns: Date, Time, Relative Time, Temperature, Resonance Frequency, Dissipation
- Timestamped filenames for organized data management

### User Interface
- Unified single-window layout with left sidebar (controls), center (plots), and right sidebar (readings)
- **Dark / Light theme** switching optimized for lab environments
- Integrated **System Log** tab with timestamped console messages
- Reference tracking for baseline comparison

---

## Installation

### Requirements

- Python 3.9
- Anaconda or Miniconda
- openQCM Q-1 device connected via USB

### Recommended: Automated Environment Setup

The project includes an automated setup script that creates a conda environment with the exact tested dependency versions. This is the recommended method as it ensures full compatibility across platforms.

```bash
cd openQCM_Q-1
chmod +x setup_env.sh
./setup_env.sh
```

The script automatically:
- Detects your platform (macOS, Linux, Windows) and CPU architecture
- Handles Apple Silicon Macs via Rosetta 2 (x86_64 packages)
- Creates a `openqcm` conda environment with pinned dependency versions
- Verifies the installation

After setup, run the application with:

```bash
/path/to/anaconda3/envs/openqcm/bin/python run.py
```

Or activate the environment first:

```bash
conda activate openqcm
python run.py
```

You can also create the environment directly from the `environment.yml` file:

```bash
conda env create -f environment.yml
```

> **Note for Apple Silicon (M1/M2/M3) users**: the environment uses x86_64 packages via Rosetta 2 for compatibility with PyQt 5.9. Rosetta 2 must be installed on your system.

### Alternative: pip install

```bash
pip install -r requirements.txt
```

Or install individually:

```bash
pip install PyQt5 pyserial pyqtgraph numpy scipy
```

> **Note**: pip install uses the latest available versions, which may cause compatibility issues. The conda environment method above is recommended.

### Linux — Serial Port Permissions

On Linux, grant access to the serial port:

```bash
sudo usermod -a -G dialout $USER
sudo usermod -a -G uucp $USER
```

Log out and log back in for changes to take effect.

---

## Usage

### Run the Application

```bash
cd openQCM_Q-1
python run.py
```

Or as a Python module:

```bash
cd openQCM_Q-1
python -m openQCM
```

### Quick Start

1. Connect the openQCM Q-1 device via USB
2. Launch the application
3. Select the serial port from the dropdown and click **Connect**
4. Choose the quartz crystal frequency (5 MHz or 10 MHz) and overtone
5. Click **START** to begin acquisition

### Build Standalone Executable

```bash
pip install pyinstaller
cd openQCM_Q-1
pyinstaller openQCM_Q-1.spec
```

The executable will be generated in `dist/openQCM_Q-1/`.

---

## Project Structure

```
openQCM_Q-1/
├── run.py                  # Application entry point
├── setup_env.sh            # Automated conda environment setup
├── environment.yml         # Conda environment specification
├── requirements.txt        # Python dependencies (pip)
├── openQCM_Q-1.spec        # PyInstaller build configuration
├── openQCM/                # Main Python package
│   ├── app.py              # Application bootstrap
│   ├── core/
│   │   ├── constants.py    # Configuration parameters
│   │   ├── worker.py       # Multiprocessing management
│   │   └── ringBuffer.py   # Circular buffer for time series
│   ├── processors/
│   │   ├── Serial.py       # Device communication and signal processing
│   │   ├── Parser.py       # Data queue distribution
│   │   └── Calibration.py  # Peak detection routines
│   ├── ui/
│   │   ├── mainWindow.py   # Main window controller
│   │   ├── mainWindow_ui.py# UI layout, stylesheets, and dialogs
│   │   └── popUp.py        # Notification dialogs
│   ├── common/             # Utilities (logging, file I/O, OS detection)
│   ├── Calibration_5MHz.txt
│   └── Calibration_10MHz.txt
├── icons/                  # Application icons
├── logged_data/            # CSV data output directory
└── docs/                   # License files
```

---

## Architecture

The application uses a **multiprocessing pipeline** to separate data acquisition from the UI:

```
┌──────────────┐    Queue 1-6    ┌────────────┐    Buffers    ┌──────────────┐
│ SerialProcess │ ─────────────> │   Worker    │ ──────────> │  MainWindow  │
│ (child proc.) │                │ (consumer)  │              │ (Qt UI loop) │
└──────────────┘                └────────────┘              └──────────────┘
      │                                                            │
   Serial Port                                              PyQtGraph Plots
   (openQCM Q-1)                                            CSV Export
```

- **SerialProcess** — Runs in a separate OS process; reads raw ADC data, applies baseline correction, Savitzky-Golay filtering, spline interpolation, and peak/bandwidth computation
- **Worker** — Consumes multiprocessing queues and stores data in ring buffers
- **MainWindow** — Qt timer (50 ms) reads buffers and updates plots using efficient `setData()` calls

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **3.0** | February 2026 | Unified single-window UI, dark/light themes, auto-tracking, Raw Data View, measurement cursors, CSV timestamp precision fix, Peak Detection restart fix, performance optimizations |
| 2.1 | 2024 | Calibration optimization, 200 ms plot refresh, macOS/Linux fixes |
| 2.0 | 2020 | Initial Python implementation |

See [CHANGELOG.md](CHANGELOG.md) for detailed development notes.

---

## License

This project is distributed under the [GNU General Public License v3.0](LICENSE).

---

## Links

- **Website**: [openqcm.com](https://openqcm.com/)
- **GitHub**: [github.com/openQCM](https://github.com/openQCM)
- **Contact**: info@openqcm.com

**Developed by** [openQCM Team](https://openqcm.com/) / [Novaetech S.r.l](https://openqcm.com/)

*Version 3.0 development assisted by [Claude Code](https://claude.ai/)*
