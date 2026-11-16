from fastapi import APIRouter, HTTPException, Request
from database import SessionDep
from schemas import *
from tables import Session
from config import ConfigDep
from sqlalchemy import select

router = APIRouter(prefix="/sessions")

@router.get("/list/", response_model=list[SessionGet])
async def get_session(db: SessionDep):
    stmt = select(Session)
    res = (await db.scalars(stmt)).all()
    if res is None:
        raise HTTPException(status_code=404, detail="sessions not found")
    return res

@router.get("/{session_id}/", response_model=SessionGet)
async def get_session(session_id: str, db: SessionDep):
    res = await db.get(Session, session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="session not found")
    return res



@router.post("/create/")
async def create_session(payload: SessionCreate, db: SessionDep, config: ConfigDep):
    raw_model = payload.model_dump()
    
    if raw_model['model_alias'] is None:
        raw_model['model_alias'] = config['default']['model_alias']
    if raw_model['title'] is None:
        raw_model['title'] = config['default']['title']

    existing = await db.get(Session, payload.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Session with this id already exists")
 
    db.add(Session (**raw_model))
    await db.commit()
    return {"success": True}

@router.put("/{session_id}/")
async def put_session(session_id: str, payload: SessionPut, db: SessionDep):
    res = await db.get(Session, session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="session not found")
    if payload.title is not None:
        res.title = payload.title
    if payload.model_alias is not None:
        res.model_alias = payload.model_alias
    await db.commit()
    return {"success": True}

@router.delete("/{session_id}/")
async def delete_session(session_id: str, db: SessionDep, request: Request):
    res = await db.get(Session, session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="session not found")
    await db.delete(res)
    request.app.state.agent.delete(session_id)
    await db.commit()
    return {"success": True}
