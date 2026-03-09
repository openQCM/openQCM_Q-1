# openQCM Q-1 — TODO

Checklist di sviluppo. Ogni item può diventare una GitHub Issue.

## Bug & Fix
- [ ] Auto-stop calibrazione (`Calibration.py:605`) — il toggle START/STOP non si disattiva automaticamente alla fine del processo di Peak Detection
- [ ] Parametri 9th overtone da validare (`constants.py:106`) — valori L/R frequency e SG window placeholder

## Ottimizzazione
- [ ] Windows: oscillazioni sampling time — busy-wait loop in `Serial.py` + timer resolution 15.6 ms. Testare su Windows nativo (non VM)
- [ ] Sostituire polling `inWaiting()` con `read()` timeout-based (pyserial best practice)

## Feature
- [ ] Rilevamento esplicito tipo QCM 5/10 MHz (`Serial.py:744,801`) — attualmente inferito da frequenza picco
- [ ] Label sensore quarzo nella GUI (`mainWindow.py:251`) — mostrare "5 MHz QCM" o "10 MHz QCM"
- [ ] Socket Client come sorgente dati (`constants.py:41`) — attualmente disabilitato

## Documentazione
- [ ] Documentare protocollo seriale firmware (comandi, formato dati sweep, comando `F`)
