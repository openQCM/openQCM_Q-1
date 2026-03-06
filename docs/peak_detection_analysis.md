# Analisi Algoritmo Peak Detection — Calibrazione openQCM Q-1
**Data**: 5 Marzo 2026 — Documento interno, uso privato

## Contesto
L'algoritmo di Peak Detection (v0.1.6) esegue la calibrazione del sensore QCM: scansiona 1–51 MHz in 10 sezioni da 5 MHz, rileva la fondamentale e le armoniche dispari (3x, 5x, 7x, 9x), con auto-detect del tipo di sensore (3/5/10 MHz).

---

## 1. Flusso dell'Algoritmo

```
Apertura porta seriale (timeout 0.1s)
    ↓
Drain dati stantii (5s deadline)
    ↓
Loop 10 sezioni (k=0..9):
  → Invio comando: "startFreq;stopFreq;fStep\n"
  → Lettura sweep dal dispositivo
  → Conversione ADC → dB/gradi
  → Accumulo in temp1 (ampiezza), temp2 (fase)
  → Invio dati alla GUI via queue
    ↓
Baseline correction (polinomio ordine 8)
    ↓
Ricerca fondamentale (1–12 MHz, argrelextrema order=6000)
    ↓
Auto-detect tipo QCM dal valore della fondamentale
    ↓
Ricerca overtoni (±400 kHz, argrelextrema order=100)
    ↓
Cross-validazione: |f_mag - f_phase| < 25 kHz AND fase > 10°
    ↓
Salvataggio PeakFrequencies.txt + Calibration_XMHz.txt
    ↓
Fallback: se l'algoritmo nuovo fallisce → FindPeak legacy
```

---

## 2. Parametri Chiave

### Acquisizione
| Parametro | Valore | Significato |
|-----------|--------|-------------|
| `calib_sections` | 10 | Sezioni dello sweep |
| `calib_fRange` | 5,000,000 Hz | Range per sezione |
| `calib_fStep` | 1,000 Hz | Risoluzione frequenza |
| `calib_samples` | 5,001 | Campioni per sezione |
| Range totale | 1–51 MHz | 50,001 campioni totali |

### Rilevazione Fondamentale
| Parametro | Valore | Significato |
|-----------|--------|-------------|
| `peak_freq_sweep_min` | 1 MHz | Limite inferiore ricerca |
| `peak_freq_sweep_max` | 12 MHz | Limite superiore ricerca |
| `peak_points_fundamental` | 6,000 | Order argrelextrema (= 6 MHz separazione minima) |

### Rilevazione Overtoni
| Parametro | Valore | Significato |
|-----------|--------|-------------|
| `peak_overtone_multipliers` | [3, 5, 7, 9] | Solo armoniche dispari |
| `peak_freq_range_half` | 400,000 Hz | Finestra di ricerca ±400 kHz |
| `peak_points_overtone` | 100 | Order argrelextrema (= 100 kHz) |
| `peak_max_frequency_limit` | 51 MHz | Limite massimo overtone |

### Cross-validazione
| Parametro | Valore | Significato |
|-----------|--------|-------------|
| `peak_phase_threshold` | 10° | Fase minima per accettare overtone |
| `peak_freq_diff_divisor` | 4 | Soglia = (1000×100)/4 = 25 kHz |

### Auto-detect QCM
| Range Fondamentale | Tipo | Distance (legacy) |
|-------------------|------|-------------------|
| 2–4 MHz | 3 MHz QCM | dist5 = 8,000 |
| 4–6 MHz | 5 MHz QCM | dist5 = 8,000 |
| 9–11 MHz | 10 MHz QCM | dist10 = 10,000 |

### Baseline
| Parametro | Valore |
|-----------|--------|
| Ordine polinomio | 8 |
| Applicato a | ampiezza e fase |

### Conversione ADC
| Parametro | Valore |
|-----------|--------|
| vmax | 3.3 V |
| bitmax | 8192 (13 bit) |
| VCP | 0.9 V |
| Scala ampiezza | (V - 0.9) / 0.03 |
| Scala fase | (V - 0.9) / 0.01 |

### Parametri Measurement (per overtone, dopo calibrazione)

#### 5 MHz QCM
| Overtone | L (Hz) | R (Hz) | SG window | Spline factor |
|----------|--------|--------|-----------|---------------|
| Fundamental | 15,000 | 5,000 | 9 | 0.05 |
| 3rd | 15,000 | 5,000 | 11 | 0.01 |
| 5th | 15,000 | 5,000 | 11 | 0.01 |
| 7th | 50,000 | 2,500 | 33 | 0.01 |
| 9th | 5,000,000 | 100,000 | 5 | 0.5 |

#### 10 MHz QCM
| Overtone | L (Hz) | R (Hz) | SG window | Spline factor |
|----------|--------|--------|-----------|---------------|
| Fundamental | 15,000 | 5,000 | 11 | 0.01 |
| 3rd | 15,000 | 5,000 | 11 | 0.01 |
| 5th | 23,000 | 3,000 | 19 | 0.01 |

---

## 3. Punti di Fragilità e Possibili Ottimizzazioni

### ALTA PRIORITÀ

#### A) Finestra overtoni fissa ±400 kHz
**Problema**: Con campioni in liquido o sensori contaminati, gli overtoni possono shiftare oltre 400 kHz dalla posizione attesa.
**Ottimizzazione**: Finestra adattiva proporzionale alla frequenza dell'overtone (es. ±1% della frequenza attesa → ±150 kHz a 15 MHz, ±450 kHz a 45 MHz).

#### B) Soglia fase fissa a 10°
**Problema**: Sensori con alto smorzamento (liquidi, film biologici) possono avere fasi < 10° su overtoni alti → vengono scartati come spuri. Sensori in aria hanno fasi > 50° → la soglia non filtra nulla.
**Ottimizzazione**: Soglia adattiva basata sulla fase della fondamentale (es. soglia = fase_fondamentale × 0.15), oppure soglia diversa per ogni overtone.

#### C) Nessuna validazione dell'ampiezza della fondamentale
**Problema**: Se lo sweep è rumoroso, un picco di rumore può essere identificato come fondamentale. Non c'è controllo SNR.
**Ottimizzazione**: Richiedere che il picco superi una soglia minima di ampiezza (es. > 3σ del rumore di fondo), oppure verificare che la larghezza del picco sia fisicamente plausibile.

### MEDIA PRIORITÀ

#### D) Polinomio baseline ordine 8 globale
**Problema**: Un singolo polinomio su 50 MHz può introdurre oscillazioni (Runge effect) che distorcono i picchi vicini ai bordi.
**Ottimizzazione**: Baseline per sezioni (es. sliding window) oppure filtro mediano + spline, oppure ordine polinomiale adattivo.

#### E) order=6000 troppo grande per sensori a bassa frequenza
**Problema**: Per un sensore a 3 MHz, la fondamentale è vicina al bordo inferiore (1 MHz) e argrelextrema con order=6000 richiede 6000 punti su entrambi i lati.
**Ottimizzazione**: Order proporzionale alla frequenza del sensore, oppure ridotto per la ricerca fondamentale (es. 3000) con validazione successiva.

#### F) Nessun checksum sui dati seriali
**Problema**: Dati corrotti passano silenziosamente. Solo ValueError (conversione float) li cattura.
**Ottimizzazione**: Controllo del numero di campioni attesi vs ricevuti. Validazione range dei valori ADC (0–8192).

#### G) order=100 uguale per tutti gli overtoni
**Problema**: La larghezza dei picchi varia con la frequenza e il fattore Q. Picchi a 10 MHz sono più stretti di quelli a 5 MHz.
**Ottimizzazione**: Order scalato con la frequenza dell'overtone.

### BASSA PRIORITÀ

#### H) Armoniche pari non rilevate
**Problema**: Solo [3, 5, 7, 9] — alcune condizioni generano armoniche pari visibili.
**Nota**: Per QCM standard (AT-cut) le pari sono trascurabili. Rilevante solo per sensori speciali.

#### I) Colonne duplicate in PeakFrequencies.txt
**Problema**: `np.column_stack([freq, freq])` salva la stessa colonna due volte — retaggio del vecchio algoritmo.
**Ottimizzazione**: Formato a singola colonna, oppure salvare freq_mag e freq_phase separatamente.

#### J) Catch generico delle eccezioni
**Problema**: `except:` cattura tutto (anche errori di programmazione, interruzioni), mascherando i problemi reali.
**Ottimizzazione**: Catch specifici (`except ValueError`, `except serial.SerialException`) con logging dettagliato.

---

## 4. Riepilogo Priorità

| # | Problema | Severità | Complessità |
|---|---------|----------|-------------|
| A | Finestra overtoni fissa ±400 kHz | ALTA | Bassa |
| B | Soglia fase fissa 10° | ALTA | Bassa |
| C | Nessuna validazione ampiezza fondamentale | ALTA | Media |
| D | Baseline polinomiale globale | MEDIA | Alta |
| E | order=6000 per basse frequenze | MEDIA | Bassa |
| F | Nessun checksum dati seriali | MEDIA | Media |
| G | order overtoni non scalato | MEDIA | Bassa |
| H | Armoniche pari non rilevate | BASSA | Bassa |
| I | Colonne duplicate PeakFrequencies | BASSA | Banale |
| J | Catch generico eccezioni | BASSA | Bassa |

---

## 5. File Coinvolti

- **`openQCM/processors/Calibration.py`** — algoritmo principale (run, baseline_correction, peak_detection_fundamental, peak_detection_overtones)
- **`openQCM/core/constants.py`** — tutti i parametri numerici
- **`openQCM/ui/calibrationPlot.py`** — plot diagnostico
- **`openQCM/ui/mainWindow.py`** — integrazione UI, consumo queue, gestione stop/risultati
- **`openQCM/core/worker.py`** — bridge CalibrationProcess ↔ GUI
