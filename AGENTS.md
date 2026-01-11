# agents.md – Instructions for ALL coding agents

Project mindset for Cyber (Jan 2026):

"Beautiful simplicity > perfect architecture"

## Sacred Rules
1. Google Sheets = database
2. CSVs = fast/pretty views / backups
3. Dashboard = pretty HTML viewer of Sheets + CSVs (phase 1 goal)
4. Backend exists **only** to:
   - serve dashboard
   - do CSV↔Sheets sync when needed
5. No databases, no redis, no celery, no message queues, no kubernetes
6. No auth system until it becomes painful not to have one

## Preferred stack right now (minimal)
- Flask or FastAPI (Flask preferred for simplicity)
- gspread + pandas + csv
- Jinja2 + Tailwind + htmx (optional but loved)
- Vanilla JS or Alpine.js at most
- .env + python-dotenv

## Priority order (very strict)
1. Fix secrets/config exposure
2. Simple & reliable CSV ↔ Sheets sync (even manual trigger is ok)
3. Beautiful dashboard – big numbers, clean tables, dark mode
4. Make Discord bot happy with same data sources
5. Basic error visibility (logs)
6. Polish & user experience
7. Only much later: automation, rate limiting, tests, etc.

## How to help me best
- First solution you propose should be **the simplest possible** that works
- Only show me more advanced patterns after I say "this is getting painful"
- Use short files, short functions
- Prefer copy-paste friendly code

Call me Tony.  
Keep it stupid simple.  
Thanks.
