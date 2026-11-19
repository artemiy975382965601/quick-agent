from fastapi import APIRouter

from schemas import StatusResponse

router = APIRouter(prefix='/health')


@router.get('/', response_model=StatusResponse)
async def health() -> StatusResponse:
    return StatusResponse(status='ok')
