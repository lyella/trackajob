"""Render resume content to download files.

Both formats must survive an ATS parse: single column, no tables, no text
boxes, no images, standard section headings, and real list styles in DOCX.
The test that matters is extracting the text back out with an independent
parser and comparing it to the resume data (tests/test_export.py).

PDF: fpdf2 drawing directly from resume data. Text uses an embedded subset
of Arial (app/fonts/ATS-Sans.ttf) rather than the PDF core fonts, because
core fonts are latin-1 only: they silently destroy "€", "—", "’" and any
accented name, which is exactly the text an ATS reads. The subset carries
Latin-1, Latin Extended-A, and common punctuation, so it costs ~22 KB and
needs no system font at runtime (Vercel has none).

DOCX: python-docx with real Word styles (Title, Heading 1/2, List Bullet)
so parsers get structure, not just text.
"""

from io import BytesIO
from pathlib import Path

from docx import Document
from fpdf import FPDF

from app.schemas import ResumeContent

FONT_PATH = Path(__file__).resolve().parent / "fonts" / "ATS-Sans.ttf"
FONT_FAMILY = "ATS"

# Separate from a dash: ATS keyword matchers treat "-" inside a word
# differently from a date range, and "Company - Role" reads as one token.
DASH = " – "
BULLET = "•"


def _pdf_safe(s: str) -> str:
    """Last-resort guard for glyphs outside the embedded subset. The subset
    covers Latin-1 and Latin Extended-A; anything rarer degrades to "?"
    rather than raising and failing the whole export."""
    if not s:
        return ""
    safe = []
    for ch in s:
        try:
            ch.encode("cp1252")
            safe.append(ch)
        except UnicodeEncodeError:
            # Latin Extended-A letters (e.g. ł, ő) are in the subset but not
            # cp1252, so keep them; only genuinely unsupported glyphs degrade.
            if 0x100 <= ord(ch) <= 0x17F or ch in "–—‘’“”•…€™·":
                safe.append(ch)
            else:
                safe.append("?")
    return "".join(safe)


def pdf_bytes(content: ResumeContent) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # Embed once per document; fpdf2 caches the parsed font on the instance.
    pdf.add_font(FONT_FAMILY, "", str(FONT_PATH))
    pdf.add_font(FONT_FAMILY, "B", str(FONT_PATH))
    pdf.add_font(FONT_FAMILY, "I", str(FONT_PATH))

    def line(text: str, size: int, style: str = "", height: float = 5.5) -> None:
        pdf.set_font(FONT_FAMILY, style, size)
        pdf.multi_cell(0, height, _pdf_safe(text), new_x="LMARGIN", new_y="NEXT")

    line(content.name or "Resume", 18, "B", 9)
    contact = " | ".join(x for x in [content.email, content.phone, content.location] if x)
    if contact:
        line(contact, 10)
    for link in content.links:
        if link.label and link.url:
            line(f"{link.label}: {link.url}", 10)
        elif link.label or link.url:
            line(link.label or link.url, 10)

    def section(title: str) -> None:
        pdf.ln(3)
        line(title.upper(), 11.5, "B", 7)
        pdf.set_draw_color(90, 90, 90)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)

    if content.summary and content.summary.strip():
        section("Summary")
        line(content.summary, 10)
    if content.skills:
        section("Skills")
        line(", ".join(content.skills), 10)
    if content.experience:
        section("Experience")
        for job in content.experience:
            heading = DASH.join(x for x in [job.company, job.role] if x)
            if heading:
                line(heading, 10.5, "B", 6)
            dates = f"{job.start or 'Start'}{DASH}{job.end or 'Present'}"
            line(dates, 9.5, "I", 5)
            for bullet in job.bullets:
                if bullet.strip():
                    # Indent the bullet text so a parser reads it as a list
                    # item under this role, not as a new section.
                    pdf.set_x(pdf.l_margin + 3)
                    pdf.set_font(FONT_FAMILY, "", 10)
                    pdf.multi_cell(
                        pdf.w - pdf.l_margin - pdf.r_margin - 3,
                        5.5,
                        _pdf_safe(f"{BULLET} {bullet}"),
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )
            pdf.ln(1.5)
    if content.education:
        section("Education")
        for ed in content.education:
            text = DASH.join(x for x in [ed.school, ed.degree] if x)
            if ed.year:
                text = f"{text} ({ed.year})" if text else ed.year
            line(text, 10)
    if content.projects:
        section("Projects")
        for pr in content.projects:
            text = f"{pr.name}: {pr.description}" if pr.description else pr.name
            line(text, 10)
            if pr.url:
                line(pr.url, 9.5)

    return bytes(pdf.output())


def docx_bytes(content: ResumeContent) -> bytes:
    doc = Document()
    # Core properties are read by some parsers and recruiters' file lists.
    doc.core_properties.title = f"{content.name} — Resume" if content.name else "Resume"
    doc.core_properties.author = content.name or ""

    doc.add_heading(content.name or "Resume", level=0)
    contact = " | ".join(x for x in [content.email, content.phone, content.location] if x)
    if contact:
        doc.add_paragraph(contact)
    for link in content.links:
        if link.label and link.url:
            doc.add_paragraph(f"{link.label}: {link.url}")
        elif link.label or link.url:
            doc.add_paragraph(link.label or link.url)

    if content.summary and content.summary.strip():
        doc.add_heading("SUMMARY", level=1)
        doc.add_paragraph(content.summary)
    if content.skills:
        doc.add_heading("SKILLS", level=1)
        doc.add_paragraph(", ".join(content.skills))
    if content.experience:
        doc.add_heading("EXPERIENCE", level=1)
        for job in content.experience:
            heading = DASH.join(x for x in [job.company, job.role] if x)
            if heading:
                doc.add_heading(heading, level=2)
            doc.add_paragraph(f"{job.start or 'Start'}{DASH}{job.end or 'Present'}")
            for bullet in job.bullets:
                if bullet.strip():
                    doc.add_paragraph(bullet, style="List Bullet")
    if content.education:
        doc.add_heading("EDUCATION", level=1)
        for ed in content.education:
            text = DASH.join(x for x in [ed.school, ed.degree] if x)
            if ed.year:
                text = f"{text} ({ed.year})" if text else ed.year
            doc.add_paragraph(text)
    if content.projects:
        doc.add_heading("PROJECTS", level=1)
        for pr in content.projects:
            doc.add_paragraph(
                f"{pr.name}: {pr.description}" if pr.description else pr.name
            )
            if pr.url:
                doc.add_paragraph(pr.url)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
