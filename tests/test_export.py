"""Export tests: both formats download, are byte-valid, and their text
extracts in reading order matching the resume structure. This is the
M4 acceptance test: extracted text must match the resume data, something
no public ATS checker can promise.

Text is extracted with pypdf, an independent parser, rather than by
scraping the PDF content stream by hand: the hand-rolled version only
worked because the old exporter used latin-1 core fonts, and it would
have silently passed while the real output was unreadable.
"""
import uuid

from docx import Document
from io import BytesIO
from pypdf import PdfReader

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

# Content an ATS must read back exactly: accented names, currency, dashes,
# curly quotes. The old core-font PDF turned every one of these into "?".
UNICODE_CONTENT = {
    "name": "José Müller-Ødegård",
    "email": "jose@example.com",
    "phone": "+49 30 1234",
    "location": "Zürich, Schweiz",
    "links": [{"label": "GitHub", "url": "https://github.com/jose"}],
    "summary": "Engineer who managed a €5M budget and cut costs by 30%.",
    "skills": ["C++", "C#", "Kubernetes"],
    "experience": [
        {
            "company": "Siemens AG",
            "role": "Ingénieur",
            "start": "2020",
            "end": None,
            "bullets": ["Cut infrastructure costs by €1.2M — a 30% reduction."],
        }
    ],
    "education": [{"school": "ETH Zürich", "degree": "MSc Informatik", "year": "2019"}],
    "projects": [],
}


def _pdf_text(data: bytes) -> str:
    return "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(data)).pages)


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
    assert "Acme Corp – Backend Developer" in text
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


# ---------------------------------------------------------------------------
# ATS fidelity: the text an applicant tracking system reads back must be the
# text the user wrote. These are the checks that would have caught the
# latin-1 core-font PDF, which turned "€", "—" and accented names into "?".
# ---------------------------------------------------------------------------


def _unicode_resume(client):
    r = client.post(
        "/api/resumes", json={"name": "unicode-check", "content": UNICODE_CONTENT}
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_pdf_preserves_accented_names_and_currency(client, new_email):
    signup(client, new_email)
    rid = _unicode_resume(client)
    text = _pdf_text(client.get(f"/api/resumes/{rid}/export/pdf").content)

    assert "José Müller-Ødegård" in text, "accented name must survive the PDF"
    assert "€5M" in text, "currency symbol must survive the PDF"
    assert "€1.2M" in text
    assert "—" in text, "em dash must survive the PDF"
    assert "Zürich" in text
    assert "Zürich" in text
    assert "?" not in text.replace("C++", "").replace("C#", ""), (
        "no character should degrade to a question mark"
    )


def test_docx_preserves_accented_names_and_currency(client, new_email):
    signup(client, new_email)
    rid = _unicode_resume(client)
    joined = "\n".join(_docx_texts(client.get(f"/api/resumes/{rid}/export/docx").content))

    assert "José Müller-Ødegård" in joined
    assert "€5M" in joined
    assert "€1.2M" in joined
    assert "—" in joined
    assert "Zürich" in joined


def test_pdf_has_no_tables_or_images(client, new_email):
    """ATS parsers read text in the order it is drawn. Tables and images are
    where extraction breaks, so the PDF must contain neither."""
    signup(client, new_email)
    rid = _unicode_resume(client)
    data = client.get(f"/api/resumes/{rid}/export/pdf").content

    assert b"/Subtype /Image" not in data, "no raster images in an ATS resume"
    # A table would appear as a structure element; fpdf2 emits none, but guard
    # the intent explicitly so a future layout change trips this test.
    assert b"/S /Table" not in data


def test_docx_has_no_tables_textboxes_or_headers(client, new_email):
    signup(client, new_email)
    rid = _unicode_resume(client)
    doc = Document(BytesIO(client.get(f"/api/resumes/{rid}/export/docx").content))

    assert len(doc.tables) == 0, "tables scramble ATS extraction"
    for section in doc.sections:
        assert not "".join(p.text for p in section.header.paragraphs).strip()
        assert not "".join(p.text for p in section.footer.paragraphs).strip()

    styles = {p.style.name for p in doc.paragraphs if p.text.strip()}
    assert "Heading 1" in styles, "section headings must be real Word headings"
    assert "List Bullet" in styles, "bullets must be real Word list items"


def test_section_headings_are_standard_ats_keywords(client, new_email):
    """Parsers map sections by their heading text. Non-standard names like
    "Work History" or "Career" are routinely dropped, so assert the set."""
    signup(client, new_email)
    rid = _unicode_resume(client)
    joined = "\n".join(_docx_texts(client.get(f"/api/resumes/{rid}/export/docx").content))
    for heading in ("SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION"):
        assert heading in joined


def test_empty_sections_are_omitted(client, new_email):
    """An empty heading with nothing under it reads as a broken resume."""
    signup(client, new_email)
    content = dict(CONTENT, summary="", skills=[], education=[], projects=[])
    rid = client.post(
        "/api/resumes", json={"name": "sparse", "content": content}
    ).json()["id"]

    pdf = _pdf_text(client.get(f"/api/resumes/{rid}/export/pdf").content)
    docx = "\n".join(_docx_texts(client.get(f"/api/resumes/{rid}/export/docx").content))
    for text in (pdf, docx):
        assert "SUMMARY" not in text
        assert "SKILLS" not in text
        assert "PROJECTS" not in text
        assert "EXPERIENCE" in text, "a section with content still renders"


def test_export_of_foreign_resume_is_404(client, new_email):
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    signup(client, new_email)
    rid = _make_resume(client)

    client.cookies.clear()
    signup(client, other)
    assert client.get(f"/api/resumes/{rid}/export/pdf").status_code == 404
    assert client.get(f"/api/resumes/{rid}/export/docx").status_code == 404
