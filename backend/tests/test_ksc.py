"""Unit test suite for Australian Key Selection Criteria (KSC) STAR Generator."""

from __future__ import annotations

from job_dashboard_light.services.ksc import (
    extract_ksc_from_jd,
    generate_ksc_report,
    generate_star_statement,
    localize_australian,
    map_ksc_to_capability_framework,
)


def test_extract_ksc_numbered_criteria():
    jd = """
    About the Role:
    Senior Project Delivery Manager with DFFH.

    Key Selection Criteria:
    1. Demonstrated experience in leading complex capital infrastructure projects.
    2. Proven ability to cultivate productive stakeholder relationships across government agencies.
    3. High-level analytical and strategic thinking capabilities to manage systemic project risks.
    4. Strong written and verbal communication skills for executive and ministerial briefings.
    """
    criteria = extract_ksc_from_jd(jd, "Senior Project Delivery Manager")
    assert len(criteria) == 4
    assert "capital infrastructure projects" in criteria[0]
    assert "stakeholder relationships" in criteria[1]


def test_extract_ksc_bullet_points():
    jd = """
    Department of Education Victoria
    Key selection criteria:
    • Proven experience managing multi-cloud AWS and Azure environments under strict SLA benchmarks.
    • Strong interpersonal skills with demonstrated capacity to mentor and lead technical teams.
    • Demonstrated commitment to public sector ethics, integrity, and Victorian child-safe standards.
    """
    criteria = extract_ksc_from_jd(jd, "Cloud Engineer")
    assert len(criteria) == 3
    assert any("AWS and Azure" in c for c in criteria)
    assert any("child-safe standards" in c for c in criteria)


def test_extract_ksc_fallback():
    criteria = extract_ksc_from_jd("", "Principal Policy Officer")
    assert len(criteria) == 5
    assert any("Principal Policy Officer" in c for c in criteria)


def test_map_capability_frameworks():
    # APS mappings
    m_rel = map_ksc_to_capability_framework(
        "Experience consulting with stakeholders and partners", framework="APS"
    )
    assert m_rel["pillar"] == "RELATIONSHIPS"
    assert "Cultivates Productive Working Relationships" in m_rel["name"]

    m_strat = map_ksc_to_capability_framework(
        "Formulating policy reforms and strategic directions", framework="APS"
    )
    assert m_strat["pillar"] == "STRATEGIC_DIRECTION"
    assert "Shapes Strategic Thinking" in m_strat["name"]

    # VPSC mapping
    m_vpsc = map_ksc_to_capability_framework(
        "Commitment to public sector values and ethical governance", framework="VPSC"
    )
    assert m_vpsc["pillar"] == "INTEGRITY_VALUES"
    assert "Public Sector Values" in m_vpsc["name"]

    # Custom mapping
    m_custom = map_ksc_to_capability_framework(
        "Deploying cloud systems", framework="CUSTOM_FRAMEWORK"
    )
    assert "CUSTOM_FRAMEWORK" in m_custom["name"]


def test_star_statement_components():
    profile = {
        "name": "Sam Taylor",
        "experience": [{"company": "Telstra Enterprise", "title": "Lead Architect"}],
        "skills": ["AWS", "DevOps", "Governance"],
    }
    job = {"title": "Principal Engineer", "company": "VEC"}
    crit = "Demonstrated ability to architect reliable enterprise systems."

    sol = generate_star_statement(
        crit, profile, job, criterion_index=1, framework="APS", word_limit=350
    )
    assert "**Situation:**" in sol.full_statement
    assert "**Task:**" in sol.full_statement
    assert "**Action:**" in sol.full_statement
    assert "**Result:**" in sol.full_statement
    assert sol.word_count <= 400
    assert "VEC" in sol.result


def test_ksc_word_limit_boundaries():
    profile = {"name": "Candidate", "skills": ["Governance"]}
    job = {"title": "Officer", "company": "APS"}

    sol100 = generate_star_statement("Crisis management", profile, job, word_limit=100)
    assert sol100.word_count <= 150

    sol1000 = generate_star_statement(
        "Executive leadership", profile, job, word_limit=1000
    )
    assert len(sol1000.full_statement) > 200


def test_ksc_australian_localization():
    text = "The organization will prioritize analyzing and optimizing programs."
    au_text = localize_australian(text)
    assert "organisation" in au_text
    assert "prioritise" in au_text
    assert "analysing" in au_text
    assert "optimising" in au_text
    assert "programmes" in au_text


def test_ksc_report_framework_tags():
    profile = {"name": "Morgan Vance"}
    job = {"id": "vps_1", "title": "Director", "company": "DEECA"}

    report_aps = generate_ksc_report(
        job, profile, custom_criteria=["Crit A"], framework="APS"
    )
    assert "APS Framework Response" in report_aps.master_document

    report_vpsc = generate_ksc_report(
        job, profile, custom_criteria=["Crit A"], framework="VPSC"
    )
    assert "VPSC Framework Response" in report_vpsc.master_document

    report_custom = generate_ksc_report(
        job, profile, custom_criteria=["Crit A"], framework="CUSTOM_FRAMEWORK"
    )
    assert "CUSTOM_FRAMEWORK" in report_custom.master_document
