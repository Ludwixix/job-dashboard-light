"""Unit test suite for 1-Click Document Export (Markdown & ReportLab PDF)."""

from __future__ import annotations

from job_dashboard_light.services.export import (
    export_markdown,
    export_pdf_bytes,
    sanitize_filename,
)


def test_sanitize_filename_prevents_traversal():
    safe1 = sanitize_filename("../../etc/passwd")
    assert ".." not in safe1
    assert "/" not in safe1
    assert "\\" not in safe1

    safe2 = sanitize_filename("my resume / cover letter!.pdf")
    assert "/" not in safe2
    assert "cover_letter" in safe2


def test_markdown_export():
    raw_md = "# Resume\n\n- Skill 1\n- Skill 2"
    content, headers = export_markdown(raw_md, title="Candidate_Resume")
    assert content == raw_md
    assert "text/markdown" in headers["Content-Type"]
    assert 'filename="Candidate_Resume.md"' in headers["Content-Disposition"]


def test_pdf_export_valid_binary():
    raw_md = "# Professional Profile\n\n**Candidate:** Alex Vance\n\n- Cloud Systems\n- Kubernetes"
    pdf_bytes = export_pdf_bytes(raw_md, title="Alex_Vance_Resume")
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_pdf_export_special_symbols():
    content = (
        "Symbols: € £ ¥ © ® ™ ± µ ¢ and quotes: 'single' and \"double\" and dash —"
    )
    pdf_bytes = export_pdf_bytes(content, title="Symbols_Test")
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_export_multipage():
    lines = ["# Comprehensive Dossier\n"]
    for i in range(120):
        lines.append(f"- Line {i}: Demonstrating multi-page stability and page breaks.")
    pdf_bytes = export_pdf_bytes("\n".join(lines), title="Multipage_Document")
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1500


def test_pdf_export_empty_content():
    pdf_bytes = export_pdf_bytes("", title="Empty_Doc")
    assert pdf_bytes.startswith(b"%PDF")
