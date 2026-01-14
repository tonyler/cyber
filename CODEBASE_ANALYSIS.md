# Codebase Analysis (Cyber)

## Rating
**6.5 / 10**

Strong MVP velocity and useful pipelines, but expansion is held back by mixed sources of truth, duplicated sync paths, and a few portability/security violations.

## What is working well
- Clear separation of concerns between dashboards, scrapers, and sync workers.
- CSV locking utilities are solid and used correctly in most data-write paths.
- Sheets parsing is pragmatic and handles column drift reasonably well.
- Scraper logic is robust in the face of dynamic pages (scroll, retries, fallbacks).

## Key risks and friction points (expansion blockers)
1. **Source of truth drift**: Sheets, CSVs, and local updates can diverge.
   - `scrapers/x_scraper.py` writes both to Sheets and CSVs; `scripts/sync_worker.py` also pushes CSV -> Sheets for X activity.
   - `scripts/generate_titles.py` writes only to `database/coordinated_tasks.csv` and never syncs back to Sheets.
2. **Credentials dependence conflicts with the new requirement**:
   - X scraper relies on `shared/x_session.json` cookies (login state). That violates “no credentials ever needed.”
   - Title generation requires OpenAI/Groq API keys.
   - Google Sheets access uses a service account JSON. This is also a credential and conflicts unless you intend to exempt Sheets access. This needs an explicit decision.
3. **Portability violations**:
   - `scripts/normalize_tasks_sheet.py` hardcodes `Path("/root/cyber")`.
4. **Multiple sync strategies**:
   - `dashboard/sync_service.py` and `scripts/sync_worker.py` overlap but follow different patterns, increasing maintenance cost.
5. **Implicit config and secrets**:
   - Hard-coded Flask `SECRET_KEY` values in `dashboard/app.py` and `dashboard2/app.py`.
   - `.env` handling is duplicated across scripts.
6. **Write-path consistency**:
   - Some CSV writes bypass `locked_csv` and can race with other processes (e.g., `_update_task_content_csv` in `scrapers/x_scraper.py`).

## Proposed changes (aligned with requirements)
### 1) Enforce one online source of truth (Google Sheets)
- **Rule**: All authoritative writes go to Sheets; local CSVs are read-only snapshots used for fast dashboard reads.
- Remove CSV -> Sheets flow in `scripts/sync_worker.py` (`_sync_x_activity_csv_to_sheet`).
- Ensure scrapers only write activities to Sheets; then run a single sync to refresh CSVs.
- Add a *manual sync trigger* (CLI or dashboard button) that pulls from Sheets on demand.

### 2) “No credentials ever needed” for scraping
- Replace X cookie session usage with anonymous scraping approaches:
  - Use the public syndication endpoint (tweet ID -> JSON) for metrics and content where possible.
  - Use non-auth HTML scraping for replies/quotes/reposts (accept reduced coverage if needed).
- Make `shared/x_session.json` optional and disabled by default.
- **Clarification needed**: If “no credentials ever needed” applies to Sheets too, then the only viable path is a public Sheet plus an unauthenticated write mechanism (e.g., Apps Script web app with no auth). That weakens integrity and should be explicitly approved. If Sheets credentials are acceptable, keep the service account for write access.

### 3) Keep local CSV and Sheets in complete harmony
- Implement a single **sync pipeline** (Sheets -> CSV only):
  - Pull Sheets -> CSVs on schedule and on demand.
  - Store `synced_at` timestamps in CSV rows for audit.
  - Use a row hash or stable ID to avoid re-adding duplicates.
- For fields generated locally (e.g., `title` or scraped `content`), write them back to the Sheets instead of only CSV.

### 4) Consolidate configuration and paths
- Create `shared/config.py` for:
  - `PROJECT_ROOT`
  - `.env` loading once
  - Sheet IDs and credential paths
- Replace hardcoded `/root/cyber` and inline `.env` parsing with a shared helper.

### 5) Simplify sync surface area
- Choose one sync entry point (prefer `scripts/sync_worker.py`) and remove/retire `dashboard/sync_service.py` if unused.
- Normalize column naming across Sheets and CSVs and document the mapping in one place.

### 6) Minor reliability and security improvements
- Move Flask `SECRET_KEY` to `.env` (still optional for read-only), and update `.env.example`.
- Use `locked_csv` in `_update_task_content_csv` to prevent races.
- Add a “dry-run” mode for any script that modifies Sheets.

## Suggested next steps (if you want me to implement)
1. Lock in the authoritative data flow (Sheets -> CSV only; CSV remains the dashboard cache).
2. Remove X session cookie dependency and replace with anonymous scraping paths.
3. Decide whether Sheets credentials are allowed under “no credentials ever needed.”
4. Centralize config and path handling; delete hardcoded paths.
5. Add a single `sync` CLI (manual + scheduled) and wire dashboard refresh to it.
