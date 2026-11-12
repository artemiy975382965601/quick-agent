from pydantic import BaseModel
from typing import Optional


class SessionGet(BaseModel):
    id: str
    model_alias: str
    title: str

class SessionPut(BaseModel):
    title: str | None
    model_alias: str | None

class SessionCreate(BaseModel):
    id: str
    title: str | None
    model_alias: str | None
