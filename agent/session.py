from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from repositories.message_repository import MessageRepository


class AgentSession:
    def __init__(self, session_factory: async_sessionmaker, session_id: str) -> None:
        self._session_factory = session_factory
        self._session_id = session_id

    async def get_items(self, limit: int | None = None) -> list[Any]:
        async with self._session_factory() as db:
            return await MessageRepository(db).get_items(self._session_id, limit)

    async def add_items(self, items: list[Any]) -> None:
        async with self._session_factory() as db:
            await MessageRepository(db).add_items(self._session_id, items)
            await db.commit()

    async def pop_item(self) -> Any | None:
        async with self._session_factory() as db:
            payload = await MessageRepository(db).pop_item(self._session_id)
            await db.commit()
            return payload

    async def clear_session(self) -> None:
        async with self._session_factory() as db:
            await MessageRepository(db).clear_session(self._session_id)
            await db.commit()
