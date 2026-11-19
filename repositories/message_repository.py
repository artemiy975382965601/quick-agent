from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tables import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_items(self, session_id: str, limit: int | None = None) -> list[Any]:
        stmt = (
            select(Message.payload)
            .where(Message.session_id == session_id)
            .order_by(Message.id.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        items = list((await self._db.scalars(stmt)).all())
        items.reverse()
        return items

    async def add_items(self, session_id: str, items: list[Any]) -> None:
        for item in items:
            self._db.add(Message(payload=item, session_id=session_id))
        await self._db.flush()

    async def pop_item(self, session_id: str) -> Any | None:
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id.desc())
            .limit(1)
        )
        item = await self._db.scalar(stmt)
        if item is None:
            return None
        payload = item.payload
        await self._db.delete(item)
        await self._db.flush()
        return payload

    async def rollback_turn(self, session_id: str) -> int:
        stmt = (
            select(Message.id)
            .where(Message.session_id == session_id)
            .where(Message.payload['role'].as_string() == 'user')
            .order_by(Message.id.desc())
            .limit(1)
        )
        last_user_id = await self._db.scalar(stmt)
        if last_user_id is None:
            return 0
        result = await self._db.execute(
            delete(Message)
            .where(Message.session_id == session_id)
            .where(Message.id >= last_user_id)
        )
        await self._db.flush()
        return result.rowcount or 0

    async def clear_session(self, session_id: str) -> None:
        stmt = delete(Message).where(Message.session_id == session_id)
        await self._db.execute(stmt)
        await self._db.flush()
