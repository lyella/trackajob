"""Request/response schemas. The resume content schema mirrors the one the
tailoring CLI uses, so the same JSON shape flows through the whole system."""

from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    """Deliberately no password length rule: login must accept whatever a
    registered account has, and return 401, not a validation 422."""
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    email: str


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


class ResumeVersionMeta(BaseModel):
    version: int
    created_at: str


class ResumeOut(BaseModel):
    id: int
    name: str
    latest_version: int
    versions: list[ResumeVersionMeta] = Field(default_factory=list)
