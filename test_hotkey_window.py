"""
Test window for hotkey demonstration.
Shows how to hide / show a PyQt6 window via global hotkeys using pynput.

Hotkeys:
    Alt + A  → show window
    Alt + Z  → hide window
"""

import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QLabel)
from PyQt6.QtCore import Qt, QTimer
from pynput import keyboard


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Hotkey Window")
        self.resize(400, 300)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Test window\nPress Alt+A to show, Alt+Z to hide")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_window(self):
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = TestWindow()
    window.show()

    # --- non-blocking global hotkey via pynput ---
    alt_pressed = False

    def on_press(key):
        nonlocal alt_pressed
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            alt_pressed = True
        elif alt_pressed:
            if hasattr(key, 'char'):
                if key.char in ('a', 'A'):
                    QTimer.singleShot(0, window.show_window)
                elif key.char in ('z', 'Z'):
                    QTimer.singleShot(0, window.hide_window)

    def on_release(key):
        nonlocal alt_pressed
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            alt_pressed = False

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    try:
        sys.exit(app.exec())
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
