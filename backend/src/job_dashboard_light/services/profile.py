"""
Candidate Profile Service: Multi-format Resume Ingestion, LLM Fact Extrapolation,
Dynamic Query Expansion, and Negative Keyword Filtering.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import httpx
import pypdf

from job_dashboard_light.config import settings
from job_dashboard_light.database import get_db_connection
from job_dashboard_light.models import (
    CandidateProfile,
    NormalizedJob,
    SearchQuery,
    now_iso,
)

logger = logging.getLogger("job_dashboard_light.services.profile")

MAX_RESUME_CHARS = 9000

COMMON_AUSTRALIAN_SKILLS = [
    # Cloud & Virtualization
    "AWS",
    "Amazon Web Services",
    "Azure",
    "Microsoft Azure",
    "GCP",
    "Google Cloud",
    "VMware",
    "vSphere",
    "Hyper-V",
    "Docker",
    "Kubernetes",
    "EKS",
    "AKS",
    "OpenShift",
    # Infrastructure & DevOps
    "Terraform",
    "Ansible",
    "CloudFormation",
    "Bicep",
    "CI/CD",
    "GitHub Actions",
    "GitLab CI",
    "Jenkins",
    "Puppet",
    "Chef",
    "Linux",
    "RHEL",
    "Ubuntu",
    "Debian",
    "Windows Server",
    "Active Directory",
    "Entra ID",
    "Azure AD",
    "Intune",
    "Autopilot",
    "PowerShell",
    "Bash",
    "Shell Scripting",
    "System Center",
    "SCCM",
    "MECM",
    # M365 & Collaboration
    "Microsoft 365",
    "Office 365",
    "SharePoint",
    "SharePoint Online",
    "Exchange Online",
    "Exchange Hybrid",
    "Microsoft Teams",
    "OneDrive",
    "Power Platform",
    "Power Automate",
    "Power Apps",
    "Power BI",
    # Networking & Security
    "Cisco",
    "Fortinet",
    "Palo Alto",
    "Juniper",
    "Firewall",
    "VPN",
    "BGP",
    "OSPF",
    "SD-WAN",
    "DNS",
    "DHCP",
    "TCP/IP",
    "Wireshark",
    "Cybersecurity",
    "Zero Trust",
    "Essential 8",
    "ISO 27001",
    "NIST",
    "SOC 2",
    "Splunk",
    "Sentinel",
    "CrowdStrike",
    "Defender",
    "SIEM",
    "Incident Response",
    "Vulnerability Management",
    # Programming & Web Development
    "Python",
    "JavaScript",
    "TypeScript",
    "React",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "Next.js",
    "Vue",
    "Angular",
    "HTML",
    "CSS",
    "Tailwind CSS",
    "Go",
    "Golang",
    "Java",
    "C#",
    ".NET",
    ".NET Core",
    "C++",
    "Rust",
    "PHP",
    "Ruby",
    # Data & Databases
    "SQL",
    "PostgreSQL",
    "MySQL",
    "Microsoft SQL Server",
    "Oracle",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "Snowflake",
    "BigQuery",
    "Databricks",
    "dbt",
    "Airflow",
    "Kafka",
    "ETL",
    "Data Warehousing",
    "Data Modeling",
    # Service Management & Methodologies
    "ITIL",
    "ITIL 4",
    "ServiceNow",
    "Jira",
    "Confluence",
    "Agile",
    "Scrum",
    "Kanban",
    "DevSecOps",
    "SRE",
    "Site Reliability Engineering",
    "Incident Management",
]

EXPANSION_TEMPLATES: Dict[str, List[str]] = {
    "systems": [
        "Systems Engineer",
        "Senior Systems Engineer",
        "Infrastructure Engineer",
        "Cloud Infrastructure Specialist",
        "Systems Administrator",
        "Wintel Engineer",
        "M365 Systems Specialist",
        "Platform Engineer",
    ],
    "cloud": [
        "Cloud Engineer",
        "Senior Cloud Engineer",
        "DevOps Engineer",
        "Cloud Architect",
        "Cloud Platform Engineer",
        "Site Reliability Engineer",
        "AWS Cloud Specialist",
        "Azure Infrastructure Engineer",
    ],
    "devops": [
        "DevOps Engineer",
        "Senior DevOps Engineer",
        "Platform Engineer",
        "Site Reliability Engineer",
        "SRE",
        "Cloud Platform Engineer",
        "CI/CD Automation Engineer",
    ],
    "software": [
        "Software Engineer",
        "Senior Software Engineer",
        "Full Stack Developer",
        "Backend Developer",
        "Frontend Developer",
        "Python Developer",
        "Software Development Engineer",
    ],
    "security": [
        "Cyber Security Engineer",
        "Information Security Specialist",
        "Cloud Security Engineer",
        "Security Analyst",
        "SOC Analyst",
        "Cybersecurity Consultant",
    ],
    "data": [
        "Data Engineer",
        "Senior Data Engineer",
        "Analytics Engineer",
        "Data Platform Engineer",
        "BI Developer",
        "Database Administrator",
    ],
    "network": [
        "Network Engineer",
        "Senior Network Engineer",
        "Network Administrator",
        "Network Infrastructure Specialist",
        "Network Security Engineer",
    ],
    "support": [
        "Desktop Support Engineer",
        "L2/L3 Systems Support",
        "Helpdesk Team Lead",
        "Service Desk Analyst",
        "Technical Support Specialist",
    ],
}


# ==============================================================================
# 1. Multi-Format Resume Text Extraction
# ==============================================================================


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract readable text from PDF bytes using pypdf.

    Handles encrypted/protected documents, empty pages, and malformed streams.
    """
    if not pdf_bytes:
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                logger.warning("PDF is password-protected and could not be decrypted.")
                return ""
        pages_text = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                pages_text.append(t.strip())
        return "\n\n".join(pages_text)
    except Exception as exc:
        logger.error(f"Failed to extract text from PDF: {exc}")
        return ""


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract readable text from DOCX (Word OpenXML) bytes.

    Zero-dependency pure Python implementation using standard zipfile and
    xml.etree.ElementTree parsing word/document.xml.
    """
    if not docx_bytes:
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            if "word/document.xml" not in zf.namelist():
                logger.warning("Invalid DOCX archive: word/document.xml not found.")
                return ""
            xml_bytes = zf.read("word/document.xml")
            tree = ET.fromstring(xml_bytes)
            paragraphs: List[str] = []
            for elem in tree.iter():
                if elem.tag.endswith("}p"):
                    text_nodes = [
                        node.text
                        for node in elem.iter()
                        if elem.tag.endswith("}p")
                        and node.tag.endswith("}t")
                        and node.text
                    ]
                    if text_nodes:
                        paragraphs.append("".join(text_nodes).strip())
            return "\n".join(p for p in paragraphs if p)
    except Exception as exc:
        logger.error(f"Failed to extract text from DOCX: {exc}")
        return ""


def extract_text_from_txt(txt_bytes: bytes) -> str:
    """Extract text from plain text or markdown bytes with encoding detection."""
    if not txt_bytes:
        return ""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"):
        try:
            return txt_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return txt_bytes.decode("utf-8", errors="ignore")


def extract_text_from_file(
    file_bytes: bytes, filename: str = "", max_chars: int = MAX_RESUME_CHARS
) -> str:
    """Extract raw text from PDF, DOCX, or TXT with 9,000 char token slicing."""
    if not file_bytes:
        return ""

    lower_name = filename.lower()
    if lower_name.endswith(".pdf") or file_bytes.startswith(b"%PDF"):
        raw = extract_text_from_pdf(file_bytes)
    elif lower_name.endswith(".docx") or file_bytes.startswith(b"PK\x03\x04"):
        raw = extract_text_from_docx(file_bytes)
    else:
        raw = extract_text_from_txt(file_bytes)

    # Normalize excessive blank lines and spaces
    cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
    return cleaned[:max_chars]


# ==============================================================================
# 2. Heuristic Profile Extractor (Zero-Cost Offline Fallback)
# ==============================================================================


def synthesize_profile_heuristic(
    raw_text: str, user_id: str = "usr_default"
) -> CandidateProfile:
    """Extract candidate facts using regex patterns and domain heuristics."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    name = "Candidate"
    for idx, candidate in enumerate(lines[:5]):
        if re.match(r"^[A-Za-z\s\.\-']{3,40}$", candidate) and not any(
            candidate.lower().startswith(w)
            for w in (
                "resume",
                "curriculum",
                "cv",
                "page",
                "summary",
                "senior",
                "lead",
                "principal",
                "profile",
                "contact",
                "email",
                "phone",
            )
        ):
            name = candidate
            break

    email = None
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", raw_text)
    if email_match:
        email = email_match.group(0).lower()

    phone = None
    phone_match = re.search(r"(?:\+?61\s?|0)[2-478](?:[ -]?[0-9]){8}", raw_text)
    if phone_match:
        phone = phone_match.group(0)

    # Experience years & Seniority
    exp_years = 3
    exp_matches = re.findall(r"(\d+)\+?\s+years?", raw_text, re.IGNORECASE)
    if exp_matches:
        try:
            years = [int(m) for m in exp_matches if 0 < int(m) < 45]
            if years:
                exp_years = max(years)
        except ValueError:
            pass

    title = ""
    title_keywords = [
        "engineer",
        "developer",
        "architect",
        "lead",
        "specialist",
        "consultant",
        "administrator",
        "analyst",
        "manager",
        "officer",
        "technician",
    ]
    for line in lines[:10]:
        if any(kw in line.lower() for kw in title_keywords) and len(line) < 65:
            if not any(
                sw in line.lower()
                for sw in ("summary", "skills", "experience", "education")
            ):
                title = line.strip()
                break

    if not title:
        title = "Systems & Cloud Engineer"

    # Infer seniority
    title_lower = title.lower()
    if any(k in title_lower for k in ("principal", "staff", "head", "director")):
        seniority = "Principal"
    elif any(k in title_lower for k in ("lead", "manager", "team lead")):
        seniority = "Lead"
    elif "senior" in title_lower or exp_years >= 6:
        seniority = "Senior"
    elif exp_years <= 2 or "junior" in title_lower or "graduate" in title_lower:
        seniority = "Junior"
    else:
        seniority = "Mid"

    # Preferred locations
    locations = []
    for city in ("Melbourne", "Sydney", "Brisbane", "Perth", "Adelaide", "Canberra"):
        if re.search(rf"\b{city}\b", raw_text, re.IGNORECASE):
            state = {
                "Melbourne": "VIC",
                "Sydney": "NSW",
                "Brisbane": "QLD",
                "Perth": "WA",
                "Adelaide": "SA",
                "Canberra": "ACT",
            }.get(city, "AU")
            locations.append(f"{city}, {state}")
    if not locations:
        locations = ["All Australia"]

    # Core skills matching
    matched_skills = set()
    raw_lower = raw_text.lower()
    for skill in COMMON_AUSTRALIAN_SKILLS:
        pattern = rf"\b{re.escape(skill.lower())}\b"
        if re.search(pattern, raw_lower):
            matched_skills.add(skill)

    # Target titles
    target_titles = [title]
    if seniority in ("Senior", "Lead") and not title.lower().startswith("senior"):
        target_titles.insert(0, f"Senior {title}")
    if "Cloud" in title or "AWS" in matched_skills or "Azure" in matched_skills:
        if "Cloud Engineer" not in target_titles:
            target_titles.append("Cloud Infrastructure Engineer")
    if (
        "Systems" in title
        or "Linux" in matched_skills
        or "Windows Server" in matched_skills
    ):
        if "Systems Engineer" not in target_titles:
            target_titles.append("Senior Systems Engineer")

    # Experience summary
    summary = ""
    summary_match = re.search(
        r"(?:summary|profile|about me|professional summary)[:\s]*\n+(.*?)(?=\n+[A-Z][a-zA-Z\s]+:|\Z)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        extracted = summary_match.group(1).strip()
        summary = " ".join(extracted.split()[:80])
    if not summary:
        summary = (
            f"Accomplished {seniority} {title} with {exp_years}+ years of expertise "
            f"delivering resilient technology solutions across Australian enterprise environments."
        )

    # Target salary baseline (AUD)
    salary_map = {
        "Junior": 75000.0,
        "Mid": 110000.0,
        "Senior": 145000.0,
        "Lead": 175000.0,
        "Principal": 210000.0,
        "Executive": 240000.0,
    }
    target_salary_min = salary_map.get(seniority, 120000.0)

    return CandidateProfile(
        user_id=user_id,
        name=name,
        email=email,
        phone=phone,
        seniority=seniority,
        target_titles=target_titles[:6],
        core_skills=sorted(list(matched_skills)),
        experience_summary=summary,
        preferred_locations=locations,
        target_salary_min=target_salary_min,
    )


# ==============================================================================
# 3. Structured Fact Extrapolation via OpenRouter LLM
# ==============================================================================

PROFILE_EXTRACTION_SYSTEM_PROMPT = """You are an expert career intelligence and resume parsing engine for the Australian job market.
Your task is to analyze candidate resume text and extract key professional facts into a standardized JSON profile.

CRITICAL INSTRUCTIONS:
1. Extract candidate facts accurately and truthfully based solely on the provided resume text.
2. Standardize Australian locations to 'City, State' format (e.g., 'Melbourne, VIC', 'Sydney, NSW', 'Brisbane, QLD', 'Perth, WA', 'Adelaide, SA', 'Canberra, ACT', or 'All Australia' / 'Remote').
3. Infer seniority ('Junior', 'Mid', 'Senior', 'Lead', 'Principal', 'Manager', 'Executive') based on years of experience and role titles:
   - 0-2 years -> 'Junior'
   - 3-5 years -> 'Mid'
   - 6-9 years -> 'Senior'
   - 10+ years or team leadership -> 'Lead' or 'Principal'
4. Generate 3 to 6 high-relevance 'target_titles' that match the candidate's core expertise.
5. Extract 10 to 25 'core_skills' (languages, cloud platforms, tools, frameworks, architectures).
6. Provide an 'experience_summary' (2-4 sentences) capturing career focus, enterprise scale, and primary achievements.
7. If target salary is not explicitly stated, estimate 'target_salary_min' in AUD based on seniority and market rates (Junior: 75000, Mid: 110000, Senior: 145000, Lead: 175000, Principal: 210000).
8. Return ONLY a single valid JSON object adhering to the schema below. Do NOT output markdown code fences, backticks, commentary, or explanations.

JSON SCHEMA:
{
  "name": "string",
  "email": "string or null",
  "phone": "string or null",
  "seniority": "Junior | Mid | Senior | Lead | Principal | Manager | Executive",
  "target_titles": ["string"],
  "core_skills": ["string"],
  "experience_summary": "string",
  "preferred_locations": ["string"],
  "target_salary_min": number or null
}
"""


def parse_llm_json_response(raw_output: str) -> Dict[str, Any]:
    """Resiliently parse JSON from LLM output, handling markdown backticks and syntax anomalies."""
    if not raw_output or not raw_output.strip():
        return {}

    cleaned = raw_output.strip()

    # 1. Strip markdown fences: ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    # 2. Try direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Locate outermost braces
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        # Remove trailing commas before closing braces/brackets
        candidate = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    logger.warning("Failed to resiliently parse JSON from LLM output.")
    return {}


async def extrapolate_profile_with_llm(
    raw_text: str,
    user_id: str = "usr_default",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> CandidateProfile:
    """Synthesize candidate profile facts using OpenRouter LLM with heuristic fallback."""
    effective_key = (
        api_key or settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
    )
    effective_model = model or settings.DEFAULT_MODEL

    # Slicing input to first 9,000 characters
    truncated_text = raw_text[:MAX_RESUME_CHARS]

    if not effective_key:
        logger.info(
            "OpenRouter API key not configured; using heuristic profile extractor."
        )
        return synthesize_profile_heuristic(truncated_text, user_id=user_id)

    headers = {
        "Authorization": f"Bearer {effective_key}",
        "HTTP-Referer": "https://job-dashboard-light.local",
        "X-Title": "Job Dashboard Light",
        "Content-Type": "application/json",
    }
    payload = {
        "model": effective_model,
        "messages": [
            {"role": "system", "content": PROFILE_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Please parse this candidate resume text into the required profile JSON:\n\n{truncated_text}",
            },
        ],
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 200:
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
                parsed = parse_llm_json_response(content)
                if parsed and parsed.get("target_titles"):
                    return CandidateProfile(
                        user_id=user_id,
                        name=str(parsed.get("name") or "Candidate"),
                        email=parsed.get("email"),
                        phone=parsed.get("phone"),
                        seniority=str(parsed.get("seniority") or "Mid"),
                        target_titles=[str(t) for t in parsed.get("target_titles", [])],
                        core_skills=[str(s) for s in parsed.get("core_skills", [])],
                        experience_summary=str(parsed.get("experience_summary") or ""),
                        preferred_locations=[
                            str(loc)
                            for loc in parsed.get(
                                "preferred_locations", ["All Australia"]
                            )
                        ],
                        target_salary_min=float(parsed["target_salary_min"])
                        if parsed.get("target_salary_min")
                        else None,
                    )
            logger.warning(
                f"OpenRouter returned status {resp.status_code}: {resp.text}"
            )
    except Exception as exc:
        logger.error(f"Error calling OpenRouter for profile extrapolation: {exc}")

    # Fallback to heuristic on any failure
    return synthesize_profile_heuristic(truncated_text, user_id=user_id)


# ==============================================================================
# 4. Dynamic Query Expansion & Negative Keyword Filtering
# ==============================================================================


def detect_query_stream(term: str) -> str:
    """Classifies a search query term into its primary industry stream."""
    lower = str(term or "").lower()
    if re.search(
        r"nurs|health|medic|clinic|patient|aged care|doctor|pharmac|hospital|allied health|physio|dental|midwife",
        lower,
    ):
        return "healthcare"
    if re.search(
        r"account|audit|cpa|\bca\b|tax|financ|bookkeep|payroll|banking|treasury|actuar",
        lower,
    ):
        return "finance"
    if re.search(
        r"construct|builder|site supervisor|site manager|carpenter|electrician|plumber|trade|whs|foreman|estimator|civil",
        lower,
    ):
        return "trades"
    if re.search(
        r"software|engineer|developer|cloud|azure|aws|devops|systems|infra|cyber|network|data|python|react|frontend|backend|platform",
        lower,
    ):
        return "technology"
    if re.search(
        r"legal|lawyer|counsel|paralegal|solicitor|barrister|litigat|compliance", lower
    ):
        return "legal"
    return "general"


def get_default_exclude_terms(seniority: str) -> List[str]:
    """Derive appropriate negative keywords based on seniority level."""
    s = str(seniority).lower()
    if s in ("senior", "lead", "principal", "executive", "manager"):
        return [
            "junior",
            "intern",
            "graduate",
            "entry level",
            "student",
            "trainee",
            "cadet",
        ]
    if s == "mid":
        return ["junior", "intern", "graduate", "trainee"]
    if s == "junior":
        return ["principal", "director", "head of", "lead", "executive"]
    return []


def expand_search_queries(
    profile: CandidateProfile,
    locations: Optional[List[str]] = None,
    custom_exclude_terms: Optional[List[str]] = None,
) -> List[SearchQuery]:
    """Generate expanded SearchQuery objects from target titles, stream classification, and seniority."""
    effective_locations = locations or profile.preferred_locations or ["All Australia"]
    exclude_terms = list(
        set(get_default_exclude_terms(profile.seniority) + (custom_exclude_terms or []))
    )

    expanded_terms: List[str] = []

    # 1. Add primary target titles from profile
    for title in profile.target_titles:
        t_clean = title.strip()
        if t_clean and t_clean not in expanded_terms:
            expanded_terms.append(t_clean)

    # 2. Add domain-template expansions
    joined_context = " ".join(profile.target_titles + profile.core_skills).lower()
    for domain, related_titles in EXPANSION_TEMPLATES.items():
        if domain in joined_context:
            for related in related_titles:
                if len(expanded_terms) >= 8:
                    break
                # Adjust for seniority
                formatted = related
                if profile.seniority in (
                    "Senior",
                    "Lead",
                ) and not related.lower().startswith("senior"):
                    formatted = f"Senior {related}"
                if formatted not in expanded_terms:
                    expanded_terms.append(formatted)

    # 3. Fallback default terms if candidate has empty target titles
    if not expanded_terms:
        expanded_terms = ["Systems Engineer", "Cloud Engineer", "Software Engineer"]

    # 4. Generate deduplicated SearchQuery items
    queries: List[SearchQuery] = []
    seen = set()

    for term in expanded_terms:
        for loc in effective_locations:
            key = (term.lower(), loc.lower())
            if key not in seen:
                seen.add(key)
                queries.append(
                    SearchQuery(
                        term=term,
                        location=loc,
                        stream=detect_query_stream(term),
                        exclude_terms=exclude_terms,
                    )
                )

    return queries


def filter_jobs_by_exclude_terms(
    jobs: Sequence[NormalizedJob], exclude_terms: Sequence[str]
) -> List[NormalizedJob]:
    """Filter out jobs whose titles or tags contain any excluded term (using word-boundary match)."""
    if not exclude_terms:
        return list(jobs)

    compiled_patterns = [
        re.compile(rf"\b{re.escape(term.strip().lower())}\b")
        for term in exclude_terms
        if term.strip()
    ]

    filtered: List[NormalizedJob] = []
    for job in jobs:
        # Check title and explicit tags
        searchable_text = f"{job.title} {' '.join(job.tags)}".lower()
        if any(pattern.search(searchable_text) for pattern in compiled_patterns):
            continue
        filtered.append(job)

    return filtered


# ==============================================================================
# 5. Database Profile Operations
# ==============================================================================


def save_candidate_profile(
    profile: CandidateProfile,
    raw_resume_text: str = "",
    db_path: Optional[str | Path] = None,
) -> CandidateProfile:
    """Persist candidate profile and user identity into SQLite database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Ensure user exists
        cursor.execute(
            """
            INSERT INTO users (id, email, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = COALESCE(excluded.name, users.name),
                email = COALESCE(excluded.email, users.email),
                updated_at = excluded.updated_at;
            """,
            (
                profile.user_id,
                profile.email or f"{profile.user_id}@example.com",
                profile.name or "Candidate",
                now_iso(),
                now_iso(),
            ),
        )

        # 2. Check if phone column exists in user_profiles
        cols = [
            r[1] for r in cursor.execute("PRAGMA table_info(user_profiles)").fetchall()
        ]
        if "phone" not in cols:
            cursor.execute("ALTER TABLE user_profiles ADD COLUMN phone TEXT;")

        # 3. Upsert into user_profiles
        cursor.execute(
            """
            INSERT INTO user_profiles (
                user_id, raw_resume_text, seniority, target_titles, core_skills,
                experience_summary, preferred_locations, target_salary_min, phone, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                raw_resume_text = CASE WHEN excluded.raw_resume_text != '' THEN excluded.raw_resume_text ELSE user_profiles.raw_resume_text END,
                seniority = excluded.seniority,
                target_titles = excluded.target_titles,
                core_skills = excluded.core_skills,
                experience_summary = excluded.experience_summary,
                preferred_locations = excluded.preferred_locations,
                target_salary_min = excluded.target_salary_min,
                phone = excluded.phone,
                updated_at = excluded.updated_at;
            """,
            (
                profile.user_id,
                raw_resume_text,
                profile.seniority,
                json.dumps(profile.target_titles),
                json.dumps(profile.core_skills),
                profile.experience_summary,
                json.dumps(profile.preferred_locations),
                profile.target_salary_min,
                profile.phone,
                now_iso(),
            ),
        )
    return profile


def get_candidate_profile(
    user_id: str, db_path: Optional[str | Path] = None
) -> Optional[CandidateProfile]:
    """Retrieve candidate profile combined with user record from SQLite."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cols = [
            r[1] for r in cursor.execute("PRAGMA table_info(user_profiles)").fetchall()
        ]
        phone_col = "p.phone" if "phone" in cols else "NULL as phone"

        row = cursor.execute(
            f"""
            SELECT
                p.user_id,
                COALESCE(u.name, 'Candidate') as name,
                u.email,
                {phone_col},
                p.seniority,
                p.target_titles,
                p.core_skills,
                p.experience_summary,
                p.preferred_locations,
                p.target_salary_min
            FROM user_profiles p
            LEFT JOIN users u ON u.id = p.user_id
            WHERE p.user_id = ?;
            """,
            (user_id,),
        ).fetchone()

        if not row:
            return None

        def safe_json_list(val: Any) -> List[str]:
            if isinstance(val, str):
                try:
                    res = json.loads(val)
                    return [str(x) for x in res] if isinstance(res, list) else []
                except Exception:
                    return []
            if isinstance(val, (list, tuple)):
                return [str(x) for x in val]
            return []

        return CandidateProfile(
            user_id=row["user_id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            seniority=row["seniority"] or "Mid",
            target_titles=safe_json_list(row["target_titles"]),
            core_skills=safe_json_list(row["core_skills"]),
            experience_summary=row["experience_summary"] or "",
            preferred_locations=safe_json_list(row["preferred_locations"]),
            target_salary_min=row["target_salary_min"],
        )
