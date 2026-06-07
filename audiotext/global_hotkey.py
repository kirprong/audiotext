from __future__ import annotations
from typing import Callable

from pynput import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


class GlobalHotkeySignals(QObject):
    triggered = pyqtSignal()
    one_triggered = pyqtSignal()
    show_triggered = pyqtSignal()
    hide_triggered = pyqtSignal()

class GlobalHotkey:
    def __init__(
        self,
        callback: Callable[[], None],
        one_callback: Callable[[], None] | None = None,
        show_callback: Callable[[], None] | None = None,
        hide_callback: Callable[[], None] | None = None,
        ):
        self._callback = callback
        self._one_callback = one_callback
        self._show_callback = show_callback
        self._hide_callback = hide_callback

        self._signals = GlobalHotkeySignals()
        self._signals.triggered.connect(self._on_triggered)
        self._signals.one_triggered.connect(self._on_one_triggered)
        self._signals.show_triggered.connect(self._on_show_triggered)
        self._signals.hide_triggered.connect(self._on_hide_triggered)        
        self._listener: keyboard.Listener | None = None
        self._alt_pressed = False

    def _on_triggered(self) -> None:
        #print("[HOTKEY] Alt+` triggered -> callback")
        self._callback()

    def _on_show_triggered(self) -> None:
        if self._show_callback:
            self._show_callback()

    def _on_one_triggered(self) -> None:
        if self._one_callback:
            self._one_callback()

    def _on_hide_triggered(self) -> None:
        if self._hide_callback:
            self._hide_callback()

    def _vk(self, key) -> int | None:
        """Return virtual-key code for a key, or None."""
        if hasattr(key, 'vk') and key.vk is not None:
            return key.vk
        # Handle Key enum members (e.g. Key.space)
        try:
            if hasattr(key, 'value') and hasattr(key.value, 'vk'):
                return key.value.vk
        except Exception:
            pass
        return None

    def start(self) -> None:
        def on_press(key):
            if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                self._alt_pressed = True
            elif self._alt_pressed:
                vk = self._vk(key)
                if vk == 49:        # 1
                    self._signals.one_triggered.emit()
                    return True
                elif vk == 192:     # `
                    self._signals.triggered.emit()
                    return True
                elif vk == 67:      # C
                    self._signals.hide_triggered.emit()
                    return True
                elif vk == 65:      # A
                    self._signals.show_triggered.emit()
                    return True

        def on_release(key):
            if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                self._alt_pressed = False

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None