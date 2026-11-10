"""Render resume content to download files.

PDF: fpdf2, single column, core fonts, mirrors the layout the tailoring
CLI renders (the CLI copy stays separate on purpose: the Vercel function
bundle excludes cli/, and the CLI is a spike that dies in M6).

DOCX: python-docx with real Word styles (Title, Heading 1/2, List
Bullet) so parsers get structure, not just text.
"""

from io import BytesIO

from docx import Document
from fpdf import FPDF

from app.schemas import ResumeContent


def _pdf_safe(s: str) -> str:
    """Core PDF fonts are latin-1; degrade rare unsupported characters
    instead of failing the whole export."""
    return (s or "").encode("latin-1", "replace").decode("latin-1")


def pdf_bytes(content: ResumeContent) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 8, _pdf_safe(content.name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    contact = " | ".join(
        x for x in [content.email, content.phone, content.location] if x
    )
    if contact:
        pdf.cell(0, 6, _pdf_safe(contact), new_x="LMARGIN", new_y="NEXT")
    for link in content.links:
        pdf.cell(0, 6, _pdf_safe(f"{link.label}: {link.url}"), new_x="LMARGIN", new_y="NEXT")

    def section(title: str) -> None:
        pdf.ln(2)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 7, title.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(80, 80, 80)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("helvetica", "", 10)

    def multi(text: str) -> None:
        pdf.multi_cell(0, 5, _pdf_safe(text), new_x="LMARGIN", new_y="NEXT")

    if content.summary:
        section("Summary")
        multi(content.summary)
    if content.skills:
        section("Skills")
        multi(", ".join(content.skills))
    if content.experience:
        section("Experience")
        for job in content.experience:
            pdf.set_font("helvetica", "B", 11)
            pdf.cell(0, 6, _pdf_safe(f"{job.company} - {job.role}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "I", 10)
            pdf.cell(0, 5, _pdf_safe(f"{job.start} - {job.end or 'Present'}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 10)
            for bullet in job.bullets:
                pdf.multi_cell(0, 5, _pdf_safe(f"- {bullet}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
    if content.education:
        section("Education")
        for ed in content.education:
            multi(f"{ed.school} - {ed.degree} ({ed.year or ''})")
    if content.projects:
        section("Projects")
        for pr in content.projects:
            multi(f"{pr.name}: {pr.description}")

    return bytes(pdf.output())


def docx_bytes(content: ResumeContent) -> bytes:
    doc = Document()
    doc.add_heading(_pdf_safe(content.name) or "Resume", level=0)
    contact = " | ".join(x for x in [content.email, content.phone, content.location] if x)
    if contact:
        doc.add_paragraph(contact)
    for link in content.links:
        doc.add_paragraph(f"{link.label}: {link.url}")

    if content.summary:
        doc.add_heading("SUMMARY", level=1)
        doc.add_paragraph(content.summary)
    if content.skills:
        doc.add_heading("SKILLS", level=1)
        doc.add_paragraph(", ".join(content.skills))
    if content.experience:
        doc.add_heading("EXPERIENCE", level=1)
        for job in content.experience:
            doc.add_heading(f"{job.company} - {job.role}", level=2)
            doc.add_paragraph(f"{job.start} - {job.end or 'Present'}")
            for bullet in job.bullets:
                doc.add_paragraph(bullet, style="List Bullet")
    if content.education:
        doc.add_heading("EDUCATION", level=1)
        for ed in content.education:
            doc.add_paragraph(f"{ed.school} - {ed.degree} ({ed.year or ''})")
    if content.projects:
        doc.add_heading("PROJECTS", level=1)
        for pr in content.projects:
            doc.add_paragraph(f"{pr.name}: {pr.description}")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
