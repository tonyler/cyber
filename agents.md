# agents.md – Instructions for ALL AI coding agents – Cyber

Current date: January 11, 2026

Project mindset:

"Make it simple. Make it portable. Make it beautiful. Nothing else matters yet."

## Absolute constraints
1. Google Sheets = source of truth
2. Local CSVs = fast access / snapshots / pretty views
3. Dashboard = pretty read-only viewer of existing data (phase 1 goal)
4. NO new databases, queues, caches, auth systems, heavy frameworks
5. NO absolute paths, NO machine-specific code
6. Secrets/config → .env file ONLY (never in git)
7. After git clone → should work after pip install + .env setup

## Preferred stack (minimal & pragmatic – Jan 2026)
- Python 3.11+
- Flask (simplicity) or FastAPI (if you must)
- gspread + pandas + csv
- python-dotenv
- pathlib for all paths
- Jinja2 + Tailwind CSS + minimal JS / htmx
- Standard logging

## Priority order – do NOT jump ahead
1. Portability (relative paths, no hardcoded locations, works when folder renamed/moved)
2. Configuration & secrets (everything from .env, good .env.example)
3. Simple CSV ↔ Google Sheets sync (manual trigger ok)
4. Clean, beautiful dashboard – read-only views first
5. Discord bot integration with same data
6. Error visibility (logs)
7. UX polish, validation, protection → later

## How to help me best
- First solution = the simplest one that could possibly work
- Only show more complex patterns after I complain about the simple one
- Prefer short files, short functions
- Use relative paths (pathlib) – always
- When suggesting config → update .env.example too
- Call me Tony

Keep it stupid simple.  
Thanks.
