from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from tables import Message
from sqlalchemy import func, select


class DBSession:
    def __init__(self, async_session_factory: async_sessionmaker, session_id: str):
        self.async_session_factory = async_session_factory
        self.session_id = session_id

    async def get_items(self, limit=None):
        async with self.async_session_factory() as session:
            if limit is not None:
                stmt = (
                    select(Message.payload)
                    .where(Message.session_id == self.session_id)
                    .order_by(Message.id.desc())
                    .limit(limit)
                )
            else:
                stmt = (
                    select(Message.payload)
                    .where(Message.session_id == self.session_id)
                    .order_by(Message.id.desc())
                )

            db_res = await session.execute(statement=stmt)
            items = list(db_res.scalars().all())
            items.reverse()
            return items

    async def add_items(self, items):
        async with self.async_session_factory() as session:
            for i in items:
                session.add(Message(payload=i, session_id=self.session_id))
            await session.commit()

    async def pop_item(self):
        async with self.async_session_factory() as session:
            stmt = (
                delete(Message)
                .where(Message.session_id == self.session_id)
                .order_by(Message.id.desc())
                .returning(Message)
            )
            result = await session.scalar(stmt)
            return result

    async def clear_session(self):
        async with self.async_session_factory() as session:
            async with self.async_session_factory() as session:
                stmt = (
                    delete(Message)
                    .where(Message.session_id == self.session_id)
                )
                await session.execute(stmt)
                await session.commit()      