#!/usr/bin/env python3
"""AudioText — main entry point."""
import sys
import os

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication, QMessageBox

from audiotext.groq_whisper import GroqWhisperClient
from audiotext.main_window import MainWindow
from audiotext.global_hotkey import GlobalHotkey


def main() -> int:
    load_dotenv()
    api_key = os.getenv('GROQ_API_KEY', '').strip()

    if not api_key:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, 'AudioText', 'GROQ_API_KEY not set in .env')
        return 1

    client = GroqWhisperClient(api_key)
    try:
        client.validate_api_key()
    except ValueError:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, 'AudioText', 'Invalid GROQ_API_KEY (401)')
        return 1
    except Exception as e:
        app = QApplication(sys.argv)
        QMessageBox.critical(None, 'AudioText', f'Network error: {e}')
        return 1

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow(api_key)
    hotkey = GlobalHotkey(
        window.on_toggle_from_hotkey,
        one_callback=window.on_one_from_hotkey,
        show_callback=window.on_show_from_hotkey,
        hide_callback=window.on_hide_from_hotkey,
    )
    hotkey.start()

    window.on_toggle()  # show dialog on startup

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
