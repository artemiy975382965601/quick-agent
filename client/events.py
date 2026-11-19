from __future__ import annotations

import json
from dataclasses import dataclass

DELTA = 'delta'
TOOL_CALLED = 'tool_called'
TOOL_OUTPUT = 'tool_output'
ERROR = 'error'
DONE = 'done'


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    data: str = ''

    def error_info(self) -> dict:
        if self.kind != ERROR:
            return {}
        try:
            info = json.loads(self.data)
        except ValueError:
            return {'code': 'error', 'message': self.data, 'retryable': False}
        return info if isinstance(info, dict) else {'code': 'error', 'message': str(info)}


class SSEParser:
    """Разбор text/event-stream построчно.

    Один парсер на оба транспорта: sync и async читают строки по-разному,
    но протокол разбирают одинаково.
    """

    def __init__(self) -> None:
        self._event = 'message'
        self._data: list[str] = []

    def feed(self, line: str) -> list[Event]:
        if line.startswith(':'):
            return []
        if line == '':
            event = self._flush()
            return [event] if event is not None else []
        if line.startswith('event:'):
            self._event = line[6:].strip()
        elif line.startswith('data:'):
            chunk = line[5:]
            if chunk.startswith(' '):
                chunk = chunk[1:]
            self._data.append(chunk)
        return []

    def close(self) -> list[Event]:
        event = self._flush()
        return [event] if event is not None else []

    def _flush(self) -> Event | None:
        if not self._data:
            self._event = 'message'
            return None
        data = '\n'.join(self._data)
        event = Event(self._event, data)
        self._event = 'message'
        self._data = []
        return event
