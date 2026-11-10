"""TrackAJob tailoring spike (M1 in PLAN.md).

Usage:
    python cli/tailor.py resume.json job.txt --out tailored [--prompt "..."]

Takes a base resume (JSON), a pasted job description (text), and an optional
prompt like "emphasize my backend work". Calls an OpenAI-compatible chat
completions API, gets a tailored resume back as JSON, validates it, prints a
change summary plus timing and cost, and writes:
    <out>.json  the tailored resume
    <out>.pdf   a rough single-column PDF rendered with fpdf2

This is the spike: its output quality is judged by eye against real job posts.
When M6 lands, this flow moves into the app behind a UI.

Environment (see .env.example; also reads .env):
    LLM_BASE_URL   default https://api.mistral.ai/v1
    LLM_API_KEY    required
    LLM_MODEL      default mistral-small-latest
    LLM_PRICE_IN   price per 1M input tokens, default 0.10
    LLM_PRICE_OUT  price per 1M output tokens, default 0.30
"""

from __future__ import annotations

import argparse
import json
import re
import os
import sys
import time
from pathlib import Path

import httpx


RESUME_FIELDS = [
    "name",
    "email",
    "phone",
    "location",
    "links",
    "summary",
    "skills",
    "experience",
    "education",
    "projects",
]

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
  "shorten to one page"). If an instruction would require lying or
  inventing facts, ignore it and note that in "tailor_notes".
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


def load_env() -> None:
    """Minimal .env loader so the spike has no config dependencies."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_settings() -> dict:
    base_url = os.environ.get("LLM_BASE_URL", "https://api.mistral.ai/v1").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("LLM_API_KEY is not set. Copy .env.example to .env and add your key.")
        sys.exit(1)
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": os.environ.get("LLM_MODEL", "mistral-small-latest"),
        "price_in": float(os.environ.get("LLM_PRICE_IN", "0.10")),
        "price_out": float(os.environ.get("LLM_PRICE_OUT", "0.30")),
    }


def call_llm(settings: dict, resume: dict, job: str, prompt: str) -> tuple[dict, dict]:
    """One chat completions call. Returns (tailored resume, usage stats)."""
    user_message = (
        "BASE RESUME:\n"
        + json.dumps(resume, ensure_ascii=False)
        + "\n\nJOB DESCRIPTION:\n"
        + job.strip()
        + "\n\nINSTRUCTION:\n"
        + (prompt.strip() if prompt else "Tailor this resume for the job above.")
    )
    started = time.perf_counter()
    response = httpx.post(
        f"{settings['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {settings['api_key']}"},
        json={
            "model": settings["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            # Some provider endpoints reject this key; drop it on retry.
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        },
        timeout=120,
    )
    elapsed = time.perf_counter() - started
    data = response.json()
    if response.status_code != 200:
        print(f"LLM API error {response.status_code} after {elapsed:.1f}s: {data}")
        sys.exit(2)
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return extract_json(content), {"elapsed": elapsed, "usage": usage}


def extract_json(content: str) -> dict:
    """Strip markdown fences if the model added them despite instructions."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)


def _token_support(new_bullet: str, base_bullets: list[str]) -> bool:
    """Heuristic check that a tailored bullet has support in the base resume:
    shares a number, or at least two significant words, with some base bullet."""
    def tokens(s: str) -> set:
        return {w for w in re.findall(r"[a-zA-Z]{4,}|\d+", s.lower())}
    def numbers(s: str) -> set:
        return {n for n in re.findall(r"\d+", s)}
    for base in base_bullets:
        if numbers(new_bullet) & numbers(base):
            return True
        if len(tokens(new_bullet) & tokens(base)) >= 2:
            return True
    return False


def _job_vocabulary_graft(new_bullets: list[str], base_bullets: list[str], job_text: str, base_resume: dict | None = None) -> list[str]:
    """Flags words that appear in a tailored bullet AND the job description but
    not anywhere in the base resume. Vocabulary the candidate never used,
    appearing only because the job post uses it, is the signature of the model
    re-scoping their experience."""
    def words(s: str) -> set:
        return {w for w in re.findall(r"[a-zA-Z]{4,}", s.lower())}
    job_words = words(job_text)
    base_words = {w for b in base_bullets for w in words(b)}
    if base_resume:
        for skill in base_resume.get("skills", []):
            base_words |= words(skill)
        for entry in base_resume.get("experience", []):
            base_words |= words(entry.get("role", ""))
        base_words |= words(base_resume.get("summary", ""))
    flagged = []
    for b in new_bullets:
        grafted = {w for w in words(b) if w in job_words and w not in base_words}
        if grafted:
            flagged.append(f"{b}  [grafted: {', '.join(sorted(grafted))}]")
    return flagged


def validate(tailored: dict, base: dict | None = None, job_text: str = "") -> list[str]:
    """Returns a list of problems; also prints warnings a tailor run should see.
    Hard failure (exception) only when the model broke the resume schema."""
    problems = []
    missing = [f for f in RESUME_FIELDS if f not in tailored]
    if missing:
        raise ValueError(f"model output is missing fields: {missing}")
    for job in tailored.get("experience", []):
        if not job.get("bullets"):
            raise ValueError(f"experience entry without bullets: {job}")
    if base:
        for base_job, new_job in zip(base.get("experience", []), tailored.get("experience", [])):
            base_bullets = base_job.get("bullets", [])
            new_bullets = new_job.get("bullets", [])
            unsupported = [b for b in new_bullets if not _token_support(b, base_bullets)]
            for b in unsupported:
                print(f"WARNING: bullet may be fabricated, no support in base resume:\n  - {b}")
                problems.append("unsupported bullet")
            for line in _job_vocabulary_graft(new_bullets, base_bullets, job_text, base_resume=base):
                print(f"WARNING: bullet uses job-post vocabulary the resume never used:\n  - {line}")
                problems.append("grafted vocabulary")
            if len(new_bullets) < len(base_bullets):
                print(f"WARNING: {base_job.get('company', '?')} dropped achievement bullets "
                      f"({len(base_bullets)} -> {len(new_bullets)}). If you did not ask for "
                      f"a shorter resume, the model cut real content.")
                problems.append("bullets dropped")
    return problems


def summary_of_changes(base: dict, tailored: dict) -> str:
    lines = []
    if base.get("summary") != tailored.get("summary"):
        lines.append("summary: rewritten")
    base_skills = set(base.get("skills", []))
    tail_skills = set(tailored.get("skills", []))
    if base_skills != tail_skills:
        lines.append(f"skills: +{sorted(tail_skills - base_skills)} -{sorted(base_skills - tail_skills)}")
    for i, (b, t) in enumerate(zip(base.get("experience", []), tailored.get("experience", []))):
        if b != t:
            lines.append(f"experience[{i}] ({t.get('company', '?')}): changed")
    if len(base.get("experience", [])) != len(tailored.get("experience", [])):
        lines.append("experience: entry count changed")
    if base.get("education") != tailored.get("education"):
        lines.append("education: changed")
    if base.get("projects") != tailored.get("projects"):
        lines.append("projects: changed")
    return "\n".join(lines) or "no changes"


def write_pdf(resume: dict, path: Path) -> None:
    """Rough single-column render. ATS-safe: plain text, one column, no tables."""
    # Imported here so the API-only part of the spike works without fpdf2.
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 8, resume["name"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    contact = " | ".join(x for x in [resume.get("email"), resume.get("phone"), resume.get("location")] if x)
    pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT")
    for link in resume.get("links", []):
        pdf.cell(0, 6, f"{link['label']}: {link['url']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def section(title: str) -> None:
        pdf.ln(2)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 7, title.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(80, 80, 80)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("helvetica", "", 10)

    if resume.get("summary"):
        section("Summary")
        pdf.multi_cell(0, 5, resume["summary"], new_x="LMARGIN", new_y="NEXT")

    if resume.get("skills"):
        section("Skills")
        pdf.multi_cell(0, 5, ", ".join(resume["skills"]), new_x="LMARGIN", new_y="NEXT")

    if resume.get("experience"):
        section("Experience")
        for job in resume["experience"]:
            pdf.set_font("helvetica", "B", 11)
            pdf.cell(0, 6, f"{job['company']} - {job['role']}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "I", 10)
            pdf.cell(0, 5, f"{job['start']} - {job.get('end', 'Present')}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 10)
            for bullet in job["bullets"]:
                # multi_cell's default leaves x at the right edge; reset to the
                # left margin so the next bullet starts at the left.
                pdf.multi_cell(0, 5, f"- {bullet}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    if resume.get("education"):
        section("Education")
        for ed in resume["education"]:
            pdf.multi_cell(0, 5, f"{ed['school']} - {ed['degree']} ({ed.get('year', '')})", new_x="LMARGIN", new_y="NEXT")

    if resume.get("projects"):
        section("Projects")
        for pr in resume["projects"]:
            pdf.multi_cell(0, 5, f"{pr['name']}: {pr['description']}", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailor a resume for a job post.")
    parser.add_argument("resume", help="path to base resume JSON")
    parser.add_argument("job", help="path to a text file with the job description")
    parser.add_argument("--prompt", default="", help="extra instruction, e.g. 'emphasize backend work'")
    parser.add_argument("--out", default="tailored", help="output filename prefix")
    args = parser.parse_args()

    load_env()
    settings = get_settings()
    resume = json.loads(Path(args.resume).read_text(encoding="utf-8"))
    job = Path(args.job).read_text(encoding="utf-8")

    print(f"Calling {settings['model']} at {settings['base_url']} ...")
    tailored, info = call_llm(settings, resume, job, args.prompt)
    raw_tailored = tailored

    try:
        problems = validate(tailored, base=resume, job_text=job)
    except ValueError as exc:
        print(f"Model returned invalid output: {exc}")
        print(json.dumps(tailored, indent=2, ensure_ascii=False))
        sys.exit(3)
    if problems:
        print("\nConsider rerunning: the model output drew scrutiny (see warnings above).")

    # Deterministic defense: strip bullets with no support in the base resume
    # from the final output. The model's unfiltered output is kept next to the
    # result so a human can review what was cut.
    removed = []
    for base_job, new_job in zip(resume.get("experience", []), tailored.get("experience", [])):
        base_bullets = base_job.get("bullets", [])
        kept = [b for b in new_job["bullets"] if _token_support(b, base_bullets)]
        for b in new_job["bullets"]:
            if b not in kept:
                removed.append(f"{base_job.get('company', '?')}: {b}")
        new_job["bullets"] = kept or list(base_bullets)  # never emit an empty entry
    if removed:
        raw_path = Path(f"{args.out}.raw.json")
        raw_path.write_text(json.dumps(raw_tailored, indent=2, ensure_ascii=False), encoding="utf-8")
        for r in removed:
            print(f"REMOVED unsupported bullet: {r}")
        print(f"Unfiltered model output kept for review: {raw_path}")

    out_json = Path(f"{args.out}.json")
    out_pdf = Path(f"{args.out}.pdf")
    out_json.write_text(json.dumps(tailored, indent=2, ensure_ascii=False), encoding="utf-8")
    write_pdf(tailored, out_pdf)

    usage = info["usage"]
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    cost = (tokens_in / 1e6) * settings["price_in"] + (tokens_out / 1e6) * settings["price_out"]
    print(f"\nCall took {info['elapsed']:.1f}s, {tokens_in} in / {tokens_out} out tokens, est. cost ${cost:.4f}")
    print("\nChanges vs base resume:")
    print(summary_of_changes(resume, tailored))
    if tailored.get("tailor_notes"):
        print(f"\nModel notes: {tailored['tailor_notes']}")
    print(f"\nWrote {out_json} and {out_pdf}")
    print("Judge the PDF by eye. If it is not good enough to send, fix the prompt, not the plan.")


if __name__ == "__main__":
    main()
