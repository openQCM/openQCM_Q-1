# openQCM Q-1 v3.0 — User Guide Generation Brief

This document is a technical briefing for an AI assistant to generate a **detailed end-user guide** for the openQCM Q-1 GUI software v3.0. It describes every feature, workflow, dialog, menu, status indicator, file format, and troubleshooting scenario the user will encounter.

## Instructions for the AI

- **Audience**: Researchers, lab technicians, and scientists using the openQCM Q-1 quartz crystal microbalance in their experiments. Assume basic familiarity with QCM measurements but not with the software.
- **Tone**: Clear, instructional, practical. Use numbered steps for procedures. Avoid jargon without explanation.
- **Format**: Organize as a full user guide with a Table of Contents, chapters for each major feature, and an appendix for reference (file formats, troubleshooting).
- **Length**: Comprehensive (target 20–40 pages). Include screenshots placeholders like `![Figure: Left sidebar layout]` where screenshots would help.
- **Language**: Generate in **English** by default. A separate Italian translation may be requested.
- **Include**: Practical examples ("To measure the mass change during protein adsorption, do..."), tips, notes on common pitfalls, and explanations of the physics where relevant.

---

## 1. Product Overview

**openQCM Q-1** is an open-source quartz crystal microbalance instrument and GUI software for real-time resonance frequency and dissipation measurements. Typical applications: thin-film mass sensing, protein/DNA binding kinetics, electrochemistry, viscoelastic property studies.

- **License**: GPLv3
- **Vendor**: openQCM / Novaetech
- **Hardware**: USB-connected board with Teensy microcontroller, socket for replaceable quartz crystal sensors (5 MHz or 10 MHz fundamental)
- **Firmware version reported by device**: 2.2
- **Software version**: 3.0 (dev)

### Key Physics Concepts (for guide context)

- **Resonance frequency (f)**: shifts as mass accumulates on the sensor. Sauerbrey equation: Δf ∝ Δm.
- **Dissipation (D = 1/Q)**: quality factor inverse. Increases for viscoelastic/soft films; stays low for rigid films.
- **Overtones**: odd harmonics (3f, 5f, 7f, 9f) probe different penetration depths. Comparing Δf across overtones discriminates rigid vs. viscoelastic behavior.

---

## 2. System Requirements & Installation

- **Platforms**: macOS, Windows, Linux
- **Python**: 3 (bundled in conda environment)
- **Dependencies**: PyQt5, pyqtgraph, pyserial, numpy, scipy, matplotlib
- **Setup**: `setup_env.sh` creates a pinned conda environment (`environment.yml`). On Apple Silicon, uses Rosetta 2 (`CONDA_SUBDIR=osx-64`).
- **Launch**: `python app.py` (or platform-specific launchers in `scripts/`)

---

## 3. Main Window Layout

The GUI has three zones:

### 3.1 Left Sidebar (top to bottom)

1. **Brand Header** — Logo (30×30 icon) + "openQCM Q-1" + subtitle "Quartz Crystal Microbalance"
2. **Serial Connection** — Port dropdown, Refresh button, Connect/Disconnect button
3. **Measurement Setup** — Mode dropdown (Measurement / Peak Detection), Frequency combobox, Overtone quick-select buttons (F0, F3, F5, F7, F9)
4. **Current Readings** — Frequency (Hz), Dissipation (×10⁻⁶), Temperature (°C)
5. **Plot Controls** — Clear, Set Reference, Autoscale (enabled only during acquisition)
6. **Acquisition** — Sampling rate display, Log filename, START/STOP (unified button)

### 3.2 Center Area (QTabWidget)

- **Plots tab**: two stacked plots in a vertical splitter
  - Top: Amplitude (white dark / black light) + Phase (blue) vs Frequency (Hz), plus Temperature (white dark / black light) vs Time
  - Bottom: Resonance Frequency (blue) + Dissipation (brown) vs Time (hh:mm:ss), shared X-axis
- **System Log tab**: scrollable plain-text log (captures stdout/stderr from Python side and Serial process)

### 3.3 Bottom Status Bar

- Left: connection state indicator (gray=disconnected, green=connected)
- Center: Status label (Disconnected / Processing / Monitoring / Warning / Tracking Stopped)
- Right: live readings (F, D, T, Sampling time in ms)
- Info bar below: contextual text messages

---

## 4. Menu Bar

### 4.1 View Menu

- **Dark Theme** (default) / **Light Theme** — toggles entire GUI stylesheet including plots
- **Toggle Cursors** — show/hide two vertical measurement cursors on the Frequency/Dissipation plot (yellow C1, green C2). ΔT (seconds), ΔF (Hz), ΔD (×10⁻⁶) shown in top-left corner of the plot. Cursors are draggable.

### 4.2 Data Menu

- **Log Data View** — open a saved CSV log file and plot Frequency/Dissipation vs elapsed time (hh:mm:ss)
- **Raw Data View** — real-time scatter plot of Savitzky-Golay filtered amplitude + spline fit + peak marker + -3dB bandwidth highlight, plus phase below (live during acquisition)
- **Peak Data View** — diagnostic view of the last calibration (raw, baseline, corrected signal, detected peaks F0/F3/F5/F7/F9 labeled)
- **Measurement Parameters** — non-modal info dialog with: mode, overtone, port, sweep start/stop/range, reference frequency, Q-factor, bandwidth, sample size

### 4.3 Help Menu

- **Firmware Check** — reads firmware version from device and compares with expected (2.2)
- **Check for Updates** — queries the remote repository for newer software versions
- **Download Update** — opens the download page in the default browser

---

## 5. Complete Workflows

### 5.1 First Connection

1. Plug in the openQCM Q-1 device via USB
2. Click **Refresh** in Serial Connection → the Port dropdown populates with available serial ports
3. Select the correct port (typically `/dev/cu.usbmodem…` on macOS, `COM…` on Windows, `/dev/ttyACM…` on Linux)
4. Click **Connect** → indicator turns green, status: "Connected"
5. The serial port stays reserved until Disconnect is pressed

### 5.2 Peak Detection (Calibration) — Required Before First Measurement

1. Select **Peak Detection** in the Mode dropdown (this is the default on startup)
2. Click **START** — the system sweeps 1–51 MHz in 10 sections (1 kHz step) and detects:
   - The **fundamental** resonance (search: 1–12 MHz)
   - The **overtones** (3×, 5×, 7×, 9× fundamental) in ±400 kHz windows
3. Status bar shows "Peak Detection Success" or "Peak Detection Warning" on completion
4. Three files are written:
   - `openQCM/PeakFrequencies.txt` — detected peaks
   - `openQCM/Calibration_5MHz.txt` or `Calibration_10MHz.txt` — full sweep data
5. Open **Data → Peak Data View** to inspect the calibration visually

### 5.3 Measurement Mode

1. Switch the Mode dropdown to **Measurement**
2. Use the **Overtone quick-select buttons** (F0, F3, F5, F7, F9) to choose which harmonic to measure — the Frequency combobox updates accordingly
3. Set the **Sample** count (default: 501) — higher samples = narrower step but slower sweeps
4. Enable **Export** checkbox to save CSV log (filename auto-generated: `YYYY-MM-DD_hh-mm-ss_Fn.csv`, saved in `logged_data/`)
5. Click **START** — real-time plotting begins immediately
6. During acquisition, the window title shows the filename
7. Click **STOP** to end

### 5.4 Setting a Reference

- After measurements stabilize, click **Set Reference** — subsequent plots show Δf and ΔD (delta from reference)
- Y-axis auto-adjusts to the new dynamic range
- Click **Set Reference** again to clear and return to absolute values

### 5.5 Using Measurement Cursors

1. Enable cursors via **View → Toggle Cursors**, or right-click the Frequency/Dissipation plot → **Show Cursors**
2. Two vertical cursors appear (C1 left yellow, C2 right green)
3. Drag each cursor horizontally along the time axis
4. Read ΔT (seconds), ΔF (Hz), ΔD (×10⁻⁶) in the top-left corner

### 5.6 Browsing Saved Data

- **Data → Log Data View** → file dialog → select CSV → new independent window plots Frequency and Dissipation vs Time (hh:mm:ss)
- Multiple Log Data View windows can be open simultaneously
- Right-click a plot → Auto-scale, Reset Zoom, Pan Mode, Select Mode

---

## 6. Plots — Details and Controls

### 6.1 Main Plot Area

- **Top row**: Amplitude (dB) + Phase (deg) dual-axis plot; Temperature (°C) plot
- **Bottom row**: Resonance Frequency (Hz) + Dissipation (dimensionless, shown ×10⁻⁶) dual-axis plot
- **X-axis**: all plots share `Time (hh:mm:ss)` format (elapsed time since START)
- **Grid**: hidden by default for cleaner appearance
- **Legends**: top-left, semi-transparent backgrounds

### 6.2 Right-Click Context Menu (all plots)

- **Auto-scale** — enable pyqtgraph auto-range on both axes
- **Reset Zoom** — view all data
- **Pan Mode** — drag to move view (default)
- **Select Mode** — drag a rectangle to zoom into that region
- **Show/Hide Cursors** (only on Frequency/Dissipation plot)

### 6.3 Minimum Y-Axis Scale (Anti-Noise Feature)

To prevent noise-driven "scale explosion" when signals are stable, minimum display ranges are enforced:

- **Frequency**: 100 Hz minimum range
- **Dissipation**: 1×10⁻⁶ minimum range
- **Temperature**: 2°C minimum range

If the real data range exceeds the minimum, autoscale behaves normally.

### 6.4 Easter Egg — Lock/Unlock Axes

**Right-click on the brand logo** (top-left of the sidebar) → context menu:
- **Unlock Axes** → disables the minimum scale enforcement (pure pyqtgraph autoscale)
- **Lock Axes** → re-enables the minimum scales
- On each toggle, an autoscale is performed automatically

---

## 7. Dialogs (Data Menu)

### 7.1 Measurement Parameters Dialog

Non-modal info window showing:
- Mode (Measurement / Peak Detection), QCM type (5 MHz / 10 MHz, auto-detected)
- Overtone name (Fundamental / 3rd / 5th / 7th / 9th)
- Port, baud rate, firmware version
- Sweep start/stop/range/step (Hz), samples per sweep
- Reference frequency, Q-factor, bandwidth

Values update in real-time (polled every ~200 ms).

### 7.2 Raw Data View Dialog

Live view during acquisition:
- **Top plot**: scatter points of filtered amplitude (white dark / black light), spline-fit curve (orange), peak marker (red diamond), -3dB bandwidth region (green shaded)
- **Bottom plot**: phase vs frequency (blue)
- X-axes are linked (zoom/pan sync)
- Info label: overtone, peak frequency, bandwidth, Q-factor, dissipation
- Updates every 300 ms (independent timer, zero overhead on acquisition pipeline)

### 7.3 Peak Data View Dialog

Shows the last calibration result:
- **Amplitude plot**: raw signal (gray thin), baseline polynomial fit (orange dashed), corrected signal (red bold), peak markers (green circles labeled F1/F3/F5/F7/F9)
- **Phase plot**: same structure with corrected signal in blue
- Title indicates QCM type and number of peaks found

### 7.4 Log Data View Dialog

Replay a saved CSV log:
- File selection dialog opens first
- Independent window shows Frequency and Dissipation vs Time (hh:mm:ss) — same colors as main GUI
- Multiple windows can be open in parallel
- Right-click menu: Auto-scale, Reset Zoom, Pan Mode, Select Mode

---

## 8. Status Indicators — What Each Color Means

### 8.1 Connection State (leftmost indicator in status bar)

- **Gray**: Disconnected
- **Green**: Connected

### 8.2 Status Label Colors

- **Green "Monitoring"** — acquisition running, signal healthy
- **Yellow "Processing"** — early data being computed (first ~50 sweeps)
- **Red "Warning"** — cut-off frequency not found (peak weak or damaged)
- **Red "Tracking Stopped"** — peak lost for 10 consecutive sweeps, auto-tracking disabled
- **Yellow "Auto-Tracking #N"** — drift detected, sweep window recalculated
- **Green "Tracking Resumed"** — peak recovered, tracking re-enabled automatically

### 8.3 Info Bar Messages

Contextual text: "Please wait, processing early data...", "Warning: lower cut-off not found — Auto-tracking stopped", "Monitoring!", "Auto-tracking activated: new sweep window...", etc.

---

## 9. Auto-Tracking (Resonance Drift Compensation)

During Measurement mode, the system monitors the resonance frequency and automatically shifts the sweep window when the peak drifts:

- **Trigger**: current frequency differs from the stored reference by more than 100 Hz
- **Action**: recomputes sweep start/stop around the new frequency, rebuilds baseline, increments tracking counter
- **User feedback**: yellow "Auto-Tracking #N" label briefly; System Log shows details

### 9.1 Tracking Safety — Auto-Disable and Auto-Resume

If the peak disappears (e.g., sensor detached, heavy damping):
- After **10 consecutive sweeps** with both -3dB cut-off frequencies missing, auto-tracking is **disabled**
- Status shows **"Tracking Stopped"** (red) with message appended to the cut-off warning
- When the peak returns and at least one cut-off can be identified again, tracking **re-enables automatically** ("Tracking Resumed", green)
- Alternatively, **STOP + START** fully resets state

### 9.2 Sensor Disconnection Detection

When the quartz crystal is physically disconnected (USB still plugged):
- The board keeps sending amplifier noise
- A minimum Q-factor check (Q ≥ 100) triggers the "cut-off not found" warning pipeline
- After 10 sweeps, tracking is disabled as described above

---

## 10. Peak Detection Algorithm (for Troubleshooting)

The user guide should mention this only at a high level; link to a separate technical doc for math details.

- **Phase 1**: fundamental frequency search in 1–12 MHz using `scipy.signal.argrelextrema` with 6 MHz minimum distance between candidates. Selects the highest-amplitude peak.
- **QCM auto-detection**: 4–6 MHz → 5 MHz sensor; 9–11 MHz → 10 MHz sensor; otherwise invalid.
- **Phase 2**: for each odd overtone (3×, 5×, 7×, 9×), search ±400 kHz around expected frequency. Cross-validate magnitude peak vs phase peak:
  - Frequency difference between mag and phase peaks must be < 50 kHz
  - Phase peak must exceed 10°
- **Validation**: fundamental must be in a valid QCM range; if all peaks are zero, peak detection is flagged as failed.

If calibration fails, open **Peak Data View** to see what was detected. Two diagnostic CLI tools are available:

- `tools/peak_detection_analyzer.py <calibration_file>` — full algorithm replay with 4-panel plot
- `tools/overtone_analyzer.py <calibration_file> <n>` — zoom on a specific overtone with mag/phase overlay

---

## 11. File Formats

### 11.1 Measurement Log CSV (`logged_data/*.csv`)

- Filename format: `YYYY-MM-DD_hh-mm-ss_Fn.csv` (e.g. `2026-03-11_11-44-15_F3.csv`)
- Columns (comma-separated):
  1. `Date` (ISO 8601)
  2. `Time` (HH:MM:SS)
  3. `Relative_time` (seconds since START, float)
  4. `Temperature` (°C, float)
  5. `Resonance_Frequency` (Hz, float)
  6. `Dissipation` (dimensionless, float — multiply by 1e6 for display)

### 11.2 Calibration Files

- **`openQCM/Calibration_5MHz.txt`** / **`Calibration_10MHz.txt`**: 50001 rows × 3 columns (frequency Hz, amplitude dB, phase deg), 1 MHz to 51 MHz in 1 kHz steps
- **`openQCM/PeakFrequencies.txt`**: 2 columns (peak frequency, peak frequency duplicated — legacy format). Rows: fundamental, 3rd, 5th, 7th, 9th overtone (missing = 0)

---

## 12. Settings and Preferences

### 12.1 Theme

- **Dark** (default): dark panels, white text, dark plot backgrounds
- **Light**: white panels, dark text, light plot backgrounds
- Theme is applied immediately; plot colors adapt (e.g., Amplitude = white in dark / black in light)

### 12.2 Tooltips

Every interactive widget has a tooltip (hover for a short description).

### 12.3 Default Window Size

- 1200 × 850 px, minimum 1000 × 600 px (fits MacBook Air 13")

---

## 13. Firmware Check and Software Updates

### 13.1 Firmware Version

- **Help → Firmware Check**: displays current firmware version reported by the device, compares with expected (2.2)
- If mismatched, the user is directed to the firmware update procedure (external `firmware_update/` tools: Teensy.app on macOS, TyUploader.exe on Windows)

### 13.2 Software Updates

- **Help → Check for Updates**: queries the GitHub repository for newer versions
- **Help → Download Update**: opens the browser to the download page
- Updates on startup can be triggered automatically (configurable)

---

## 14. Troubleshooting

### 14.1 Port not found / "Disconnected" after clicking Connect

- Check USB cable and ports on computer side
- On Linux/macOS: ensure user has permission to access serial devices (on Linux, add user to `dialout` group)
- On Windows: check Device Manager for correct COM port number; install Teensy driver if missing
- Click **Refresh** before Connect

### 14.2 Peak Detection Warning

- Verify the quartz sensor is correctly inserted in the socket (spring-loaded contacts)
- Verify that it's a supported type (5 MHz or 10 MHz)
- If the calibration always finds a spurious peak outside valid QCM ranges, open **Peak Data View** or use `tools/peak_detection_analyzer.py` to diagnose

### 14.3 "Tracking Stopped" during measurement

- The peak was lost for 10 consecutive sweeps
- Possible causes: sensor detached, heavy loading, extreme viscosity, cable issue
- Tracking auto-resumes as soon as the peak returns with at least one identifiable -3dB cut-off
- If the signal is permanently lost, STOP and restart the calibration

### 14.4 Sampling time spikes (Windows only)

- Known issue: Windows' 15.6 ms timer resolution causes occasional jitter in sampling time
- Typical sampling: 60–80 ms; occasional spikes to 150 ms are normal
- Does not affect data quality (the timestamp reflects actual acquisition time)

### 14.5 Log file not created

- Verify the **Export** checkbox is enabled before clicking START
- Verify write permissions in `logged_data/` directory

---

## 15. Advanced Tools (`tools/`)

These are CLI scripts for power users and developers:

- **`sampling_time_monitor.py`** — analyze sampling time from a CSV log (histogram + time series)
- **`peak_detection_analyzer.py`** — standalone replay of the peak detection algorithm on a calibration file, with full 4-panel diagnostic plot
- **`overtone_analyzer.py`** — zoom into a specific overtone window to see why it was accepted or rejected (magnitude peak, phase peak, frequency difference, thresholds)

Usage:
```
python tools/peak_detection_analyzer.py openQCM/Calibration_5MHz.txt
python tools/overtone_analyzer.py openQCM/Calibration_10MHz.txt 3
python tools/sampling_time_monitor.py logged_data/2026-03-11_11-44-15_F3.csv
```

---

## 16. Keyboard and Mouse Interactions Reference

| Action | Where | Effect |
|---|---|---|
| Left-drag on plot | Any plot | Pan (default) or zoom rectangle (Select Mode) |
| Mouse wheel on plot | Any plot | Zoom around cursor position |
| Right-click on plot | Any plot | Context menu (Auto-scale, Reset Zoom, Pan/Select Mode, Cursors) |
| Drag cursor | Freq/Diss plot | Move measurement cursor |
| Right-click on logo | Brand header | Easter egg: Lock/Unlock minimum axis scale |
| Hover widget | Any button/combobox | Tooltip |

---

## 17. Known Limitations (to mention in guide)

- 9th overtone parameters (`L5_9th_overtone`, `R5_9th_overtone`, SG window) are placeholders pending validation
- On Windows, sampling time can show occasional oscillations due to timer resolution
- Peak detection freq_diff threshold is set to 50 kHz (raised from 25 kHz); may need per-overtone tuning
- Minimum dissipation display range (1×10⁻⁶) is provisional; to be tuned based on real measurements

---

## 18. Version History Reference

The CHANGELOG.md in the repository contains 8 parts covering all v3.0 developments:
- PART 1: Critical code fixes (memory leak, signal accumulation)
- PART 2: UI restructure (left sidebar, status dock, unified START/STOP)
- PART 3: Cross-platform fixes (Windows/Linux/macOS)
- PART 4: Peak detection improvements (two-phase algorithm, validation)
- PART 5: GUI features (theme toggle, tooltips, cursors, reference)
- PART 6: Firmware check and updater integration
- PART 7: Infrastructure (setup scripts, TODO/CHANGELOG)
- PART 8: GUI polish, plot improvements, tracking safety, sensor disconnect detection, Q-factor check

---

## 19. Screenshots Needed for the Guide

The AI generating the guide should insert placeholders for these:

1. Full window — Dark theme, during acquisition with peak visible
2. Full window — Light theme, with reference set (Δf plotted)
3. Left sidebar close-up showing all groups
4. Measurement Parameters dialog
5. Raw Data View during Peak Detection
6. Peak Data View with all 5 peaks labeled
7. Log Data View replaying a 2-hour session
8. Status bar close-up with Monitoring / Warning / Tracking Stopped states
9. Right-click context menu on a plot
10. Measurement cursors with ΔT/ΔF/ΔD annotation
11. Error state: sensor disconnected → warning visible

---

## 20. Glossary (to include in guide)

- **QCM**: Quartz Crystal Microbalance — mass sensor based on a resonating quartz crystal
- **Overtone**: odd harmonic of the fundamental resonance frequency (3f, 5f, 7f, 9f)
- **Dissipation (D)**: inverse of the quality factor Q, proportional to energy loss per cycle
- **Q-factor**: resonance frequency divided by -3dB bandwidth; quantifies resonance sharpness
- **-3dB bandwidth**: frequency width where amplitude drops to 70.7% of peak (half power)
- **Baseline correction**: polynomial fit subtracted from the raw sweep to remove instrumental drift
- **Savitzky-Golay filter**: sliding polynomial smoothing that preserves peak shape
- **Auto-tracking**: automatic shift of the sweep window to follow the drifting resonance peak
- **Sauerbrey equation**: Δf = -Cf·Δm (for thin rigid films on the sensor)

---

## End of Brief

Please generate a complete user guide based on this information. Include examples, tips, and practical workflows. If any area needs additional technical detail, ask before generating or make reasonable assumptions documented as notes.
