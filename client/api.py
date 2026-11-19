from __future__ import annotations

# Слой чистых функций: URL, метод и тело запроса. Транспорты (sync/aio)
# только отправляют то, что здесь собрано, — пути и тела не дублируются.

Request = tuple[str, str, dict | None]


def health() -> Request:
    return 'GET', '/health/', None


def session_list() -> Request:
    return 'GET', '/sessions/list/', None


def session_create(session_id: str, title: str | None = None, model_alias: str | None = None) -> Request:
    payload: dict = {'id': session_id}
    if title:
        payload['title'] = title
    if model_alias:
        payload['model_alias'] = model_alias
    return 'POST', '/sessions/create/', payload


def session_get(session_id: str) -> Request:
    return 'GET', f'/sessions/{session_id}/', None


def session_put(session_id: str, title: str | None = None, model_alias: str | None = None) -> Request:
    payload: dict = {}
    if title is not None:
        payload['title'] = title
    if model_alias is not None:
        payload['model_alias'] = model_alias
    if not payload:
        raise ValueError('нужен title и/или model_alias')
    return 'PUT', f'/sessions/{session_id}/', payload


def session_delete(session_id: str) -> Request:
    return 'DELETE', f'/sessions/{session_id}/', None


def chat_start(session_id: str, query: str, client_prompt_paths: list[str]) -> Request:
    return 'POST', f'/chat/{session_id}/start', {
        'query': query,
        'client_prompt_paths': list(client_prompt_paths),
    }


def chat_stop(session_id: str) -> Request:
    return 'POST', f'/chat/{session_id}/stop', None


def chat_cancel(session_id: str) -> Request:
    """Откат последнего сообщения на стороне сервера (POST /cancel)."""
    return 'POST', f'/chat/{session_id}/cancel', None


def chat_history(session_id: str, limit: int = 10, before_id: int | None = None) -> Request:
    limit = max(1, min(200, int(limit)))
    path = f'/chat/{session_id}/?limit={limit}'
    if before_id is not None:
        path += f'&before_id={int(before_id)}'
    return 'GET', path, None


def chat_clear(session_id: str) -> Request:
    return 'DELETE', f'/chat/{session_id}/', None


def pinned_list(session_id: str) -> Request:
    return 'GET', f'/sessions/{session_id}/pinned/', None


def pinned_pin(session_id: str, full_paths: list[str], space: str = 'user') -> Request:
    return 'POST', f'/sessions/{session_id}/pinned/', {
        'full_paths': list(full_paths),
        'space_for_insert': space,
    }


def pinned_unpin(session_id: str, full_paths: list[str]) -> Request:
    return 'DELETE', f'/sessions/{session_id}/pinned/', {'full_paths': list(full_paths)}
