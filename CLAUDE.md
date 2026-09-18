# CLAUDE.md — orientation guide for AI assistants working on openQCM Q-1

This file is meant to be read **first** by any Claude (or other LLM) agent
that picks up work on this project. It captures the architecture, the
non-obvious conventions, and the gotchas that took several sessions to
sort out, so a fresh agent does not have to rediscover them.

The user (Marco) prefers Italian for conversation but **English-only** in
all source code, comments, commit messages and docs. Comments should
explain *why*, not restate *what*. Be concise. Always run an `ast.parse`
syntax check before committing.

---

## 1 · What this project is

openQCM Q-1 is the GUI software v3.0 for the open-source openQCM Q-1
Quartz Crystal Microbalance instrument. PyQt5 + pyqtgraph + serial
acquisition + scipy signal processing. License GPLv3.

Repo: `https://github.com/openQCM/openQCM_Q-1`

Marco keeps a clone on a Mac (development) and a Windows machine
(build/test of the standalone .exe). Local paths may have been
renamed at any time — never assume them, derive from the working
directory at session start. The package layout below is what
matters; the parent folder name is incidental.

Tested on macOS, Windows (Parallels VM and native), Linux.

---

## 2 · Repository layout

```
OPENQCM/
├─ run.py                    # entry point (thin wrapper that calls openQCM.app)
├─ openQCM/
│  ├─ app.py                 # OPENQCM class: QApplication + lifecycle
│  ├─ core/
│  │  ├─ constants.py        # all tunables + custom pyqtgraph axis classes
│  │  ├─ ringBuffer.py       # fixed-size NumPy circular buffer (newest at idx 0)
│  │  └─ worker.py           # bridge GUI ↔ child process; CSV log; tracking events
│  ├─ processors/
│  │  ├─ Serial.py           # SerialProcess — measurement-mode child process
│  │  ├─ Calibration.py      # CalibrationProcess — peak detection child process
│  │  ├─ Parser.py           # ParserProcess — fan-out queues GUI ⇄ children
│  │  └─ SocketClient.py     # reserved (unused)
│  ├─ ui/
│  │  ├─ mainWindow.py       # MainWindow — controller, plot updates, menu actions
│  │  ├─ mainWindow_ui.py    # Ui_Main, DataViewerDialog, RawDataViewDialog,
│  │  │                      # DeviceInfoDialog, _SecondsTimeAxis
│  │  ├─ calibrationPlot.py  # Peak Detection Diagnostic dialog
│  │  └─ popUp.py            # QMessageBox wrappers
│  └─ common/                # architecture / arguments / fileManager / fileStorage /
│                            # logger / resources / switcher
├─ icons/                    # bundled in PyInstaller (favicon, splash, button icons)
├─ firmware/                 # Teensy .ino sources (reference only)
├─ firmware_update/          # TyUploader.exe + Teensy.app + .hex   (used by Help → Check Firmware Version)
├─ logged_data/              # measurement CSV logs (runtime-generated, .csv ignored)
├─ tools/                    # diagnostic CLI scripts + Windows release build
│  ├─ build_release.bat              # one-shot Windows build (clean+pyinst+package)
│  ├─ package_release.py             # post-PyInstaller release-bundle assembler
│  ├─ peak_detection_analyzer.py     # standalone peak-detection replay (matplotlib)
│  ├─ overtone_analyzer.py           # zoom on a single overtone window
│  ├─ qcm_data_analyzer.py           # PyQt5 GUI for offline CSV analysis with cursors
│  ├─ sampling_time_monitor.py       # simple sampling-period histogram script
│  ├─ Calibration_10MHz.txt          # counter-example calibration file (F3 phase 35 kHz off)
│  └─ Calibration_8MHz.txt           # only real 8 MHz sweep we have (Jan 2019) — see §6
├─ tests/
│  └─ test_peak_detection.py         # offline replay of the 4 calibration files + synthetic cases
├─ docs/
│  ├─ USER_GUIDE_BRIEF.md            # spec for AI to generate the public user manual
│  ├─ peak_detection_analysis.md     # algorithm notes
│  └─ 2026-04-24_10-25-14_F0.csv     # 5h27 reference acquisition log
├─ openQCM_Q-1.spec          # PyInstaller spec (single-file Windows build)
├─ environment.yml           # conda env (Python 3.9, pyqt5, pyqtgraph, scipy, …)
├─ requirements.txt          # equivalent for pip
├─ setup_env.sh              # one-shot conda env creation
├─ TODO.md                   # tracked work items (Italian + English)
├─ CHANGELOG.md              # release notes, PART 1 … PART 11 currently
└─ README.md                 # public README
```

`Calibration_5MHz.txt`, `Calibration_10MHz.txt`, `PeakFrequencies.txt` in
`openQCM/` are runtime-written by Peak Detection. They are committed
because they double as factory defaults for fresh installs.

---

## 3 · Process model

```
            ┌──────────────────────┐
            │  GUI process (Qt)    │
            │   MainWindow         │
            │   QTimer @ 50 ms     │
            │                      │
            │   ┌──────────────┐   │
            │   │  Worker      │ ──┼──▶ ParserProcess (multiprocessing)
            │   │  (bridge)    │   │     │
            │   └──────────────┘   │     │  shared queues:
            │                      │     │   q1 amplitude trace
            └──────────────────────┘     │   q2 phase trace
                                         │   q3 (ts, smoothed_freq)
                                         │   q4 (ts, smoothed_diss)
                                         │   q5 (ts, smoothed_temp)  + cancel sentinel
                                         │   q6 [_err1, _err2, k, _flag_error_usb, _sampling]
                                         │   q_tracking [activated, start, stop, ref, count, disabled]
                                         ▼
                          ┌─────────────────────────────┐
                          │ Acquisition child process    │
                          │  · SerialProcess  (measure)  │
                          │  · CalibrationProcess (peak) │
                          └─────────────────────────────┘
                                         │
                                         ▼
                                  USB serial (Teensy)
```

Child processes are `multiprocessing.Process` subclasses. They never
touch Qt directly — every result flows through the parser queues.
The GUI polls those queues with `Worker.consume_queue*` from a
`QTimer.timeout` (`Constants.plot_update_ms = 50`).

The serial port is held open in the GUI process via `_serial_lock` to
keep it reserved across acquisitions. It is **closed** before any
START (so the child can claim it) and reacquired in
`_finalize_acquisition_stop()` after STOP.

---

## 4 · Acquisition pipeline (per sweep, in `Serial.elaborate`)

1. Subtract baseline polynomial (8th order, fit on full calibration sweep)
2. Savitzky-Golay smoothing (per-overtone window size, order 3)
3. Spline oversampling (`UnivariateSpline`, per-overtone smoothing factor)
4. `parameters_finder` — argmax + walk to ±70.7 % (-3dB) crossings →
   bandwidth, Q-factor. Sets `_err1` / `_err2` if either edge missing,
   or if `Qfac < Constants.min_valid_q_factor` (sensor disconnect detection).
5. **Tracking-safety hysteresis** (see §5)
6. Append `(freq, 1/Qfac, temperature)` to per-channel `RingBuffer` of
   size `Constants.environment` (= 50)
7. After warm-up: aggregate via `scipy.stats.trim_mean(buffer, 0.10)`
   — drops top 10 % + bottom 10 %, averages the central 80 %.
   Per-channel smoothed values pushed to GUI queues.
8. Auto-tracking re-evaluation on the smoothed frequency (see §5).

The trimmed mean is **the** outlier-suppression mechanism. Earlier we
used a Savitzky-Golay pre-filter then `np.average`, which we proved
mathematically equivalent to `np.average` alone w.r.t. outliers.

---

## 5 · Auto-tracking & tracking-safety state machine

Lives entirely in `SerialProcess.elaborate` + `check_and_update_tracking`.

```
                          ACTIVE
                          (tracking on, sweep window
                          recentred when smoothed freq drifts
                          > Constants.auto_tracking_threshold = 100 Hz)
                              │
   10 sweeps with both -3dB   │
   missing in a row           │   5 sweeps with at least one -3dB
                              ▼   in a row → re-enable
                          ARMED
                          (tracking off, GUI shows
                          "Tracking Stopped" red banner)
```

- `_consecutive_edge_errors` counts up while `(_err1 == 1 and _err2 == 1)`,
  resets on any good sweep.
- `_consecutive_good_sweeps` counts up only while ARMED and the sweep
  is good, resets on any bad sweep or after re-enable.
- Both transitions emit a payload on `parser_tracking.add_tracking([...])`
  with the trailing `disabled_by_errors` flag (`True`/`False`).
- `Worker._queue_data_tracking` translates the transitions into the
  one-shot `(disabled, first_disabled, reenabled)` tuple consumed by
  `MainWindow._handle_auto_tracking`.

Hysteresis (5 vs 10) is the cure for the "Monitoring flicker during
sensor distach" bug — see TODO.md and the commit history.

---

## 6 · Critical conventions / gotchas

- **`os.path.join` everywhere** — `Constants.slash` is legacy.
- **Never bake calibration filenames into hidden imports** — the bundled
  PyInstaller `datas` do *not* go inside the .exe; `openQCM/` lives
  next to the executable. `app.OPENQCM._ensure_runtime_dirs()` creates
  it on first run.
- **`get_data_path()`** in `openQCM/common/resources.py` is the right
  way to resolve a writable path that works in dev *and* frozen mode.
  `get_resource_path()` is for read-only bundled assets only
  (`_MEIPASS`).
- **`os.system('cls')` is forbidden in frozen builds** — it spawns a
  CONSOLE-subsystem cmd.exe and flashes a black window every time. We
  removed the one in `MainWindow.start`.
- **Multiprocessing flash on Windows** — there is a guarded patch at
  the top of `app.py` that injects `CREATE_NO_WINDOW` into
  `_winapi.CreateProcess`. Do not remove it.
- **Right-click menus and shared scenes**: when several `PlotItem`s
  share a `GraphicsLayoutWidget`, they share the same `QGraphicsScene`.
  Connecting `sigMouseClicked` per-plot means N handlers fire on every
  click. Always use a single connection per scene + hit-test (see
  `MainWindow._dispatch_right_click`, `DataViewerDialog._on_scene_click`,
  `RawDataViewDialog._on_scene_click`,
  `CalibrationPlotWindow._on_scene_right_click`).
- **`_err1`/`_err2` are per-sweep**: read by the tracking-safety logic
  in `elaborate`, then sent to GUI on parser6, then reset to 0 at the
  end of `run` for the next iteration.
- **Q-factor ≪ 100 = sensor disconnected**, *not* a bandwidth glitch.
  The check in `parameters_finder` raises both edge flags so the
  existing warning + tracking-safety pipelines kick in.
- **Splash text widget**: PyInstaller 5.x bootloader writes every
  extracted DLL filename into the splash text label by default. We
  intentionally enable `text_pos` and accept the verbose label so the
  user gets *some* feedback during startup. Setting `text_pos=None`
  silences it but also disables `pyi_splash.update_text(...)`. There is
  a TODO to investigate a custom Tcl script that suppresses the
  bootloader chatter while keeping our messages.
- **GUI grid is OFF by default everywhere**, with a Show/Hide Grid
  toggle in every custom right-click menu. `_is_grid_on(plot)` helper
  is duplicated in mainWindow.py / mainWindow_ui.py / calibrationPlot.py
  to avoid a circular import.
- **Wording**: the -3dB amplitude crossings are "**-3dB frequencies**",
  *never* "cut-off". The renaming is in commit `d1a39cf`.
- **No predefined crystal type.** Since branch `feature/generic-quartz-frequency`
  the *measured* fundamental drives everything: overtone search and validity
  (`CalibrationProcess.describe_quartz` / `is_valid_quartz`), labels and file
  names (`Constants.quartz_label` / `calibration_path_for`), Measurement
  sweep windows (`Constants.sweep_profile_for`, keyed on absolute frequency),
  GUI overtone buttons (`OvertoneSwitcher.harmonic_name`). Never reintroduce
  `4e6 < f < 6e6`-style range checks. The phase cross-check looks at the
  phase *within ±50 kHz of the magnitude peak*, not at the strongest phase
  peak of the ±400 kHz window (a spur 96 kHz off F3 of the 8 MHz sweep beat
  the true peak by 1.3°). The only real 8 MHz data is
  `tools/Calibration_8MHz.txt` (2019, custom job): the 8 MHz support was
  validated **blind** on that single file — the customer must be told so
  when they test a real 8 MHz quartz, and the 40 MHz profile in
  `sweep_profiles` is borrowed from 50 MHz pending their feedback.

---

## 7 · Build & distribution

### Dev run
```
python run.py
```

### Windows standalone build
```
cd OPENQCM
tools\build_release.bat        # one-shot: clean + pyinstaller + package
```

The script:
1. wipes `build/` and `dist/`
2. runs `pyinstaller --clean --log-level WARN --noconfirm openQCM_Q-1.spec`
3. runs `python tools\package_release.py`

Output: `dist\openQCM_Q-1_release\` containing
```
openQCM_Q-1.exe
openQCM/ (factory-default calibration files)
firmware_update/ (TyUploader.exe + .hex)
logged_data/ (empty)
README.txt
```

The release folder is what gets zipped and shared via GitHub Release.

### Spec configuration
`openQCM_Q-1.spec` exposes two top-level switches:
- `CONSOLE = False` — currently False (release mode, no DOS window)
- `ONEFILE = True` — single .exe in `dist/`
Excludes `pandas` / `matplotlib` / `tkinter` / `IPython` / `jupyter` /
`notebook` to keep the bundle around 305 MB.

`pandas` is required by `MainWindow.get_web_info()` for HTML parsing
of the openQCM news page; the import is wrapped in `try/except` so the
update-check feature self-disables in the frozen build.

---

## 8 · Diagnostic / offline tools (`tools/`)

| Tool | Purpose |
|---|---|
| `peak_detection_analyzer.py <calib_file>` | full algorithm replay with 4-panel matplotlib plot (matplotlib is *not* in the `openqcm` env; stub it or install it) |
| `overtone_analyzer.py <calib_file> <n>` | zoom on a single overtone window with mag/phase cross-validation |
| `qcm_data_analyzer.py` | interactive PyQt5 + pyqtgraph: opens a CSV log, two draggable cursors, live stats and histograms |
| `sampling_time_monitor.py <csv_file>` | simple matplotlib sampling-period histogram |
| `package_release.py` | post-PyInstaller release-bundle assembler |
| `build_release.bat` | Windows one-shot build |

The standalone analyzer scripts are intentionally **decoupled** from
the main package — they re-implement constants and helpers locally so
that they can be shipped alone for QA without dragging in the GUI.

---

## 9 · Common tasks playbook

### Add a new constant
Edit `openQCM/core/constants.py` in the matching section. Document the
reason in an inline comment. If it tunes a feature that has a TODO,
cross-reference that line.

### Add a right-click menu entry
Touch *every* custom handler:
- `MainWindow._on_plot_right_click`
- `DataViewerDialog._on_scene_click` (mainWindow_ui.py)
- `RawDataViewDialog._on_scene_click` (mainWindow_ui.py)
- `CalibrationPlotWindow._on_scene_right_click` (calibrationPlot.py)
The `qcm_data_analyzer` tool keeps pyqtgraph's default menu — leave it.

### Modify a warning string visible in the GUI
Search both branches in `MainWindow._update_plot`: there are two
parallel blocks (`vector1[0]=='nan'` early-data path vs the
acquisition-running path) with **identical** strings. Update both.

### Run the offline regression tests
```
conda activate openqcm
python -m unittest discover -s tests -v
```
Replays the four real calibration sweeps (5, 10, 10-counter-example,
8 MHz) through the production `CalibrationProcess` methods and checks
the sweep-profile table and switcher naming. No hardware needed.

### Verify imports after refactor
```
python -c "import ast; ast.parse(open('PATH').read()); print('OK')"
```
For a deeper sanity check, instantiate Ui_Main against a stub
QApplication — see the helper in commit messages.

### Sync Windows machine
```
cd C:\Users\marco\Documents\openQCM_Q-1
git checkout -- openQCM/Calibration_5MHz.txt openQCM/PeakFrequencies.txt openQCM/Calibration_10MHz.txt
git pull
```
Calibration files are runtime-modified by Peak Detection — discard the
local changes before pulling.

---

## 10 · Things NOT to do

- Do not commit `.DS_Store`, `dist/`, `build/`, `__pycache__/`,
  `*.csv` from `logged_data/`, `Real-Time openQCM GUI.log`. The
  `.gitignore` covers most of it but `.DS_Store` keeps creeping in.
- Do not commit binary build artifacts to git history. Use a GitHub
  Release with a tag instead — see HANDOFF.md / earlier conversation.
- Do not add `pandas` / `matplotlib` / heavy stdlib hidden imports to
  the spec without checking actual usage; we worked hard to keep the
  bundle < 350 MB.
- Do not change `_err1` / `_err2` semantics without re-reading the
  hysteresis state machine — it is sensitive to the per-sweep reset.
- Do not move resource path resolution off `get_data_path` /
  `get_resource_path` — both dev and frozen modes break in subtle ways.
- Do not rewrite history of `main` once a tag has been pushed.

---

## 11 · User preferences

- Italian for chat, English for code/comments/commits.
- Concise explanations, root cause analysis before fix.
- Always present a plan before non-trivial code changes; wait for
  approval, then implement and commit.
- Commit messages are full prose with a one-line summary, blank line,
  multi-paragraph body explaining *why*. Bottom signature
  `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` (or current
  model identifier) included.
- The user runs from a Mac and tests on a Windows VM (Parallels) and
  Windows native. Always provide both sets of commands when relevant.
- Never push to remote without explicit user approval — except inside
  a sequence where the user has already said "fai commit e push".
