from typing import Annotated, Any

from pydantic import Field

from schemas.base import ORMModel

MessageLimit = Annotated[int, Field(ge=1, le=200)]


class ChatStart(ORMModel):
    query: Annotated[str, Field(min_length=1, max_length=100_000)]
    client_prompt_paths: list[str] = Field(default_factory=list)


class ChatQuery(ORMModel):
    limit: MessageLimit = 50
    before_id: Annotated[int, Field(ge=1)] | None = None


class ChatMessages(ORMModel):
    messages: list[Any]
    has_more: bool
    next_cursor: int | None


class StatusResponse(ORMModel):
    status: str
