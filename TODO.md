# openQCM Q-1 v3.0 — TODO

Development checklist. Each item can become a GitHub Issue.

---

## Release

- [ ] **New pre-release build after cross-platform validation of the pre-v2.2
  firmware-query fix** (added 2026-06-23, commit `d9cb2ef`). The range-priming
  + reply-format validation fix (`mainWindow._query_device`) is verified on
  macOS against legacy firmware. Pending validation on:
    - [ ] second macOS machine
    - [ ] Linux
    - [ ] Windows (VM)
  If all three pass, cut a new pre-release executable: `tools\build_release.bat`
  → `dist\openQCM_Q-1_release\`, then zip and publish a GitHub Release with a
  new `rcN` tag.

---

## Validation

- [ ] **Trimmed mean fraction** (`constants.py:226`, `trim_mean_fraction = 0.10`):
  validate on real long-running experiments with known outlier patterns.
    - Compare response to drift vs pure mean (should be very close)
    - Tune per-signal if needed (freq / diss / temp may need different fractions)
    - If 10% is insufficient: evaluate Hampel filter or median as alternatives

- [ ] **Min Q-factor threshold** (`constants.py:219`, `min_valid_q_factor = 100`):
  current value is conservative — validate on multiple real sensors.
    - Per-overtone thresholds (higher overtones have inherently lower Q)
    - Additional checks: minimum post-baseline peak amplitude, max bandwidth
      per overtone, SNR estimate
    - Dedicated `_signal_quality_error` flag with user-facing message
      ("No valid resonance — check sensor connection") instead of reusing
      the existing -3dB edge flags

- [ ] **Peak detection freq_diff threshold** (`constants.py:196-198`,
  `peak_freq_diff_divisor = 2` gives ~50 kHz): provisional fix after
  counter-example `tools/Calibration_10MHz.txt` showed valid F3 rejected
  by only 10 kHz excess.
    - Collect more counter-examples to validate
    - Consider adaptive threshold proportional to frequency (e.g. 0.1% of f_expected)
    - Evaluate weighting by amplitude and phase beyond frequency diff alone
    - Higher overtones have broader asymmetric peaks — may need per-overtone tuning

- [ ] **9th overtone parameters** (`constants.py:98-100`): `L5_9th_overtone`,
  `R5_9th_overtone`, `SG_window_size5_9th_overtone` are placeholders —
  need real calibration data to set proper values

- [ ] **`MIN_DISS_RANGE`** (`mainWindow.py:48`, currently `1e-6`): provisional
  minimum Y-axis range for dissipation — validate against real measurement data

---

## Monitoring

Known behaviours to watch during testing — not blocking, but worth tracking:

- [ ] **Tracking re-enable buffer contamination**: after hysteresis re-enable
  (5 good sweeps), the `trim_mean` buffer of 50 still holds ~45 stale samples.
  The smoothed `freq_range_mean` may be briefly off-target, potentially causing
  a spurious `check_and_update_tracking` window shift. A `_post_resume_skip_count`
  delay was discussed but not implemented — observe in long sessions.

- [ ] **Windows VM frequency/dissipation jitter**: seen once, could not reproduce.
  Likely VM resource contention under load. Re-verify if it surfaces again on
  native Windows.

---

## Optimization

- [ ] **Windows sampling time oscillations**: busy-wait loop in `Serial.py` +
  Windows 15.6 ms timer resolution causes jitter. Test on native Windows (not VM).

- [ ] **Replace `inWaiting()` with timeout-based `read()`** (`Serial.py:571`):
  pyserial best practice — avoids busy-wait and simplifies the read loop.

- [ ] **Splash screen text**: `text_pos` is enabled in the spec; PyInstaller 5.x
  bootloader overwrites our default message with extracted-DLL filenames.
  Accepted as-is (user prefers verbose over silent). Future enhancement:
  custom Tcl splash script to suppress bootloader chatter while keeping
  our progress messages.

---

## Features

- [ ] **Explicit QCM 5/10 MHz type detection** — currently inferred from peak
  frequency in calibration. Add explicit detection logic in `Serial.py`.

- [ ] **Quartz sensor label in GUI** — display "5 MHz QCM" or "10 MHz QCM"
  in the main window status area.

- [ ] **Socket Client data source** (`constants.py:36`) — reserved enum value,
  currently unused. Implement when remote acquisition is needed.

---

## Documentation

- [ ] **Firmware serial protocol** — document commands, sweep data format,
  and the `F` command for community contributors.

- [ ] **User Guide link** (`mainWindow_ui.py:1295`): currently points to
  v2.0 manual (`openQCM_Q-1-userguide-v2.0.pdf`). Update URL once the
  v3.0 user guide PDF is published.

- [ ] **CHANGELOG PART 12** — not yet written. Should cover the work since
  commit `d1a9d79`: splash screen, `CONSOLE=False`, tracking-safety
  hysteresis, grid toggle, "-3dB frequency" rename, calibration plot
  redesign, build pipeline polish, repo cleanup.
