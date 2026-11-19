from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
import uuid
from typing import Iterator

import client.api as api
from client.config import Config
from client.errors import ApiError, ClientError, ConnectionFailed
from client.events import Event, SSEParser
from client.history import USER, Item, normalize_all


class SyncClient:
    """Синхронный транспорт для CLI. Только stdlib."""

    def __init__(self, config: Config) -> None:
        self.config = config

    # ---------------------------------------------------------------- низкий уровень
    def _open(self, request: api.Request, timeout: float):
        method, path, payload = request
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(
            self.config.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode('utf-8', 'replace')
            try:
                detail = json.loads(raw)
            except ValueError:
                detail = raw[:2000]
            raise ApiError(exc.code, detail, path) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            reason = getattr(exc, 'reason', exc)
            raise ConnectionFailed(self.config.base_url, reason) from None

    @staticmethod
    def _decode(raw: str):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw

    def request(self, request: api.Request, timeout: float | None = None):
        with self._open(request, timeout or self.config.timeout) as resp:
            raw = resp.read().decode('utf-8', 'replace')
        return self._decode(raw)

    def stream(self, request: api.Request) -> Iterator[Event]:
        """Читает SSE и отдаёт события по мере поступления."""
        parser = SSEParser()
        with self._open(request, self.config.stream_timeout) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                for event in parser.feed(line):
                    yield event
        for event in parser.close():
            yield event

    # ---------------------------------------------------------------- сервис
    def health(self) -> bool:
        try:
            body = self.request(api.health(), timeout=5)
        except (ApiError, ConnectionFailed):
            return False
        return isinstance(body, dict) and body.get('status') == 'ok'

    # ---------------------------------------------------------------- сессии
    def list_sessions(self) -> list[dict]:
        body = self.request(api.session_list())
        return body if isinstance(body, list) else []

    def create_session(self, title: str | None = None, model_alias: str | None = None,
                       session_id: str | None = None) -> str:
        sid = session_id or uuid.uuid4().hex[:12]
        self.request(api.session_create(sid, title, model_alias))
        return sid

    def get_session(self, session_id: str) -> dict:
        body = self.request(api.session_get(session_id))
        return body if isinstance(body, dict) else {}

    def update_session(self, session_id: str, title: str | None = None,
                       model_alias: str | None = None) -> dict:
        body = self.request(api.session_put(session_id, title, model_alias))
        return body if isinstance(body, dict) else {}

    def delete_session(self, session_id: str) -> None:
        self.request(api.session_delete(session_id))

    # ---------------------------------------------------------------- чат
    def start(self, session_id: str, query: str, mode: str) -> Iterator[Event]:
        prompts = self.config.prompt_paths(mode)
        return self.stream(api.chat_start(session_id, query, prompts))

    def last_user_query(self, session_id: str) -> str:
        """Последний запрос пользователя. История отдаётся от новых к старым,
        поэтому подходит первый user-item."""
        items, _ = self.history(session_id, 50)
        for item in items:
            if item.kind == USER and item.text.strip():
                return item.text
        raise ClientError('в истории нет сообщения пользователя')

    def retry(self, session_id: str, mode: str) -> Iterator[Event]:
        """Откат последнего хода (cancel удаляет его целиком) и повтор того же текста."""
        query = self.last_user_query(session_id)
        self.cancel(session_id)
        yield from self.start(session_id, query, mode)

    def stop(self, session_id: str) -> None:
        self.request(api.chat_stop(session_id))

    def cancel(self, session_id: str) -> None:
        self.request(api.chat_cancel(session_id))

    def history(self, session_id: str, limit: int = 10) -> tuple[list[Item], bool]:
        body = self.request(api.chat_history(session_id, limit))
        if not isinstance(body, dict):
            return [], False
        return normalize_all(body.get('messages')), bool(body.get('has_more'))

    def clear(self, session_id: str) -> None:
        self.request(api.chat_clear(session_id))

    # ---------------------------------------------------------------- pinned
    def pinned(self, session_id: str) -> list[dict]:
        body = self.request(api.pinned_list(session_id))
        return body if isinstance(body, list) else []

    def pin(self, session_id: str, paths: list[str], space: str = 'user') -> list[str]:
        body = self.request(api.pinned_pin(session_id, paths, space))
        return body.get('results', []) if isinstance(body, dict) else []

    def unpin(self, session_id: str, paths: list[str]) -> list[str]:
        body = self.request(api.pinned_unpin(session_id, paths))
        return body.get('results', []) if isinstance(body, dict) else []
