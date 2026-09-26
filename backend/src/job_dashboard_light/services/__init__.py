"""Core business logic, synchronization, and AI services."""

from .coordinator import ScrapeCoordinator
from .dedup import compute_job_dedup_hash, sanitize_url
from .expiry import run_hybrid_expiry_check
from .export import export_markdown, export_pdf_bytes, sanitize_filename
from .ksc import (
    extract_ksc_from_jd,
    generate_ksc_report,
    generate_ksc_statements,
    generate_star_statement,
    map_ksc_to_capability_framework,
)
from .llm import (
    DEFAULT_MODEL_ID,
    DELIMITER_COVER_LETTER,
    DELIMITER_KSC,
    DELIMITER_RESUME,
    MODEL_PRESETS,
    OpenRouterAPIError,
    OpenRouterAuthError,
    OpenRouterClient,
    OpenRouterError,
    OpenRouterRateLimitError,
    audit_cover_letter_swappability,
    extract_delimited_content,
    generate_polarized_cover_letter,
    generate_tailored_cv,
    localize_australian,
)
from .profile import (
    expand_search_queries,
    extract_text_from_file,
    extrapolate_profile_with_llm,
    filter_jobs_by_exclude_terms,
    get_candidate_profile,
    save_candidate_profile,
    synthesize_profile_heuristic,
)
from .salary import normalize_australian_salary
from .storage import StorageService, get_storage_service
from .verifier import batch_verify_urls, clear_verify_cache, verify_job_url, verify_job_urls

__all__ = [
    "StorageService",
    "get_storage_service",
    "normalize_australian_salary",
    "sanitize_url",
    "compute_job_dedup_hash",
    "ScrapeCoordinator",
    "OpenRouterClient",
    "OpenRouterError",
    "OpenRouterAuthError",
    "OpenRouterRateLimitError",
    "OpenRouterAPIError",
    "MODEL_PRESETS",
    "DEFAULT_MODEL_ID",
    "DELIMITER_RESUME",
    "DELIMITER_COVER_LETTER",
    "DELIMITER_KSC",
    "localize_australian",
    "extract_delimited_content",
    "audit_cover_letter_swappability",
    "generate_tailored_cv",
    "generate_polarized_cover_letter",
    "generate_ksc_report",
    "generate_ksc_statements",
    "generate_star_statement",
    "map_ksc_to_capability_framework",
    "extract_ksc_from_jd",
    "export_markdown",
    "export_pdf_bytes",
    "sanitize_filename",
    "verify_job_url",
    "verify_job_urls",
    "batch_verify_urls",
    "clear_verify_cache",
    "run_hybrid_expiry_check",
    "extract_text_from_file",
    "extrapolate_profile_with_llm",
    "get_candidate_profile",
    "save_candidate_profile",
    "expand_search_queries",
    "filter_jobs_by_exclude_terms",
    "synthesize_profile_heuristic",
]
