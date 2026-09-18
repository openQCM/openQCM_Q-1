"""
Thin wrappers around QMessageBox used by the GUI for user prompts.

All methods are static; the parent argument is the window that owns the
dialog (typically the MainWindow). The non-blocking variants return
immediately and let Qt manage the lifecycle, useful when the call site
is inside a tight UI loop.
"""
from PyQt5 import QtGui, QtCore


TAG = "[PopUp]"


class PopUp:

    @staticmethod
    def warning(parent, title, message):
        """Modal warning popup (Ok button)."""
        QtGui.QMessageBox.warning(parent, title, message, QtGui.QMessageBox.Ok)

    @staticmethod
    def question(parent, title, message):
        """Modal Yes/No popup. Returns True if the user clicked Yes."""
        ans = QtGui.QMessageBox.question(
            parent, title, message,
            QtGui.QMessageBox.Yes, QtGui.QMessageBox.No)
        return ans == QtGui.QMessageBox.Yes

    @staticmethod
    def info(parent, title, message):
        """Modal information popup (Ok button)."""
        QtGui.QMessageBox.information(parent, title, message, QtGui.QMessageBox.Ok)

    @staticmethod
    def info_nonblocking(parent, title, message):
        """Non-blocking information popup. Auto-deletes when closed."""
        box = QtGui.QMessageBox(parent)
        box.setIcon(QtGui.QMessageBox.Information)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QtGui.QMessageBox.Ok)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        box.show()

    @staticmethod
    def warning_nonblocking(parent, title, message):
        """Non-blocking warning popup. Auto-deletes when closed."""
        box = QtGui.QMessageBox(parent)
        box.setIcon(QtGui.QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QtGui.QMessageBox.Ok)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        box.show()
