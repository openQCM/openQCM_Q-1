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
    def question_QCM(parent, title, message):
        """
        Ask the user to choose the QCM sensor type at startup.
        Currently unused (auto-detection from the calibration file is preferred),
        kept for backward compatibility with older entry points.

        :return: 1 → @10 MHz, 0 → @5 MHz
        """
        box = QtGui.QMessageBox(parent)
        box.setIcon(QtGui.QMessageBox.Question)
        box.setWindowTitle(title)
        box.setGeometry(700, 400, 340, 220)
        box.setText(message)
        box.setStandardButtons(QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        b10 = box.button(QtGui.QMessageBox.Yes)
        b10.setText('@10MHz')
        b5 = box.button(QtGui.QMessageBox.No)
        b5.setText(' @5MHz')
        box.exec_()
        if box.clickedButton() == b10:
            print(TAG, 'Quartz Crystal Sensor installed on the openQCM Device: @10MHz')
            return 1
        if box.clickedButton() == b5:
            print(TAG, 'Quartz Crystal Sensor installed on the openQCM Device: @5MHz')
            return 0

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
