from sqlalchemy import JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tables.base import Base


class Message(Base):
    __tablename__ = 'messages'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'))
    payload: Mapped[dict] = mapped_column(JSON)

    sessions: Mapped['Session'] = relationship(back_populates='messages')

    __table_args__ = (
        Index('ix_messages_session_id_id', 'session_id', 'id'),
    )
