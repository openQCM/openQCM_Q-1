# openQCM Q-1 — TODO

Development checklist. Each item can become a GitHub Issue.

## Bug & Fix
- [ ] Controllare la procedura di peak detection, ho trovato un contro - esempio di peak detection che non ha funzionato, quarzo da 10 Mhz non ha identificato 3rd overotono. 
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
