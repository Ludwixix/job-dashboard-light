"""
URL Sanitization and Cross-Source Deduplication for Job Dashboard Light.

Functions:
- sanitize_url: Strips tracking queries (utm_*, gclid, fbclid, ref, etc.) and fragments.
- compute_job_dedup_hash: Produces consistent 16-character SHA-256 fingerprint from
  normalized company name, job title, and cleaned URL.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse

# Query parameters to strip during sanitization
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "ref_id",
    "tracking",
    "source",
    "trackingid",
    "campaignid",
    "spref",
}


def sanitize_url(url: str) -> str:
    """Strip marketing tracking parameters, campaign identifiers, and fragments."""
    if not url or not str(url).strip():
        return ""

    parsed = urllib.parse.urlparse(str(url).strip())
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)

    cleaned_params = [
        (k, v)
        for k, v in query_params
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]

    cleaned_query = urllib.parse.urlencode(cleaned_params)
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

    cleaned_url = urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            cleaned_query,
            "",  # strip fragment
        )
    )
    return cleaned_url


def _normalize_string(text: str) -> str:
    """Lowercase and strip punctuation/extra whitespace for consistent hashing."""
    if not text:
        return ""
    # Remove non-alphanumeric except spaces
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())


def compute_job_dedup_hash(company: str, title: str, clean_url: str) -> str:
    """Compute a deterministic 16-character SHA-256 hash for cross-source deduplication."""
    norm_company = _normalize_string(company)
    norm_title = _normalize_string(title)
    norm_url = sanitize_url(clean_url).lower()

    content = f"{norm_company}|{norm_title}|{norm_url}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
