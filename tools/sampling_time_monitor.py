"""
Sampling Time Monitor for openQCM Q-1
Reads a CSV log file and plots the sampling time (time between consecutive sweeps).
Usage: python sampling_time_monitor.py <csv_file>
"""
import sys
import csv
import numpy as np
import matplotlib.pyplot as plt

if len(sys.argv) < 2:
    print("Usage: python sampling_time_monitor.py <csv_file>")
    sys.exit(1)

csv_path = sys.argv[1]

# Read Relative_time column
times = []
with open(csv_path, 'r') as f:
    reader = csv.reader(f)
    header = next(reader)  # skip header
    for row in reader:
        try:
            times.append(float(row[2]))  # Relative_time
        except (ValueError, IndexError):
            continue

times = np.array(times)
sampling_times = np.diff(times)  # delta between consecutive sweeps (seconds)
sampling_ms = sampling_times * 1000  # convert to milliseconds

# Statistics
print("File: {}".format(csv_path))
print("Sweeps: {}".format(len(times)))
print("Sampling time (ms):")
print("  Mean:   {:.1f}".format(np.mean(sampling_ms)))
print("  Std:    {:.1f}".format(np.std(sampling_ms)))
print("  Min:    {:.1f}".format(np.min(sampling_ms)))
print("  Max:    {:.1f}".format(np.max(sampling_ms)))
print("  Median: {:.1f}".format(np.median(sampling_ms)))

# Plot
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))

# Time series
ax1.plot(sampling_ms, linewidth=0.8, color='#008EC0')
ax1.axhline(np.mean(sampling_ms), color='red', linestyle='--', linewidth=1, label='Mean: {:.1f} ms'.format(np.mean(sampling_ms)))
ax1.set_xlabel('Sweep #')
ax1.set_ylabel('Sampling Time (ms)')
ax1.set_title('Sampling Time per Sweep')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Histogram
ax2.hist(sampling_ms, bins=50, color='#DD8E6B', edgecolor='black', linewidth=0.5)
ax2.axvline(np.mean(sampling_ms), color='red', linestyle='--', linewidth=1, label='Mean: {:.1f} ms'.format(np.mean(sampling_ms)))
ax2.set_xlabel('Sampling Time (ms)')
ax2.set_ylabel('Count')
ax2.set_title('Sampling Time Distribution (std: {:.1f} ms)'.format(np.std(sampling_ms)))
ax2.legend()
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
