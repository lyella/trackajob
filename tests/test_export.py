"""Export tests: both formats download, are byte-valid, and their text
extracts in reading order matching the resume structure. This is the
M4 acceptance test: extracted text must match the resume data, something
no public ATS checker can promise."""
import re
import uuid
import zlib

from docx import Document
from io import BytesIO

from tests.conftest import signup

CONTENT = {
    "name": "Zyx Omega",
    "email": "zyx@example.com",
    "phone": "+55 000",
    "location": "Testville",
    "links": [],
    "summary": "SUMMARYMARK developer with deep experience.",
    "skills": ["Python", "Kubernetes"],
    "experience": [
        {
            "company": "Acme Corp",
            "role": "Backend Developer",
            "start": "2022-01",
            "end": None,
            "bullets": ["BulletMark built resilient services"],
        }
    ],
    "education": [],
    "projects": [],
}


def _pdf_text(data: bytes) -> str:
    m = re.search(rb"stream\r?\n(.*?)endstream", data, re.S)
    raw = zlib.decompress(m.group(1))
    chunks = re.findall(rb"\((.*?)\) (?:Tj|TJ)", raw)
    return "\n".join(c.decode("latin-1") for c in chunks)


def _docx_texts(data: bytes) -> list[str]:
    doc = Document(BytesIO(data))
    return [p.text for p in doc.paragraphs]


def _make_resume(client):
    r = client.post("/api/resumes", json={"name": "export-check", "content": CONTENT})
    assert r.status_code == 201
    return r.json()["id"]


def test_pdf_export_valid_and_in_reading_order(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    r = client.get(f"/api/resumes/{rid}/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF-")

    text = _pdf_text(r.content)
    name = text.index("Zyx Omega")
    summary = text.index("SUMMARYMARK")
    bullet = text.index("BulletMark")
    assert name < summary < bullet, f"reading order broken: {name}, {summary}, {bullet}"
    assert "Acme Corp - Backend Developer" in text
    assert "SKILLS" in text.upper()


def test_docx_export_valid_and_in_reading_order(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    r = client.get(f"/api/resumes/{rid}/export/docx")
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"PK"), "docx is a zip container"

    texts = _docx_texts(r.content)
    joined = "\n".join(texts)
    name_i = joined.index("Zyx Omega")
    summary_i = joined.index("SUMMARYMARK")
    bullet_i = joined.index("BulletMark built resilient services")
    assert name_i < summary_i < bullet_i
    assert "SKILLS" in joined
    # The bullet must carry the real Word list style, not just a dash.
    doc = Document(BytesIO(r.content))
    bullet_para = next(p for p in doc.paragraphs if "BulletMark" in p.text)
    assert bullet_para.style.name == "List Bullet"


def test_export_requires_auth(client):
    assert client.get("/api/resumes/1/export/pdf").status_code == 401
    assert client.get("/api/resumes/1/export/docx").status_code == 401


def test_export_of_foreign_resume_is_404(client, new_email):
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    signup(client, new_email)
    rid = _make_resume(client)

    client.cookies.clear()
    signup(client, other)
    assert client.get(f"/api/resumes/{rid}/export/pdf").status_code == 404
    assert client.get(f"/api/resumes/{rid}/export/docx").status_code == 404
