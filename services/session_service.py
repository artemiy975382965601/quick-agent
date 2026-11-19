from core.config import AppConfig
from core.exceptions import ConflictError, NotFoundError, ValidationError
from core.uow import UnitOfWork
from schemas import SessionCreate, SessionOut, SessionPut


class SessionService:
    def __init__(self, uow: UnitOfWork, config: AppConfig):
        self.uow = uow
        self.config = config

    async def list(self) -> list[SessionOut]:
        return [SessionOut.model_validate(s) for s in await self.uow.sessions.list()]

    async def get(self, session_id: str) -> SessionOut:
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise NotFoundError('session not found')
        return SessionOut.model_validate(session)

    def _validate_model_alias(self, model_alias: str) -> None:
        if model_alias not in self.config.models:
            raise ValidationError(f'unknown model alias: {model_alias}')

    async def create(self, payload: SessionCreate) -> SessionOut:
        if await self.uow.sessions.exists(payload.id):
            raise ConflictError('Session with this id already exists')

        title = payload.title if payload.title is not None else self.config.default.title
        model_alias = (
            payload.model_alias
            if payload.model_alias is not None
            else self.config.default.model_alias
        )
        self._validate_model_alias(model_alias)
        session = await self.uow.sessions.create(payload.id, title, model_alias)
        return SessionOut.model_validate(session)

    async def update(self, session_id: str, payload: SessionPut) -> SessionOut:
        if payload.model_alias is not None:
            self._validate_model_alias(payload.model_alias)
        session = await self.uow.sessions.update(session_id, payload.title, payload.model_alias)
        if session is None:
            raise NotFoundError('session not found')
        return SessionOut.model_validate(session)

    async def delete(self, session_id: str) -> None:
        if not await self.uow.sessions.delete(session_id):
            raise NotFoundError('session not found')
