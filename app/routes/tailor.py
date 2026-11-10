"""M6 tailoring endpoints: tailor against a saved job, revert to an old
version, and the per-user usage meter."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import tailoring
from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import JobPost, Resume, ResumeVersion, TailorUsage, User, utcnow
from app.schemas import ResumeContent
from app.tailoring import TailorError

router = APIRouter(tags=["tailor"])


class TailorRequest(BaseModel):
    job_id: int
    prompt: str = ""


class RevertRequest(BaseModel):
    version: int


class TailorResponse(BaseModel):
    resume_id: int
    base_version: int
    base_content: ResumeContent
    version: int
    version_id: int
    content: ResumeContent
    warnings: list[str]
    notes: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _latest(db: Session, user: User, resume_id: int) -> ResumeVersion:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="resume not found")
    row = (
        db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version.desc())
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="resume has no versions")
    return row


@router.post("/api/resumes/{resume_id}/tailor")
def tailor_resume(
    resume_id: int,
    payload: TailorRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TailorResponse:
    settings = get_settings()
    if not settings.llm_api_key:
        raise HTTPException(status_code=503, detail="tailoring is not configured (no LLM key)")

    base_row = _latest(db, user, resume_id)
    base_content = ResumeContent.model_validate_json(base_row.content)

    job = db.get(JobPost, payload.job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    if not (job.description or "").strip():
        raise HTTPException(status_code=422, detail="job has no description to tailor against")

    try:
        result = tailoring.tailor(base_content.model_dump(), job.description, payload.prompt)
    except TailorError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))

    # Validate and fall back to the base content when the model broke shape.
    try:
        new_content = ResumeContent.model_validate(result.content)
    except Exception:
        raise HTTPException(status_code=502, detail="model returned an unusable resume; nothing was saved")

    next_version = base_row.version + 1
    row = ResumeVersion(
        resume_id=resume_id,
        version=next_version,
        content=new_content.model_dump_json(exclude_none=True),
    )
    db.add(row)
    db.flush()

    cost = (
        result.tokens_in / 1e6 * settings.llm_price_in
        + result.tokens_out / 1e6 * settings.llm_price_out
    )
    db.add(
        TailorUsage(
            user_id=user.id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_micro_usd=int(cost * 1_000_000),
        )
    )
    db.commit()

    return TailorResponse(
        resume_id=resume_id,
        base_version=base_row.version,
        base_content=base_content,
        version=next_version,
        version_id=row.id,
        content=new_content,
        warnings=result.warnings,
        notes=result.notes,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=round(cost, 6),
    )


@router.post("/api/resumes/{resume_id}/revert")
def revert_resume(
    resume_id: int,
    payload: RevertRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Revert copies an old snapshot into a NEW version; history is never
    rewritten or deleted, which is what makes diff-and-revert safe."""
    latest = _latest(db, user, resume_id)
    target = (
        db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id, ResumeVersion.version == payload.version)
        )
        .scalars()
        .one_or_none()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="version not found")
    if target.version == latest.version:
        raise HTTPException(status_code=409, detail="that version is already the latest")
    new_row = ResumeVersion(
        resume_id=resume_id,
        version=latest.version + 1,
        content=target.content,
        created_at=utcnow(),
    )
    db.add(new_row)
    db.commit()
    return {"version": new_row.version, "reverted_from": payload.version}


@router.get("/api/tailor/usage")
def usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        select(
            func.count(TailorUsage.id),
            func.coalesce(func.sum(TailorUsage.tokens_in), 0),
            func.coalesce(func.sum(TailorUsage.tokens_out), 0),
            func.coalesce(func.sum(TailorUsage.cost_micro_usd), 0),
        ).where(TailorUsage.user_id == user.id)
    ).one()
    return {
        "calls": row[0],
        "tokens_in": row[1],
        "tokens_out": row[2],
        "cost_usd": row[3] / 1_000_000,
    }
