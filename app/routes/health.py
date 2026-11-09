from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db import get_engine

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    """Reports app and database status. Used by M0 to prove the deployed
    function actually reaches the database, not just that it boots."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unreachable: {exc}") from exc
    return {"status": "ok", "database": "ok"}
