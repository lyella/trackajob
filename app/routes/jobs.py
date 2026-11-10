"""Job tracker: CRUD over saved job posts with a status workflow. Every
status change appends to the history; the plan asks for timestamps on
status changes, and the JSON history doubles as a change log for the UI."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import JobPost, User, utcnow
from app.schemas import JobCreate, JobOut, JobStatusEntry, JobUpdate

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job: JobPost) -> JobOut:
    return JobOut(
        id=job.id,
        title=job.title,
        company=job.company,
        source=job.source,
        url=job.url,
        description=job.description,
        status=job.status,
        notes=job.notes,
        status_history=[JobStatusEntry(**e) for e in json.loads(job.status_history)],
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _owned_job(db: Session, user: User, job_id: int) -> JobPost:
    job = db.get(JobPost, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("", status_code=201)
def create_job(
    payload: JobCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    job = JobPost(
        user_id=user.id,
        title=payload.title,
        company=payload.company,
        source=payload.source,
        url=payload.url,
        description=payload.description,
        notes=payload.notes,
        status="interested",
        status_history=json.dumps([{"status": "interested", "at": utcnow().isoformat()}]),
    )
    db.add(job)
    db.commit()
    return _job_out(job)


@router.get("")
def list_jobs(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobOut]:
    query = select(JobPost).where(JobPost.user_id == user.id).order_by(
        JobPost.updated_at.desc()
    )
    if status is not None:
        query = query.where(JobPost.status == status)
    return [_job_out(j) for j in db.execute(query).scalars()]


@router.get("/{job_id}")
def get_job(
    job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> JobOut:
    return _job_out(_owned_job(db, user, job_id))


@router.patch("/{job_id}")
def update_job(
    job_id: int,
    payload: JobUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobOut:
    job = _owned_job(db, user, job_id)
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] and data["status"] != job.status:
        history = json.loads(job.status_history)
        history.append({"status": data["status"], "at": utcnow().isoformat()})
        job.status_history = json.dumps(history)
        job.status = data["status"]
    if "notes" in data and data["notes"] is not None:
        job.notes = data["notes"]
    for field in ("title", "company", "source", "url", "description"):
        if field in data and data[field] is not None:
            setattr(job, field, data[field])
    db.commit()
    return _job_out(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    job = _owned_job(db, user, job_id)
    db.delete(job)
    db.commit()
