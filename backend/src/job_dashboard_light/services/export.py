"""
1-Click Document Export Service: Clean Markdown and ReportLab Vector A4 PDF.

Features:
- Clean Markdown export with UTF-8 encoding and sanitized attachment filenames.
- Professional vector PDF generation using ReportLab:
  * A4 page size (210mm x 297mm) with 20mm margins.
  * Antigravity dark teal palette (#123c42 headings, #26383a body, #607477 muted meta, #d4e2e2 dividers).
  * Strict typographic hierarchy (DocTitle, Headings 1-3, Body, Bullet lists, Metadata).
  * XML character escaping (<, >, &) preserving ReportLab formatting tags (<b>, <i>).
  * Safe multi-page running footers with 'Page X of Y' numbering and title.
  * Special unicode and currency character support (€, £, ¥, ©, ®, ™, ±, µ, ¢).
  * Complete in-memory buffer processing (zero disk writes, zero path traversal vulnerabilities).
"""

from __future__ import annotations

import io
import re
import xml.sax.saxutils

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer


def sanitize_filename(title: str, default: str = "document") -> str:
    """Sanitize title into a safe filename without path traversal or invalid characters."""
    if not title or not isinstance(title, str):
        return default
    # Replace directory separators and path traversal sequences
    clean = title.replace("\\", "_").replace("/", "_")
    clean = re.sub(r"\.\.+", "_", clean)  # Replace .. with _
    clean = re.sub(r"[^\w\-. ]", "_", clean).strip()
    clean = re.sub(r"\s+", "_", clean)
    clean = clean.strip("._")
    return clean[:64] if clean else default


def export_markdown(
    content: str, title: str = "document"
) -> tuple[str, dict[str, str]]:
    """Export clean Markdown string with appropriate response headers."""
    clean_title = sanitize_filename(title, default="document")
    normalized_content = (content or "").replace("\r\n", "\n")
    headers = {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{clean_title}.md"',
    }
    return normalized_content, headers


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print total page count 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#607477"))
        # Subtle horizontal divider line
        self.setStrokeColor(colors.HexColor("#d4e2e2"))
        self.setLineWidth(0.5)
        self.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)

        # Footer metadata
        doc_title = getattr(self, "_doc_title", "Job Application Document")
        self.drawString(20 * mm, 11 * mm, doc_title[:45])
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(190 * mm, 11 * mm, page_str)
        self.restoreState()


def export_pdf_bytes(content: str, title: str = "document") -> bytes:
    """Generate professional vector A4 PDF bytes from Markdown text using ReportLab."""
    clean_title = sanitize_filename(title, default="document")
    display_title = (
        title.replace("_", " ").replace("-", " ").strip() or "Job Application Asset"
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title=clean_title,
        author="Job Dashboard Light",
    )

    # Styles
    sample = getSampleStyleSheet()
    base = sample["Normal"]

    style_title = ParagraphStyle(
        "DocTitle",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#123c42"),
        spaceAfter=6,
        keepWithNext=True,
    )
    style_h1 = ParagraphStyle(
        "Heading1",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#123c42"),
        spaceBefore=12,
        spaceAfter=5,
        keepWithNext=True,
    )
    style_h2 = ParagraphStyle(
        "Heading2",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#123c42"),
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True,
    )
    style_h3 = ParagraphStyle(
        "Heading3",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#26383a"),
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=True,
    )
    style_body = ParagraphStyle(
        "DocBody",
        parent=base,
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#26383a"),
        spaceAfter=4,
    )
    style_bullet = ParagraphStyle(
        "DocBullet",
        parent=base,
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#26383a"),
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3,
    )
    style_meta = ParagraphStyle(
        "DocMeta",
        parent=base,
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#607477"),
        spaceAfter=3,
        keepWithNext=True,
    )

    def format_line(raw: str) -> str:
        # Escape XML entities
        escaped = xml.sax.saxutils.escape(raw)
        # Restore markdown bold **text** to <b>text</b>
        formatted = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
        # Restore markdown italic *text* or _text_ to <i>text</i>
        formatted = re.sub(
            r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"<i>\1</i>", formatted
        )
        return formatted

    story = []
    lines = (content or "").replace("\r\n", "\n").splitlines()

    # If completely empty content, emit a placeholder space to build valid PDF
    if not any(line.strip() for line in lines):
        story.append(Spacer(1, 10))
    else:
        for line in lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 3 * mm))
                continue

            # Heading 1: # Title
            if stripped.startswith("# "):
                story.append(Paragraph(format_line(stripped[2:].strip()), style_title))
            # Heading 2: ## Subheading
            elif stripped.startswith("## "):
                story.append(Paragraph(format_line(stripped[3:].strip()), style_h1))
            # Heading 3: ### Section
            elif stripped.startswith("### "):
                story.append(Paragraph(format_line(stripped[4:].strip()), style_h2))
            # Heading 4: #### Sub-section
            elif stripped.startswith("#### "):
                story.append(Paragraph(format_line(stripped[5:].strip()), style_h3))
            # Horizontal divider: --- or ___
            elif stripped in ("---", "___", "***"):
                story.append(Spacer(1, 1 * mm))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#d4e2e2"),
                        spaceAfter=3 * mm,
                    )
                )
            # Bullet point: - or * or •
            elif stripped.startswith(("- ", "* ", "• ")):
                bullet_text = stripped[2:].strip()
                story.append(
                    Paragraph(f"&bull; {format_line(bullet_text)}", style_bullet)
                )
            # Metadata / Date patterns (e.g., "Jan 2020 – Present", "Date: 2026-09-26")
            elif re.search(
                r"^(?:date|posted|framework|applicant|organisation|position|status)[:\s]",
                stripped,
                re.IGNORECASE,
            ):
                story.append(Paragraph(format_line(stripped), style_meta))
            else:
                story.append(Paragraph(format_line(stripped), style_body))

    # Build PDF with custom NumberedCanvas
    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c._doc_title = display_title
        return c

    doc.build(story, canvasmaker=_canvas_factory)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data
