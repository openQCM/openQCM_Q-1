# Double instrument — implementation plan

Branch: `feature/double-instrument` (from `main` @ `8490b31`)
Worktree: `../openQCM_Q-1-double-instrument`
Status: **approved 2026-10-06** — two side-by-side windows; overview (step 5) deferred

## Goal

Acquire from **two openQCM Q-1 boards** (one flow cell each) inside a
**single application**, in **parallel**: one acquisition child process
per board, both fully independent, each sweep at the native ~0.4 s
period. Single-instrument behaviour on `main` must stay byte-identical.

## Why two GUI instances fail today

Port locking between instances already works (`fcntl` lock file on
macOS/Linux, exclusive COM handle on Windows). What the instances still
share is:

| Shared resource | Effect |
|---|---|
| `openQCM/PeakFrequencies.txt`, `Calibration_5MHz.txt`, `Calibration_10MHz.txt` | Peak Detection on board B overwrites board A's calibration; A's next START uses B's baseline and sweep window. A read during the other instance's write can hit a half-written file (`loadtxt` → exception). |
| `logged_data/Real-Time openQCM GUI.log` | One `RotatingFileHandler` (5 kB, `backupCount=0`) per process on the same file; rotation fails on Windows while the other process holds it. |
| CSV name `YYYY-MM-DD_hh-mm-ss_<overtone>.csv` | Two STARTs in the same second on the same overtone open the same file with `'w'`. |

The calibration collision is the defect that matters: calibration is a
property of the **board + sensor**, but it is stored per installation.

## Architecture

```
                 QApplication (one process)
        ┌──────────────────┴──────────────────┐
   MainWindow CH1                        MainWindow CH2
   (channel="CH1")                       (channel="CH2")
   Worker ── ParserProcess               Worker ── ParserProcess
        └─ SerialProcess / Calibration        └─ SerialProcess / Calibration
             │  calib_dir = boards/<SN-A>          │  calib_dir = boards/<SN-B>
             ▼                                     ▼
          board A (USB)                         board B (USB)
```

**Reuse `MainWindow` as-is, one top-level window per board.** `Worker`,
`SerialProcess`, `CalibrationProcess` are already per-port and share no
state except the calibration paths, so two `MainWindow` instances in the
same `QApplication` give each channel every existing feature (Peak
Detection, overtone buttons, reference/Δf, cursors, Raw Data View,
tracking banners, CSV log) with no duplicated UI code. The alternative —
a new combined window — would re-implement most of the 2 600 lines of
`mainWindow.py` and is rejected.

Launch: `python run.py --dual` (frozen: `openQCM_Q-1.exe --dual`, plus a
`openQCM_Q-1_dual.bat` launcher in the Windows release folder). The two
windows are tiled on the left/right halves of the available screen.
Without `--dual` nothing changes.

## Steps (one commit each)

### 1 · Per-board calibration paths
- New `openQCM/common/calibrationPaths.py`: `CalibrationPaths(root)` with
  `peak_frequencies`, `calibration_5`, `calibration_10`, `calibration_3`,
  `calibration_for(f0)` and constructors `legacy()` (= today's
  `openQCM/` folder) and `for_board(serial, port)` →
  `openQCM/boards/<serial>/`; fallback key = sanitised port name when the
  EEPROM has no serial (`NO_SERIAL` / pre-v2.2 firmware), with a warning.
- `SerialProcess`, `CalibrationProcess`, `Worker` take `calib_dir: str`
  (a plain string so it pickles cleanly under `spawn` on Windows/macOS);
  default = legacy root. Replace every direct use of
  `Constants.cvs_peakfrequencies_path` / `csv_calibration_path*` /
  `csv_calibration_export_path` (Serial.py ×4, Calibration.py ×~10,
  worker.py ×1, mainWindow.py ×6). `get_speeds()` becomes an instance /
  parametrised call.
- No behaviour change in single mode (legacy root).

### 2 · Channel-aware `MainWindow`
- Constructor gains `channel=None` (`None` = single mode). In dual mode:
  - window title `openQCM Q-1 - version 3.0 — CH1 [SN]`, channel badge in the sidebar;
  - after Connect + `S` query, `self._calib = CalibrationPaths.for_board(...)`;
    overtone list / Measurement availability re-read from that folder;
    if the board has no calibration yet, Measurement stays disabled with
    "Run Peak Detection for this board first" (no copying of legacy files:
    we cannot know which board they belong to);
  - CSV name `YYYY-MM-DD_hh-mm-ss_CH1_<SN>_<overtone>.csv`;
  - `get_web_info()` only in CH1;
  - firmware updater action disabled (Teensy loader cannot be told which
    of two boards to flash) with a hint to use single mode with one board;
  - closing either window asks once and closes both (stops both workers,
    releases both ports).
- `sys.stdout/stderr` redirect installed once and fanned out to every
  window's System Log (today a second window would wrap the first one's
  `LogStream`).

### 3 · `--dual` launch
- `Arguments`: `--dual` flag. `app.py`: build CH1 + CH2, tile them, keep
  the splash/exit flow. `package_release.py`: add the `.bat` launcher.

### 4 · Docs
- CHANGELOG PART 15, README "Two instruments" section, TODO, CLAUDE.md §3
  note on per-board calibration; window build label as on the generic
  quartz branch (cleared on merge).

### 5 (optional, after field feedback) · Overview window
- Overlay of CH1/CH2 Δf and ΔD vs time read from the two workers' ring
  buffers, plus START all / STOP all. Not needed for a first delivery.

## Out of scope (separate TODO)
- `SerialProcess.run` read loop has no timeout (`while True … 's' in
  buffer`); a wedged board blocks its own channel until STOP's
  `wait_for_process` terminates it. In parallel mode it no longer
  affects the other channel.
- Shared rotating log file between *separate* processes (dual mode is one
  process, so it is unaffected).
- Moving single mode to per-board calibration (would force every user to
  redo Peak Detection after upgrading — decide later).

## Test plan
1. `ast.parse` on every touched file.
2. Single mode, board 19-0000: Peak Detection + Measurement F0/F3 —
   identical files and CSV columns to `main`.
3. Dual mode, two boards: connect both, Peak Detection on both (in
   parallel), check `openQCM/boards/<SN>/` contents, Measurement on both
   for ≥ 30 min, sampling ~0.4 s on each, STOP/START one channel while
   the other runs, unplug one board mid-run (other must continue), close.
4. Dual mode with one board: CH2 port list shows only free ports; the
   board already held by CH1 is refused by the lock.
5. macOS + Windows (Parallels and native) + Linux; Windows frozen build
   via `tools\build_release.bat` and the `--dual` launcher.

If a second board is not available: a `tools/fake_qcm_board.py`
pseudo-terminal simulator (Lorentzian + noise, `F`/`S` replies) and an
`OPENQCM_EXTRA_PORTS` dev-only env var to list it — macOS/Linux only.

## Open questions
1. Two tiled windows (proposed) vs a single combined window?
2. Second Q-1 board available for testing, or build the simulator?
3. Should step 5 (overview + START/STOP all) be part of the first
   delivery to the customer?
