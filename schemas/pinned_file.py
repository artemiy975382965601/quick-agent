from typing import Annotated, Literal

from pydantic import Field

from schemas.base import ORMModel


class PinnedFileCreate(ORMModel):
    full_paths: Annotated[list[str], Field(min_length=1)]
    space_for_insert: Literal['system', 'user']


class PinnedFileGet(ORMModel):
    id: int
    session_id: str
    file: str
    type_of_inject: str
    type_of_content: str


class PinResult(ORMModel):
    results: list[str]


class UnpinRequest(ORMModel):
    full_paths: Annotated[list[str], Field(min_length=1)]


class UnpinResult(ORMModel):
    results: list[str]
