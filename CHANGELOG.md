# openQCM Q-1 - Changelog v3.0

## Version 3.0 - February 2026

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

*Development assisted by Claude Code — February–March 2026*
