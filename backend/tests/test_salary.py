"""
Unit tests for Australian Salary Normalization Engine.
"""

from job_dashboard_light.services.salary import normalize_australian_salary


def test_empty_or_none_salary():
    res1 = normalize_australian_salary(None)
    assert res1.rate_type == "undisclosed"
    assert res1.annualized_midpoint is None
    assert res1.super_rate == 0.115

    res2 = normalize_australian_salary("")
    assert res2.rate_type == "undisclosed"
    assert res2.annualized_midpoint is None


def test_annual_range_standard():
    res = normalize_australian_salary("$120,000 - $140,000")
    assert res.rate_type == "annual"
    assert res.min_amount == 120000.0
    assert res.max_amount == 140000.0
    assert res.annualized_min == 120000.0
    assert res.annualized_max == 140000.0
    assert res.annualized_midpoint == 130000.0
    assert res.super_included is False


def test_annual_k_format_with_plus_super():
    res = normalize_australian_salary("$120k - $140k + super")
    assert res.rate_type == "annual"
    assert res.min_amount == 120000.0
    assert res.max_amount == 140000.0
    # 120k * 1.115 = 133,800
    assert res.annualized_min == 133800.0
    # 140k * 1.115 = 156,100
    assert res.annualized_max == 156100.0
    assert res.annualized_midpoint == 144950.0


def test_hourly_rate_annualization():
    # 38 hrs * 52 wks = 1976 hrs
    # $50/hr -> $98,800
    res = normalize_australian_salary("$50 per hour")
    assert res.rate_type == "hourly"
    assert res.min_amount == 50.0
    assert res.max_amount == 50.0
    assert res.annualized_min == 98800.0
    assert res.annualized_max == 98800.0
    assert res.annualized_midpoint == 98800.0


def test_daily_rate_annualization():
    # 220 working days * $800 = $176,000
    # 220 working days * $1000 = $220,000
    res = normalize_australian_salary("$800 - $1000 a day")
    assert res.rate_type == "daily"
    assert res.min_amount == 800.0
    assert res.max_amount == 1000.0
    assert res.annualized_min == 176000.0
    assert res.annualized_max == 220000.0
    assert res.annualized_midpoint == 198000.0


def test_aps_superannuation_rate():
    # APS uses 15.4% superannuation rate
    res = normalize_australian_salary("$100,000 + super", is_aps=True)
    assert res.super_rate == 0.154
    assert res.annualized_min == 115400.0
    assert res.annualized_max == 115400.0
