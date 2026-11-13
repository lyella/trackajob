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


def _content(
    db: Session, user: User, resume_id: int, version: int | None = None
) -> tuple[str, ResumeContent]:
    """Latest snapshot by default; a specific version when asked, so the
    version history can re-download exactly what was sent to an employer."""
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="resume not found")
    query = select(ResumeVersion).where(ResumeVersion.resume_id == resume_id)
    if version is not None:
        query = query.where(ResumeVersion.version == version)
    row = db.execute(query.order_by(ResumeVersion.version.desc())).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="version not found")
    return resume.name, ResumeContent.model_validate_json(row.content)


def _disposition(name: str, ext: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " .-" else "_" for ch in name) or "resume"
    return f"attachment; filename=\"{safe.strip()}.{ext}\""


@router.get("/{resume_id}/export/pdf")
def export_pdf(
    resume_id: int,
    version: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    name, content = _content(db, user, resume_id, version)
    return Response(
        pdf_bytes(content),
        media_type="application/pdf",
        headers={"Content-Disposition": _disposition(name, "pdf")},
    )


@router.get("/{resume_id}/export/docx")
def export_docx(
    resume_id: int,
    version: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    name, content = _content(db, user, resume_id, version)
    return Response(
        docx_bytes(content),
        media_type=_DOCX_TYPE,
        headers={"Content-Disposition": _disposition(name, "docx")},
    )
