from sqlalchemy.orm import Mapped, mapped_column, relationship

from tables.base import Base


class Session(Base):
    __tablename__ = 'sessions'

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    model_alias: Mapped[str]

    pinned_files: Mapped[list['PinnedFile']] = relationship(
        back_populates='sessions',
        cascade='all, delete-orphan',
    )
    messages: Mapped[list['Message']] = relationship(
        back_populates='sessions',
        cascade='all, delete-orphan',
    )
