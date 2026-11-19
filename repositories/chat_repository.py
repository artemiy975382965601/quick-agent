from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tables import Message


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_messages(
        self,
        session_id: str,
        limit: int,
        before_id: int | None = None,
    ) -> tuple[list[Message], bool]:
        stmt = select(Message).where(Message.session_id == session_id)

        if before_id is not None:
            stmt = stmt.where(Message.id < before_id)

        stmt = stmt.order_by(Message.id.desc()).limit(limit + 1)
        rows = (await self.db.scalars(stmt)).all()

        has_more = len(rows) > limit
        return rows[:limit], has_more

    async def clear_messages(self, session_id: str) -> None:
        stmt = delete(Message).where(Message.session_id == session_id)
        await self.db.execute(stmt)
        await self.db.flush()
