# openQCM Q-1 v3.0 — TODO

Development checklist. Each item can become a GitHub Issue.

---

## Release

- [ ] **New pre-release build after cross-platform validation of the pre-v2.2
  firmware-query fix** (added 2026-06-23, commit `d9cb2ef`). The range-priming
  + reply-format validation fix (`mainWindow._query_device`) is verified on
  macOS against legacy firmware. Pending validation on:
    - [x] second macOS machine (Intel, from source) — OK 2026-06-24
    - [x] macOS Apple Silicon (M2, arm64, dedicated conda env) — OK 2026-06-24
    - [x] Linux — OK 2026-06-24
    - [x] Windows (VM) — OK 2026-06-24
  Cross-platform validation COMPLETE — all targets OK 2026-06-24. Pre-release
  build deferred (to be cut later as `v3.0.0-rc5`): `tools\build_release.bat`
  → `dist\openQCM_Q-1_release\`, then zip + GitHub Release with the
  `v3.0.0-rc5` tag.

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

## GUI defects

Found on 2026-10-16 while capturing the user-manual screenshots
(v3.0.0-rc5, macOS). The manual documents them as current behaviour.

- [ ] **Peak Data View legend covers the F1 label** (`calibrationPlot.py`):
  the legend at the top-left of both plots overlaps the fundamental's
  "F1: … Hz" text.
- [ ] **Cursor overlays overlap** (`mainWindow.py`, cursor code ~2051-2167):
  the Δt/ΔF/ΔD box covers the Frequency/Dissipation legend, and each
  "C1: F=…, D=…" readout is drawn over its grey C1/C2 tag.
- [ ] **Disabled menu items not greyed in the light theme**
  (`mainWindow_ui._get_light_stylesheet`): e.g. Help → Download Update looks
  clickable while disabled. Add a `QMenu::item:disabled` rule.
- [ ] **Shape mismatch during Peak Detection** (`mainWindow.py:1301-1303`):
  "X and Y arrays must be the same shape (35001 vs 40001)" because the
  amplitude and phase buffers are read while still growing. Read both once
  and trim to the common length before `setData`.
- [ ] **RuntimeError on Quit after closing a viewer** (`MainWindow.closeEvent`
  ~l. 507): Raw Data View and Data View use `WA_DeleteOnClose`, so
  `dlg.close()` on the stale Python reference raises "wrapped C/C++ object
  … has been deleted". Guard with `sip.isdeleted()` or clear the reference
  on `destroyed`.
- [ ] **Time-axis tick format** (`ElapsedTimeAxis`, `constants.py`): the axes
  are labelled "Time (hh:mm:ss)" but short runs show "4, 24, 1:04"
  (seconds, then m:ss). Pad to a consistent format or relabel.
- [ ] **Update pop-up names a non-existent menu item** (`mainWindow.py`
  `_check_for_updates`): it says "Use Help → Download", but the item is
  "Download Update" / "Download v<X>".

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

- [ ] **v3.0 User Guide / manual** (added 2026-07-14). Author the public user
  manual as **Markdown** at `docs/USER_GUIDE.md`, based on the existing spec
  in `docs/USER_GUIDE_BRIEF.md`. Rationale for the format: Markdown keeps the
  source git-tracked with readable diffs and editable remotely (github.dev /
  GitHub web editor) — a `.docx` is binary (opaque diffs, no browser editing,
  merge conflicts) so it is NOT the source of truth. Marco decided on
  2026-10-12 to also commit the Word and PDF renders next to the Markdown;
  keep all three in sync on every edition and attach the PDF to the GitHub
  Release. Once the PDF is published,
  update the in-app User Guide link (see item below, `mainWindow_ui.py:1295`).
  **Status 2026-10-12:** Edition 1.2 (rc5) in `docs/user-manual/` as
  `.md` + `assets/`, `.docx` and `.pdf`. Reference links are pinned to the
  `v3.0.0-rc5` tag, so they resolve only once that tag is pushed. The PDF is
  exported from the `.docx` with Microsoft Word (same pagination as the
  LibreOffice original: 34 pages, static contents page numbers).

- [ ] **Firmware serial protocol** — document commands, sweep data format,
  and the `F` command for community contributors.

- [ ] **User Guide link** (`mainWindow_ui.py:1295`): currently points to
  v2.0 manual (`openQCM_Q-1-userguide-v2.0.pdf`). Update URL once the
  v3.0 user guide PDF is published.

- [x] **CHANGELOG PART 12** — written (splash screen, `CONSOLE=False`,
  tracking-safety hysteresis, grid toggle, "-3dB frequency" rename,
  calibration plot redesign, build pipeline polish, repo cleanup).
- [x] **CHANGELOG PART 13** — written (pre-v2.2 firmware query compatibility:
  range-priming + reply validation, commit `d9cb2ef`).
