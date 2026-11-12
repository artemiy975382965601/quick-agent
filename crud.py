from fastapi import APIRouter, HTTPException
from core.database import SessionDep
from schemas import *
from tables import Session

router = APIRouter(prefix="/sessions")

@router.get("/{session_id}/", response_model=SessionGet)
async def get_session(session_id: str, db: SessionDep):
    res = await db.get(Session, session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="session not found")
    return res

@router.post("/create/")
async def create_session(payload: SessionCreate, db: SessionDep):
    db.add(Session (**payload.model_dump()))
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
async def delete_session(session_id: str, db: SessionDep):
    res = await db.get(Session, session_id)
    if res is None:
        raise HTTPException(status_code=404, detail="session not found")
    await db.delete(res)
    await db.commit()
    return {"success": True}
