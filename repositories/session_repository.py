from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tables import Session


class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self) -> list[Session]:
        stmt = select(Session)
        return (await self.db.scalars(stmt)).all()

    async def get(self, session_id: str) -> Session | None:
        return await self.db.get(Session, session_id)

    async def exists(self, session_id: str) -> bool:
        return await self.db.get(Session, session_id) is not None

    async def create(self, session_id: str, title: str, model_alias: str) -> Session:
        session = Session(id=session_id, title=title, model_alias=model_alias)
        self.db.add(session)
        await self.db.flush()
        return session

    async def update(self, session_id: str, title: str | None = None, model_alias: str | None = None) -> Session | None:
        session = await self.db.get(Session, session_id)
        if session is None:
            return None
        if title is not None:
            session.title = title
        if model_alias is not None:
            session.model_alias = model_alias
        await self.db.flush()
        return session

    async def get_model_alias(self, session_id: str) -> str | None:
        stmt = select(Session.model_alias).where(Session.id == session_id)
        return await self.db.scalar(stmt)

    async def delete(self, session_id: str) -> bool:
        session = await self.db.get(Session, session_id)
        if session is None:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True
