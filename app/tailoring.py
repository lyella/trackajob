"""Server-side tailoring. Ported from the M1 CLI spike with the same
anti-fabrication rules: hardened system prompt, lexical support checks,
job-post vocabulary graft detection, and deterministic removal of any
bullet with no support in the base resume. Structured JSON in and out;
the model never touches layout (ADR-0003)."""

import json
import re
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

SYSTEM_PROMPT = """You tailor resumes for job applications.

You receive a base resume as JSON, a job description, and an instruction from
the user. You return the tailored resume as JSON with the same schema and
field names. Never add, remove, or rename fields.

Hard rules:
- Never invent employers, job titles, dates, degrees, certifications, achievements,
  technologies, or numbers. Rewrite and reorder what is there; fabricate nothing.
- Every bullet in the output must be a rephrased version of a bullet that exists
  in the base resume. Do not delete an existing achievement to make room for a
  better-sounding one, and do not add bullets whose substance is not in the base
  resume. If a job requirement has no support in the resume, leave it out: it is
  fine for the tailored resume to not mention it.
- Do not import vocabulary from the job description into a bullet unless the
  base resume already uses those words. Rephrasing selects and orders words the
  base resume contains; it never re-scopes what the work was about. A bullet
  about serving API traffic must not become a bullet about processing payments
  just because the job post mentions payments.
- Keep the wording plain and factual. No first person pronouns.
- Keep every bullet from the base resume, rephrased where useful. Merge bullets
  only when they describe the same work. Cut a bullet only when the user's
  instruction explicitly asks for a shorter or one-page resume.
- Shift emphasis toward what the job description asks for, using only real
  content from the resume.
- Honor the user's instruction (for example "emphasize project work" or
  "shorten to one page"). If an instruction would require lying or inventing
  facts, ignore it and note that in "tailor_notes".
- "summary" is at most four sentences, aligned with the job description.
- Output must be a single JSON object, no markdown fences, no commentary
  outside the JSON. The schema also has an optional field "tailor_notes" for
  a short message to the user about what you changed or refused to change.

Schema:
{
  "name": str, "email": str, "phone": str, "location": str,
  "links": [{"label": str, "url": str}],
  "summary": str,
  "skills": [str],
  "experience": [{"company": str, "role": str, "start": str, "end": str,
                  "bullets": [str]}],
  "education": [{"school": str, "degree": str, "year": str}],
  "projects": [{"name": str, "description": str, "url": str}]
}
"""


class TailorError(Exception):
    """LLM or validation failure with a client-safe message."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class TailorResult:
    content: dict
    warnings: list[str] = field(default_factory=list)
    notes: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-zA-Z]{4,}", (s or "").lower())}


def _numbers(s: str) -> set:
    return set(re.findall(r"\d+", s or ""))


def _token_support(new_bullet: str, base_bullets: list) -> bool:
    for base in base_bullets:
        if _numbers(new_bullet) & _numbers(base):
            return True
        if len(_words(new_bullet) & _words(base)) >= 2:
            return True
    return False


def _base_vocabulary(base_resume: dict) -> set:
    words = set(_words(base_resume.get("summary", "")))
    for s in base_resume.get("skills", []):
        words |= _words(s)
    for e in base_resume.get("experience", []):
        words |= _words(e.get("role", ""))
        for b in e.get("bullets", []):
            words |= _words(b)
    return words


def call_chat_completion(resume: dict, job_text: str, prompt: str) -> tuple[dict, dict]:
    """The injectable LLM boundary: tests stub this, production hits the API."""
    settings = get_settings()
    user_message = (
        "BASE RESUME:\n"
        + json.dumps(resume, ensure_ascii=False)
        + "\n\nJOB DESCRIPTION:\n"
        + job_text.strip()
        + "\n\nINSTRUCTION:\n"
        + (prompt.strip() if prompt.strip() else "Tailor this resume for the job above.")
    )
    response = httpx.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        },
        timeout=50,
    )
    data = response.json()
    if response.status_code != 200:
        raise TailorError(f"LLM API error {response.status_code}: {str(data)[:200]}")
    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TailorError("model did not return valid JSON") from exc
    return parsed, data.get("usage", {})


def tailor(resume: dict, job_text: str, prompt: str) -> TailorResult:
    full, usage = call_chat_completion(resume, job_text, prompt)
    notes = full.get("tailor_notes", "")

    required = ["name", "summary", "skills", "experience", "education", "projects"]
    missing = [f for f in required if f not in full]
    if missing:
        raise TailorError(f"model output is missing fields: {', '.join(missing)}")

    warnings: list[str] = []
    base_vocab = _base_vocabulary(resume)
    job_words = _words(job_text)

    for base_job, new_job in zip(resume.get("experience", []), full.get("experience", [])):
        base_bullets = base_job.get("bullets", [])
        kept = []
        for b in new_job.get("bullets", []):
            if not _token_support(b, base_bullets):
                warnings.append(f"Removed potentially fabricated bullet: {b}")
                continue
            grafted = {w for w in _words(b) if w in job_words and w not in base_vocab}
            if grafted:
                warnings.append(
                    f"Bullet uses job-post vocabulary the resume never used "
                    f"({', '.join(sorted(grafted))}): {b}"
                )
            kept.append(b)
        if base_bullets and not kept:
            kept = list(base_bullets)
            warnings.append("All bullets for an entry were unsupported; base bullets kept.")
        new_job["bullets"] = kept
        if len(kept) < len(base_bullets):
            warnings.append(
                f"{base_job.get('company', '?')}: fewer bullets than the base "
                f"({len(base_bullets)} -> {len(kept)}); verify nothing was lost."
            )

    return TailorResult(
        content=full,
        warnings=warnings,
        notes=notes,
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
    )
