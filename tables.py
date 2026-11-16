from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.mysql import JSON


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    model_alias: Mapped[str]

    pinned_files: Mapped[list['PinnedFile']] = relationship(back_populates='sessions', cascade='all, delete-orphan')
    messages: Mapped[list['Message']] = relationship(back_populates='sessions', cascade='all, delete-orphan')

class PinnedFile(Base):
    __tablename__ = 'pinned_files'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'))
    file: Mapped[str]
    type_of_inject: Mapped[str]
    sessions: Mapped['Session'] = relationship(back_populates='pinned_files')
    

class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'))
    payload: Mapped[dict] = mapped_column(JSON)

    sessions: Mapped['Session'] = relationship(back_populates='messages')
