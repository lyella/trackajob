from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Resume, ResumeVersion, User
from app.schemas import ResumeContent, ResumeCreate, ResumeOut, ResumeVersionMeta

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _versions(db: Session, resume_id: int) -> list[ResumeVersion]:
    return list(
        db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.version)
        ).scalars()
    )


def _resume_out(db: Session, resume: Resume) -> ResumeOut:
    versions = _versions(db, resume.id)
    return ResumeOut(
        id=resume.id,
        name=resume.name,
        latest_version=versions[-1].version if versions else 0,
        versions=[ResumeVersionMeta(version=v.version, created_at=v.created_at.isoformat()) for v in versions],
    )


def _owned_resume(db: Session, user: User, resume_id: int) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="resume not found")
    return resume


@router.post("", status_code=201)
def create_resume(
    payload: ResumeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeOut:
    resume = Resume(user_id=user.id, name=payload.name)
    db.add(resume)
    db.flush()  # get the id before writing version 1
    db.add(
        ResumeVersion(
            resume_id=resume.id,
            version=1,
            content=payload.content.model_dump_json(exclude_none=True),
        )
    )
    db.commit()
    return _resume_out(db, resume)


@router.get("")
def list_resumes(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ResumeOut]:
    resumes = list(
        db.execute(select(Resume).where(Resume.user_id == user.id)).scalars()
    )
    return [_resume_out(db, r) for r in resumes]


@router.get("/{resume_id}")
def get_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    resume = _owned_resume(db, user, resume_id)
    versions = _versions(db, resume.id)
    if not versions:
        raise HTTPException(status_code=404, detail="resume has no versions")
    return {
        "id": resume.id,
        "name": resume.name,
        "version": versions[-1].version,
        "content": versions[-1].content,
    }


@router.get("/{resume_id}/versions")
def list_versions(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ResumeVersionMeta]:
    resume = _owned_resume(db, user, resume_id)
    return [
        ResumeVersionMeta(version=v.version, created_at=v.created_at.isoformat())
        for v in _versions(db, resume.id)
    ]


@router.post("/{resume_id}/versions", status_code=201)
def append_version(
    resume_id: int,
    payload: ResumeContent,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeVersionMeta:
    """Adds a new snapshot. This is the endpoint the M6 tailoring flow will
    call; ordering here defines what the diff view and revert use."""
    resume = _owned_resume(db, user, resume_id)
    versions = _versions(db, resume.id)
    next_version = (versions[-1].version + 1) if versions else 1
    row = ResumeVersion(
        resume_id=resume.id,
        version=next_version,
        content=payload.model_dump_json(exclude_none=True),
    )
    db.add(row)
    db.commit()
    return ResumeVersionMeta(version=next_version, created_at=row.created_at.isoformat())
