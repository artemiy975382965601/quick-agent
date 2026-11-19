import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from core.exceptions import AppError, ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError):
        return JSONResponse(status_code=422, content={'detail': str(exc)})

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=400, content={'detail': str(exc)})

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError):
        logger.warning('rate limit on %s %s', request.method, request.url.path)
        return JSONResponse(status_code=429, content={'detail': 'rate limit exceeded'})

    @app.exception_handler(APITimeoutError)
    async def api_timeout_handler(request: Request, exc: APITimeoutError):
        logger.warning('upstream timeout on %s %s', request.method, request.url.path)
        return JSONResponse(status_code=504, content={'detail': 'upstream timeout'})

    @app.exception_handler(APIConnectionError)
    async def api_connection_handler(request: Request, exc: APIConnectionError):
        logger.warning('upstream connection error on %s %s', request.method, request.url.path)
        return JSONResponse(status_code=502, content={'detail': 'upstream connection error'})

    @app.exception_handler(APIStatusError)
    async def api_status_handler(request: Request, exc: APIStatusError):
        logger.warning('upstream status %s on %s %s', exc.status_code, request.method, request.url.path)
        return JSONResponse(status_code=502, content={'detail': f'upstream error: {exc.status_code}'})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception('unhandled error on %s %s', request.method, request.url.path)
        return JSONResponse(status_code=500, content={'detail': 'internal error'})
