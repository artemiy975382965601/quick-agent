from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_BASE_URL = os.environ.get('QUICK_AGENT_URL', 'http://127.0.0.1:7777')
PROMPTS_DIR = Path(os.environ.get('QUICK_AGENT_PROMPTS_DIR', '/home/art-dev/prompts'))

CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'quick-agent-client'
CONFIG_FILE = CONFIG_DIR / 'config.json'

# Порядок важен: client_base ссылается на «следующий файл».
MODE_PROMPTS = {
    'cli': ('client_base', 'client_mode_terminal'),
    'tg': ('client_base', 'client_mode_tg'),
}

DEFAULT_TIMEOUT = 60
DEFAULT_STREAM_TIMEOUT = 900


class Config:
    """Настройки клиента: адрес API, таймауты, текущие сессии, клиентские промпты."""

    def __init__(self, data: dict | None = None, path: Path = CONFIG_FILE) -> None:
        self._data = data or {}
        self._path = path

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> 'Config':
        try:
            return cls(json.loads(path.read_text()), path)
        except (OSError, ValueError):
            return cls({}, path)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))
        tmp.chmod(0o600)
        tmp.replace(self._path)

    # ---------------------------------------------------------------- адрес
    @property
    def base_url(self) -> str:
        return (self._data.get('base_url') or DEFAULT_BASE_URL).rstrip('/')

    def set_base_url(self, url: str) -> None:
        self._data['base_url'] = url.rstrip('/')
        self.save()

    # ---------------------------------------------------------------- таймауты
    @property
    def timeout(self) -> int:
        return int(self._data.get('timeout') or DEFAULT_TIMEOUT)

    @property
    def stream_timeout(self) -> int:
        return int(self._data.get('stream_timeout') or DEFAULT_STREAM_TIMEOUT)

    # ---------------------------------------------------------------- сессии
    def current(self, mode: str) -> str | None:
        return (self._data.get('current') or {}).get(mode)

    def set_current(self, mode: str, session_id: str | None) -> None:
        current = self._data.setdefault('current', {})
        if session_id is None:
            current.pop(mode, None)
        else:
            current[mode] = session_id
        self.save()

    # ---------------------------------------------------------------- промпты
    def prompt_paths(self, mode: str) -> list[str]:
        """Пути клиентских промптов. Переопределяются в конфиге ключом prompt_paths.<mode>."""
        custom = (self._data.get('prompt_paths') or {}).get(mode)
        if custom is not None:
            return [str(p) for p in custom]
        names = MODE_PROMPTS.get(mode, ())
        return [str(PROMPTS_DIR / name) for name in names]

    def missing_prompts(self, mode: str) -> list[str]:
        return [p for p in self.prompt_paths(mode) if not Path(p).is_file()]
