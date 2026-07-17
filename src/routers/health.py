from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import verify_api_key
from src.database import get_db

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        # https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#getting-orm-results-from-textual-statements
        result = await db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database Unreachable")

    return {"status": "healthy", "database": "ok", "query_result": result.scalar()}
