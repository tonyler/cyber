# CLAUDE.md – Cyber Project Rules (minimal & pragmatic edition – Jan 2026)

Cyber = Discord interaction + very simple backend + beautiful data showcase  
Goal: Maximum value with minimum code & complexity.

## Core Philosophy – Repeat This To Yourself
"Simple is violently preferable to clever."
If you can solve it with 30 lines instead of 300 → do the 30.
If Google Sheets + CSV already contain the data → don't create new storage.
If something can be a static page or simple template → don't make it dynamic yet.

## Absolute Rules
1. Google Sheets is **the** database. Period.
2. Local CSVs are **caches / snapshots / fast views**. They exist to make dashboard loading fast.
3. Never add new persistent storage without Tony's explicit blessing.
4. Dashboard phase 1 = **beautiful read-only viewer** of existing Sheets + CSVs
5. No authentication system yet → simple shared links or Discord role check is enough for now
6. Backend = **only what's strictly necessary** to:
   - Serve dashboard
   - Handle occasional CSV↔Sheets sync
   - Expose minimal API endpoints if needed for Discord bot

## Strong Technical Preferences (keep it dead simple)
- Python 3.11+
- FastAPI or even just Flask (Flask is winning for simplicity right now)
- **No database ORM** — use gspread + pandas + csv module
- **No complex state management** — reload data on demand or on timer
- Jinja2 + Tailwind CSS + minimal vanilla JS → beautiful & maintainable
- Logging: just Python `logging` + console/file
- Config: `.env` file + python-dotenv (that's it)

## Naming & UX Style
- Dashboard should feel **premium & clean** even with very little code
- Use big numbers, simple charts, dark mode by default
- Discord commands: keep them stupid simple
  Good: /submit, /register, /myprofile, /raidstats
  Avoid: /advanced-content-submission-v3-with-options

## Current Priority Ladder (do in this exact order)
1. Make credentials & sheet IDs live only in .env (security basics)
2. Create ultra-simple bidirectional CSV ↔ Sheets sync script (manual run ok)
3. Build the "wow" dashboard – beautiful read-only views of:
   • Current month's raid content
   • Member registry overview
   • Simple stats (submissions count, top posters, etc)
4. Make Discord bot read/write to same Sheets + update CSVs
5. Add very basic error logging (file + optional Discord channel)
6. Only then: think about rate limits, input validation, tests...

## When suggesting code
- Prefer 20–60 line solutions over 200+ line ones
- Show the **simplest possible** version first
- Only add abstraction when the simple version is clearly painful
- If you want to suggest something more advanced → mark it clearly as "phase 2/3 idea"

Call me Tony.  
Be brutally pragmatic.  
Complexity is the enemy.

Last updated: 11 January 2026
