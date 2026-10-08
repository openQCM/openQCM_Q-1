# openQCM Q-1 — Dual-instrument mode

> **First attempt.** Developed and checked offline and on a single
> workstation; not yet validated with two real boards. Feedback welcome.

Acquire from **two openQCM Q-1 boards** (e.g. one flow cell each) in a
single application. One Q-1 board drives one sensor, so two flow cells need
two boards.

## Start

| Platform | Command |
|---|---|
| From source (macOS / Linux / Windows) | `python run.py --dual` |
| Windows standalone release | double-click `openQCM_Q-1_dual.bat` (next to `openQCM_Q-1.exe`) |

Two windows open side by side: **CH1** (left) and **CH2** (right).
Without `--dual` the software works exactly as the normal single-board version.

## Use

In each window, independently:

1. Select the board's port and click **Connect**.
2. **First time with a board:** run **Peak Detection** (START in Peak
   Detection mode).
3. Switch to **Measurement**, choose the overtone, click **START**.

The two boards are acquired **in parallel** and independently (~0.4 s per
sweep each). Stopping or losing one channel does not affect the other.

## Calibration per board

Each board keeps its own Peak Detection files in

```
openQCM/boards/<board serial number>/
```

so calibrating one board never overwrites the other. Boards without a serial
number in their EEPROM are stored by port name (a warning is shown): keep
them on the same USB port.

## Data files

One CSV log per channel in `logged_data/`:

```
YYYY-MM-DD_hh-mm-ss_CH1_<serial>_<overtone>.csv
```

Same columns as the single-board version (Date, Time, Relative_time,
Temperature, Resonance_Frequency, Dissipation).

## Limitations

- **Firmware update** is disabled in this mode: close the application, leave
  only that board connected and use the normal version
  (Tools → Check Firmware Version).
- Closing either window closes both.
- The System Log tab shows the messages of both channels.

## Feedback

Please report problems or results (OS, software version, the
`logged_data/Real-Time openQCM GUI.log` file and the CSV logs) to openQCM
support or as a GitHub issue.
