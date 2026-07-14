# openQCM Q-1 - Changelog v3.0

## Version 3.0 - May 2026

---

# PART 1: CODE FIXES AND OPTIMIZATIONS

## CRITICAL FIX: Signal Accumulation (Memory Leak)

### Problem
In `_update_plot()`, `sigResized.connect()` was called on every timer tick (50ms), causing exponential accumulation of signal handlers.

```python
# BEFORE - in _update_plot() called every 50ms
def updateViews1():
    self._plt1.setGeometry(self._plt0.vb.sceneBoundingRect())
    self._plt1.linkedViewChanged(self._plt0.vb, self._plt1.XAxis)

updateViews1()
self._plt0.vb.sigResized.connect(updateViews1)  # MEMORY LEAK
```

### Impact
| Time | Accumulated Handlers | Effect |
|------|---------------------|--------|
| 1 sec | 20 handlers | Slight slowdown |
| 10 sec | 200 handlers | Laggy GUI |
| 1 min | 1200 handlers | Resize impossible |

### Solution
Moved `sigResized.connect()` to `_configure_plot()` (called once at startup).

```python
# AFTER - in _configure_plot() called ONCE
def updateViews1():
    self._plt1.setGeometry(self._plt0.vb.sceneBoundingRect())
    self._plt1.linkedViewChanged(self._plt0.vb, self._plt1.XAxis)

self._plt0.vb.sigResized.connect(updateViews1)  # Single handler
updateViews1()  # Initial sync
```

### Modified Files
- `mainWindow.py`: lines 488-530 (`_configure_plot`)
- `mainWindow.py`: lines 805-827 (`_update_plot` - REFERENCE SET section)
- `mainWindow.py`: lines 844-870 (`_update_plot` - REFERENCE NOT SET section)

---

## OPTIMIZATION: CPU with setData()

### Problem
Inefficient `clear()` + `plot()` pattern on every timer tick.

### Solution
Use persistent `PlotCurveItem` objects with `setData()`.

```python
# Initialization (once)
self._curve_frequency = self._plt2.plot(pen=Constants.plot_colors[2], name='Frequency')

# Update (every 50ms)
self._curve_frequency.setData(x=time_buffer, y=freq_buffer)
```

### Benefits
- Eliminates continuous memory allocation/deallocation
- Reduces CPU overhead
- Smoother plot rendering

---

## OPTIMIZATION: Resize Event Debouncing

### Problem
During window resize, plots were redrawn continuously causing lag.

### Solution
Implemented debounce mechanism that suspends updates during resize.

```python
def resizeEvent(self, event):
    if hasattr(self, '_resize_timer'):
        self._is_resizing = True
        self._resize_timer.start(150)  # 150ms debounce
    super(MainWindow, self).resizeEvent(event)

def _on_resize_finished(self):
    self._is_resizing = False

def _update_plot(self):
    # Always consume queues (prevents overflow)
    self.worker.consume_queue1()
    # ...

    # Skip drawing during resize
    if self._is_resizing:
        return
```

---

## CONFIG: Timer Polling

Timer reduced from 200ms to 50ms for better responsiveness.

```python
# constants.py
plot_update_ms = 50  # Was 200ms
```

---

# PART 2: GUI DEVELOPMENT

## Unified Single Window Interface

Consolidated original 3-window architecture into single unified window.

### Layout
```
┌─────────────────────────────────────────────────────────────┐
│                        Menu Bar                             │
├──────────┬────────────────────────────────┬─────────────────┤
│          │                                │                 │
│  LEFT    │          CENTER                │     RIGHT       │
│ SIDEBAR  │         (TabWidget)            │    SIDEBAR      │
│          │                                │                 │
│ Controls │  ┌──────────┬───────────┐      │  Current        │
│          │  │  Plots   │ System Log│      │  Readings       │
│ - Mode   │  ├──────────┴───────────┤      │                 │
│ - Port   │  │                      │      │  Reference      │
│ - Freq   │  │   Amplitude/Phase    │      │                 │
│          │  │                      │      │  Software       │
│ Actions  │  │   Frequency/Diss     │      │  Info           │
│          │  │                      │      │                 │
│ Plot     │  │   Temperature        │      │                 │
│ Controls │  │                      │      │                 │
│          │  └──────────────────────┘      │                 │
│ Status   │                                │                 │
└──────────┴────────────────────────────────┴─────────────────┘
```

---

## Tab System

### TAB 1: Plots
Real-time graphs:
- Amplitude / Phase (dual Y-axis)
- Resonance Frequency / Dissipation (dual Y-axis)
- Temperature

### TAB 2: System Log
Integrated console displaying all log messages:
- Redirects `stdout` and `stderr`
- Auto timestamp `[HH:MM:SS]`
- Monospace font (Consolas)
- Dark background with green text (#00ff00)

```python
class LogStream:
    def write(self, text):
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        QtCore.QMetaObject.invokeMethod(
            self.text_widget, "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, timestamp + text.rstrip())
        )
```

---

## Dark/Light Theme System

### Menu Access
`View > Theme > Dark Theme / Light Theme`

### Dark Theme Colors
| Element | Color |
|---------|-------|
| Background | #2b2b2b |
| Foreground | #e0e0e0 |
| Accent | #00bcd4 |
| Plot BG | #2b2b2b |

### Light Theme Colors
| Element | Color |
|---------|-------|
| Background | #f5f5f5 |
| Foreground | #333333 |
| Accent | #00838f |
| Plot BG | #ffffff |

### Curve Colors (Light Theme)
Darker colors for visibility on white background:
- Frequency: #0066cc
- Dissipation: #cc6600
- Temperature: #cc3300

---

## Layout Fixes

### Minimum Window Height
```python
MainWindow.setMinimumSize(QtCore.QSize(1200, 720))
```

### Plot Control Buttons
Fixed height to prevent overlap:
```python
self.pButton_Clear.setFixedHeight(30)
self.pButton_Reference.setFixedHeight(30)
self.pButton_Autoscale.setFixedHeight(30)
```

---

## Plot Enhancements

### Grid
Added grid with transparency on all plots:
```python
self._plt0.showGrid(x=True, y=True, alpha=0.3)
```

### Legends
Added legends to identify curves:
```python
self._legend0 = self._plt0.addLegend(offset=(10, 10))
self._legend0.setBrush(pg.mkBrush('#3c3c3c80'))
```

### Standardized Axes
Uniform color (#a0a0a0) for all axes.

---

---

# PART 3: CROSS-PLATFORM COMPATIBILITY

## Windows Serial Port Fixes

Three sequential fixes to achieve full Windows compatibility:

### 1. fcntl Module Not Available
**Problem:** `fcntl` is Unix-only; importing it on Windows raises `ModuleNotFoundError`.

**Solution:** Platform-conditional import — `msvcrt.locking()` on Windows, `fcntl.flock()` on Unix.

### 2. False "Port Already in Use" Error
**Problem:** The `fcntl`-based file lock incorrectly reported COM ports as busy on Windows (including Parallels VMs).

**Solution:** Skip file-based locking entirely on Windows (`sys.platform == 'win32'` → `return True`). Windows COM ports are natively exclusive — only one process can open them at a time.

### 3. "Access is Denied" on Measurement Start
**Problem:** `_serial_lock` (the `serial.Serial` object held open to reserve the port) was only released before Peak Detection, not before Measurement mode. On Windows, where COM ports are truly exclusive, `SerialProcess` could not open the port → `PermissionError 13`.

**Solution:** Release `_serial_lock` before **any** acquisition (both Measurement and Peak Detection). Reacquire via `_finalize_acquisition_stop()` after stop.

### Modified Files
- `openQCM/common/fileManager.py` — Platform-conditional locking
- `openQCM/ui/mainWindow.py` — Serial lock release for all acquisition modes

---

## Windows Sampling Time Optimization

**Problem:** Busy-wait loop in `Serial.py` polling `inWaiting()` with no pause caused CPU scheduling contention on Windows (default timer resolution 15.6 ms), leading to sampling time oscillations.

**Solution:** Added `sleep(0.001)` between polls. The 1 ms sleep yields the CPU quantum to the scheduler, reducing jitter. The sleep only executes while waiting for data — once the sweep terminator `'s'` arrives, the loop exits immediately.

```python
while 1:
    buffer += self._serial.read(self._serial.inWaiting()).decode(Constants.app_encoding)
    if 's' in buffer:
        break
    sleep(0.001)  # Yield CPU to reduce Windows scheduling jitter
```

### Modified Files
- `openQCM/processors/Serial.py` — Busy-wait loop sleep

---

## Left Panel Scroll Fix

**Problem:** Left sidebar elements overlapped when the window height was reduced below the content height.

**Solution:** Wrapped the left sidebar in a `QScrollArea` so content scrolls instead of overlapping. Increased right margin to prevent scrollbar from covering widgets.

### Modified Files
- `openQCM/ui/mainWindow_ui.py` — QScrollArea wrapper for left sidebar

---

# PART 4: PEAK DETECTION SYSTEM

## Two-Phase Peak Detection Algorithm

Replaced the legacy single-pass peak finder with a two-phase algorithm:

### Phase 1 — Fundamental Search
- Scans the full 1–12 MHz range
- Identifies the strongest peak as the fundamental frequency
- Auto-detects QCM type (5 MHz or 10 MHz) from the fundamental value

### Phase 2 — Overtone Search
- Searches in ±400 kHz windows centered on expected overtone frequencies
- Cross-validates candidates against the phase signal (frequency difference + phase threshold)
- Filters out spurious peaks from electrical noise

### Fallback
If the new algorithm fails (no peaks found), a legacy `FindPeak()` fallback activates automatically.

### Modified Files
- `openQCM/processors/Calibration.py` — Two-phase algorithm, auto-detect QCM type
- `openQCM/core/constants.py` — Calibration frequency files for 5/10 MHz

---

## Peak Data View

Diagnostic visualization accessible from **Data → Peak Data View**:
- Raw amplitude signal with baseline correction
- Detected peak markers (labeled F1, F3, F5, F7, F9)
- Performance optimized: `clipToView`, `downsample(mode='peak')`, `skipFiniteCheck` for 50k+ data points
- Follows the main GUI dark/light theme setting

### Modified Files
- `openQCM/ui/mainWindow.py` — Peak Data View dialog, data menu integration
- `openQCM/ui/mainWindow_ui.py` — Menu item, dialog class

---

## Peak Detection UI Improvements

- Popup labels: peaks named as **Fundamental**, **Overtone 3**, **Overtone 5**, etc. (QCM odd harmonics: 1, 3, 5, 7, 9)
- Peak Data View plot: peaks labeled as **F1**, **F3**, **F5**, **F7**, **F9**
- Removed 3 MHz QCM references (only 5 MHz and 10 MHz supported)

---

# PART 5: ADDITIONAL GUI FEATURES

## Unified Plot Colors

Standardized curve colors across all themes and reference modes:

| Curve | Color | Hex |
|-------|-------|-----|
| Frequency | Blue | #008EC0 |
| Dissipation | Brown | #DD8E6B |

Only the temperature curve changes color with theme switching.

### Modified Files
- `openQCM/core/constants.py` — Color palette indices 2, 3

---

## Overtone Quick-Select Buttons

Five checkable buttons (**F0**, **F3**, **F5**, **F7**, **F9**) below the frequency dropdown for rapid overtone selection:

- Buttons enabled only for peaks found during calibration
- Bidirectional sync: click button → updates dropdown; change dropdown → highlights button
- Disabled during acquisition, hidden in calibration mode
- Styled for both dark and light themes (blue `#008EC0` when selected)
- Selected overtone stays highlighted with blue even when buttons are disabled (`:checked:disabled` CSS state)

### Modified Files
- `openQCM/ui/mainWindow.py` — Button creation, sync logic, enable/disable management
- `openQCM/ui/mainWindow_ui.py` — Button container, dark/light theme stylesheets

---

## Log Filename Display

Shows the current acquisition CSV filename during measurement:

- **Sidebar:** Truncated with `QFontMetrics.elidedText(Qt.ElideMiddle)` to prevent layout disruption; full name in tooltip
- **Window title bar:** Full filename (e.g., `openQCM Q-1 — 2026-Mar-09_14-15-08_fundamental.csv`)
- Cleared when acquisition stops, restoring default title

### Modified Files
- `openQCM/ui/mainWindow.py` — Filename display in `start()` / `stop()`
- `openQCM/ui/mainWindow_ui.py` — `lblLogFile` QLabel (blue `#008EC0`)

---

# PART 6: FIRMWARE VERSION CHECK

## Firmware Query Protocol

Added firmware version identification via serial command:

- **Python side:** Sends `b'F\n'` to device, reads response after 400 ms timeout
- **Firmware side (.ino):** `#define FW_VERSION "2.2"`, command handler responds with `Serial.println(FW_VERSION)`
- Input buffer flushed with `reset_input_buffer()` before sending query to clear residual ADC sweep data

---

## Version Check Logic

Three cases after querying the device:

| Response | Action |
|----------|--------|
| Empty (no response) | Warning: firmware doesn't support version query → offer update |
| Different version | Warning: version mismatch → offer update |
| Matching version | Info popup (manual) or silent pass (auto-check) |

### Double Escalation
If the user declines the first update prompt, a second critical warning explains the risks of running with incorrect firmware and offers the update again.

### Trigger Points
- **Automatic:** After successful serial connection (`auto_mode=True`, silent if OK)
- **Manual:** Help → Check Firmware Version (`auto_mode=False`, always shows result)

---

## Firmware Updater Integration

Cross-platform launcher for external firmware update tools:

| Platform | Tool | Launch Method |
|----------|------|---------------|
| macOS | `Teensy.app` | `subprocess.Popen(["open", path])` |
| Windows | `TyUploader.exe` | `subprocess.Popen([path])` |
| Linux | `Teensy` | `subprocess.Popen(["xdg-open", path])` |

### Serial Port Release
Before launching the updater, the application performs a full disconnect:
1. Close `_serial_lock` (serial.Serial object)
2. Release file-based port lock
3. Update UI to disconnected state

This ensures the external updater can access the USB/serial device without conflicts.

### Modified Files
- `openQCM/ui/mainWindow.py` — `_check_firmware_version()`, `_run_firmware_updater()`
- `openQCM/ui/mainWindow_ui.py` — Help menu item
- `openQCM/core/constants.py` — `fw_version = "2.2"`
- `firmware/openQCM_Q-1_FW_py_v2.2_T40/openQCM_Q-1_FW_py_v2.2_T40.ino` — FW_VERSION define, `F` command handler

---

# PART 7: INFRASTRUCTURE

## Conda Environment Setup

Automated environment creation with `setup_env.sh` and `environment.yml`:
- Exact pinned dependency versions (PyQt 5.9.2, pyqtgraph 0.11.0, etc.)
- Apple Silicon support via Rosetta 2 (`CONDA_SUBDIR=osx-64`)
- Cross-platform: macOS, Linux, Windows

## Repository Structure

Added to the repository:
- `firmware/` — Teensy firmware source code (Arduino `.ino`), build artifacts excluded via `.gitignore`
- `firmware_update/` — Platform-specific firmware update tools (Teensy.app, TyUploader.exe, compiled `.hex`)
- `TODO.md` — Development checklist with GitHub-compatible checkboxes

## Production Configuration

`Constants.environment` set to `50` (production ring buffer size for sweep accumulation / temporal averaging).

---

# PART 8: GUI POLISH, PLOT IMPROVEMENTS & BUG FIXES — March 2026

## Brand Header Relocated to Tab Bar

Moved brand header (logo + "openQCM Q-1" + subtitle) from left sidebar to the tab bar using `QTabWidget.setCornerWidget(Qt.TopRightCorner)`. Text-first layout (right-aligned) with 30x30 icon. Frees sidebar vertical space, no vertical space taken from plots.

## Log Filename Format

Changed CSV log filename format from `2026-Mar-11_11-44-15_3th Overtone.csv` to `2026-03-11_11-44-15_F3.csv`:
- Numeric month (`%m`) instead of abbreviated (`%b`)
- Compact overtone names: F0, F3, F5, F7, F9

## Log Data View Improvements

- X-axis now uses `hh:mm:ss` time format (matching main GUI)
- Custom right-click context menu: Auto-scale, Reset Zoom, Pan Mode, Select Mode
- Fixed double context menu bug (both plots shared same scene, signal was connected twice)

## Minimum Y-Axis Scale Enforcement

Prevents autoscale "noise explosion" when signals are stable:
- Frequency: minimum 100 Hz range
- Dissipation: minimum 1e-6 range
- Temperature: minimum 2°C range

Hidden easter egg: right-click on logo → "Unlock Axes" / "Lock Axes" to toggle limits.

## Plot Color Uniformity

- Amplitude: white (dark mode) / black (light mode)
- Phase: #008EC0 (blue, matching frequency color)
- Same colors applied in Raw Data View (scatter + spline)
- Raw Data View: larger scatter points (size 5), proper legends
- Raw Data View: custom right-click context menu

## Peak Detection Bug Fixes

- **False "Success" fix**: validate fundamental is a plausible QCM frequency (4-6 MHz or 9-11 MHz range). Spurious peaks (e.g. 1.173 MHz) now correctly trigger "Peak Detection Warning"
- **Flag missing overtones**: error flag set when ALL expected peaks are zero
- **CalibrationPlot crash fix**: `np.atleast_2d()` prevents IndexError when only one peak is found in PeakFrequencies.txt

## Cursor Delta Time Fix

Fixed cursor ΔT calculation: values were in microseconds (raw timestamp units), now correctly converted to seconds for display.

## Default Window Size

Reduced from 900px to 850px height — fits MacBook Air 13" with dock visible.

---

# PART 9: TRACKING SAFETY, SIGNAL QUALITY & BUFFER STATISTICS — April 2026

## Tracking Safety (Auto-disable / Auto-resume)

Auto-tracking now disables itself when the resonance peak is lost for too many consecutive sweeps and re-enables itself automatically when the peak returns. New constants in `constants.py`:

- `auto_tracking_max_edge_errors = 10` — disable after 10 consecutive sweeps with both -3dB frequencies missing
- Re-enable trigger: a single sweep with the peak back and at least one -3dB frequency identifiable

The Serial process maintains a `_consecutive_edge_errors` counter and emits dedicated tracking events (`disabled_by_errors=True/False`) on the `parser_tracking` queue. The Worker turns these into one-shot GUI notifications: the status bar shows **"Tracking Stopped"** (red) on the disable transition and **"Tracking Resumed"** (green) on auto re-enable.

## Sensor Disconnection Detection

When the quartz sensor is physically disconnected, the openQCM board keeps streaming amplifier noise. `parameters_finder()` would still find a "peak" (argmax of noise) and the -3dB walk would find spurious edges — no warning was ever raised. Fix:

- New `Constants.min_valid_q_factor = 100`
- `parameters_finder()` now sets `_err1 = _err2 = 1` if the computed Q-factor is below this threshold
- This reuses the existing "-3dB frequency not found" warning pipeline AND the tracking-safety counter, so a disconnected sensor triggers the same recovery flow as a lost peak

## Trimmed Mean Buffer Statistics

The circular buffer of 50 samples used for frequency / dissipation / temperature smoothing was previously processed with Savitzky-Golay (window=3, order=1) followed by `np.average`. Numerical analysis revealed that mean(SG(buffer)) ≡ mean(buffer) w.r.t. outlier sensitivity (a single outlier of 10 kHz contributed +200 Hz regardless of SG window size).

Switched to `scipy.stats.trim_mean` with 10% per side (drops 5 highest + 5 lowest, averages the remaining 40). Verified on synthetic scenarios:

| Method | 1 outlier (+10 kHz) | Burst of 3 outliers | Linear drift (real signal) |
|---|---|---|---|
| `np.average` | +200 Hz error | +600 Hz error | +0.17 Hz |
| `np.median` | +0.23 Hz | +0.32 Hz | +1.10 Hz |
| **`trim_mean(0.10)`** | **+0.31 Hz** | **0.00 Hz** | **+0.26 Hz** |

5h27 acquisition validation on Windows VM showed continuous fluid streaming with zero drops. The 10% parameter is provisional and tracked for tuning in TODO.md.

## Cut-off Edge Threshold Refinement

Peak detection magnitude/phase frequency-difference threshold raised from 25 kHz to 50 kHz (`peak_freq_diff_divisor: 4 → 2`). A real-world counter-example (`tools/Calibration_10MHz.txt`) showed a valid F3 overtone at 30.091 MHz being rejected by only 10 kHz excess due to asymmetric peak shape on higher overtones.

## Standalone Diagnostic Tools

Three new analysis scripts in `tools/`:

- **`peak_detection_analyzer.py`** — full replay of the peak-detection algorithm on a calibration file with 4-panel matplotlib diagnostic
- **`overtone_analyzer.py`** — focused zoom on a single overtone window (magnitude + phase + cross-validation visualisation)
- **`qcm_data_analyzer.py`** — interactive PyQt5 + pyqtgraph tool: opens a CSV log, plots Frequency / Dissipation vs Time with two draggable cursors, shows live statistics (mean, variance, std, min, max, median) and histograms (sampling interval, frequency, dissipation) on the cursor-selected subset

Counter-example data is shipped in `tools/Calibration_10MHz.txt` for regression analysis.

---

# PART 10: CODE CLEANUP & PUBLIC RELEASE PREP — April 2026

Comprehensive cleanup pass to prepare the codebase for public sharing on GitHub and openQCM community contribution. No behavioural changes.

## Module-Level Cleanup

Every backend module (`Serial.py`, `Calibration.py`, `worker.py`, `constants.py`, `switcher.py`, `Parser.py`, `ringBuffer.py`, `app.py`, `popUp.py`, common helpers) received:

- Module-level docstrings describing responsibilities
- Removal of dead commented-out code (legacy CSV-on-each-sweep dumps, wavelet smoothing demo, `#TODO check QCM` Italian banners, debug-only `print` lines, unused `progress` import comments)
- Method-level docstrings rewritten in idiomatic English
- Italian comments translated
- Section banners (`####################`) trimmed and made functional
- Imports regrouped per PEP 8 (stdlib → third-party → project)

Total: ~3500 lines removed, ~2400 added. Net reduction in source size while improving readability.

## Latent Bugfixes Found During Cleanup

Real defects spotted and corrected in passing:

- `Architecture.get_os()` was missing the `@staticmethod` decorator (the line read just `staticmethod` without the `@`)
- `FileManager.create_full_path()` used `is (A or B)` for the OS check, which evaluates to `is A` due to Python operator precedence → on Linux it incorrectly used Windows backslashes
- `FileManager.create_dir(None)` raised `TypeError` instead of returning False
- `FileManager.file_exists(None)` returned `None` implicitly

## Menu Bar Reorganisation

Switched from `View / Data / Help` to the standard scientific desktop convention `File / View / Tools / Help`:

| Menu | Contents |
|---|---|
| **File** | Open Log… (Ctrl+O) — Quit (Ctrl+Q) |
| **View** | Left Panel — Status Bar — Cursors — Theme submenu |
| **Tools** | Measurement Parameters — Raw Data View — Peak Data View — `─` — Check Firmware Version |
| **Help** | User Guide — Website — Email Support — `─` — Check for Updates… — Download Update — `─` — About openQCM Q-1 |

All action variable names preserved → no signal-wiring changes needed in `mainWindow.py`. Convention aligns with Origin, ImageJ, MATLAB, NIS-Elements, FIJI.

## UI Polish

- Default window size finalised to 1200 × 900 px
- Dissipation displayed with one decimal digit (`{:.1f}e-06`)
- `pandas` import in `get_web_info()` wrapped in try/except so the application boots even when the dependency is excluded from the frozen build

---

# PART 11: WINDOWS STANDALONE DISTRIBUTION — April 2026

First binary release infrastructure: a single self-contained `.exe` for Windows users who do not want a Python install.

## PyInstaller Configuration

`openQCM_Q-1.spec` reorganised:

- `ONEFILE = True` → single `dist/openQCM_Q-1.exe` (~305 MB after exclusions)
- `CONSOLE = True` for the first beta builds (toggle to False for production)
- Hidden imports added: `progressbar`, `scipy.stats`, `urllib.request`, `webbrowser`
- `pandas` excluded from the bundle (saves ~150 MB) — `get_web_info()` falls back gracefully
- Other excludes: `tkinter`, `matplotlib`, `IPython`, `jupyter`, `notebook`

## Robustness for Fresh Installs

The application now self-creates its runtime directories at startup so the bundled `.exe` works on a fresh Windows install with no companion folder:

- New `OPENQCM._ensure_runtime_dirs()` helper creates `openQCM/`, `logged_data/` and the log directory next to the executable
- `Serial.get_speeds()` returns `[]` instead of crashing if `PeakFrequencies.txt` is missing
- `MainWindow._source_changed()` shows a guidance message in Measurement mode when no calibration is available
- `Worker.start()` blocks Measurement-mode acquisition with a clear log message if the calibration file is absent
- `Calibration.py` does `os.makedirs(..., exist_ok=True)` defensively before `np.savetxt`
- Spurious init-time `_source_changed(Measurement)` call (caused by the Qt signal firing before `setCurrentIndex(calibration)`) eliminated by blocking signals during the default-mode setup

## Firmware Updater Path Fix

`mainWindow._run_firmware_updater()` resolved its target path with `os.path.dirname(__file__)`, which points inside `_MEIPASS` in frozen builds and could never find `firmware_update/TyUploader.exe`. Switched to `get_data_path("firmware_update")` so the path resolves to the executable's directory in production and to `OPENQCM/` in dev mode.

## Release Bundle Workflow

New `tools/build_release.bat` (Windows one-shot build) and `tools/package_release.py` (post-build assembler):

```
tools\build_release.bat
```

builds `dist/openQCM_Q-1_release/`:

```
openQCM_Q-1.exe                          (the application)
openQCM/PeakFrequencies.txt              (factory-default calibration)
openQCM/Calibration_5MHz.txt
openQCM/Calibration_10MHz.txt
firmware_update/TyUploader.exe           (Teensy firmware tool)
firmware_update/openQCM_Q-1_FW_*.hex     (firmware binary)
logged_data/                             (empty — fills with CSV runs)
README.txt                               (first-run instructions)
```

This folder can be zipped and distributed directly. The release was validated on Windows: full Peak Detection + Measurement cycle works on a clean machine without a Python install.

---

# PART 12: SPLASH, HYSTERESIS, PLOTS & BUILD POLISH — May 2026

## Splash Screen

Added a PyInstaller splash screen that displays during the one-file `.exe` extraction phase. The splash uses an opaque PNG (`icons/splash.png`) with `text_pos=(40, 470)` enabled so users get visual feedback while the bootloader unpacks DLLs.

PyInstaller 5.x overwrites our default text with extracted-DLL filenames. This was initially disabled (image-only), then re-enabled after user preference — verbose extraction messages are preferred over a silent splash. A custom Tcl script to filter bootloader chatter while keeping application progress messages is tracked as a future enhancement.

## Console Window Removed

Two changes to eliminate the DOS console flash on Windows:

- **`os.system('cls')` removed** from `MainWindow.start()` — it was spawning a `CONSOLE`-subsystem `cmd.exe` on every START, causing a visible flash and a 100-300 ms delay in the windowed `.exe`.
- **`_winapi.CreateProcess` monkey-patch** in `app.py` — injects `CREATE_NO_WINDOW` into the creation flags for `multiprocessing` child processes, preventing console windows from spawning.
- **`CONSOLE = False`** in the spec file — the `.exe` now runs as a pure Windows application with no attached console.

## Tracking-Safety Hysteresis

Refined the auto-tracking disable/re-enable thresholds to prevent "monitoring flicker" when the sensor is being detached or reconnected:

| Transition | Threshold | Before |
|---|---|---|
| Disable (peak lost) | **10** consecutive bad sweeps | 10 (unchanged) |
| Re-enable (peak back) | **5** consecutive good sweeps | 1 (too sensitive) |

New constant: `auto_tracking_consecutive_good_to_resume = 5` in `constants.py`. The asymmetric hysteresis (5 vs 10) eliminates rapid enable/disable cycling during gradual sensor detachment while still recovering promptly when the peak stabilises.

## Calibration Plot Redesign

Full visual overhaul of the Peak Detection Diagnostic dialog (`calibrationPlot.py`):

- **Colour alignment**: plot colours now match the main GUI palette instead of using independent colours
- **Layering**: solid baseline drawn above the raw signal for clarity; raw signal uses a lighter shade
- **Raw signal in legend**: previously unlabeled, now visible with its own legend entry
- **Phase peak markers**: star markers on the phase plot show detected phase peaks; circle markers show the corresponding amplitude-peak reference frequency for cross-validation
- **Custom right-click menu**: Auto-scale, Reset Zoom, Pan Mode, Show/Hide Grid — consistent with all other plot dialogs

## Grid Toggle

Grid is now **OFF by default** in all plots (main window, Data Viewer, Raw Data View, Calibration Plot). A **Show/Hide Grid** toggle has been added to every custom right-click context menu. The `_is_grid_on(plot)` helper is duplicated in each module to avoid circular imports.

## Right-Click on Temperature Plot Fix

Right-click on the Temperature plot was incorrectly dispatching to the Amplitude/Phase context menu. Root cause: the hit-test logic only checked `_plt0`/`_plt2` but not `_plt4` (Temperature). Fixed with a unified `_dispatch_right_click` helper that tests all plot viewboxes against the click position.

## Terminology: "cut-off" → "-3dB frequency"

Renamed every occurrence of "cut-off frequency" to "-3dB frequency" across 5 files (GUI labels, console prints, comments, docs). The term "-3dB frequency" is technically precise for the amplitude crossings used in bandwidth / Q-factor computation, while "cut-off" implies a filter characteristic that does not apply here.

## Build Pipeline Polish

- `tools/build_release.bat`: added `--log-level WARN` to suppress per-DLL extraction noise during PyInstaller builds
- `tools/package_release.py`: switched from `shutil.copy` to `shutil.move` for the `.exe`; cleans stray `dist/logged_data` directory left by PyInstaller

## Repository Cleanup

- Removed `docs/LICENSE.txt` and `docs/gpl.txt` — redundant copies of the GPLv3 license already present in the root `LICENSE` file
- Rewrote `TODO.md`: translated to English, removed completed items, updated file/line references, added Monitoring section for known behaviours to watch

---

# PART 13: PRE-v2.2 FIRMWARE QUERY COMPATIBILITY — June 2026

## Problem

Connecting the v3.0 software to a device running **firmware older than v2.2**
(no `F`/`S` command handlers) produced two failures: the firmware-version and
serial-number dialogs showed a dump of raw sweep data instead of the version /
serial, and the board could become wedged for minutes and stop responding to
acquisition (measurement and peak detection produced no data).

## Root Cause

Pre-v2.2 firmware feeds any serial input straight to its sweep parser. That
parser latches an internal `message` flag to `1` after the first acquisition
and **never clears it**. So a bare `F\n` / `S\n` is misread as a sweep command:
`freq_start = atol("F") = 0` while `freq_stop` / `freq_step` keep the previous
measurement's values. The result is a full scan from 0 Hz to several MHz at a
few-Hz step — **hundreds of thousands of points (~375k)** that flood the serial
line and wedge the Teensy 4.0 until it is physically reset.

Confirmed empirically (2026-06-23): the RX buffer is empty (`inWaiting()==0`)
*before* the query and only fills *after* `F` is sent — it is **not** a stale
host/OS buffer. A physical USB replug appears to "fix" it only because it
power-cycles the Teensy (native USB CDC, no FTDI), resetting `message` and
aborting the giant sweep.

## Solution — Range-Priming + Reply Validation (commit `d9cb2ef`)

Unified all device queries in `mainWindow._query_device()`:

1. **Range-prime**: send a trivial `1;1;1\n` sweep command first, pinning
   `freq_start = freq_stop = freq_step = 1`. Any subsequent legacy misparse is
   then bounded to a 1–2 point sweep instead of a 375k-point scan. Flush the
   tiny priming sweep, then send the real `F\n` / `S\n`.
2. **Validate the reply format**: version must match `^\d{1,2}\.\d{1,3}$`
   (e.g. `2.2`); serial must match `^\d{1,3}-\d{4}$` (e.g. `19-0055`) or be
   `NO_SERIAL`. Anything else is treated as "firmware too old" — a clean
   prompt to update, never a raw sweep dump in the dialog.

On v2.2+ the priming is an inert 1-point sweep (flushed before reading), and
the `F`/`S` handlers short-circuit before the sweep parser regardless — so
behaviour is unchanged for current firmware.

### Why both parts are required
Two earlier single-part attempts were reverted (commits `c432e49`,
`b873b49`/`9cffa66`). Drain/timeout machinery alone **blocks** for the entire
375k-point sweep; format-validation alone cleans the display but leaves the
board wedged (still needs a replug). Only **priming + validation together**
let old firmware be used across connect/disconnect without a physical replug.

## Validation (2026-06-24)

- **Cross-platform** (pre-v2.2 firmware + v3.0 software): connect → refuse
  update → measure → stop → disconnect → reconnect → clean "firmware too old?"
  prompt, no sweep dump, no wedge, no replug. PASS on macOS Intel (from
  source), macOS Apple Silicon M2 (arm64), Linux, Windows (Parallels VM).
- **Backward compatibility** (v2.2 firmware + old `openQCM_Q-1_py_v2.1`
  software): PASS. The old software never sends `F`/`S`, so v2.2's new handlers
  are never hit; the measurement path is byte-identical (POT 240, AVERAGING 1,
  RESOLUTION 12, AVERAGE_SAMPLE 5000, 115200 baud).

### Modified Files
- `openQCM/ui/mainWindow.py` — `_query_device()` (new, range-primed), used by
  `_check_firmware_version()` and `_query_serial_number()`

---

*Development assisted by Claude Code — February 2026 onwards*
