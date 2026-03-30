"""
Overtone Detail Analyzer for openQCM Q-1
Zooms into a specific overtone window to show magnitude and phase signals
in detail, with peak detection diagnostics.

Usage: python overtone_analyzer.py <calibration_file> <overtone_multiplier>
Example: python overtone_analyzer.py tools/Calibration_10MHz.txt 3

Shows: magnitude and phase in the ±400 kHz window, detected peaks,
frequency difference, and acceptance/rejection analysis.
"""
import sys
import numpy as np
import scipy.signal
import matplotlib.pyplot as plt

# Constants (same as peak_detection_analyzer.py)
POLY_ORDER = 8
PEAK_FREQ_MIN = 1_000_000
PEAK_FREQ_MAX = 12_000_000
PEAK_POINTS_FUNDAMENTAL = 6000
PEAK_FREQ_RANGE_HALF = 400_000
PEAK_POINTS_OVERTONE = 100
PEAK_PHASE_THRESHOLD = 10
PEAK_FREQ_DIFF_DIVISOR = 4


def main():
    if len(sys.argv) < 3:
        print("Usage: python overtone_analyzer.py <calibration_file> <overtone_multiplier>")
        print("Example: python overtone_analyzer.py tools/Calibration_10MHz.txt 3")
        sys.exit(1)

    filepath = sys.argv[1]
    n = int(sys.argv[2])

    # Load
    data = np.loadtxt(filepath)
    freq, mag_raw, phase_raw = data[:, 0], data[:, 1], data[:, 2]
    fStep = freq[1] - freq[0]
    diff_threshold = (fStep * PEAK_POINTS_OVERTONE) / PEAK_FREQ_DIFF_DIVISOR

    print(f"File: {filepath}")
    print(f"Overtone: {n}x")
    print(f"Freq diff threshold: {diff_threshold:.0f} Hz")
    print()

    # Baseline correction
    mag_coeffs = np.polyfit(freq, mag_raw, POLY_ORDER)
    mag_corrected = mag_raw - np.polyval(mag_coeffs, freq)
    phase_coeffs = np.polyfit(freq, phase_raw, POLY_ORDER)
    phase_corrected = phase_raw - np.polyval(phase_coeffs, freq)

    # Detect fundamental
    idx_min = np.abs(freq - PEAK_FREQ_MIN).argmin()
    idx_max = np.abs(freq - PEAK_FREQ_MAX).argmin()
    freq_sub = freq[idx_min:idx_max]
    mag_sub = mag_corrected[idx_min:idx_max]
    peaks_idx = scipy.signal.argrelextrema(mag_sub, np.greater, order=PEAK_POINTS_FUNDAMENTAL)[0]

    if len(peaks_idx) == 0:
        print("ERROR: No fundamental found")
        sys.exit(1)

    best = np.argmax(mag_sub[peaks_idx])
    f_fundamental = freq_sub[peaks_idx[best]]
    print(f"Fundamental: {f_fundamental/1e6:.6f} MHz")

    # Expected overtone frequency
    expected_f = n * f_fundamental
    print(f"Expected F{n}: {expected_f/1e6:.3f} MHz")
    print()

    # Extract overtone window
    win_lo = expected_f - PEAK_FREQ_RANGE_HALF
    win_hi = expected_f + PEAK_FREQ_RANGE_HALF
    idx_lo = np.abs(freq - win_lo).argmin()
    idx_hi = np.abs(freq - win_hi).argmin()

    f_win = freq[idx_lo:idx_hi]
    mag_win = mag_corrected[idx_lo:idx_hi]
    phase_win = phase_corrected[idx_lo:idx_hi]
    f_win_mhz = f_win / 1e6

    # Detect magnitude peaks
    mag_peaks = scipy.signal.argrelextrema(mag_win, np.greater, order=PEAK_POINTS_OVERTONE)[0]
    # Detect phase peaks
    phase_peaks = scipy.signal.argrelextrema(phase_win, np.greater, order=PEAK_POINTS_OVERTONE)[0]

    # Best magnitude peak
    f_mag, a_mag = 0, 0
    best_mag_idx = None
    if len(mag_peaks) > 0:
        best_mag_idx = mag_peaks[np.argmax(mag_win[mag_peaks])]
        f_mag = f_win[best_mag_idx]
        a_mag = mag_win[best_mag_idx]

    # Best phase peak
    f_phase, a_phase = 0, 0
    best_phase_idx = None
    if len(phase_peaks) > 0:
        best_phase_idx = phase_peaks[np.argmax(phase_win[phase_peaks])]
        f_phase = f_win[best_phase_idx]
        a_phase = phase_win[best_phase_idx]

    freq_diff = abs(f_mag - f_phase) if (f_mag > 0 and f_phase > 0) else float('inf')

    # Print analysis
    print(f"{'='*60}")
    print(f"OVERTONE F{n} — DETAILED ANALYSIS")
    print(f"{'='*60}")
    print(f"Window: {win_lo/1e6:.3f} — {win_hi/1e6:.3f} MHz")
    print()

    print(f"Magnitude peaks found: {len(mag_peaks)}")
    for i, pi in enumerate(mag_peaks):
        marker = " <<< BEST" if pi == best_mag_idx else ""
        print(f"  [{i}] {f_win[pi]/1e6:.6f} MHz  amp={mag_win[pi]:.4f}{marker}")

    print()
    print(f"Phase peaks found: {len(phase_peaks)}")
    for i, pi in enumerate(phase_peaks):
        marker = " <<< BEST" if pi == best_phase_idx else ""
        print(f"  [{i}] {f_win[pi]/1e6:.6f} MHz  phase={phase_win[pi]:.2f}°{marker}")

    print()
    print(f"Cross-validation:")
    print(f"  Magnitude best: {f_mag/1e6:.6f} MHz")
    print(f"  Phase best:     {f_phase/1e6:.6f} MHz")
    print(f"  Freq diff:      {freq_diff:.0f} Hz")
    print(f"  Threshold:      {diff_threshold:.0f} Hz")
    print(f"  Phase max:      {a_phase:.2f}°  (threshold: {PEAK_PHASE_THRESHOLD}°)")
    print()

    reasons = []
    if freq_diff > diff_threshold:
        reasons.append(f"freq diff {freq_diff:.0f} > {diff_threshold:.0f} Hz")
    if a_phase <= PEAK_PHASE_THRESHOLD:
        reasons.append(f"phase {a_phase:.1f}° <= {PEAK_PHASE_THRESHOLD}°")

    if reasons:
        print(f"  VERDICT: REJECTED — {'; '.join(reasons)}")
    else:
        print(f"  VERDICT: ACCEPTED")

    # =========================================================================
    # Plot: 3 panels
    # =========================================================================
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"Overtone F{n} Detail — Window ±400 kHz around {expected_f/1e6:.3f} MHz",
                 fontsize=13, fontweight='bold')

    # --- Panel 1: Magnitude ---
    ax1.set_title("Corrected Amplitude (Magnitude)")
    ax1.plot(f_win_mhz, mag_win, color='#008EC0', linewidth=1, label='Magnitude')
    # All peaks
    for pi in mag_peaks:
        ax1.plot(f_win_mhz[pi], mag_win[pi], 'v', color='gray', markersize=6, alpha=0.5)
    # Best peak
    if best_mag_idx is not None:
        ax1.plot(f_win_mhz[best_mag_idx], mag_win[best_mag_idx], 'rv', markersize=12,
                 label=f'Best: {f_mag/1e6:.6f} MHz')
    # Expected
    ax1.axvline(expected_f / 1e6, color='green', linestyle=':', linewidth=1, alpha=0.7,
                label=f'Expected: {expected_f/1e6:.3f} MHz')
    ax1.set_ylabel('Amplitude')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # --- Panel 2: Phase ---
    ax2.set_title("Corrected Phase")
    ax2.plot(f_win_mhz, phase_win, color='#DD8E6B', linewidth=1, label='Phase')
    # All peaks
    for pi in phase_peaks:
        ax2.plot(f_win_mhz[pi], phase_win[pi], '^', color='gray', markersize=6, alpha=0.5)
    # Best peak
    if best_phase_idx is not None:
        ax2.plot(f_win_mhz[best_phase_idx], phase_win[best_phase_idx], 'r^', markersize=12,
                 label=f'Best: {f_phase/1e6:.6f} MHz ({a_phase:.1f}°)')
    # Expected
    ax2.axvline(expected_f / 1e6, color='green', linestyle=':', linewidth=1, alpha=0.7)
    # Phase threshold
    ax2.axhline(PEAK_PHASE_THRESHOLD, color='red', linestyle='--', linewidth=0.8, alpha=0.5,
                label=f'Phase threshold: {PEAK_PHASE_THRESHOLD}°')
    ax2.set_ylabel('Phase (deg)')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    # --- Panel 3: Overlay magnitude + phase (dual Y-axis) ---
    ax3.set_title("Magnitude + Phase Overlay")
    l1, = ax3.plot(f_win_mhz, mag_win, color='#008EC0', linewidth=1, label='Magnitude')
    ax3.set_ylabel('Amplitude', color='#008EC0')
    ax3.tick_params(axis='y', labelcolor='#008EC0')

    ax3r = ax3.twinx()
    l2, = ax3r.plot(f_win_mhz, phase_win, color='#DD8E6B', linewidth=1, label='Phase')
    ax3r.set_ylabel('Phase (deg)', color='#DD8E6B')
    ax3r.tick_params(axis='y', labelcolor='#DD8E6B')

    # Mark both peaks with vertical lines
    if f_mag > 0:
        ax3.axvline(f_mag / 1e6, color='#008EC0', linestyle='--', linewidth=1, alpha=0.7)
    if f_phase > 0:
        ax3.axvline(f_phase / 1e6, color='#DD8E6B', linestyle='--', linewidth=1, alpha=0.7)

    # Annotate frequency difference
    if f_mag > 0 and f_phase > 0:
        mid_f = (f_mag + f_phase) / 2 / 1e6
        y_pos = ax3.get_ylim()[1] * 0.9
        color = 'red' if freq_diff > diff_threshold else 'green'
        ax3.annotate(f'Δf = {freq_diff:.0f} Hz\n(threshold: {diff_threshold:.0f} Hz)',
                     xy=(mid_f, y_pos), fontsize=10, fontweight='bold', color=color,
                     ha='center', bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax3.set_xlabel('Frequency (MHz)')
    ax3.legend([l1, l2], ['Magnitude', 'Phase'], fontsize=9, loc='upper left')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    main()
