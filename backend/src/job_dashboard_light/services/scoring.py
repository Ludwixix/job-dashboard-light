"""
Match Scoring & Skill Gap Analysis Service.
Evaluates candidate profile alignment against job descriptions and requirements.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set


def normalize_skill(skill: str) -> str:
    """Normalize skill string for case- and symbol-insensitive comparison."""
    if not skill:
        return ""
    clean = skill.strip().lower()
    # Normalize synonyms
    synonyms = {
        "k8s": "kubernetes",
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "golang": "go",
        "react.js": "react",
        "vue.js": "vue",
        "node.js": "node",
        "aws cloud": "aws",
        "azure cloud": "azure",
        "gcp cloud": "gcp",
        "google cloud": "gcp",
    }
    return synonyms.get(clean, clean)


def extract_skills_from_text(text: str, candidate_skills: List[str]) -> Set[str]:
    """Identify which candidate skills or general tech skills are mentioned in text."""
    if not text:
        return set()
    text_lower = text.lower()
    found: Set[str] = set()

    for skill in candidate_skills:
        clean = normalize_skill(skill)
        if not clean:
            continue
        # Word boundary or special symbol boundary
        escaped = re.escape(clean)
        pattern = rf"(?:\b|(?<=[^a-zA-Z0-9])){escaped}(?:\b|(?=[^a-zA-Z0-9]))"
        if re.search(pattern, text_lower):
            found.add(skill)

    return found


def calculate_match_score(
    job: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate 0-100% match score and breakdown between candidate and job posting.

    Components:
    - Skill alignment (up to 55 points):
      Percentage of profile core skills present in job description/tags.
    - Title / Role alignment (up to 25 points):
      Overlap between target titles and job title.
    - Seniority alignment (up to 10 points):
      Matching Junior, Mid, Senior, Lead, Executive levels.
    - Location preference (up to 10 points):
      Job location matches preferred locations or is 'All Australia' / Remote.
    """
    profile_skills: List[str] = profile.get("core_skills") or profile.get("skills") or []
    target_titles: List[str] = profile.get("target_titles") or []
    candidate_seniority: str = (profile.get("seniority") or "Mid").lower()
    preferred_locations: List[str] = profile.get("preferred_locations") or []

    job_title: str = job.get("title", "")
    job_desc: str = job.get("description", "")
    job_location: str = job.get("location", "All Australia")
    job_tags: List[str] = job.get("tags") or []
    full_job_text = f"{job_title} {job_desc} {' '.join(job_tags)}".lower()

    # 1. Skill scoring
    matched_skills: List[str] = []
    missing_skills: List[str] = []

    if profile_skills:
        for skill in profile_skills:
            clean = normalize_skill(skill)
            if not clean:
                continue
            escaped = re.escape(clean)
            pattern = rf"(?:\b|(?<=[^a-zA-Z0-9])){escaped}(?:\b|(?=[^a-zA-Z0-9]))"
            if re.search(pattern, full_job_text):
                matched_skills.append(skill)
            else:
                missing_skills.append(skill)

        skill_ratio = len(matched_skills) / len(profile_skills)
        skill_score = skill_ratio * 55.0
    else:
        # Default baseline if candidate has not listed skills yet
        skill_score = 30.0

    # 2. Title alignment (25 points)
    title_score = 0.0
    job_title_lower = job_title.lower()
    if target_titles:
        for target in target_titles:
            target_clean = target.strip().lower()
            if not target_clean:
                continue
            # Direct or partial token overlap
            target_words = set(re.findall(r"\w+", target_clean))
            job_title_words = set(re.findall(r"\w+", job_title_lower))
            if target_clean in job_title_lower:
                title_score = 25.0
                break
            elif target_words and target_words.issubset(job_title_words):
                title_score = max(title_score, 20.0)
            elif len(target_words & job_title_words) >= 1:
                title_score = max(title_score, 12.0)
    else:
        title_score = 15.0

    # 3. Seniority alignment (10 points)
    seniority_score = 5.0
    seniority_map = {
        "junior": ["junior", "entry level", "graduate", "associate"],
        "mid": ["mid", "intermediate", "experienced", "engineer", "specialist"],
        "senior": ["senior", "sr", "lead", "principal", "staff"],
        "lead": ["lead", "manager", "head", "director", "architect"],
    }
    target_levels = seniority_map.get(candidate_seniority, [candidate_seniority])
    if any(level in job_title_lower for level in target_levels):
        seniority_score = 10.0
    elif any(level in full_job_text for level in target_levels):
        seniority_score = 8.0

    # 4. Location alignment (10 points)
    location_score = 5.0
    if not preferred_locations or "All Australia" in preferred_locations or "Australia" in preferred_locations:
        location_score = 10.0
    else:
        job_loc_lower = job_location.lower()
        if any(pref.lower() in job_loc_lower or job_loc_lower in pref.lower() for pref in preferred_locations):
            location_score = 10.0
        elif "remote" in job_loc_lower or "hybrid" in job_loc_lower:
            location_score = 8.0

    total_score = min(100.0, max(0.0, skill_score + title_score + seniority_score + location_score))

    # Formulate quick reason summary
    if total_score >= 80:
        fit = "Strong Match"
    elif total_score >= 60:
        fit = "Good Fit"
    elif total_score >= 40:
        fit = "Moderate Fit"
    else:
        fit = "Stretch Role"

    return {
        "score": round(total_score, 1),
        "fit": fit,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "breakdown": {
            "skills": round(skill_score, 1),
            "title": round(title_score, 1),
            "seniority": round(seniority_score, 1),
            "location": round(location_score, 1),
        },
    }
