import requests
from pathlib import Path


class RetryableError(Exception):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(Exception):
    pass


class GroqWhisperClient:
    _URL = 'https://api.groq.com/openai/v1'
    _MODEL = 'whisper-large-v3-turbo'

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            'Authorization': f'Bearer {api_key}',
        }

    def validate_api_key(self) -> bool:
        """True on 200, raise ValueError on 401."""
        try:
            r = requests.get(
                f'{self._URL}/models',
                headers=self._headers,
                timeout=5,
            )
        except requests.RequestException as e:
            raise NetworkError(str(e))
        if r.status_code == 200:
            return True
        if r.status_code == 401:
            raise ValueError('Invalid API key')
        raise ValueError(f'Unexpected status {r.status_code}: {r.text}')

    def transcribe(self, wav_path: Path) -> str:
        try:
            with open(wav_path, 'rb') as f:
                r = requests.post(
                    f'{self._URL}/audio/transcriptions',
                    headers=self._headers,
                    files={'file': ('audio.wav', f, 'audio/wav')},
                    data={'model': self._MODEL},
                    timeout=30,
                )
            if 200 <= r.status_code < 300:
                if wav_path.exists():
                    wav_path.unlink()
                return r.json()['text']
            if r.status_code in (400, 401, 413):
                if wav_path.exists():
                    wav_path.unlink()
                raise ValueError(f'API error {r.status_code}: {r.text}')
            if r.status_code in (429, 500, 502, 503, 504):
                # WAV NOT deleted - will be retried later
                retry_after = r.headers.get('Retry-After')
                try:
                    retry_after_int = int(retry_after) if retry_after else None
                except (ValueError, TypeError):
                    retry_after_int = None
                raise RetryableError(
                    f'Rate limited / server error {r.status_code}: {r.text}',
                    retry_after=retry_after_int,
                )
            raise ValueError(f'Unexpected status {r.status_code}: {r.text}')
        except requests.RequestException as e:
            # WAV NOT deleted - will be retried later via QueueManager
            raise NetworkError(str(e))
