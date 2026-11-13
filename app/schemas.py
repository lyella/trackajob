"""Request/response schemas. The resume content schema mirrors the one the
tailoring CLI uses, so the same JSON shape flows through the whole system."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # Cloudflare Turnstile token from the widget. Optional at the schema
    # level so the API returns a clear captcha error rather than a generic
    # validation error when it is missing.
    captcha_token: str | None = Field(default=None, max_length=4096)


class LoginIn(BaseModel):
    """Deliberately no password length rule: login must accept whatever a
    registered account has, and return 401, not a validation 422."""
    email: EmailStr
    password: str = Field(max_length=128)
    captcha_token: str | None = Field(default=None, max_length=4096)


class ForgotPasswordIn(BaseModel):
    email: EmailStr
    captcha_token: str | None = Field(default=None, max_length=4096)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class ResendVerificationIn(BaseModel):
    captcha_token: str | None = Field(default=None, max_length=4096)


class UserOut(BaseModel):
    id: int
    email: str
    email_verified: bool = True


class LinkEntry(BaseModel):
    label: str
    url: str


class ExperienceEntry(BaseModel):
    company: str
    role: str
    start: str
    end: str | None = None
    bullets: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    school: str
    degree: str
    year: str | None = None


class ProjectEntry(BaseModel):
    name: str
    description: str
    url: str | None = None


class ResumeContent(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[LinkEntry] = Field(default_factory=list)
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)


class ResumeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    content: ResumeContent


class ResumeRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ResumeVersionMeta(BaseModel):
    version: int
    created_at: str


class ResumeOut(BaseModel):
    id: int
    name: str
    latest_version: int
    versions: list[ResumeVersionMeta] = Field(default_factory=list)


# Job tracker statuses, from PRD FR-7. Typo'd or invalid statuses are
# rejected at the schema layer rather than corrected.
JOB_STATUSES = Literal["interested", "applied", "interview", "offer", "rejected", "closed"]


class JobStatusEntry(BaseModel):
    status: str
    at: str


class JobCreate(BaseModel):
    # Strict: a typo like "statu" must not be silently dropped.
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=150)
    source: str = Field(default="", max_length=80)
    url: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=50000)
    notes: str = Field(default="", max_length=10000)
    # Optional opening status, so a job applied to an hour ago is not
    # recorded as "interested" first. Defaults to interested.
    status: JOB_STATUSES = "interested"


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=150)
    source: str | None = Field(default=None, max_length=80)
    url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=50000)
    status: JOB_STATUSES | None = None
    notes: str | None = Field(default=None, max_length=10000)
    # Which resume version was sent for this application.
    resume_version_id: int | None = None


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    source: str
    url: str
    description: str
    status: str
    notes: str
    status_history: list[JobStatusEntry] = Field(default_factory=list)
    resume_version_id: int | None = None
    sent_resume: str | None = None
    created_at: str
    updated_at: str
