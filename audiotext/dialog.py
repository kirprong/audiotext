from __future__ import annotations
import math
import os
import time
import shutil
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QThread,
    QTimer,
    pyqtSignal,
    Qt,
    QObject,
)
from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFrame,
    QWidget,
    QLabel,
)

from .groq_whisper import GroqWhisperClient, RetryableError, NetworkError
from .audio_capture import AudioCapture


class NoFocusTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable = False
        self.setReadOnly(True)

    def setEditable(self, editable: bool) -> None:
        self._editable = editable
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if editable else Qt.FocusPolicy.NoFocus)
        self.setReadOnly(not editable)


# ─── AmplitudeBars ─────────────────────────────────────────────────────
class AmplitudeBars(QWidget):
    BAR_COUNT = 10
    BAR_WIDTH = 6
    MIN_HEIGHT = 4
    MAX_HEIGHT = 24
    BAR_COLORS = ['#6366F1', '#8B5CF6', '#A855F7', '#8B5CF6', '#6366F1']

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._bars = []
        self._anim_timer = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        for i in range(self.BAR_COUNT):
            bar = QFrame()
            bar.setFixedWidth(self.BAR_WIDTH)
            bar.setMinimumHeight(self.MIN_HEIGHT)
            bar.setMaximumHeight(self.MAX_HEIGHT)
            bar.setStyleSheet('QFrame{background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366F1, stop:1 #A855F7);border-radius:3px;}')
            self._bars.append(bar)
            layout.addWidget(bar)
        self.setFixedHeight(self.MAX_HEIGHT + 8)

    def start_animation(self) -> None:
        if self._anim_timer is None:
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate)
            self._anim_timer.start(50)

    def stop_animation(self) -> None:
        if self._anim_timer:
            self._anim_timer.stop()
            self._anim_timer.deleteLater()
            self._anim_timer = None
        for bar in self._bars:
            bar.setStyleSheet('QFrame{background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366F1, stop:1 #A855F7);border-radius:3px;}')

    def _animate(self) -> None:
        self._phase += 0.15
        for i, bar in enumerate(self._bars):
            offset = (i - (self.BAR_COUNT - 1) / 2) / (self.BAR_COUNT / 2)
            height = self.MIN_HEIGHT + (self.MAX_HEIGHT - self.MIN_HEIGHT) * (
                (math.sin(self._phase + offset * math.pi) + 1) / 2
            )
            bar.setFixedHeight(int(height))
        self.update()


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
    REC_CSS = 'MicButton{background:#7F1D1D;color:#6366F1;border-radius:22px;font-size:22px}'
    SENDING_CSS = 'MicButton{background:#A1A1AA;color:#D4D4D8;border-radius:22px;font-size:14px}'

    def __init__(self, parent=None):
        super().__init__(MIC_EMOJI, parent)
        self.setFixedSize(44, 44)
        self.setStyleSheet(self.IDLE_CSS)
        self._state = self.STATE_IDLE

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
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
        elif state == self.STATE_SENDING:
            self.setText('Распознаётся...')
            self.setFixedSize(140, 44)
            self.setDisabled(True)
            self.setStyleSheet(self.SENDING_CSS)
        self._state = state


# ─── AudioDialog ─────────────────────────────────────────────────
class AudioDialog(QDialog):
    MIC_IDLE = 0
    MIC_REC = 1
    MIC_SENDING = 2

    def __init__(
        self,
        api_key: str,
        toggle_callback: Callable[[], None],
    ):
        super().__init__()
        self._api_key = api_key
        self._groq_client = GroqWhisperClient(api_key)
        self._toggle_callback = toggle_callback
        self._mic_state = None
        self._audio_capture = AudioCapture()
        self._transcribe_thread = None
        self._wav_path = Path(os.path.join(os.getenv('TEMP', '/tmp'), 'audiotext.wav'))
        self._queue_dir = Path(os.getenv('APPDATA', '/tmp')) / 'AudioText' / 'queue'
        self._queue_dir.mkdir(parents=True, exist_ok=True)
        self._retry_btn = None
        self._pending_wav = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('QDialog{background:#18181B}')
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

        self._amplitude_bars = AmplitudeBars()
        self._amplitude_bars.hide()

        self._retry_btn = QPushButton('Retry')
        self._retry_btn.setFixedSize(72, 30)
        self._retry_btn.clicked.connect(self._on_retry)
        self._retry_btn.setStyleSheet(
            'QPushButton{background:#3B82F6;color:#FAFAFA;border:1px solid #6366F1;border-radius:6px;padding:0 8px}'
            'QPushButton:hover{background:#6366F1}'
        )
        self._retry_btn.hide()

        self._close_btn = QPushButton('✕')
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.clicked.connect(self._on_close)
        self._close_btn.setStyleSheet(
            'QPushButton{background:#18181B;color:#9CA3AF;border:none;border-radius:4px}'
            'QPushButton:hover{background:#27272A;color:#E4E4E7}'
        )

        self._text_edit = NoFocusTextEdit()
        self._text_edit.setFont(QFont('Segoe UI', 14))
        self._text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self._text_edit.setStyleSheet(
            'QTextEdit{background:#09090B;color:#FAFAFA;border:1px solid #3F3F46;border-top:none;border-radius:0 0 8px 8px;padding:8px}'
        )
        self._text_edit.setText('')
        self._text_edit.setEditable(False)
        self._text_edit.mouseDoubleClickEvent = self._text_edit_double_click

        self._error_widget = QWidget(self)
        self._error_widget.setObjectName('error_widget')
        self._error_widget.setStyleSheet(
            '#error_widget{background:#27272A;border-radius:6px}'
        )
        error_layout = QHBoxLayout(self._error_widget)
        error_layout.setContentsMargins(12, 8, 12, 8)
        self._error_widget_label = QLabel('')
        self._error_widget_label.setObjectName('error_label')
        self._error_widget_label.setStyleSheet(
            '#error_label{color:#FEE2E2;font-size:13px}'
        )
        self._error_widget_label.setWordWrap(True)
        self._error_widget_label.setMaximumWidth(300)
        error_layout.addWidget(self._error_widget_label)
        self._error_widget.hide()
        self._error_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._hide_error_widget)

        self._setup_layout()
        self._set_mic_state(self.MIC_IDLE)
        self._setup_capture()

    # -- layout --
    def _setup_layout(self) -> None:
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(4)

        bar_h = QHBoxLayout(self._bar)
        bar_h.setContentsMargins(12, 6, 12, 6)
        bar_h.setSpacing(8)
        bar_h.addWidget(self._mic_btn)
        bar_h.addWidget(self._amplitude_bars)
        bar_h.addWidget(self._retry_btn)
        bar_h.addStretch()
        bar_h.addWidget(self._close_btn)

        main.addWidget(self._bar)
        main.addWidget(self._text_edit, 1)

    # -- capture setup --
    def _setup_capture(self) -> None:
        self._audio_capture.set_timeout_callback(self._on_capture_timeout)

    def showEvent(self, event) -> None:
        self._text_edit.setEditable(False)
        event.accept()

    def focusOutEvent(self, event) -> None:
        self._text_edit.setEditable(False)
        event.accept()

    def _on_capture_timeout(self) -> None:
        if self._mic_state != self.MIC_REC:
            return
        self._show_error('Recording auto-stopped: 5 minute limit.')
        self._do_stop_and_transcribe()

    def _do_stop_and_transcribe(self) -> None:
        try:
            self._audio_capture.save_wav(self._wav_path)
        except Exception as e:
            self._show_error(str(e))
            self._set_mic_state(self.MIC_IDLE)
            self._amplitude_bars.stop_animation()
            self._amplitude_bars.hide()
            return

        self._amplitude_bars.stop_animation()
        self._amplitude_bars.hide()
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
        if self._mic_state == self.MIC_IDLE:
            self._do_start_recording()

    def stop_recording(self) -> None:
        if self._mic_state == self.MIC_REC:
            self._do_stop_and_transcribe()

    def toggle_recording(self) -> None:
        if self._mic_state == self.MIC_IDLE:
            self._do_start_recording()
        elif self._mic_state == self.MIC_REC:
            self._do_stop_and_transcribe()

    def stop_recording_without_transcribe(self) -> None:
        if self._mic_state == self.MIC_REC:
            try:
                self._audio_capture.stop()
            except Exception as e:
                self._show_error(str(e))
            self._set_mic_state(self.MIC_IDLE)
            self._amplitude_bars.stop_animation()
            self._amplitude_bars.hide()

    def _do_start_recording(self) -> None:
        self._error_timer.stop()
        self._hide_error_widget()
        try:
            self._audio_capture.start()
        except Exception as e:
            self._show_error(f'Mic error: {e}')
            return
        self._set_mic_state(self.MIC_REC)
        self._amplitude_bars.show()
        self._amplitude_bars.start_animation()

    def _on_close(self) -> None:
        QApplication.instance().quit()

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

    @property
    def current_text(self) -> str:
        return self._text_edit.toPlainText()

    def set_text(self, text: str) -> None:
        self._text_edit.setPlainText(text)

    # -- transcription callbacks --
    def _on_transcribe_done(self, text: str) -> None:
        wav_to_delete = self._pending_wav or self._wav_path
        if wav_to_delete.exists():
            wav_to_delete.unlink()
        self.insert_transcription(text)
        self._set_mic_state(self.MIC_IDLE)
        self._pending_wav = None

    def _on_transcribe_error(self, error_msg: str, retry_after: int = -1) -> None:
        wav_to_queue = self._wav_path
        if wav_to_queue.exists():
            shutil.copy2(wav_to_queue, self._queue_dir / f'queue_{int(time.time())}.wav')
        self._set_mic_state(self.MIC_IDLE)
        self._retry_btn.show()
        if retry_after is not None and retry_after >= 0:
            self._show_error(f'Please wait {retry_after} seconds before re-trying.')
            return
        self._show_error(f'Error: {error_msg}')

    def _show_error(self, message: str) -> None:
        self._error_widget_label.setText(f'\u26a0 {message}')
        self._error_widget.adjustSize()
        self._error_widget.move(
            (self.width() - self._error_widget.width()) // 2,
            (self.height() - self._error_widget.height()) // 2
        )
        self._error_widget.raise_()
        self._error_widget.show()
        self._error_timer.start(5000)

    def _hide_error_widget(self) -> None:
        self._error_widget.hide()

    def _on_retry(self) -> None:
        if self._mic_state == self.MIC_SENDING:
            return
        wav_files = sorted(self._queue_dir.glob('queue_*.wav'), reverse=True)
        if not wav_files:
            self._retry_btn.hide()
            return
        self._error_timer.stop()
        self._hide_error_widget()
        self._pending_wav = wav_files[0]
        self._set_mic_state(self.MIC_SENDING)
        self._retry_btn.hide()
        self._transcribe_thread = TranscribeThread(self._groq_client, self._pending_wav)
        self._transcribe_thread.finished.connect(self._on_transcribe_done)
        self._transcribe_thread.error.connect(self._on_transcribe_error)
        self._transcribe_thread.start()

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

    def _text_edit_double_click(self, event) -> None:
        self._text_edit.setEditable(True)
        self._text_edit.setFocus()
        cursor = self._text_edit.cursorForPosition(event.pos())
        self._text_edit.setTextCursor(cursor)
        event.accept()

    def hideEvent(self, event) -> None:
        self._text_edit.setEditable(False)
        event.accept()