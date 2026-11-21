from core.config import AppConfig
from core.exceptions import ConflictError, NotFoundError
from core.uow import UnitOfWork
from schemas import ChatMessages, ChatStart


class ChatService:
    def __init__(self, uow: UnitOfWork, config: AppConfig, agent):
        self.uow = uow
        self.config = config
        self.agent = agent

    async def _ensure_session(self, session_id: str) -> None:
        if not await self.uow.sessions.exists(session_id):
            raise NotFoundError('session not found')

    async def start(self, session_id: str, payload: ChatStart):
        await self._ensure_session(session_id)
        return await self.agent.start(
            session_id,
            [{'role': 'user', 'content': payload.query}],
            tuple(payload.client_prompt_paths),
        )

    async def stop(self, session_id: str) -> None:
        await self._ensure_session(session_id)
        await self.agent.stop(session_id)

    async def get_messages(
        self,
        session_id: str,
        limit: int,
        before_id: int | None = None,
    ) -> ChatMessages:
        await self._ensure_session(session_id)
        rows, has_more = await self.uow.chat.get_messages(session_id, limit, before_id)
        next_cursor = rows[-1].id if has_more and rows else None
        return ChatMessages(
            messages=[row.payload for row in rows],
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def cancel_answer(self, session_id: str) -> None:
        """Убирает ответ, оставляя вопрос пользователя на месте."""
        await self._ensure_session(session_id)
        if self.agent.is_running(session_id):
            raise ConflictError('stream is running, stop it first')
        if await self.uow.messages.rollback_answer(session_id) == 0:
            raise NotFoundError('nothing to cancel')

    async def retry_answer(self, session_id: str, payload: ChatStart):
        """Повторяет генерацию на том же вопросе, не добавляя новый."""
        await self._ensure_session(session_id)
        if self.agent.is_running(session_id):
            raise ConflictError('stream is running, stop it first')
        await self.uow.messages.rollback_answer(session_id)
        return await self.agent.start(
            session_id,
            [],
            tuple(payload.client_prompt_paths),
        )

    async def clear(self, session_id: str) -> None:
        await self._ensure_session(session_id)
        await self.uow.chat.clear_messages(session_id)

    async def cancel_last(self, session_id: str) -> None:
        await self._ensure_session(session_id)
        if self.agent.is_running(session_id):
            raise ConflictError('stream is running, stop it first')
        if await self.uow.messages.rollback_turn(session_id) == 0:
            raise NotFoundError('no messages to cancel')
