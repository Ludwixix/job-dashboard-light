# System Architecture — Job Dashboard Light

## Core Principles
1. **Unified Scraper Adapter**: All scrapers (Seek, Indeed, LinkedIn, Adzuna, Careers Vic, APS Jobs) implement the `BaseJobSource` protocol (`search`, `get_details`, `check_expired`, `health_check`).
2. **Database-First Ingestion**: Coalesce simultaneous searches with single-flight coordinator; return local matches (<21 days, >=10 jobs) before external network requests.
3. **SQLite WAL & GCS Backup**: High-concurrency WAL mode (`jobs.sqlite3`) with FTS5 inverted text index, synchronized to dedicated GCS bucket (`acaa-agent-job-dashboard-light-data`) on startup and SIGTERM via atomic WAL TRUNCATE and generation-checked optimistic concurrency.
4. **Data Isolation**: Public deduplicated jobs pool paired with strictly private user profiles, tailored documents, and Kanban tracker stages.
5. **Australian Career Specializations**: Australian salary normalization engine, Australian Key Selection Criteria (KSC) STAR generator (APS ILS / VPSC), and 1-click Markdown / PDF export.
