"""Import a job post from a URL, and export application statistics."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import scraper
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.stats import compute_stats, stats_to_csv

router = APIRouter(prefix="/api", tags=["import"])


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@router.post("/jobs/scrape")
def scrape_job(
    payload: ScrapeRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Fetch and parse a job post. Never creates a job: the client shows the
    fields for review first, so a bad scrape cannot pollute the tracker.

    Failures return a reason the UI turns into a specific next step, because
    "could not import" alone leaves the user stuck.
    """
    try:
        job = scraper.scrape(payload.url)
    except scraper.ScrapeError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail={"reason": exc.reason, "message": exc.message},
        )
    return job.as_dict()


@router.get("/stats")
def get_stats(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return compute_stats(db, user)


@router.get("/stats/export.csv")
def export_stats_csv(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    stats = compute_stats(db, user)
    body = stats_to_csv(stats)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="trackajob-statistics-{stamp}.csv"'
        },
    )
