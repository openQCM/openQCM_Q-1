"""
Peak Detection Analyzer for openQCM Q-1
Standalone diagnostic tool that reproduces the exact peak detection algorithm
from the main application (Calibration.py).

Usage: python peak_detection_analyzer.py <calibration_file>

Input: Calibration_5MHz.txt or Calibration_10MHz.txt
       3 columns (space-separated): frequency, amplitude, phase
       50001 rows, 1 MHz to 51 MHz, 1 kHz step
"""
import sys
import numpy as np
import scipy.signal
import matplotlib.pyplot as plt

# =============================================================================
# CONSTANTS (copied from constants.py — standalone, no imports from project)
# =============================================================================
POLY_ORDER = 8                          # Baseline polynomial order
PEAK_FREQ_MIN = 1_000_000              # 1 MHz — fundamental search lower bound
PEAK_FREQ_MAX = 12_000_000             # 12 MHz — fundamental search upper bound
PEAK_POINTS_FUNDAMENTAL = 6000         # argrelextrema order (~6 MHz min spacing)
PEAK_FREQ_RANGE_HALF = 400_000         # ±400 kHz overtone search window
PEAK_POINTS_OVERTONE = 100             # argrelextrema order (~100 kHz min spacing)
OVERTONE_MULTIPLIERS = [3, 5, 7, 9]   # Odd harmonics
PEAK_MAX_FREQ_LIMIT = 51_000_000       # 51 MHz upper limit
PEAK_PHASE_THRESHOLD = 10              # degrees — minimum phase peak
PEAK_FREQ_DIFF_DIVISOR = 4            # For mag/phase cross-validation threshold
VALID_5MHZ = (4e6, 6e6)               # Valid fundamental range for 5 MHz QCM
VALID_10MHZ = (9e6, 11e6)             # Valid fundamental range for 10 MHz QCM


def load_calibration(filepath):
    """Load calibration file: 3 columns (frequency, amplitude, phase)."""
    data = np.loadtxt(filepath)
    return data[:, 0], data[:, 1], data[:, 2]


def baseline_correction(freq, data, poly_order=POLY_ORDER):
    """Polynomial baseline estimation and correction."""
    coeffs = np.polyfit(freq, data, poly_order)
    baseline = np.polyval(coeffs, freq)
    corrected = data - baseline
    return corrected, baseline, coeffs


def detect_fundamental(freq, mag_corrected):
    """
    Phase 1: Detect fundamental resonance frequency in 1-12 MHz range.
    Uses scipy.signal.argrelextrema with large order to find isolated peaks.
    """
    idx_min = np.abs(freq - PEAK_FREQ_MIN).argmin()
    idx_max = np.abs(freq - PEAK_FREQ_MAX).argmin()

    freq_sub = freq[idx_min:idx_max]
    mag_sub = mag_corrected[idx_min:idx_max]

    # Find local maxima with large spacing (6 MHz minimum distance)
    peaks_idx = scipy.signal.argrelextrema(mag_sub, np.greater, order=PEAK_POINTS_FUNDAMENTAL)[0]

    if len(peaks_idx) == 0:
        print("  ERROR: No peaks found in 1-12 MHz range")
        return 0, []

    # Select peak with maximum amplitude
    best = np.argmax(mag_sub[peaks_idx])
    f_fundamental = freq_sub[peaks_idx[best]]

    # Report all candidates
    all_candidates = [(freq_sub[i], mag_sub[i]) for i in peaks_idx]

    print(f"  Found {len(peaks_idx)} candidate(s) in 1-12 MHz:")
    for i, (f, a) in enumerate(all_candidates):
        marker = " <<<" if i == best else ""
        print(f"    {f/1e6:.3f} MHz  (amplitude: {a:.3f}){marker}")

    return f_fundamental, all_candidates


def detect_qcm_type(f_fundamental):
    """Auto-detect QCM sensor type from fundamental frequency."""
    if VALID_5MHZ[0] < f_fundamental < VALID_5MHZ[1]:
        return "5 MHz QCM", True
    elif VALID_10MHZ[0] < f_fundamental < VALID_10MHZ[1]:
        return "10 MHz QCM", True
    else:
        return f"Unknown ({f_fundamental/1e6:.3f} MHz)", False


def detect_overtones(freq, mag_corrected, phase_corrected, f_fundamental):
    """
    Phase 2: Detect overtones in narrow windows around expected positions.
    Cross-validates magnitude and phase peaks.
    """
    fStep = freq[1] - freq[0]
    diff_threshold = (fStep * PEAK_POINTS_OVERTONE) / PEAK_FREQ_DIFF_DIVISOR

    results = []
    for n in OVERTONE_MULTIPLIERS:
        expected_f = n * f_fundamental
        if expected_f > PEAK_MAX_FREQ_LIMIT:
            print(f"  Overtone {n}x: {expected_f/1e6:.1f} MHz exceeds {PEAK_MAX_FREQ_LIMIT/1e6:.0f} MHz limit — skipped")
            continue

        # Search window
        idx_min = np.abs(freq - (expected_f - PEAK_FREQ_RANGE_HALF)).argmin()
        idx_max = np.abs(freq - (expected_f + PEAK_FREQ_RANGE_HALF)).argmin()
        freq_sub = freq[idx_min:idx_max]
        mag_sub = mag_corrected[idx_min:idx_max]
        phase_sub = phase_corrected[idx_min:idx_max]

        # Find magnitude peak
        mag_peaks = scipy.signal.argrelextrema(mag_sub, np.greater, order=PEAK_POINTS_OVERTONE)[0]
        f_mag, a_mag = 0, 0
        if len(mag_peaks) > 0:
            best = np.argmax(mag_sub[mag_peaks])
            f_mag = freq_sub[mag_peaks[best]]
            a_mag = mag_sub[mag_peaks[best]]

        # Find phase peak
        phase_peaks = scipy.signal.argrelextrema(phase_sub, np.greater, order=PEAK_POINTS_OVERTONE)[0]
        f_phase, a_phase = 0, 0
        if len(phase_peaks) > 0:
            best = np.argmax(phase_sub[phase_peaks])
            f_phase = freq_sub[phase_peaks[best]]
            a_phase = phase_sub[phase_peaks[best]]

        # Cross-validation
        freq_diff = abs(f_mag - f_phase) if (f_mag > 0 and f_phase > 0) else float('inf')
        reject_reasons = []

        if f_mag == 0:
            reject_reasons.append("no magnitude peak found")
        if f_phase == 0:
            reject_reasons.append("no phase peak found")
        if freq_diff > diff_threshold:
            reject_reasons.append(f"freq diff {freq_diff:.0f} Hz > threshold {diff_threshold:.0f} Hz")
        if a_phase <= PEAK_PHASE_THRESHOLD:
            reject_reasons.append(f"phase max {a_phase:.1f}° <= {PEAK_PHASE_THRESHOLD}° threshold")

        accepted = len(reject_reasons) == 0
        status = "ACCEPT" if accepted else "REJECT"

        result = {
            'n': n,
            'expected_f': expected_f,
            'f_mag': f_mag,
            'f_phase': f_phase,
            'a_mag': a_mag,
            'a_phase': a_phase,
            'freq_diff': freq_diff,
            'accepted': accepted,
            'reasons': reject_reasons,
            'window': (freq_sub, mag_sub, phase_sub),
            'mag_peaks_idx': mag_peaks,
            'phase_peaks_idx': phase_peaks,
        }
        results.append(result)

        print(f"  Overtone {n}x ({expected_f/1e6:.1f} MHz): {status}")
        if f_mag > 0:
            print(f"    Magnitude peak: {f_mag/1e6:.6f} MHz (amp: {a_mag:.3f})")
        if f_phase > 0:
            print(f"    Phase peak:     {f_phase/1e6:.6f} MHz (phase: {a_phase:.1f}°)")
        if freq_diff < float('inf'):
            print(f"    Freq diff:      {freq_diff:.0f} Hz (threshold: {diff_threshold:.0f} Hz)")
        for r in reject_reasons:
            print(f"    REASON: {r}")

    return results


def plot_results(freq, mag_raw, phase_raw, mag_corrected, phase_corrected,
                 mag_baseline, phase_baseline, f_fundamental, fund_candidates,
                 overtone_results, qcm_type):
    """Generate 4-panel diagnostic plot."""
    freq_mhz = freq / 1e6

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(f"Peak Detection Analyzer — {qcm_type}", fontsize=14, fontweight='bold')

    # =========================================================================
    # Panel 1: Raw Data
    # =========================================================================
    ax1 = axes[0, 0]
    ax1.set_title("1. Raw Data")
    ax1.plot(freq_mhz, mag_raw, color='#008EC0', linewidth=0.5, label='Amplitude')
    ax1.set_xlabel('Frequency (MHz)')
    ax1.set_ylabel('Amplitude (dB)', color='#008EC0')
    ax1.tick_params(axis='y', labelcolor='#008EC0')
    ax1_r = ax1.twinx()
    ax1_r.plot(freq_mhz, phase_raw, color='#DD8E6B', linewidth=0.5, label='Phase')
    ax1_r.set_ylabel('Phase (deg)', color='#DD8E6B')
    ax1_r.tick_params(axis='y', labelcolor='#DD8E6B')
    ax1.grid(True, alpha=0.3)

    # =========================================================================
    # Panel 2: Baseline Correction
    # =========================================================================
    ax2 = axes[0, 1]
    ax2.set_title("2. Baseline Correction (Amplitude)")
    ax2.plot(freq_mhz, mag_raw, color='gray', linewidth=0.5, alpha=0.5, label='Raw')
    ax2.plot(freq_mhz, mag_baseline, color='orange', linewidth=1, linestyle='--', label='Baseline (poly 8)')
    ax2.plot(freq_mhz, mag_corrected, color='#008EC0', linewidth=0.5, label='Corrected')
    ax2.set_xlabel('Frequency (MHz)')
    ax2.set_ylabel('Amplitude')
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    # =========================================================================
    # Panel 3: Peak Detection Results (full range)
    # =========================================================================
    ax3 = axes[1, 0]
    ax3.set_title("3. Peak Detection Results")
    ax3.plot(freq_mhz, mag_corrected, color='#008EC0', linewidth=0.5, label='Corrected amplitude')

    # Mark fundamental
    if f_fundamental > 0:
        idx_f = np.abs(freq - f_fundamental).argmin()
        ax3.axvline(f_fundamental / 1e6, color='red', linewidth=0.8, linestyle='--', alpha=0.5)
        ax3.plot(f_fundamental / 1e6, mag_corrected[idx_f], 'rv', markersize=10, label=f'F0: {f_fundamental/1e6:.3f} MHz')

    # Mark overtones
    for ot in overtone_results:
        if ot['accepted'] and ot['f_mag'] > 0:
            idx_o = np.abs(freq - ot['f_mag']).argmin()
            ax3.plot(ot['f_mag'] / 1e6, mag_corrected[idx_o], 'g^', markersize=8)
            ax3.annotate(f"F{ot['n']}\n{ot['f_mag']/1e6:.3f}",
                         (ot['f_mag'] / 1e6, mag_corrected[idx_o]),
                         textcoords="offset points", xytext=(0, 12),
                         ha='center', fontsize=7, color='green')
        elif ot['f_mag'] > 0:
            idx_o = np.abs(freq - ot['f_mag']).argmin()
            ax3.plot(ot['f_mag'] / 1e6, mag_corrected[idx_o], 'rx', markersize=8)
            ax3.annotate(f"F{ot['n']} REJECTED",
                         (ot['f_mag'] / 1e6, mag_corrected[idx_o]),
                         textcoords="offset points", xytext=(0, 12),
                         ha='center', fontsize=7, color='red')

    # Mark all fund candidates
    for f, a in fund_candidates:
        if f != f_fundamental:
            ax3.plot(f / 1e6, a, 'ko', markersize=5, alpha=0.5)
            ax3.annotate(f"{f/1e6:.3f} MHz\n(rejected)",
                         (f / 1e6, a), textcoords="offset points", xytext=(0, -15),
                         ha='center', fontsize=6, color='gray')

    ax3.set_xlabel('Frequency (MHz)')
    ax3.set_ylabel('Corrected Amplitude')
    ax3.legend(fontsize=8, loc='upper right')
    ax3.grid(True, alpha=0.3)

    # =========================================================================
    # Panel 4: Overtone Detail Windows
    # =========================================================================
    ax4 = axes[1, 1]
    ax4.set_title("4. Overtone Windows (±400 kHz)")

    if len(overtone_results) > 0:
        colors_mag = ['#008EC0', '#2196F3', '#03A9F4', '#00BCD4']
        colors_phase = ['#DD8E6B', '#FF9800', '#FF5722', '#E91E63']

        for i, ot in enumerate(overtone_results):
            f_sub, m_sub, p_sub = ot['window']
            f_sub_mhz = f_sub / 1e6
            ci = i % len(colors_mag)

            # Magnitude
            ax4.plot(f_sub_mhz, m_sub, color=colors_mag[ci], linewidth=0.8,
                     label=f"F{ot['n']} mag" if i == 0 else f"F{ot['n']} mag")

            # Mark mag peaks
            for pi in ot['mag_peaks_idx']:
                marker = 'v' if ot['accepted'] else 'x'
                ax4.plot(f_sub_mhz[pi], m_sub[pi], marker, color=colors_mag[ci], markersize=6)

    ax4.set_xlabel('Frequency (MHz)')
    ax4.set_ylabel('Corrected Amplitude')
    ax4.legend(fontsize=7, loc='upper right')
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


def main():
    if len(sys.argv) < 2:
        print("Usage: python peak_detection_analyzer.py <calibration_file>")
        print("Example: python peak_detection_analyzer.py openQCM/Calibration_5MHz.txt")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"{'='*60}")
    print(f"Peak Detection Analyzer — openQCM Q-1")
    print(f"{'='*60}")
    print(f"File: {filepath}")
    print()

    # Step 1: Load
    print("[Step 1] Loading calibration file...")
    freq, mag_raw, phase_raw = load_calibration(filepath)
    print(f"  Loaded {len(freq)} samples")
    print(f"  Frequency range: {freq[0]/1e6:.1f} - {freq[-1]/1e6:.1f} MHz")
    print(f"  Step: {freq[1]-freq[0]:.0f} Hz")
    print()

    # Step 2: Baseline correction
    print("[Step 2] Baseline correction (polynomial order {})...".format(POLY_ORDER))
    mag_corrected, mag_baseline, _ = baseline_correction(freq, mag_raw)
    phase_corrected, phase_baseline, _ = baseline_correction(freq, phase_raw)
    print(f"  Amplitude corrected range: [{mag_corrected.min():.3f}, {mag_corrected.max():.3f}]")
    print(f"  Phase corrected range:     [{phase_corrected.min():.3f}, {phase_corrected.max():.3f}]")
    print()

    # Step 3: Fundamental detection
    print("[Step 3] Phase 1 — Fundamental detection (1-12 MHz)...")
    f_fundamental, fund_candidates = detect_fundamental(freq, mag_corrected)
    print()

    # Step 4: QCM type
    print("[Step 4] QCM type detection...")
    qcm_type, is_valid = detect_qcm_type(f_fundamental)
    if is_valid:
        print(f"  Detected: {qcm_type} (fundamental: {f_fundamental/1e6:.6f} MHz)")
    else:
        print(f"  WARNING: {qcm_type} — NOT a valid QCM fundamental frequency!")
        print(f"  Valid ranges: 4-6 MHz (5 MHz sensor) or 9-11 MHz (10 MHz sensor)")
    print()

    # Step 5: Overtone detection
    print("[Step 5] Phase 2 — Overtone detection...")
    overtone_results = detect_overtones(freq, mag_corrected, phase_corrected, f_fundamental)
    print()

    # Summary
    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  QCM Type:    {qcm_type}")
    print(f"  Fundamental: {f_fundamental/1e6:.6f} MHz {'(VALID)' if is_valid else '(INVALID)'}")
    accepted = [ot for ot in overtone_results if ot['accepted']]
    rejected = [ot for ot in overtone_results if not ot['accepted']]
    print(f"  Overtones:   {len(accepted)} accepted, {len(rejected)} rejected")
    print()

    if accepted:
        print("  Accepted overtones:")
        for ot in accepted:
            print(f"    F{ot['n']}: {ot['f_mag']/1e6:.6f} MHz")
    if rejected:
        print("  Rejected overtones:")
        for ot in rejected:
            reasons = "; ".join(ot['reasons'])
            print(f"    F{ot['n']}: {reasons}")

    # Final verdict
    print()
    all_zero = all(ot['f_mag'] == 0 for ot in overtone_results)
    if not is_valid:
        print("  VERDICT: FAIL — Fundamental is not a valid QCM frequency")
    elif all_zero and len(overtone_results) > 0:
        print("  VERDICT: FAIL — All overtones are zero")
    elif len(accepted) == 0 and len(overtone_results) > 0:
        print("  VERDICT: WARNING — No overtones accepted (fundamental only)")
    else:
        print(f"  VERDICT: OK — {1 + len(accepted)} peaks detected")
    print()

    # Plot
    plot_results(freq, mag_raw, phase_raw, mag_corrected, phase_corrected,
                 mag_baseline, phase_baseline, f_fundamental, fund_candidates,
                 overtone_results, qcm_type)


if __name__ == '__main__':
    main()
