from pydantic import BaseModel
from typing import Optional


class SessionGet(BaseModel):
    id: str
    model_alias: str
    title: str

class SessionPut(BaseModel):
    title: str | None = None
    model_alias: str | None = None

class SessionCreate(BaseModel):
    id: str
    title: Optional[str] = None
    model_alias: Optional[str] = None

class ChatStart(BaseModel):
    query: str

