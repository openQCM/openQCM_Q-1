"""
Capture GUI screenshots for the openQCM Q-1 software user manual.

Run from the repository root (the folder containing run.py):

    python docs/tools/capture_gui.py            # all offline captures
    python docs/tools/capture_gui.py --list     # list offline capture names
    python docs/tools/capture_gui.py menus data_view
    python docs/tools/capture_gui.py --live     # captures with the Q-1 connected

Every image is taken with QWidget.grab(), so no screen-recording permission
is needed. The PNGs are written unannotated, at the display's native pixel
ratio, to docs/user-manual/assets/gui/raw/. Annotation and resizing are a
separate step (annotate_gui.py).

Offline mode produces the states that need no instrument: menus, plot context menu, Peak Data View (from the calibration files in
openQCM/) and the CSV Data View (from the reference log in docs/).

Live mode opens the real application plus a separate "Manual capture"
window. The operator drives the application normally (Connect, Peak
Detection, START, ...) and presses the capture buttons when the GUI shows
the wanted state. Status-bar states (Standby, Processing, Monitoring,
Warning, Tracking Stopped, Auto-Tracking, Peak Detection ...) are grabbed
automatically the first time each one appears, because several of them
last less than a second.

The application code is not modified. To keep the run deterministic and
side-effect free the script, at runtime only:
  - replaces MainWindow.get_web_info with a no-op (it performs a blocking
    request to openqcm.com at start-up);
  - forces the light theme through QSettings and restores the user's saved
    preference on exit;
  - uses an in-window menu bar (AA_DontUseNativeMenuBar) so that menus look
    as they do on Windows and Linux, where most users run the software;
  - bypasses the quit confirmation by setting MainWindow._is_closing.
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(REPO_ROOT, 'docs', 'user-manual', 'assets', 'gui', 'raw')
# Reference acquisition tracked in the repository, so the Data View capture
# is reproducible on any clone.
EXAMPLE_CSV = os.path.join(REPO_ROOT, 'docs', '2026-04-24_10-25-14_F0.csv')

WINDOW_SIZE = (1200, 900)   # MainWindow's own initial size
DIALOG_SIZE = (1050, 750)

# Status-bar states auto-captured in live mode: (status prefix, file suffix).
# Matched against the left part of "<status> | <message>".
AUTO_STATES = [
    ('Standby', 'standby'),
    ('Processing', 'processing'),
    ('Monitoring', 'monitoring'),
    ('Warning', 'warning'),
    ('Tracking Stopped', 'tracking_stopped'),
    ('Auto-Tracking', 'auto_tracking'),
    ('Peak Detection Processing', 'peak_processing'),
    ('Peak Detection Success', 'peak_success'),
    ('Peak Detection Warning', 'peak_warning'),
]

sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

# Qt is imported here but QApplication is created only in main(): the
# acquisition runs in multiprocessing children, which on macOS and Windows
# re-import this module.
from PyQt5 import QtCore, QtWidgets  # noqa: E402


def log(msg):
    # MainWindow redirects sys.stdout into its System Log tab.
    print(msg, file=sys.__stdout__, flush=True)


def settle(ms=400):
    """Let Qt lay out and paint before grabbing."""
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def save_pixmap(pix, name):
    path = os.path.join(OUT_DIR, name + '.png')
    pix.save(path, 'PNG')
    log('saved {} ({}x{} px, dpr {})'.format(
        os.path.relpath(path, REPO_ROOT), pix.width(), pix.height(),
        pix.devicePixelRatio()))
    return path


def save(widget, name, wait=400):
    if wait:
        settle(wait)
    return save_pixmap(widget.grab(), name)


class _FakeRightClick:
    """Minimal stand-in for a pyqtgraph MouseClickEvent, so the real
    MainWindow._on_plot_right_click builds the real context menu."""

    def __init__(self, screen_pos):
        self._pos = screen_pos

    def button(self):
        return QtCore.Qt.RightButton

    def screenPos(self):
        return QtCore.QPointF(self._pos)

    def accept(self):
        pass


# ---------------------------------------------------------------------------
# Offline captures
# ---------------------------------------------------------------------------

def cap_mode_selection(win):
    """Measurement Setup group in both modes."""
    win.ui.cBox_Source.setCurrentIndex(1)
    save(win.ui.grpMeasurement, 'q1_08_mode_peak_detection')
    win.ui.cBox_Source.setCurrentIndex(0)
    save(win.ui.grpMeasurement, 'q1_08_mode_measurement')


def cap_menus(win):
    """Each menu bar menu, plus the Theme submenu."""
    menus = [('file', win.ui.menuFile), ('view', win.ui.menuView),
             ('tools', win.ui.menuTools), ('help', win.ui.menuHelp),
             ('view_theme', win.ui.menuTheme)]
    for key, menu in menus:
        menu.popup(win.mapToGlobal(QtCore.QPoint(40, 40)))
        save(menu, 'q1_07_menu_' + key)
        menu.hide()


def cap_context_menu(win):
    """Real right-click menu of the Frequency/Dissipation plot."""
    def grab_popup():
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is None:
            log('context menu not found')
            return
        save_pixmap(popup.grab(), 'q1_11_plot_context_menu')
        popup.close()

    QtCore.QTimer.singleShot(600, grab_popup)
    centre = win.ui.pltB.mapToGlobal(win.ui.pltB.rect().center())
    win._on_plot_right_click(win._plt2, _FakeRightClick(centre))


def cap_peak_data_view(win):
    """Peak Data View, using the calibration files in openQCM/."""
    win._open_peak_data_viewer()
    dlg = getattr(win, '_calib_plot_window', None)
    if dlg is None:
        log('Peak Data View not opened (no calibration files?)')
        return
    dlg.resize(*DIALOG_SIZE)
    save(dlg, 'q1_09_peak_data_view')
    dlg.close()


def cap_data_view(win):
    """File -> Open Log... viewer on the reference acquisition."""
    from openQCM.ui.mainWindow_ui import DataViewerDialog
    dlg = DataViewerDialog(None, csv_path=EXAMPLE_CSV, theme='light')
    dlg.resize(*DIALOG_SIZE)
    dlg.show()
    save(dlg, 'q1_14_data_view')
    dlg.close()


CAPTURES = {
    'mode_selection': cap_mode_selection,
    'menus': cap_menus,
    'context_menu': cap_context_menu,
    'peak_data_view': cap_peak_data_view,
    'data_view': cap_data_view,
}


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

class LiveCapturePanel(QtWidgets.QWidget):
    """Separate top-level window: manual capture buttons plus automatic
    capture of status-bar states. It is never part of a screenshot."""

    def __init__(self, win):
        super().__init__(None, QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle('Manual capture')
        self._win = win
        self._seen = set()

        layout = QtWidgets.QVBoxLayout(self)
        buttons = [
            ('Main window', self._main_window),
            ('Serial Connection group', self._serial_connection),
            ('Plots area', self._plots),
            ('Freq/Diss plot (cursors)', self._freq_diss_plot),
            ('Measurement Parameters', self._measurement_parameters),
            ('Raw Data View', self._raw_data_view),
            ('Status bar (manual)', self._status_manual),
            ('Re-arm auto status captures', self._rearm),
        ]
        for text, slot in buttons:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        self._last = QtWidgets.QLabel('Auto status capture armed')
        self._last.setWordWrap(True)
        layout.addWidget(self._last)
        self.resize(260, 360)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll_status)
        self._timer.start(150)

    def _done(self, path):
        if path:
            self._last.setText('Saved ' + os.path.basename(path))

    # Manual captures -------------------------------------------------------
    def _main_window(self):
        self._done(save(self._win, 'q1_06_main_window', wait=0))

    def _serial_connection(self):
        self._done(save(self._win.ui.grpConnection, 'q1_04_serial_connection', wait=0))

    def _plots(self):
        self._done(save(self._win.ui.tabWidget, 'q1_12_live_plots', wait=0))

    def _freq_diss_plot(self):
        self._done(save(self._win.ui.pltB, 'q1_14_cursors', wait=0))

    def _measurement_parameters(self):
        dlg = self._win.ui.deviceInfoDialog
        if not dlg.isVisible():
            self._last.setText('Open Tools > Measurement Parameters first')
            return
        self._done(save(dlg, 'q1_13_measurement_parameters', wait=0))

    def _raw_data_view(self):
        dlg = getattr(self._win, '_raw_data_viewer', None)
        if dlg is None or not dlg.isVisible():
            self._last.setText('Open Tools > Raw Data View first')
            return
        self._done(save(dlg, 'q1_13_raw_data_view', wait=0))

    def _status_manual(self):
        n = len([f for f in os.listdir(OUT_DIR) if f.startswith('q1_15_status_manual')])
        self._done(save(self._win.ui.statusDockWidget,
                        'q1_15_status_manual_{}'.format(n + 1), wait=0))

    def _rearm(self):
        self._seen.clear()
        self._last.setText('Auto status capture re-armed')

    # Automatic status captures ---------------------------------------------
    def _poll_status(self):
        # Quitting the application (with its own confirmation) ends the session.
        if getattr(self._win, '_is_closing', False):
            self._timer.stop()
            QtWidgets.QApplication.quit()
            return
        status = self._win.ui.infostatus.text()
        for prefix, suffix in AUTO_STATES:
            if status.startswith(prefix):
                if suffix not in self._seen:
                    self._seen.add(suffix)
                    self._done(save(self._win.ui.statusDockWidget,
                                    'q1_15_status_' + suffix, wait=0))
                return


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    parser.add_argument('names', nargs='*', help='offline captures to run (default: all)')
    parser.add_argument('--list', action='store_true', help='list offline capture names')
    parser.add_argument('--live', action='store_true', help='live capture with the Q-1 connected')
    args = parser.parse_args()
    if args.list:
        print('\n'.join(CAPTURES))
        return 0
    unknown = [n for n in args.names if n not in CAPTURES]
    if unknown:
        parser.error('unknown capture(s): ' + ', '.join(unknown))

    os.makedirs(OUT_DIR, exist_ok=True)

    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_DontUseNativeMenuBar, True)
    app = QtWidgets.QApplication(sys.argv[:1])
    from openQCM.ui import mainWindow as mw_module

    settings = QtCore.QSettings('openQCM', 'Q-1')
    saved_theme = settings.value('theme', None)
    settings.setValue('theme', 'light')
    settings.sync()

    mw_module.MainWindow.get_web_info = lambda self: None
    win = mw_module.MainWindow()
    try:
        win.resize(*WINDOW_SIZE)
        win.move(40, 40)
        settle(800)
        if args.live:
            panel = LiveCapturePanel(win)
            panel.move(40 + WINDOW_SIZE[0] + 20, 40)
            panel.show()
            app.exec_()
        else:
            for name in (args.names or CAPTURES):
                CAPTURES[name](win)
    finally:
        if saved_theme is None:
            settings.remove('theme')
        else:
            settings.setValue('theme', saved_theme)
        settings.sync()
        if not args.live:
            win._is_closing = True
            win.close()
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    return 0


if __name__ == '__main__':
    sys.exit(main())
