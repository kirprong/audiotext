from __future__ import annotations
import os
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QThread,
    QTimer,
    pyqtSignal,
    Qt,
    QObject,
)
from PyQt6.QtGui import QFont, QPalette, QTextOption
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFrame,
)

from .groq_whisper import GroqWhisperClient, RetryableError, NetworkError
from .audio_capture import AudioCapture


# ─── Worker ──────────────────────────────────────────────────────────
class TranscribeThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str, int)

    def __init__(self, client: GroqWhisperClient, wav_path: Path):
        super().__init__()
        self._client = client
        self._wav_path = wav_path

    def run(self) -> None:
        try:
            text = self._client.transcribe(self._wav_path)
            self.finished.emit(text)
        except ValueError as e:
            self.error.emit(str(e), -1)
        except RetryableError as e:
            retry_after = e.retry_after if hasattr(e, 'retry_after') else None
            self.error.emit(str(e), retry_after if retry_after is not None else -1)
        except NetworkError as e:
            self.error.emit(str(e), -1)


# ─── MicButton ─────────────────────────────────────────────────────
MIC_EMOJI = '\U0001F399'

class MicButton(QPushButton):
    STATE_IDLE = 'idle'
    STATE_REC = 'rec'
    STATE_SENDING = 'sending'

    IDLE_CSS = 'MicButton{background:#52525B;color:white;border-radius:22px;font-size:22px}MicButton:hover{background:#71717A}MicButton:disabled{background:#A1A1AA;color:#D4D4D8}'
    REC_CSS = 'MicButton{background:#EF4444;color:white;border-radius:22px;font-size:22px}'
    REC_CSS2 = 'MicButton{background:#DC2626;color:white;border-radius:22px;font-size:22px}'
    SENDING_CSS = 'MicButton{background:#A1A1AA;color:#D4D4D8;border-radius:22px;font-size:14px}'

    def __init__(self, parent=None):
        super().__init__(MIC_EMOJI, parent)
        self.setFixedSize(44, 44)
        self.setStyleSheet(self.IDLE_CSS)
        self._state = self.STATE_IDLE
        self._anim_timer = None

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        self._stop_anim()
        if state == self.STATE_IDLE:
            self.setText(MIC_EMOJI)
            self.setFixedSize(44, 44)
            self.setDisabled(False)
            self.setStyleSheet(self.IDLE_CSS)
        elif state == self.STATE_REC:
            self.setText(MIC_EMOJI)
            self.setFixedSize(44, 44)
            self.setDisabled(False)
            self.setStyleSheet(self.REC_CSS)
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._pulse)
            self._anim_timer.start(250)
        elif state == self.STATE_SENDING:
            self.setText('Распознаётся...')
            self.setFixedSize(140, 44)
            self.setDisabled(True)
            self.setStyleSheet(self.SENDING_CSS)
        self._state = state

    def _stop_anim(self) -> None:
        if self._anim_timer:
            self._anim_timer.stop()
            self._anim_timer.deleteLater()
            self._anim_timer = None

    def _pulse(self) -> None:
        cur = self.palette().color(QPalette.ColorRole.Button)
        if cur.red() > 220:
            self.setStyleSheet(self.REC_CSS2)
        else:
            self.setStyleSheet(self.REC_CSS)


# ─── AudioDialog ─────────────────────────────────────────────────
class AudioDialog(QDialog):
    MIC_IDLE = 0
    MIC_REC = 1
    MIC_SENDING = 2

    def __init__(
        self,
        api_key: str,
        toggle_callback: Callable[[], None],
        cut_callback: Callable[[str], None],
    ):
        super().__init__()
        self._api_key = api_key
        self._groq_client = GroqWhisperClient(api_key)
        self._toggle_callback = toggle_callback
        self._cut_callback = cut_callback
        self._mic_state = None
        self._audio_capture = AudioCapture()
        self._transcribe_thread = None
        self._wav_path = Path(os.path.join(os.getenv('TEMP', '/tmp'), 'audiotext.wav'))

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(480, 300)

        self._bar = QFrame()
        self._bar.setObjectName('dialog_bar')
        self._bar.setFixedHeight(50)
        self._bar.setStyleSheet(
            '#dialog_bar{background:#18181B;border:1px solid #3F3F46;border-bottom:none;border-radius:8px 8px 0 0}'
        )
        self._bar.setCursor(Qt.CursorShape.SizeAllCursor)
        self._bar.mousePressEvent = self._bar_mouse_press
        self._bar.mouseMoveEvent = self._bar_mouse_move
        self._bar.mouseReleaseEvent = self._bar_mouse_release
        self._drag_pos = None

        self._mic_btn = MicButton()
        self._mic_btn.clicked.connect(self.on_mic_toggle)

        self.copy_btn = QPushButton('Cut')
        self.copy_btn.setFixedSize(72, 30)
        self.copy_btn.clicked.connect(self.on_cut)
        self.copy_btn.setStyleSheet(
            'QPushButton{background:#27272A;color:#E4E4E7;border:1px solid #3F3F46;border-radius:6px;padding:0 8px}'
            'QPushButton:hover{background:#3F3F46}'
        )

        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont('Segoe UI', 14))
        self._text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self._text_edit.setStyleSheet(
            'QTextEdit{background:#09090B;color:#FAFAFA;border:1px solid #3F3F46;border-top:none;border-radius:0 0 8px 8px;padding:8px}'
        )

        self._setup_layout()
        self._set_mic_state(self.MIC_IDLE)
        self._setup_capture()

    # -- layout --
    def _setup_layout(self) -> None:
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(0)

        bar_h = QHBoxLayout(self._bar)
        bar_h.setContentsMargins(12, 6, 12, 6)
        bar_h.setSpacing(8)
        bar_h.addWidget(self._mic_btn)
        bar_h.addStretch()
        bar_h.addWidget(self.copy_btn)

        main.addWidget(self._bar)
        main.addWidget(self._text_edit, 1)

    # -- capture setup --
    def _setup_capture(self) -> None:
        self._audio_capture.set_timeout_callback(self._on_capture_timeout)

    def _on_capture_timeout(self) -> None:
        if self._mic_state != self.MIC_REC:
            return
        self._text_edit.append('\u26a0 Recording auto-stopped: 5 minute limit.')
        self._do_stop_and_transcribe()

    def _do_stop_and_transcribe(self) -> None:
        try:
            self._audio_capture.save_wav(self._wav_path)
        except Exception as e:
            self._text_edit.append(f'Error: {e}')
            self._set_mic_state(self.MIC_IDLE)
            return

        self._set_mic_state(self.MIC_SENDING)
        self._start_transcribe_thread()

    def _start_transcribe_thread(self) -> None:
        self._transcribe_thread = TranscribeThread(
            self._groq_client, self._wav_path
        )
        self._transcribe_thread.finished.connect(
            self._on_transcribe_done
        )
        self._transcribe_thread.error.connect(
            self._on_transcribe_error
        )
        self._transcribe_thread.start()

    # -- state --
    def _set_mic_state(self, state: int) -> None:
        self._mic_state = state
        if state == self.MIC_IDLE:
            self._mic_btn.set_state(MicButton.STATE_IDLE)
        elif state == self.MIC_REC:
            self._mic_btn.set_state(MicButton.STATE_REC)
        elif state == self.MIC_SENDING:
            self._mic_btn.set_state(MicButton.STATE_SENDING)

    # -- actions --
    def on_mic_toggle(self) -> None:
        if self._mic_state == self.MIC_IDLE:
            self._do_start_recording()
        elif self._mic_state == self.MIC_REC:
            self._do_stop_and_transcribe()
        elif self._mic_state == self.MIC_SENDING:
            pass

    def start_recording(self) -> None:
        """
        Public API for global hotkeys:
        start recording only if currently idle.
        """
        if self._mic_state == self.MIC_IDLE:
            self._do_start_recording()

    def stop_recording(self) -> None:
        """
        Public API for global hotkeys:
        stop recording only if currently recording (REC).
        """
        if self._mic_state == self.MIC_REC:
            self._do_stop_and_transcribe()

    def toggle_recording(self) -> None:
        """
        Public API for global hotkeys:
        - if idle -> start recording
        - if recording -> stop and transcribe
        - if sending -> ignore
        """
        if self._mic_state == self.MIC_IDLE:
            self._do_start_recording()
        elif self._mic_state == self.MIC_REC:
            self._do_stop_and_transcribe()

    def stop_recording_without_transcribe(self) -> None:
        """
        Stop recording but DO NOT send audio for transcription.
        Used when hiding the UI via Alt+`.
        """
        if self._mic_state == self.MIC_REC:
            try:
                # Stop audio capture and discard buffered audio.
                self._audio_capture.stop()
            except Exception as e:
                self._text_edit.append(f'Error: {e}')
            self._set_mic_state(self.MIC_IDLE)

    def _do_start_recording(self) -> None:
        try:
            self._audio_capture.start()
        except Exception as e:
            self._text_edit.append(f'Mic error: {e}')
            return
        self._set_mic_state(self.MIC_REC)

    def on_cut(self) -> None:
        self._cut_callback(self.current_text)
        self._text_edit.clear()

    def insert_transcription(self, text: str) -> None:
        cursor = self._text_edit.textCursor()
        pos = cursor.position()
        block = cursor.document().findBlock(pos)
        block_text = block.text()
        before = block_text[:pos - block.position()]
        after = block_text[pos - block.position():]

        insert = text
        if before and not before[-1].isspace():
            insert = ' ' + insert
        if after and not after[0].isspace():
            insert = insert + ' '

        cursor.insertText(insert)

    # -- properties --
    @property
    def current_text(self) -> str:
        return self._text_edit.toPlainText()

    def set_text(self, text: str) -> None:
        self._text_edit.setPlainText(text)

    # -- transcription callbacks --
    def _on_transcribe_done(self, text: str) -> None:
        self.insert_transcription(text)
        self._set_mic_state(self.MIC_IDLE)

    def _on_transcribe_error(self, error_msg: str, retry_after: int = -1) -> None:
        self._set_mic_state(self.MIC_IDLE)
        if retry_after is not None and retry_after >= 0:
            self._text_edit.append(f'\u26a0 Please wait {retry_after} seconds before re-trying.')
            return
        self._text_edit.append(f'\u26a0 Error: {error_msg}')

    def _bar_mouse_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _bar_mouse_move(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _bar_mouse_release(self, event) -> None:
        self._drag_pos = None
        event.accept()

    # -- properties --
