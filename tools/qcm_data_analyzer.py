"""
openQCM Q-1 Data Analyzer
Interactive PyQt5/pyqtgraph tool for statistical analysis of Q-1 log files.

Features:
- Open a Q-1 CSV acquisition log
- Plot Resonance Frequency and Dissipation vs Time (hh:mm:ss)
- Two draggable vertical cursors to select a time range
- Real-time statistics on the selected subset:
    mean, variance, standard deviation, min, max, median
- Histograms of sampling intervals, frequency, and dissipation
- Mean line overlaid on each histogram

Usage:
    python tools/qcm_data_analyzer.py

Expected CSV format (openQCM Q-1 log):
    Date, Time, Relative_time, Temperature, Resonance_Frequency, Dissipation
"""
import sys
import csv
import os
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

# Colors (aligned with the main GUI dark theme)
PLOT_BG = '#2b2b2b'
TEXT_COLOR = '#e0e0e0'
AXIS_COLOR = '#aaaaaa'
FREQ_COLOR = '#008EC0'
DISS_COLOR = '#DD8E6B'
CURSOR1_COLOR = '#d4c85c'   # soft yellow
CURSOR2_COLOR = '#6abf7b'   # soft green
MEAN_LINE_COLOR = '#ff5252'


class SecondsTimeAxis(pg.AxisItem):
    """Format elapsed seconds as hh:mm:ss or m:ss."""
    def tickStrings(self, values, scale, spacing):
        result = []
        for t in values:
            if t < 0:
                t = 0
            if t >= 3600:
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                result.append(f"{h}:{m:02d}:{s:02d}")
            elif t >= 60:
                m = int(t // 60)
                s = int(t % 60)
                result.append(f"{m}:{s:02d}")
            else:
                result.append(f"{int(t)}")
        return result


class QCMAnalyzer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("openQCM Q-1 Data Analyzer")
        self.resize(1500, 950)

        # Data state
        self._time = None
        self._freq = None
        self._diss = None
        self._csv_path = None

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        self.btn_open = QtWidgets.QPushButton("Open CSV…")
        self.btn_open.clicked.connect(self.open_file)
        toolbar.addWidget(self.btn_open)

        self.lbl_file = QtWidgets.QLabel("No file loaded")
        self.lbl_file.setStyleSheet("padding-left: 12px;")
        toolbar.addWidget(self.lbl_file)
        toolbar.addStretch()
        self.lbl_info = QtWidgets.QLabel("")
        toolbar.addWidget(self.lbl_info)
        layout.addLayout(toolbar)

        # Splitter: plots | stats panel
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(PLOT_BG)
        splitter.addWidget(self.plot_widget)
        self._setup_plots()

        stats_panel = QtWidgets.QWidget()
        stats_layout = QtWidgets.QVBoxLayout(stats_panel)
        stats_layout.setContentsMargins(8, 8, 8, 8)
        stats_panel.setMinimumWidth(320)
        stats_panel.setMaximumWidth(420)

        title = QtWidgets.QLabel("<b>Statistics — selected range</b>")
        title.setStyleSheet("font-size: 11pt;")
        stats_layout.addWidget(title)
        self.lbl_range = QtWidgets.QLabel("(select a range with the cursors)")
        self.lbl_range.setWordWrap(True)
        stats_layout.addWidget(self.lbl_range)

        self.txt_stats = QtWidgets.QTextEdit()
        self.txt_stats.setReadOnly(True)
        fixed_font = QtGui.QFont("Courier New")
        fixed_font.setStyleHint(QtGui.QFont.Monospace)
        fixed_font.setPointSize(9)
        self.txt_stats.setFont(fixed_font)
        stats_layout.addWidget(self.txt_stats)

        splitter.addWidget(stats_panel)
        splitter.setSizes([1160, 340])

    def _setup_plots(self):
        # Row 0: Frequency vs time
        xaxis_f = SecondsTimeAxis(orientation='bottom')
        xaxis_f.setPen(AXIS_COLOR)
        xaxis_f.setTextPen(AXIS_COLOR)
        self.plt_freq = self.plot_widget.addPlot(
            row=0, col=0, colspan=2, axisItems={'bottom': xaxis_f})
        self._style_plot(self.plt_freq, "Resonance Frequency",
                         "Time (hh:mm:ss)", left_unit="Hz")

        # Row 1: Dissipation vs time
        xaxis_d = SecondsTimeAxis(orientation='bottom')
        xaxis_d.setPen(AXIS_COLOR)
        xaxis_d.setTextPen(AXIS_COLOR)
        self.plt_diss = self.plot_widget.addPlot(
            row=1, col=0, colspan=2, axisItems={'bottom': xaxis_d})
        self._style_plot(self.plt_diss, "Dissipation",
                         "Time (hh:mm:ss)")
        self.plt_diss.setXLink(self.plt_freq)

        # Row 2: Sampling interval histogram (full width)
        self.plt_sampling = self.plot_widget.addPlot(row=2, col=0, colspan=2)
        self._style_plot(self.plt_sampling, "Sampling Interval Distribution",
                         "Sampling Interval (ms)", left_name="Count")

        # Row 3: Frequency histogram | Dissipation histogram
        self.plt_hist_freq = self.plot_widget.addPlot(row=3, col=0)
        self._style_plot(self.plt_hist_freq, "Frequency Distribution",
                         "Frequency (Hz)", left_name="Count")
        self.plt_hist_diss = self.plot_widget.addPlot(row=3, col=1)
        self._style_plot(self.plt_hist_diss, "Dissipation Distribution",
                         "Dissipation", left_name="Count")

        # Curves (populated on file load)
        self.curve_freq = self.plt_freq.plot(pen=pg.mkPen(FREQ_COLOR, width=1))
        self.curve_diss = self.plt_diss.plot(pen=pg.mkPen(DISS_COLOR, width=1))

        # Cursors: two InfiniteLines per plot, kept in sync
        self.cursor1_f = self.cursor1_d = None
        self.cursor2_f = self.cursor2_d = None

    @staticmethod
    def _style_plot(plot, title, bottom_label, left_name="", left_unit=""):
        plot.setTitle(title, color=TEXT_COLOR)
        plot.setLabel('left', left_name, units=left_unit, color=TEXT_COLOR)
        plot.setLabel('bottom', bottom_label, color=TEXT_COLOR)
        plot.showGrid(x=True, y=True, alpha=0.3)
        plot.getAxis('left').setPen(AXIS_COLOR)
        plot.getAxis('left').setTextPen(AXIS_COLOR)
        plot.getAxis('bottom').setPen(AXIS_COLOR)
        plot.getAxis('bottom').setTextPen(AXIS_COLOR)

    # ------------------------------------------------------------ File I/O
    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open openQCM Q-1 Acquisition Log", "",
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        try:
            self._load_csv(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Error loading file", f"Failed to load:\n{e}")
            return
        self._csv_path = path
        self.lbl_file.setText(os.path.basename(path))
        self._update_plots()
        self._add_cursors()
        self._compute_stats()

    def _load_csv(self, path):
        rel_time, freq, diss = [], [], []
        with open(path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                try:
                    rel_time.append(float(row[2]))
                    freq.append(float(row[4]))
                    diss.append(float(row[5]))
                except (ValueError, IndexError):
                    continue
        if len(rel_time) < 2:
            raise ValueError("Not enough valid rows in the file")
        self._time = np.array(rel_time)
        self._freq = np.array(freq)
        self._diss = np.array(diss)
        duration = self._time[-1] - self._time[0]
        self.lbl_info.setText(
            f"{len(self._time)} samples  |  {duration:.1f} s  "
            f"(~{duration/60:.1f} min)")

    # ------------------------------------------------------------ Plotting
    def _update_plots(self):
        self.curve_freq.setData(self._time, self._freq)
        self.curve_diss.setData(self._time, self._diss)
        self.plt_freq.enableAutoRange()
        self.plt_diss.enableAutoRange()

    def _add_cursors(self):
        # Remove any existing cursors
        for c in (self.cursor1_f, self.cursor1_d, self.cursor2_f, self.cursor2_d):
            if c is not None and c.scene() is not None:
                c.scene().removeItem(c)

        t_min, t_max = self._time[0], self._time[-1]
        pos1 = t_min + (t_max - t_min) * 0.25
        pos2 = t_min + (t_max - t_min) * 0.75

        def make_cursor(color, pos):
            c = pg.InfiniteLine(pos=pos, angle=90, movable=True,
                                pen=pg.mkPen(color, width=2))
            return c

        # Cursor 1 (yellow) on both plots
        self.cursor1_f = make_cursor(CURSOR1_COLOR, pos1)
        self.cursor1_d = make_cursor(CURSOR1_COLOR, pos1)
        # Cursor 2 (green) on both plots
        self.cursor2_f = make_cursor(CURSOR2_COLOR, pos2)
        self.cursor2_d = make_cursor(CURSOR2_COLOR, pos2)

        self.plt_freq.addItem(self.cursor1_f, ignoreBounds=True)
        self.plt_freq.addItem(self.cursor2_f, ignoreBounds=True)
        self.plt_diss.addItem(self.cursor1_d, ignoreBounds=True)
        self.plt_diss.addItem(self.cursor2_d, ignoreBounds=True)

        # Sync: whichever cursor is dragged, mirror its value on the paired one
        self.cursor1_f.sigPositionChanged.connect(
            lambda: self._sync_cursor(self.cursor1_f, self.cursor1_d))
        self.cursor1_d.sigPositionChanged.connect(
            lambda: self._sync_cursor(self.cursor1_d, self.cursor1_f))
        self.cursor2_f.sigPositionChanged.connect(
            lambda: self._sync_cursor(self.cursor2_f, self.cursor2_d))
        self.cursor2_d.sigPositionChanged.connect(
            lambda: self._sync_cursor(self.cursor2_d, self.cursor2_f))

    def _sync_cursor(self, source, target):
        target.blockSignals(True)
        target.setValue(source.value())
        target.blockSignals(False)
        self._compute_stats()

    # ------------------------------------------------------------- Stats
    def _compute_stats(self):
        if self._time is None or self.cursor1_f is None:
            return
        t1 = self.cursor1_f.value()
        t2 = self.cursor2_f.value()
        t_lo, t_hi = min(t1, t2), max(t1, t2)
        self.lbl_range.setText(
            f"Range: {t_lo:.2f} s → {t_hi:.2f} s   (Δt = {t_hi - t_lo:.2f} s)")

        mask = (self._time >= t_lo) & (self._time <= t_hi)
        n = int(np.sum(mask))
        if n < 2:
            self.txt_stats.setPlainText(
                "Not enough samples in the selected range.")
            self._clear_histograms()
            return

        sel_time = self._time[mask]
        sel_freq = self._freq[mask]
        sel_diss = self._diss[mask]
        sel_samp_ms = np.diff(sel_time) * 1000.0  # sampling interval in ms

        txt = f"Samples in range: {n}\n"
        txt += "-" * 42 + "\n"
        txt += self._stats_block("Frequency (Hz)", sel_freq, "{:.3f}")
        txt += self._stats_block("Dissipation", sel_diss, "{:.3e}")
        if len(sel_samp_ms) > 0:
            txt += self._stats_block("Sampling Interval (ms)", sel_samp_ms, "{:.2f}")
        self.txt_stats.setPlainText(txt)

        self._draw_hist(self.plt_sampling, sel_samp_ms, FREQ_COLOR, n_bins=50)
        self._draw_hist(self.plt_hist_freq, sel_freq, FREQ_COLOR, n_bins=50)
        self._draw_hist(self.plt_hist_diss, sel_diss, DISS_COLOR, n_bins=50)

    @staticmethod
    def _stats_block(name, data, fmt="{:.4f}"):
        data = np.asarray(data)
        data = data[~np.isnan(data)]
        if len(data) == 0:
            return f"{name}\n  (no valid data)\n\n"
        mean = np.mean(data)
        var = np.var(data, ddof=1) if len(data) > 1 else 0.0
        std = np.std(data, ddof=1) if len(data) > 1 else 0.0
        lines = [
            f"{name}",
            f"  Mean     = {fmt.format(mean)}",
            f"  Variance = {fmt.format(var)}",
            f"  Std Dev  = {fmt.format(std)}",
            f"  Min      = {fmt.format(np.min(data))}",
            f"  Max      = {fmt.format(np.max(data))}",
            f"  Median   = {fmt.format(np.median(data))}",
            "",
        ]
        return "\n".join(lines) + "\n"

    def _draw_hist(self, plot, data, color, n_bins=50):
        plot.clear()
        data = np.asarray(data)
        data = data[~np.isnan(data)]
        if len(data) == 0:
            return
        if np.all(data == data[0]):
            # Degenerate: all values equal → single bin
            plot.addItem(pg.InfiniteLine(
                pos=data[0], angle=90,
                pen=pg.mkPen(color, width=2)))
            return
        hist, edges = np.histogram(data, bins=n_bins)
        width = edges[1] - edges[0]
        centers = edges[:-1] + width / 2.0
        bar = pg.BarGraphItem(
            x=centers, height=hist, width=width * 0.9,
            brush=color, pen=pg.mkPen(None))
        plot.addItem(bar)
        # Mean line overlay
        mean_line = pg.InfiniteLine(
            pos=float(np.mean(data)), angle=90,
            pen=pg.mkPen(MEAN_LINE_COLOR, width=1, style=QtCore.Qt.DashLine))
        plot.addItem(mean_line)
        plot.enableAutoRange()

    def _clear_histograms(self):
        self.plt_sampling.clear()
        self.plt_hist_freq.clear()
        self.plt_hist_diss.clear()


def _apply_dark_stylesheet(app):
    app.setStyleSheet("""
        QMainWindow, QWidget { background-color: #2b2b2b; color: #e0e0e0; }
        QTextEdit {
            background-color: #1e1e1e; color: #e0e0e0;
            border: 1px solid #555; border-radius: 3px;
        }
        QLabel { color: #e0e0e0; }
        QPushButton {
            background-color: #3c3c3c; color: #e0e0e0;
            padding: 6px 14px; border: 1px solid #555; border-radius: 3px;
        }
        QPushButton:hover { background-color: #4a4a4a; }
        QSplitter::handle { background-color: #555; }
    """)


def main():
    app = QtWidgets.QApplication(sys.argv)
    _apply_dark_stylesheet(app)
    w = QCMAnalyzer()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
