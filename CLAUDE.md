# CLAUDE.md – Cyber Project Rules (minimal & portable edition – 2026-01-11)

You are helping build Cyber – a lightweight raid/content coordination tool  
Main components: Discord bot + very simple backend + beautiful dashboard  
Data: Google Sheets (source of truth) + local CSVs (fast views / snapshots)

## Core Philosophy – Repeat this constantly
"Simple beats clever. Portable beats everything. Complexity is the enemy."

If you can solve it with 20 lines instead of 150 → choose 20.  
If the folder can be renamed/moved/cloned anywhere → make sure it still works.

## Sacred Rules (never break these)

1. Google Sheets = only persistent database. No exceptions.
2. Local CSVs = caches / fast/pretty views / backups. Sync must be dead simple.
3. NO absolute paths ANYWHERE (no /root, no /home, no C:\, no D:\...)
   → only relative paths from project root (use pathlib)
4. NO machine-specific things in code (usernames, IPs, drive letters...)
5. Credentials/secrets/tokens/sheet IDs → ONLY from .env file
6. After git clone / git pull → should work after:
   • pip install -r requirements.txt
   • cp .env.example .env && edit .env
   • (maybe one manual sync if needed)
7. Dashboard phase 1 goal = beautiful read-only showcase of Sheets + CSVs
   → keep it stupid simple (Flask/Jinja2/Tailwind or even static HTML+JS)

## Strong technical preferences right now
- Python 3.11+
- Flask > FastAPI (simplicity wins)
- gspread + pandas + csv module → that's the data stack
- python-dotenv for config
- pathlib everywhere for paths
- logging (standard module) → no print() in production code
- Tailwind + minimal vanilla JS or htmx (if dynamic needed)
- Black + ruff + isort (or very close)

## Naming style
Discord commands: short & obvious  
/submit /register /myprofile /raidstats /dashboard-link

Dashboard: clean, dark mode default, big numbers, simple tables/charts

## Current priority order (strict)
1. Make project 100% portable (relative paths, no machine-specific code)
2. Centralize ALL configuration & secrets in .env (+ create good .env.example)
3. Simple & reliable CSV ↔ Google Sheets sync (manual run is acceptable)
4. Beautiful minimal dashboard (read-only views of current data)
5. Make Discord bot happy with same data sources
6. Basic visibility of errors (log file + optional Discord channel)
7. Polish UX, input validation, rate limiting → only after above

## When suggesting changes
- Prefer smallest possible fix that works
- Show before → after style when refactoring
- First solution should be the simplest realistic one
- Only suggest more advanced patterns AFTER I say the simple one hurts

Call me Tony.  
Be brutally pragmatic.  
Portability and simplicity are sacred.

Last updated: 2026-01-11
