from fastapi import APIRouter, HTTPException, Request
from database import SessionDep
from schemas import *
from tables import Session, Message, PinnedFile
from config import ConfigDep
from starlette.background import BackgroundTask
from sse_starlette import EventSourceResponse
from openai.types.responses import ResponseTextDeltaEvent
from sqlalchemy import select

router = APIRouter(prefix="/chat")


@router.post("/{session_id}/start")
async def start_chat(session_id: str, payload: ChatStart, request: Request, db: SessionDep, config: ConfigDep):    
    res = request.app.state.agent.start(session_id, [{'role': 'user', 'content': payload.query}])

    async def event_generator():
        async for e in res.stream_events():
            if e.type == "raw_response_event":
                if isinstance(e.data, ResponseTextDeltaEvent):
                    yield {"event": "delta", "data": e.data.delta}
            elif e.type == "run_item_stream_event":
                if e.name == "tool_called": 
                    yield {"event": "tool_called", "data": getattr(e.item.raw_item, "name", "Unknown Tool")}
                elif e.name == "tool_output":
                    yield {"event": "tool_output", "data": str(e.item.output)}
        yield

    return EventSourceResponse(
        event_generator(),
    )



@router.post("/{session_id}/stop")
async def start_chat(session_id: str, request: Request, db: SessionDep, config: ConfigDep):    
    res = await request.app.state.agent.stop(session_id)
    return {"status": "stopped"} 

@router.get("/{session_id}/")
async def get_chat(session_id: str, db: SessionDep):
    stmt = (
        select(Message.payload)
        .where(Message.session_id == session_id)
        .order_by(Message.id)
    )
    db_res = await db.execute(statement=stmt)
    messages = db_res.scalars().all() 
    return {'messages': messages}

