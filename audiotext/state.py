import os
import json
import tempfile
from pathlib import Path


class StateManager:
    def __init__(self):
        self.state_dir = Path(os.getenv('APPDATA')) / 'AudioText'
        self.state_file = self.state_dir / 'state.json'

    def load_text(self) -> str:
        try:
            data = json.loads(self.state_file.read_text(encoding='utf-8'))
            return data.get('text', '')
        except (FileNotFoundError, json.JSONDecodeError):
            return ''

    def save_text(self, text: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.state_dir, prefix='.state_tmp_', suffix='.json'
        )
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump({'text': text}, f)
            os.replace(temp_path, str(self.state_file))
        except:
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
