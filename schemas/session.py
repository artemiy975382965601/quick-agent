from typing import Annotated

from pydantic import Field, model_validator

from schemas.base import ORMModel

SessionId = Annotated[str, Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')]
SessionTitle = Annotated[str, Field(min_length=1, max_length=200)]
ModelAlias = Annotated[str, Field(min_length=1, max_length=64)]


class SessionOut(ORMModel):
    id: str
    model_alias: str
    title: str


class SessionPut(ORMModel):
    title: SessionTitle | None = None
    model_alias: ModelAlias | None = None

    @model_validator(mode='after')
    def at_least_one_field(self):
        if self.title is None and self.model_alias is None:
            raise ValueError('at least one of title or model_alias must be provided')
        return self


class SessionCreate(ORMModel):
    id: SessionId
    title: SessionTitle | None = None
    model_alias: ModelAlias | None = None
