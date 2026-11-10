from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])
logger = logging.getLogger("voxflow.health")


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Database health check warning: {e}")
        db_status = f"degraded: {str(e)}"

    return HealthResponse(
        status="ok",
        version="1.0.0",
        database=db_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

