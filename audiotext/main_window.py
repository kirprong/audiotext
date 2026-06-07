from __future__ import annotations
from typing import Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow

from .clipboard_util import copy_to_clipboard
from .dialog import AudioDialog
from .state import StateManager


class MainWindow(QMainWindow):
    def __init__(self, api_key: str):
        super().__init__()
        self._state_manager = StateManager()
        self._is_dialog_visible = False

        self._dialog = AudioDialog(
            api_key=api_key,
            toggle_callback=self.on_toggle,
        )

    def _run_in_gui_thread(self, fn: Callable[[], None]) -> None:
        app = QApplication.instance()
        if app is None:
            fn()
            return
        QTimer.singleShot(0, fn)

    def on_toggle_from_hotkey(self) -> None:
        self._run_in_gui_thread(self.on_toggle)

    def on_show_from_hotkey(self) -> None:
        self._run_in_gui_thread(self.on_show)

    def on_hide_from_hotkey(self) -> None:
        self._run_in_gui_thread(self.on_hide)

    def on_one_from_hotkey(self) -> None:
        self._run_in_gui_thread(self.on_one)

    def on_toggle(self) -> None:
        if not self._is_dialog_visible:
            self._show()
            self._dialog.start_recording()
        else:
            self._hide()

    def on_show(self) -> None:
        if not self._is_dialog_visible:
            self._show()

    def on_hide(self) -> None:
        if self._is_dialog_visible:
            self._hide()

    def on_one(self) -> None:
        if self._is_dialog_visible:
            self._dialog.toggle_recording()

    def is_dialog_visible(self) -> bool:
        return self._is_dialog_visible

    def _show(self) -> None:
        self._dialog.set_text('')
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        self._is_dialog_visible = True

    def _hide(self) -> None:
        self._dialog.stop_recording_without_transcribe()

        text = self._dialog.current_text
        self._state_manager.save_text(text)
        if text:
            copy_to_clipboard(text)
        self._dialog.hide()
        self._is_dialog_visible = False