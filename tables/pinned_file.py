from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tables.base import Base


class PinnedFile(Base):
    __tablename__ = 'pinned_files'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'))
    file: Mapped[str]
    type_of_inject: Mapped[str]
    type_of_content: Mapped[str]

    sessions: Mapped['Session'] = relationship(back_populates='pinned_files')

    __table_args__ = (
        Index(
            'ix_pinned_files_session_inject_content',
            'session_id',
            'type_of_inject',
            'type_of_content',
        ),
        Index('ix_pinned_files_session_file', 'session_id', 'file', unique=True),
    )
