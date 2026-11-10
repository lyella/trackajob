"""Download endpoints for the latest resume version, both formats."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.exporters import docx_bytes, pdf_bytes
from app.models import Resume, ResumeVersion, User
from app.schemas import ResumeContent

router = APIRouter(prefix="/api/resumes", tags=["export"])

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _latest_content(db: Session, user: User, resume_id: int) -> tuple[str, ResumeContent]:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="resume not found")
    row = db.execute(
        select(ResumeVersion)
        .where(ResumeVersion.resume_id == resume_id)
        .order_by(ResumeVersion.version.desc())
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="resume has no versions")
    return resume.name, ResumeContent.model_validate_json(row.content)


def _disposition(name: str, ext: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " .-" else "_" for ch in name) or "resume"
    return f"attachment; filename=\"{safe.strip()}.{ext}\""


@router.get("/{resume_id}/export/pdf")
def export_pdf(
    resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    name, content = _latest_content(db, user, resume_id)
    return Response(
        pdf_bytes(content),
        media_type="application/pdf",
        headers={"Content-Disposition": _disposition(name, "pdf")},
    )


@router.get("/{resume_id}/export/docx")
def export_docx(
    resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    name, content = _latest_content(db, user, resume_id)
    return Response(
        docx_bytes(content),
        media_type=_DOCX_TYPE,
        headers={"Content-Disposition": _disposition(name, "docx")},
    )
