import json
import logging

from fastapi import APIRouter, Depends
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from openai.types.responses import ResponseTextDeltaEvent
from sse_starlette import EventSourceResponse

from api.deps import ChatServiceDep
from schemas import ChatMessages, ChatQuery, ChatStart, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/chat')


def _classify_error(exc: Exception) -> dict:
    if isinstance(exc, RateLimitError):
        return {'code': 'rate_limit', 'message': 'rate limit exceeded', 'retryable': True}
    if isinstance(exc, APITimeoutError):
        return {'code': 'timeout', 'message': 'upstream timeout', 'retryable': True}
    if isinstance(exc, APIConnectionError):
        return {'code': 'connection', 'message': 'upstream connection error', 'retryable': True}
    if isinstance(exc, APIStatusError):
        detail = ''
        try:
            body = exc.response.text
            detail = body[:800]
        except Exception:
            detail = str(exc)[:800]
        return {
            'code': 'upstream_error',
            'message': f'upstream status {exc.status_code}',
            'detail': detail,
            'retryable': exc.status_code >= 500,
        }
    return {'code': 'internal', 'message': 'internal error', 'retryable': False}


@router.post('/{session_id}/start')
async def start_chat(session_id: str, payload: ChatStart, service: ChatServiceDep):
    res = await service.start(session_id, payload)

    async def event_generator():
        delta_count = 0
        run = res
        attempt = 0
        while True:
            try:
                async for e in run.stream_events():
                    if e.type == 'raw_response_event':
                        if isinstance(e.data, ResponseTextDeltaEvent):
                            delta_count += 1
                            yield {'event': 'delta', 'data': e.data.delta}
                    elif e.type == 'run_item_stream_event':
                        if e.name == 'tool_called':
                            yield {'event': 'tool_called', 'data': getattr(e.item.raw_item, 'name', 'Unknown Tool')}
                        elif e.name == 'tool_output':
                            yield {'event': 'tool_output', 'data': str(e.item.output)}
            except Exception as exc:
                logger.exception('stream failed for session %s', session_id)
                classified = _classify_error(exc)
                # обрыв до первого токена лечится повтором: новый прогон на новом соединении
                if attempt == 0 and delta_count == 0 and classified['retryable']:
                    attempt += 1
                    logger.warning('retrying stream for session %s after %s', session_id, classified['code'])
                    run = await service.start(session_id, payload)
                    continue
                yield {'event': 'error', 'data': json.dumps(classified)}
                return
            break

        if delta_count == 0:
            logger.warning('empty stream for session %s', session_id)
            yield {
                'event': 'error',
                'data': json.dumps({
                    'code': 'empty_stream',
                    'message': 'model returned no content',
                    'retryable': True,
                }),
            }
            return

        logger.info('stream finished for session %s, deltas: %s', session_id, delta_count)
        yield {'event': 'done', 'data': 'ok'}

    return EventSourceResponse(event_generator(), ping=10)


@router.post('/{session_id}/stop', response_model=StatusResponse)
async def stop_chat(session_id: str, service: ChatServiceDep):
    await service.stop(session_id)
    return StatusResponse(status='stopped')


@router.get('/{session_id}/', response_model=ChatMessages)
async def get_chat(
    session_id: str,
    service: ChatServiceDep,
    query: ChatQuery = Depends(),
):
    return await service.get_messages(session_id, query.limit, query.before_id)


@router.delete('/{session_id}/', status_code=204)
async def clear_chat(session_id: str, service: ChatServiceDep):
    await service.clear(session_id)


@router.post('/{session_id}/cancel', response_model=StatusResponse)
async def cancel_last(session_id: str, service: ChatServiceDep):
    await service.cancel_last(session_id)
    return StatusResponse(status='cancelled')
