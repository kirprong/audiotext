import os
import json
import tempfile
from pathlib import Path


class StateManager:
    CURRENT_VERSION = 1

    def __init__(self):
        self.state_dir = Path(os.getenv('APPDATA')) / 'AudioText'
        self.state_file = self.state_dir / 'state.json'

    def load_text(self) -> str:
        data = self._load_raw()
        return data.get('text', '')

    def save_text(self, text: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = self._load_raw()
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.state_dir, prefix='.state_tmp_', suffix='.json'
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump({'version': self.CURRENT_VERSION, 'text': text, 'undo_stack': data.get('undo_stack', [])}, f)
            os.replace(temp_path, str(self.state_file))
        except:
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def save_undo_stack(self, texts: list[str]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = self._load_raw()
        data['undo_stack'] = texts[-100:]
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.state_dir, prefix='.state_tmp_', suffix='.json'
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump({'version': self.CURRENT_VERSION, 'text': data.get('text', ''), 'undo_stack': data['undo_stack']}, f)
            os.replace(temp_path, str(self.state_file))
        except:
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def load_undo_stack(self) -> list[str]:
        data = self._load_raw()
        return data.get('undo_stack', [])

    def _load_raw(self) -> dict:
        try:
            data = json.loads(self.state_file.read_text(encoding='utf-8'))
            if 'version' not in data:
                return {'version': self.CURRENT_VERSION, 'text': data.get('text', ''), 'undo_stack': []}
            return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {'version': self.CURRENT_VERSION, 'text': '', 'undo_stack': []}
