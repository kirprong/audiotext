#!/usr/bin/env python3
"""Demo script for animated amplitude bars widget with sinusoidal wave."""
import math
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QWidget


class AmplitudeBars(QWidget):
    """Animated bars widget with sinusoidal wave animation."""
    BAR_COUNT = 10
    BAR_WIDTH = 6
    MIN_HEIGHT = 4
    MAX_HEIGHT = 24

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
            bar.setStyleSheet(
                'QFrame{background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366F1, stop:1 #A855F7);border-radius:3px;}'
            )
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
            bar.setStyleSheet(
                'QFrame{background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6366F1, stop:1 #A855F7);border-radius:3px;}'
            )

    def _animate(self) -> None:
        self._phase += 0.15
        for i, bar in enumerate(self._bars):
            offset = (i - (self.BAR_COUNT - 1) / 2) / (self.BAR_COUNT / 2)
            height = self.MIN_HEIGHT + (self.MAX_HEIGHT - self.MIN_HEIGHT) * (
                (math.sin(self._phase + offset * math.pi) + 1) / 2
            )
            bar.setFixedHeight(int(height))
        self.update()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    bars = AmplitudeBars()
    bars.setStyleSheet('background:#18181B;padding:12px;border-radius:8px;')
    bars.start_animation()
    bars.resize(140, 80)
    bars.show()
    sys.exit(app.exec())