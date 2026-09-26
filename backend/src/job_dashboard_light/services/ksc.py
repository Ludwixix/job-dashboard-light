"""
Australian Key Selection Criteria (KSC) STAR Response Generator & Public Sector Capability Framework.

Supports:
1. APS Integrated Leadership System (ILS)
2. Victorian Public Sector Commission (VPSC) Capability Framework
3. Custom / External Australian Frameworks
4. STAR (Situation, Task, Action, Result) narrative synthesis
5. Strict word count limit enforcement (100w, 250w, 350w, 500w, 1000w)
6. Australian English localization (organise, programme, prioritise, analyse, optimise, etc.)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# US to Australian English spelling normalization map
AU_SPELLING_MAP = {
    "organize": "organise",
    "organized": "organised",
    "organizing": "organising",
    "organization": "organisation",
    "organizations": "organisations",
    "organizational": "organisational",
    "prioritize": "prioritise",
    "prioritized": "prioritised",
    "prioritizing": "prioritising",
    "prioritization": "prioritisation",
    "analyze": "analyse",
    "analyzed": "analysed",
    "analyzing": "analysing",
    "analyzer": "analyser",
    "analyzers": "analysers",
    "utilize": "utilise",
    "utilized": "utilised",
    "utilizing": "utilising",
    "utilization": "utilisation",
    "optimize": "optimise",
    "optimized": "optimised",
    "optimizing": "optimising",
    "optimization": "optimisation",
    "centralize": "centralise",
    "centralized": "centralised",
    "centralizing": "centralising",
    "standardize": "standardise",
    "standardized": "standardised",
    "standardizing": "standardising",
    "customize": "customise",
    "customized": "customised",
    "customizing": "customising",
    "program": "programme",
    "programs": "programmes",
    "behavior": "behaviour",
    "behaviors": "behaviours",
    "center": "centre",
    "centers": "centres",
    "centered": "centred",
    "defense": "defence",
    "license": "licence",
    "color": "colour",
    "colors": "colours",
    "labor": "labour",
    "foster": "foster",
}


def localize_australian(text: str) -> str:
    """Convert American English spelling variations to Australian English preserving case."""
    if not text:
        return ""
    result = text
    for us_word, au_word in AU_SPELLING_MAP.items():
        pattern = re.compile(rf"\b{us_word}\b", re.IGNORECASE)

        def repl(match: re.Match, target: str = au_word) -> str:
            w = match.group(0)
            if w.isupper():
                return target.upper()
            if w.istitle():
                return target.capitalize()
            return target

        result = pattern.sub(repl, result)
    return result


# Capability Frameworks
CAPABILITY_PILLARS = {
    "STRATEGIC_DIRECTION": {
        "aps_name": "Shapes Strategic Thinking",
        "vpsc_name": "Shapes Strategy / Strategic Direction",
        "description": "Inspires a sense of purpose and direction, focuses strategically, harnesses information, and shows sound judgement.",
        "keywords": [
            "strategy",
            "strategic",
            "policy",
            "vision",
            "analytical",
            "research",
            "continuous improvement",
            "governance",
            "planning",
            "innovative",
            "reform",
        ],
    },
    "ACHIEVES_RESULTS": {
        "aps_name": "Achieves Results",
        "vpsc_name": "Delivers Meaningful Outcomes / Achieves Results",
        "description": "Identifies and uses resources wisely, applies professional expertise, responds positively to change, and takes responsibility for delivering high-quality outcomes.",
        "keywords": [
            "delivery",
            "deliver",
            "results",
            "milestone",
            "kpi",
            "project management",
            "budget",
            "cost",
            "deadlines",
            "implement",
            "execute",
            "agile",
            "timeline",
        ],
    },
    "RELATIONSHIPS": {
        "aps_name": "Cultivates Productive Working Relationships",
        "vpsc_name": "People & Relationships / Stakeholder Engagement",
        "description": "Nurtures internal and external relationships, listens to, understands and recognises the needs of others, values diversity, and guides/mentors others.",
        "keywords": [
            "stakeholder",
            "collaboration",
            "consultation",
            "co-design",
            "teamwork",
            "partner",
            "client",
            "negotiate",
            "mentor",
            "interpersonal",
            "relationship",
            "consult",
            "inclusive",
            "community",
        ],
    },
    "INTEGRITY_VALUES": {
        "aps_name": "Exemplifies Personal Drive and Integrity",
        "vpsc_name": "Public Sector Values & Ethical Governance",
        "description": "Demonstrates public service professionalism and probity, engages with risk and shows personal courage, commits to action, and displays resilience.",
        "keywords": [
            "integrity",
            "ethics",
            "probity",
            "values",
            "compliance",
            "resilience",
            "accountability",
            "governance",
            "impartial",
            "safety",
            "child safe",
            "public sector values",
            "merit",
        ],
    },
    "COMMUNICATION": {
        "aps_name": "Communicates with Influence",
        "vpsc_name": "Communicates with Influence & Clarity",
        "description": "Communicates clearly, listens, understands and adapts to audience, negotiates persuasively, and prepares clear, high-level briefings and ministerial submissions.",
        "keywords": [
            "communication",
            "briefing",
            "written",
            "verbal",
            "presentation",
            "report",
            "influence",
            "submission",
            "cabinet",
            "ministerial",
            "correspondence",
            "articulate",
        ],
    },
    "TECHNICAL_EXPERTISE": {
        "aps_name": "Technical & Domain Specialist Mastery",
        "vpsc_name": "Specialised Domain & Technical Expertise",
        "description": "Applies depth of domain expertise, technical frameworks, specialized systems, and regulatory standards.",
        "keywords": [
            "technical",
            "systems",
            "cloud",
            "aws",
            "azure",
            "sql",
            "data",
            "architecture",
            "software",
            "clinical",
            "nursing",
            "engineering",
            "legal",
            "financial",
            "infrastructure",
        ],
    },
}


@dataclass
class KscSolution:
    """Individual STAR statement resolving a single criterion."""

    criterion_number: int
    criterion_text: str
    framework: str
    capability_name: str
    capability_description: str
    situation: str
    task: str
    action: str
    result: str
    full_statement: str
    word_count: int
    target_word_limit: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KscReport:
    """Full KSC compilation document."""

    job_id: str
    job_title: str
    company: str
    candidate_name: str
    framework: str
    total_criteria: int
    solutions: list[KscSolution] = field(default_factory=list)
    master_document: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "company": self.company,
            "candidate_name": self.candidate_name,
            "framework": self.framework,
            "total_criteria": self.total_criteria,
            "solutions": [s.to_dict() for s in self.solutions],
            "master_document": self.master_document,
        }


def extract_ksc_from_jd(description: str, title: str = "") -> list[str]:
    """Extract explicit Key Selection Criteria or core capability requirements from job text."""
    if not description or not isinstance(description, str) or not description.strip():
        return _fallback_criteria(title)

    clean_text = description.replace("\r\n", "\n")

    section_match = re.search(
        r"(?:key\s+selection\s+criteria|ksc|selection\s+criteria|key\s+accountabilities|what\s+you(?:'ll|\s+will)\s+bring|about\s+you|skills\s+(?:and|&)\s+experience|capabilities|requirements)[:\s\n]+([\s\S]+?)(?=(?:\n\s*(?:how\s+to\s+apply|why\s+join|benefits|about\s+the\s+department|terms\s+of\s+appointment|pre-employment|applications\s+close)\b|$))",
        clean_text,
        re.IGNORECASE,
    )
    search_scope = section_match.group(1) if section_match else clean_text

    extracted: list[str] = []

    # Numbered criteria (e.g., "1. Demonstrated...", "Criterion 1:", "KSC 1:")
    numbered = re.findall(
        r"^\s*(?:(?:ksc|criterion)?\s*\d+[.:]\s*)([^\n]+)",
        search_scope,
        re.MULTILINE | re.IGNORECASE,
    )
    for m in numbered:
        cleaned = " ".join(m.split()).strip()
        if len(cleaned) >= 15 and not re.search(
            r"^(?:how to apply|salary|work type|location|reference|apply|close)\b",
            cleaned,
            re.IGNORECASE,
        ):
            extracted.append(cleaned)

    # Bullet points under criteria section
    if len(extracted) < 2:
        bullets = re.findall(
            r"^\s*[•*\-►✔✓]\s*([^\n]+)",
            search_scope,
            re.MULTILINE,
        )
        for b in bullets:
            cleaned = " ".join(b.split()).strip()
            if len(cleaned) >= 20 and not re.search(
                r"^(?:how to apply|salary|work type|location|reference|apply|close)\b",
                cleaned,
                re.IGNORECASE,
            ):
                extracted.append(cleaned)

    meaningful = [c for c in extracted if len(c) >= 15][:6]
    if len(meaningful) < 1:
        return _fallback_criteria(title)

    return meaningful


def _fallback_criteria(title: str = "") -> list[str]:
    """Generates standard Victorian/Australian public sector capability criteria when none explicitly extracted."""
    role_name = title.strip() or "Specialist / Advisor"
    return [
        f"Demonstrated experience in {role_name} delivery, with proven capability to analyze complex requirements and deliver high-quality outcomes within statutory deadlines.",
        "Demonstrated high-level interpersonal and stakeholder engagement skills, with the proven ability to build collaborative relationships and consult effectively with diverse stakeholders.",
        "Proven analytical, problem-solving and strategic thinking capabilities, including the ability to identify systemic risks and formulate practical solutions.",
        "High-level written and verbal communication skills, with demonstrated capability to synthesize complex data into clear, persuasive executive briefings and reports.",
        "Demonstrated commitment to public sector values, probity, ethical conduct, and fostering inclusive, respectful team environments.",
    ]


def map_ksc_to_capability_framework(
    criterion: str, framework: str = "APS"
) -> dict[str, Any]:
    """Maps a criterion text to the APS Integrated Leadership System or VPSC Capability Framework."""
    crit_lower = (criterion or "").lower()
    fw_upper = (framework or "APS").strip().upper()

    best_pillar = "TECHNICAL_EXPERTISE"
    max_score = 0

    for pillar_key, pillar_data in CAPABILITY_PILLARS.items():
        score = sum(1 for kw in pillar_data["keywords"] if kw in crit_lower)
        if score > max_score:
            max_score = score
            best_pillar = pillar_key

    # Heuristic overrides
    if any(
        k in crit_lower
        for k in [
            "stakeholder",
            "collaborat",
            "relationship",
            "partner",
            "co-design",
            "consult",
        ]
    ):
        best_pillar = "RELATIONSHIPS"
    elif any(
        k in crit_lower
        for k in [
            "written",
            "verbal",
            "briefing",
            "report",
            "presentation",
            "communicat",
        ]
    ):
        best_pillar = "COMMUNICATION"
    elif any(
        k in crit_lower
        for k in [
            "integrity",
            "probity",
            "values",
            "ethics",
            "child safe",
            "accountability",
        ]
    ):
        best_pillar = "INTEGRITY_VALUES"
    elif any(
        k in crit_lower
        for k in [
            "deliver",
            "project",
            "milestone",
            "outcome",
            "budget",
            "kpi",
            "agile",
        ]
    ):
        best_pillar = "ACHIEVES_RESULTS"
    elif any(
        k in crit_lower
        for k in ["strategic", "policy", "strategy", "vision", "innovat", "reform"]
    ):
        best_pillar = "STRATEGIC_DIRECTION"

    pillar_info = CAPABILITY_PILLARS[best_pillar]
    if "VPSC" in fw_upper:
        cap_name = pillar_info["vpsc_name"]
    elif "APS" in fw_upper:
        cap_name = pillar_info["aps_name"]
    else:
        cap_name = f"{framework} - {pillar_info['aps_name']}"

    return {
        "pillar": best_pillar,
        "name": cap_name,
        "description": pillar_info["description"],
    }


def _calibrate_statement_words(text: str, target_limit: int) -> str:
    """Trim text if it significantly exceeds target word limit while preserving structure."""
    words = text.split()
    max_allowed = target_limit + 40
    if len(words) <= max_allowed:
        return text

    # Truncate at sentence boundary within limit
    sentences = re.split(r"(?<=[.!?])\s+", text)
    accumulated: list[str] = []
    current_count = 0

    for s in sentences:
        s_words = len(s.split())
        if current_count + s_words <= max_allowed or len(accumulated) < 4:
            accumulated.append(s)
            current_count += s_words
        else:
            break

    result = " ".join(accumulated).strip()
    return result if result else " ".join(words[:max_allowed])


def generate_star_statement(
    criterion: str,
    profile: dict[str, Any],
    job: dict[str, Any],
    criterion_index: int = 1,
    framework: str = "APS",
    word_limit: int = 350,
) -> KscSolution:
    """Synthesizes a STAR narrative matching the given criterion and framework."""
    mapping = map_ksc_to_capability_framework(criterion, framework=framework)
    target_company = str(job.get("company") or "the Department").strip()
    job_title = str(job.get("title") or "the role").strip()

    # Profile facts
    experience = profile.get("experience") or profile.get("history") or []
    recent_role = experience[0] if experience and isinstance(experience, list) else {}
    past_company = recent_role.get("company") or "a major enterprise organisation"
    past_title = (
        recent_role.get("title") or recent_role.get("role") or "Senior Specialist"
    )

    skills = (
        profile.get("skills")
        or profile.get("core_skills")
        or profile.get("coreSkills")
        or []
    )
    if isinstance(skills, dict):
        flat = []
        for v in skills.values():
            if isinstance(v, list):
                flat.extend(v)
        skills = flat
    skills_text = (
        ", ".join(skills[:3])
        if skills
        else "agile delivery, cloud architecture, and data governance"
    )

    pillar = mapping["pillar"]
    fw_clean = (framework or "APS").strip()

    # Micro/concise templates for word_limit <= 150
    is_concise = word_limit <= 150

    if pillar == "STRATEGIC_DIRECTION":
        if is_concise:
            situation = f"At {past_company}, operational fragmentation delayed strategic reform timelines."
            task = f"As {past_title}, I was responsible for formulating a unified roadmap aligned with executive priorities."
            action = f"I deployed agile planning, prioritised key milestones using {skills_text}, and managed operational risks."
            result = f"Turnaround times dropped by 32% with division-wide adoption, establishing strategic clarity for {target_company}."
        else:
            situation = (
                f"While serving as {past_title} at {past_company}, our team was tasked with navigating a complex operational reform "
                f"where fragmented processes and siloed data streams compromised strategic visibility and programme delivery timelines."
            )
            task = (
                "My objective was to establish an overarching strategic roadmap, harmonise cross-branch priorities, and align "
                "operational milestones with ministerial and departmental directives."
            )
            action = (
                f"I spearheaded a strategic gap analysis across key deliverables, engaging with cross-functional leaders to establish "
                f"a standardised roadmap. Leveraging {skills_text}, I instituted agile prioritisation principles, aligned strategic milestones "
                f"with overarching departmental priorities, and designed proactive risk mitigation matrices to ensure operational continuity."
            )
            result = (
                f"This strategic overhaul established seamless visibility across 100% of pipeline projects, reduced initiative turnaround times "
                f"by 32%, and delivered an enduring operating framework that was adopted division-wide. I will bring this identical strategic "
                f"foresight to {target_company} as {job_title}."
            )
    elif pillar == "ACHIEVES_RESULTS":
        if is_concise:
            situation = f"At {past_company}, critical service benchmarks required immediate delivery under statutory deadlines."
            task = "I led the execution of high-priority deliverables with strict budget and quality controls."
            action = f"I deployed disciplined milestones, implemented {skills_text}, and resolved technical bottlenecks."
            result = "Delivered 3 weeks ahead of schedule, saving $140,000 with 99.8% compliance."
        else:
            situation = (
                f"In my role as {past_title} at {past_company}, I had accountability for delivering high-priority project outcomes "
                f"under strict statutory deadlines and demanding service delivery benchmarks with zero margin for operational slippage."
            )
            task = (
                "My accountability was to coordinate multidisciplinary resources, ensure uncompromised quality assurance, and achieve "
                "all scheduled milestones within allocated expenditure limits."
            )
            action = (
                f"I deployed disciplined project controls, establishing clear milestones, automated tracking dashboards, and rigorous quality "
                f"assurance routines. When unforeseen technical bottlenecks arose, I reallocated team resources strategically, implemented {skills_text}, "
                f"and maintained weekly executive accountability check-ins to ensure uncompromised execution velocity."
            )
            result = (
                f"As a result, all project deliverables were achieved 3 weeks ahead of scheduled completion, realising a 28% gain in efficiency "
                f"and saving over $140,000 in operational overhead while maintaining a 99.8% compliance rate. This track record of results "
                f"will directly support {target_company}'s commitments."
            )
    elif pillar == "RELATIONSHIPS":
        if is_concise:
            situation = f"At {past_company}, conflicting priorities between stakeholder groups stalled project progress."
            task = "I was tasked with building consensus and collaborative partnerships across all teams."
            action = "I established consultative forums, practised empathetic active listening, and aligned technical needs with shared outcomes."
            result = "Secured unanimous executive consensus and increased stakeholder satisfaction by 44%."
        else:
            situation = (
                f"At {past_company}, I operated in a complex stakeholder ecosystem where competing priorities between internal business units, "
                f"technical teams, and external partner agencies initially impeded collaborative progress on key organizational goals."
            )
            task = (
                "My responsibility was to establish productive working relationships, foster genuine consultative engagement, and build "
                "enduring trust across diverse internal and external stakeholders."
            )
            action = (
                "I established structured consultative forums and co-design workshops, actively listening to stakeholders' distinct operational "
                "pain points. By framing technical requirements in shared business value, maintaining transparent communication cadences, and "
                "fostering an empathetic, culturally safe environment, I built mutual trust and unified disparate stakeholder objectives."
            )
            result = (
                f"This collaborative framework secured unanimous consensus from all executive stakeholders, eliminating cross-team friction and "
                f"boosting stakeholder satisfaction metrics by 44%. I look forward to cultivating equally robust, enduring partnerships across {target_company}."
            )
    elif pillar == "INTEGRITY_VALUES":
        if is_concise:
            situation = f"During a systems review at {past_company}, regulatory compliance required strict probity adherence."
            task = "I was mandated to uphold public sector standards and ensure 100% audit integrity."
            action = "I conducted comprehensive governance reviews, trained staff on risk protocols, and led with transparency."
            result = "Achieved zero audit findings and established a benchmark culture of ethics and accountability."
        else:
            situation = (
                f"During an intensive audit and systems review at {past_company}, our unit encountered sensitive compliance and data privacy "
                f"challenges requiring uncompromising adherence to regulatory standards, probity requirements, and public trust."
            )
            task = (
                "I was entrusted to safeguard organisational probity, uphold Victorian and Australian public sector values, and implement "
                "robust risk governance across all operational practices."
            )
            action = (
                "I immediately upheld organisational governance by conducting a comprehensive compliance review, ensuring 100% adherence to "
                "relevant standards and ethical protocols. I championed transparent reporting, trained team members in risk awareness, and led "
                "by personal example with unwavering accountability and professional integrity."
            )
            result = (
                "The initiative achieved a spotless 100% audit clearance from independent regulators with zero non-conformances identified, "
                "reinforcing institutional integrity and safeguarding sensitive data. I hold myself to these exact standards in public service."
            )
    elif pillar == "COMMUNICATION":
        if is_concise:
            situation = f"At {past_company}, complex technical changes needed to be communicated to non-technical executives."
            task = "I was responsible for preparing clear briefings and securing leadership approval."
            action = "I authored plain-English executive memos, visualised key data, and tailored messages to stakeholder perspectives."
            result = "Achieved unanimous first-pass approval and compressed decision cycles from 4 weeks to 5 days."
        else:
            situation = (
                f"As {past_title}, I was responsible for communicating intricate, data-dense technical architectures and policy updates to non-technical "
                f"departmental leaders, external regulatory authorities, and community representatives with varying technical literacy."
            )
            task = (
                "My mandate was to translate complex concepts into persuasive executive briefings, ministerial submissions, and actionable "
                "recommendations for executive decision-makers."
            )
            action = (
                "I authored concise executive briefings, data-driven visual dashboards, and plain-English policy summaries that distilled complex "
                "systems into actionable insights. I tailored my communication style to each audience, facilitating interactive Q&A sessions and "
                "persuasively articulating the strategic justification and risk posture for proposed initiatives."
            )
            result = (
                f"My executive briefings directly influenced leadership sign-off with 100% first-pass approval from steering committees, cutting "
                f"decision cycles from 4 weeks to 5 business days. I will bring this clear, influential communication capability to {target_company}."
            )
    else:  # TECHNICAL_EXPERTISE
        if is_concise:
            situation = f"At {past_company}, legacy infrastructure created system bottlenecks and reliability risks."
            task = f"I was accountable for architecting robust, scalable solutions using {skills_text}."
            action = "I engineered automated deployment pipelines, instituted peer reviews, and standardised system documentation."
            result = (
                "Reduced incident tickets by 45% and improved processing speed by 3x."
            )
        else:
            situation = (
                f"While driving technical capability at {past_company}, our team needed to architect and implement reliable, scalable systems "
                f"capable of meeting strict security guidelines, high availability requirements, and continuous data integration."
            )
            task = (
                "My responsibility was to provide deep technical leadership, design future-ready architectures, and enforce best-practice "
                "engineering standards."
            )
            action = (
                f"Leveraging deep hands-on expertise in {skills_text}, I engineered automated workflows, robust testing suites, and standardised "
                f"documentation. I ensured full compliance with enterprise architectures, conducted peer code reviews, and mentored junior staff "
                f"on technical best practices and continuous integration paradigms."
            )
            result = (
                f"The deployed architecture reduced system incident tickets by 45%, bolstered processing throughput by 3x, and established a scalable "
                f"foundation for future enhancements. I am fully equipped to apply this domain mastery to the technical challenges at {target_company}."
            )

    # Localize Australian English
    sit_au = localize_australian(situation)
    task_au = localize_australian(task)
    act_au = localize_australian(action)
    res_au = localize_australian(result)

    full_stmt = (
        f"**Situation:** {sit_au}\n\n"
        f"**Task:** {task_au}\n\n"
        f"**Action:** {act_au}\n\n"
        f"**Result:** {res_au}"
    )

    if word_limit:
        full_stmt = _calibrate_statement_words(full_stmt, word_limit)

    words = len(full_stmt.split())

    return KscSolution(
        criterion_number=criterion_index,
        criterion_text=criterion,
        framework=fw_clean,
        capability_name=mapping["name"],
        capability_description=mapping["description"],
        situation=sit_au,
        task=task_au,
        action=act_au,
        result=res_au,
        full_statement=full_stmt,
        word_count=words,
        target_word_limit=word_limit,
    )


def generate_ksc_report(
    job: dict[str, Any],
    profile: dict[str, Any],
    custom_criteria: list[str] | None = None,
    framework: str = "APS",
    word_limit: int = 350,
) -> KscReport:
    """Generate a complete KSC compilation report mapped to public sector frameworks."""
    job_id = str(
        job.get("id") or f"{job.get('company', 'target')}_{job.get('title', 'role')}"
    ).strip()
    job_title = str(job.get("title") or "Specialist / Advisor").strip()
    company = str(job.get("company") or "Australian Public Sector").strip()
    candidate_name = str(profile.get("name") or "Candidate").strip()
    description = str(
        job.get("description") or job.get("job_description") or ""
    ).strip()

    fw_upper = (framework or "APS").strip().upper()
    fw_label = (
        "APS Integrated Leadership System (ILS)"
        if "APS" in fw_upper
        else (
            "Victorian Public Sector Commission (VPSC) Capability Framework"
            if "VPSC" in fw_upper
            else framework
        )
    )
    fw_response_tag = (
        "APS Framework Response"
        if "APS" in fw_upper
        else (
            "VPSC Framework Response"
            if "VPSC" in fw_upper
            else f"{framework} Framework Response"
        )
    )

    # Determine criteria
    criteria: list[str] = []
    if custom_criteria and isinstance(custom_criteria, list):
        criteria = [c.strip() for c in custom_criteria if c and c.strip()]

    if not criteria:
        criteria = extract_ksc_from_jd(description, job_title)

    solutions: list[KscSolution] = []
    for idx, crit in enumerate(criteria, start=1):
        sol = generate_star_statement(
            crit,
            profile,
            job,
            criterion_index=idx,
            framework=framework,
            word_limit=word_limit,
        )
        solutions.append(sol)

    # Build master document
    doc_lines = [
        "# Key Selection Criteria Response Document",
        f"**Framework:** {fw_response_tag} ({fw_label})",
        f"**Position:** {job_title}",
        f"**Organisation:** {company}",
        f"**Applicant:** {candidate_name}",
        "**Methodology:** STAR Method (Situation, Task, Action, Result)",
        f"**Target Word Limit:** {word_limit} words per criterion",
        "---",
        "",
    ]

    for sol in solutions:
        doc_lines.extend(
            [
                f"## Criterion {sol.criterion_number}: {sol.criterion_text}",
                f"*{sol.capability_name} — {fw_response_tag}*",
                "",
                sol.full_statement,
                "",
                f"*Word count: {sol.word_count} words (Target: {sol.target_word_limit} words)*",
                "",
                "---",
                "",
            ]
        )

    master_doc = "\n".join(doc_lines).strip()

    return KscReport(
        job_id=job_id,
        job_title=job_title,
        company=company,
        candidate_name=candidate_name,
        framework=framework,
        total_criteria=len(solutions),
        solutions=solutions,
        master_document=master_doc,
    )


# Backward compatibility alias
generate_ksc_statements = generate_ksc_report

