# To Fix

This file is a handoff for another LLM. It is based on code inspection plus recent logs under `logs/` as of 2026-04-24 UTC.

## Scope

Focus on issues that have clearly surfaced during the last days/weeks, not general cleanup.

## Highest Priority

### 1. X scraper is effectively broken for recent runs and is no longer extracting replies, quotes, reposts, or tweet metrics

Severity: critical

Impact:
- Since at least 2026-03-31, the X pipeline has mostly produced zero extracted activity for recent links.
- March and April links in `database/links.csv` have no populated `impressions`.
- `database/x_activity_log.csv` stops at 2026-02-05, so member activity tracking has been dead for weeks.

Evidence:
- `logs/scrapers.log` and rotated `logs/cyber.log*` contain repeated warnings every day from 2026-03-31 through 2026-04-24:
  - `No tweet elements found on ...; skipping replies.`
  - `No quote tweet elements found on ...; skipping quotes.`
  - `No repost user cells found on ...; skipping reposts.`
  - `No tweet article found on ...`
- Daily counts from the logs are very high. Example:
  - 2026-04-23: `No tweet elements found` 2236 times
  - 2026-04-23: `No tweet article found` 2234 times
  - 2026-04-24: same failure pattern continues
- `database/links.csv` summary:
  - `2026-01`: 66 rows, 53 with nonzero impressions
  - `2026-02`: 117 rows, 33 with nonzero impressions
  - `2026-03`: 68 rows, 0 with nonzero impressions
  - `2026-04`: 71 rows, 0 with nonzero impressions
- `database/x_activity_log.csv` last activity is from 2026-02-05.

Likely cause:
- The scraper is tied to fragile mobile/X selectors and page assumptions that no longer hold.
- The browser is forced into iPhone mode in [scrapers/base_scraper.py](/root/cyber/scrapers/base_scraper.py:58).
- URLs are normalized to `https://x.com/i/status/<id>` in [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:155).
- Activity extraction depends on `article` and `[data-testid="UserCell"]` in [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:348), [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:400), [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:448), and `_find_target_article` in [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:493).
- Metrics extraction also depends on finding the target `article` and aria-labels inside it in [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:545).

What to do:
- Rework X navigation and selectors against the current live DOM.
- Do not assume `article` and `UserCell` exist in mobile mode.
- Validate whether `i/status/<id>` still yields a stable DOM for authenticated sessions. If not, keep canonical author/status URLs instead of rewriting to `i/status`.
- Add explicit detection/logging for cases like login wall, rate limit, interstitial, unsupported layout, or challenge page so the scraper can distinguish “page shape changed” from “zero activities”.
- Add a fallback strategy:
  - try authenticated desktop context first, or
  - support both mobile and desktop selector sets.
- Verify that metrics are still extracted when activities are zero.

Acceptance criteria:
- Scraping a recent April X link populates `impressions` and engagement fields in `database/links.csv`.
- At least one recent link produces nonzero extracted activities or a clear, classified failure reason.
- `database/x_activity_log.csv` starts receiving new rows again for current-month links.
- The repeated `No tweet elements found` / `No tweet article found` storm disappears from logs.

### 2. Reddit comment scraping is also failing on recent URLs, especially share and redirect-style URLs

Severity: high

Impact:
- Reddit posts are being processed, but comment extraction is usually zero.
- Member Reddit activity is not being captured.
- `database/reddit_activity_log.csv` does not currently exist.

Evidence:
- `logs/scrapers.log` and `logs/cyber.log.1` repeatedly show:
  - `No Reddit comment elements found on https://old.reddit.com/...; skipping.`
- This happens across many recent URLs, including `/s/` share URLs and normal post URLs.
- Daily counts are also high:
  - 2026-04-23: 494 occurrences
  - 2026-04-24: 182 occurrences already by the captured log point

Likely cause:
- The scraper converts everything to `old.reddit.com` via [scrapers/reddit_scraper.py](/root/cyber/scrapers/reddit_scraper.py:53), then assumes comments are available via `.comment` in [scrapers/reddit_scraper.py](/root/cyber/scrapers/reddit_scraper.py:137).
- For `/s/` share links, `scrape_post_metrics()` resolves redirects first in [scrapers/reddit_scraper.py](/root/cyber/scrapers/reddit_scraper.py:69), but `scrape_reddit_comments()` does not do equivalent canonicalization before selecting comments in [scrapers/reddit_scraper.py](/root/cyber/scrapers/reddit_scraper.py:127).
- The current selectors likely no longer match all current old/new Reddit render paths.

What to do:
- Canonicalize Reddit URLs before both metrics scraping and comment scraping.
- Resolve `/s/` share links and any other redirect format before extracting comments.
- Support both old and current Reddit DOMs if needed instead of assuming `.comment` exists.
- Add page-state detection for deleted/removed/quarantined/login/interstitial pages.
- Only write zero metrics when the page was actually parsed successfully; otherwise classify the scrape as failed.

Acceptance criteria:
- A recent Reddit `/s/` link resolves to a canonical post URL and yields either extracted comments or a classified non-data failure.
- `database/reddit_activity_log.csv` is created when recent member comments are found.
- The repeated `No Reddit comment elements found` warnings stop dominating the scraper logs.

## Medium Priority

### 3. Monthly KPI snapshots are writing misleading zeroes for March and April instead of surfacing upstream scrape failure

Severity: medium

Impact:
- Dashboard monthly performance charts are misleading.
- The system currently records “0 views” and “0 actions” as if those were real measurements, when the upstream scrapers appear broken.

Evidence:
- `logs/monthly_views.log` records zeroes every day from at least 2026-03-16 through 2026-04-24:
  - `Recorded views snapshot for 2026-04-24: total=0 (Δ=0)`
  - `Recorded actions for 2026-04: 0 total across 0 days`
- `database/monthly_views/2026-03-views.csv` and `database/monthly_views/2026-04-views.csv` contain day-by-day zero totals.
- `database/monthly_actions/2026-03-actions.csv` and `database/monthly_actions/2026-04-actions.csv` contain only the header row.

Likely cause:
- The snapshot jobs are functioning mechanically, but they derive their totals from already-empty upstream data:
  - views from `database/links.csv` in [scripts/monthly_views_snapshot.py](/root/cyber/scripts/monthly_views_snapshot.py:73)
  - actions from activity logs in [scripts/monthly_actions_snapshot.py](/root/cyber/scripts/monthly_actions_snapshot.py:59)
- There is no health check or “data freshness” guard before writing zeros.

What to do:
- Treat “no scrape data exists for current month” differently from “real total is zero”.
- Add a data-freshness check before writing month snapshots.
- If there are current-month links but all impressions are blank and no current-month activities exist, write a warning and skip the snapshot or mark it as stale/unknown.
- Consider storing status metadata alongside snapshots so the dashboard can show “data unavailable” instead of plotting zero.

Acceptance criteria:
- March/April-style scraper outages no longer silently turn into believable zero-value charts.
- Snapshot logs explicitly say when data is stale, missing, or blocked upstream.

### 4. Sync worker only backs up X activity rows, so recent Reddit activity and dashboard-style monthly stats are not represented in Google Sheets backup

Severity: medium

Impact:
- Sync logs currently report only January and February activity tab backups, because `x_activity_log.csv` stops in February.
- Even after scraper fixes, Reddit activity is not included in the current backup routine.
- Monthly summary CSVs are also local-only.

Evidence:
- `logs/sync_daemon.log` repeatedly shows:
  - `Backed up activities to 01/26: 675 updated, 0 added`
  - `Backed up activities to 02/26: 274 updated, 0 added`
- It never reports March or April activity tabs.
- The backup implementation reads only `database/x_activity_log.csv` in [scripts/sync_worker.py](/root/cyber/scripts/sync_worker.py:272).

Likely cause:
- `backup_activities_to_sheets()` only uploads X activity rows and ignores `database/reddit_activity_log.csv`.
- This may have been acceptable initially, but it no longer matches the rest of the system, which tracks both X and Reddit contributions.

What to do:
- Expand backup logic to include Reddit activity, with a sheet format decision that preserves platform information.
- Decide whether monthly summaries should also be synced or whether Sheets should recompute them from raw activity/tasks.
- Make logs explicit about which sources are being backed up.

Acceptance criteria:
- After scraper fixes, sync logs reflect current-month activity tabs.
- Reddit activity is no longer omitted from the backup pipeline.

## Low Priority / Verify Before Changing

### 5. Dashboard startup failure on 2026-03-31 may be environment-specific, not necessarily a code defect

Severity: low

Evidence:
- `logs/dashboard3.log` shows:
  - startup at 2026-03-31 12:38:59
  - `PermissionError: [Errno 1] Operation not permitted`
- The bind call is in [dashboard3/app.py](/root/cyber/dashboard3/app.py:509).

Notes:
- This may have happened because the process was started in a restricted environment where binding a socket was not allowed.
- Do not spend time on this until the scraper/data issues above are handled, unless the dashboard is currently failing in production too.

## Useful Starting Files

- [scrapers/base_scraper.py](/root/cyber/scrapers/base_scraper.py:41)
- [scrapers/x_scraper.py](/root/cyber/scrapers/x_scraper.py:155)
- [scrapers/reddit_scraper.py](/root/cyber/scrapers/reddit_scraper.py:53)
- [scripts/monthly_views_snapshot.py](/root/cyber/scripts/monthly_views_snapshot.py:64)
- [scripts/monthly_actions_snapshot.py](/root/cyber/scripts/monthly_actions_snapshot.py:59)
- [scripts/sync_worker.py](/root/cyber/scripts/sync_worker.py:266)

## Suggested Fix Order

1. Fix X scraping and validate on one recent April link.
2. Fix Reddit comment scraping and validate on one recent Reddit `/s/` link.
3. Re-run the scrapers and confirm current-month data starts appearing in `links.csv`, `x_activity_log.csv`, and optionally `reddit_activity_log.csv`.
4. Update monthly snapshot logic so it no longer records silent zeroes during scraper outages.
5. Expand sync backup coverage once raw data flow is healthy again.
