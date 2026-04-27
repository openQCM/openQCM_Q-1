# openQCM Q-1 — TODO

Development checklist. Each item can become a GitHub Issue.

## Bug & Fix

- [x] Tracking safety: se il picco scompare e **entrambe** le cut-off frequencies
  non vengono trovate per 10 sweep consecutivi (`auto_tracking_max_edge_errors`
  in constants.py), l'auto-tracking viene disabilitato automaticamente.
  La GUI mostra "Tracking Stopped" (rosso). Re-abilitazione automatica non appena
  il picco torna con almeno una cut-off frequency identificabile ("Tracking Resumed", verde).

- [ ] Trimmed mean buffer statistics: replaced SG + np.average with
  `scipy.stats.trim_mean` on frequency/dissipation/temperature circular buffers
  (50 samples, 10% trim per side). Verified robustness on synthetic outliers,
  but the 10% parameter needs validation on real measurement data:
    - Test on long experiments with known outlier patterns
    - Compare response to drift vs pure mean (should be very close)
    - Tune `trim_mean_fraction` in constants.py if needed
    - Consider per-signal tuning (freq/diss/temp may need different fractions)
    - Evaluate alternatives if 10% is not enough: Hampel filter or median

- [ ] Signal quality check: aggiunto minimo Q-factor (`min_valid_q_factor = 100`
  in constants.py) per rilevare il caso in cui il sensore è staccato ma la
  board continua a inviare rumore. Approfondire:
    - Soglie Q per-overtone (overtoni alti hanno tipicamente Q inferiore)
    - Check aggiuntivi: ampiezza minima picco post-baseline, bandwidth massima
      per overtone, stima SNR
    - Flag dedicato `_signal_quality_error` con messaggio utente specifico
      ("No valid resonance — check sensor connection") invece di riusare i flag
      cut-off esistenti
    - Soglia 100 è conservativa: validare su più sensori reali

- [ ] Peak detection mag/phase freq_diff threshold: raised to 50 kHz (was 25 kHz)
  after counter-example `tools/Calibration_10MHz.txt` showed valid F3 overtone
  rejected by only 10 kHz excess. Provisional fix — need to:
    - Collect more counter-examples to validate the threshold value
    - Consider adaptive threshold proportional to frequency (e.g. 0.1% of f_expected)
    - Evaluate weighting decision by amplitude and phase beyond frequency diff alone
    - Higher overtones have broader asymmetric peaks — may need per-overtone tuning
- [ ] Validate 9th overtone parameters (`constants.py:106`) — L/R frequency and SG window values are placeholders

## Optimization
- [ ] Windows: sampling time oscillations — busy-wait loop in `Serial.py` + 15.6 ms timer resolution. Test on native Windows (not VM)
- [ ] Replace `inWaiting()` polling with timeout-based `read()` (pyserial best practice)
- [x] Minimum Y-axis display range for Frequency (100 Hz), Dissipation (1e-6), Temperature (2°C)
- [x] Easter egg: right-click on logo → Unlock/Lock Axes
- [ ] Fine-tune `MIN_DISS_RANGE` value based on real-world measurement data (currently 1e-6, needs validation)


## Features
- [ ] Explicit QCM 5/10 MHz type detection (`Serial.py:744,801`) — currently inferred from peak frequency
- [ ] Quartz sensor label in GUI (`mainWindow.py:251`) — display "5 MHz QCM" or "10 MHz QCM"
- [ ] Socket Client as data source (`constants.py:41`) — currently disabled

## Documentation
- [ ] Document firmware serial protocol (commands, sweep data format, `F` command)
- [ ] Fix the User Guide link in Help → User Guide. The current URL points
  to the v2.0 manual (`https://openqcm.com/shared/q-1/openQCM_Q-1-userguide-v2.0.pdf`)
  which is outdated for v3.0. Set in `mainWindow_ui.py` (lambda on
  `actionUserGuide.triggered`). Update once the new user guide PDF is published.
