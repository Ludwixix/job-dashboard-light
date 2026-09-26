"""
Australian Salary Normalization Engine for Job Dashboard Light.

Converts Australian salary representations into standardized annualized values:
- Hourly rates ($45/hr, $70 - $90 per hour) -> annualized (amount * 38 hrs * 52 wks = 1976 hrs)
- Daily rates ($600/day, $800-$1000 daily) -> annualized (amount * 220 standard work days)
- Annual packages ($120k - $150k, $120,000 - $140,000)
- Superannuation handling:
    - Standard AU superannuation guarantee: 11.5% (super_rate = 0.115)
    - APS (Australian Public Service) superannuation: 15.4% (super_rate = 0.154)
    - Distinguishes "super included" / "package" from explicit "+ super" / "plus super"
"""

from __future__ import annotations

import re
from typing import Optional

from ..models import SalaryAnalysis

# Regex patterns for rate period detection
HOURLY_PATTERN = re.compile(r"\b(?:hr|hour|p/?h|per\s+hour)\b", re.IGNORECASE)
DAILY_PATTERN = re.compile(r"\b(?:day|daily|p/?d|per\s+day)\b", re.IGNORECASE)
ANNUAL_PATTERN = re.compile(r"\b(?:annum|annual|year|yearly|p/?a|per\s+annum)\b", re.IGNORECASE)

# Superannuation detection
PLUS_SUPER_PATTERN = re.compile(
    r"(?:\+\s*super|plus\s*super|\+\s*superannuation|plus\s*superannuation|excl(?:usive)?\s*(?:of)?\s*super)",
    re.IGNORECASE,
)
INC_SUPER_PATTERN = re.compile(
    r"(?:inc(?:luding|lusive)?\s*(?:of)?\s*super|package|total\s*remuneration|total\s*package)",
    re.IGNORECASE,
)

# Number extraction patterns (e.g. $120k, $120,000, 120000, 75.50)
AMOUNT_PATTERN = re.compile(
    r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(k)?\b", re.IGNORECASE
)


def _clean_amount(num_str: str, has_k: bool) -> float:
    """Parse string representation of number to float, accounting for 'k' suffix."""
    val = float(num_str.replace(",", ""))
    if has_k:
        val *= 1000.0
    return val


def normalize_australian_salary(salary_text: Optional[str], is_aps: bool = False) -> SalaryAnalysis:
    """Normalize any Australian salary string into standardized annualized figures."""
    super_rate = 0.154 if is_aps else 0.115

    if not salary_text or not str(salary_text).strip():
        return SalaryAnalysis(
            raw_salary="",
            min_amount=None,
            max_amount=None,
            annualized_min=None,
            annualized_max=None,
            annualized_midpoint=None,
            rate_type="undisclosed",
            super_included=False,
            super_rate=super_rate,
        )

    raw = str(salary_text).strip()

    # Detect explicit super details
    has_plus_super = bool(PLUS_SUPER_PATTERN.search(raw))
    has_inc_super = bool(INC_SUPER_PATTERN.search(raw))
    super_included = has_inc_super and not has_plus_super

    # Extract numerical figures
    matches = AMOUNT_PATTERN.findall(raw)
    parsed_numbers: list[float] = []
    for num_str, k_suffix in matches:
        try:
            amount = _clean_amount(num_str, bool(k_suffix))
            # Filter out tiny numbers (e.g. hours or days misidentified) unless hourly
            if amount > 10:
                parsed_numbers.append(amount)
        except ValueError:
            continue

    if not parsed_numbers:
        return SalaryAnalysis(
            raw_salary=raw,
            min_amount=None,
            max_amount=None,
            annualized_min=None,
            annualized_max=None,
            annualized_midpoint=None,
            rate_type="undisclosed",
            super_included=super_included,
            super_rate=super_rate,
        )

    min_val = min(parsed_numbers)
    max_val = max(parsed_numbers)

    # Determine rate period
    is_hourly = bool(HOURLY_PATTERN.search(raw))
    is_daily = bool(DAILY_PATTERN.search(raw))
    is_annual = bool(ANNUAL_PATTERN.search(raw))

    if is_hourly:
        rate_type = "hourly"
    elif is_daily:
        rate_type = "daily"
    elif is_annual:
        rate_type = "annual"
    else:
        # Heuristic determination based on magnitudes
        if max_val < 300:
            rate_type = "hourly"
        elif 300 <= max_val <= 3000:
            rate_type = "daily"
        else:
            rate_type = "annual"

    # Annualization multiplier:
    # Hourly: 38 hours/week * 52 weeks = 1,976 hours
    # Daily: 220 working days/year
    # Annual: 1.0
    if rate_type == "hourly":
        multiplier = 38.0 * 52.0
    elif rate_type == "daily":
        multiplier = 220.0
    else:
        multiplier = 1.0

    ann_min = min_val * multiplier
    ann_max = max_val * multiplier

    # If salary was stated as '+ super', add superannuation to annualized total
    if has_plus_super:
        ann_min *= 1.0 + super_rate
        ann_max *= 1.0 + super_rate

    midpoint = (ann_min + ann_max) / 2.0

    return SalaryAnalysis(
        raw_salary=raw,
        min_amount=min_val,
        max_amount=max_val,
        annualized_min=round(ann_min, 2),
        annualized_max=round(ann_max, 2),
        annualized_midpoint=round(midpoint, 2),
        rate_type=rate_type,
        super_included=super_included,
        super_rate=super_rate,
    )
