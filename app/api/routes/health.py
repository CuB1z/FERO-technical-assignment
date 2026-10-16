from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import DbSession

router = APIRouter()


@router.get("/health")
async def health(db: DbSession) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
