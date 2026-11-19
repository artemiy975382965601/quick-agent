from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx

import client.api as api
from client.config import Config
from client.errors import ApiError, ClientError, ConnectionFailed
from client.events import Event, SSEParser
from client.history import USER, Item, normalize_all


class AsyncClient:
    """Асинхронный транспорт для Telegram-бота."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(timeout, connect=15),
        )

    async def request(self, request: api.Request, timeout: float | None = None):
        method, path, payload = request
        async with self._client(timeout or self.config.timeout) as http:
            try:
                resp = await http.request(method, path, json=payload)
            except httpx.HTTPError as exc:
                raise ConnectionFailed(self.config.base_url, exc) from None
        self._raise_for_status(resp, path)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    @staticmethod
    def _raise_for_status(resp: httpx.Response, path: str) -> None:
        if resp.status_code < 400:
            return
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text[:2000]
        raise ApiError(resp.status_code, detail, path)

    async def stream(self, request: api.Request) -> AsyncIterator[Event]:
        method, path, payload = request
        parser = SSEParser()
        async with self._client(self.config.stream_timeout) as http:
            try:
                async with http.stream(method, path, json=payload,
                                       headers={'Accept': 'text/event-stream'}) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        try:
                            detail = resp.json()
                        except Exception:
                            detail = body.decode('utf-8', 'replace')[:2000]
                        raise ApiError(resp.status_code, detail, path)
                    async for line in resp.aiter_lines():
                        for event in parser.feed(line):
                            yield event
            except httpx.HTTPError as exc:
                raise ConnectionFailed(self.config.base_url, exc) from None
        for event in parser.close():
            yield event

    # ---------------------------------------------------------------- сервис
    async def health(self) -> bool:
        try:
            body = await self.request(api.health(), timeout=5)
        except (ApiError, ConnectionFailed):
            return False
        return isinstance(body, dict) and body.get('status') == 'ok'

    # ---------------------------------------------------------------- сессии
    async def list_sessions(self) -> list[dict]:
        body = await self.request(api.session_list())
        return body if isinstance(body, list) else []

    async def create_session(self, title: str | None = None, model_alias: str | None = None,
                             session_id: str | None = None) -> str:
        sid = session_id or uuid.uuid4().hex[:12]
        await self.request(api.session_create(sid, title, model_alias))
        return sid

    async def get_session(self, session_id: str) -> dict:
        body = await self.request(api.session_get(session_id))
        return body if isinstance(body, dict) else {}

    async def update_session(self, session_id: str, title: str | None = None,
                             model_alias: str | None = None) -> dict:
        body = await self.request(api.session_put(session_id, title, model_alias))
        return body if isinstance(body, dict) else {}

    async def delete_session(self, session_id: str) -> None:
        await self.request(api.session_delete(session_id))

    # ---------------------------------------------------------------- чат
    def start(self, session_id: str, query: str, mode: str) -> AsyncIterator[Event]:
        prompts = self.config.prompt_paths(mode)
        return self.stream(api.chat_start(session_id, query, prompts))

    async def last_user_query(self, session_id: str) -> str:
        """Последний запрос пользователя. История отдаётся от новых к старым,
        поэтому подходит первый user-item."""
        items, _ = await self.history(session_id, 50)
        for item in items:
            if item.kind == USER and item.text.strip():
                return item.text
        raise ClientError('в истории нет сообщения пользователя')

    async def retry(self, session_id: str, mode: str) -> AsyncIterator[Event]:
        """Откат последнего хода (cancel удаляет его целиком) и повтор того же текста."""
        query = await self.last_user_query(session_id)
        await self.cancel(session_id)
        async for event in self.start(session_id, query, mode):
            yield event

    async def stop(self, session_id: str) -> None:
        await self.request(api.chat_stop(session_id))

    async def cancel(self, session_id: str) -> None:
        await self.request(api.chat_cancel(session_id))

    async def history(self, session_id: str, limit: int = 10) -> tuple[list[Item], bool]:
        body = await self.request(api.chat_history(session_id, limit))
        if not isinstance(body, dict):
            return [], False
        return normalize_all(body.get('messages')), bool(body.get('has_more'))

    async def clear(self, session_id: str) -> None:
        await self.request(api.chat_clear(session_id))

    # ---------------------------------------------------------------- pinned
    async def pinned(self, session_id: str) -> list[dict]:
        body = await self.request(api.pinned_list(session_id))
        return body if isinstance(body, list) else []

    async def pin(self, session_id: str, paths: list[str], space: str = 'user') -> list[str]:
        body = await self.request(api.pinned_pin(session_id, paths, space))
        return body.get('results', []) if isinstance(body, dict) else []

    async def unpin(self, session_id: str, paths: list[str]) -> list[str]:
        body = await self.request(api.pinned_unpin(session_id, paths))
        return body.get('results', []) if isinstance(body, dict) else []
