import wave
import threading
from pathlib import Path

import sounddevice as sd

from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject


class AudioCapture:
    SAMPLE_RATE = 16000
    CHANNELS = 1
    DTYPE = 'int16'
    TIMEOUT_SECONDS = 300

    def __init__(self):
        self._buffer = bytearray()
        self._stream = None
        self._lock = threading.Lock()
        self._timer: QTimer | None = None
        self._timeout_callback: callable | None = None

    def start(self) -> None:
        self._buffer = bytearray()
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype=self.DTYPE,
            callback=self._callback,
        )
        self._stream.start()
        if self._timer:
            self._timer.stop()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(self.TIMEOUT_SECONDS * 1000)

    def stop(self) -> bytearray:
        if self._timer:
            self._timer.stop()
            self._timer = None
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            buf = bytes(self._buffer)
            self._buffer = bytearray()
            return buf

    def save_wav(self, filepath: Path) -> None:
        pcm = self.stop()
        with wave.open(str(filepath), 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(pcm)

    def set_timeout_callback(self, callback: callable) -> None:
        self._timeout_callback = callback

    def _callback(self, samples, frame_count, time, status):
        with self._lock:
            self._buffer.extend(samples.tobytes())

    def _on_timeout(self):
        if self._timeout_callback:
            self._timeout_callback()
