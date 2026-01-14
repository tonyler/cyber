# Cyber Bot

Discord bot that manages content raids and member registrations using Google Sheets. It posts raid announcements to a channel and records submissions and member profiles in separate spreadsheets.

## What it does

- `/submit` collects X (Twitter) or Reddit links, writes them into a monthly Google Sheet tab, and posts an @everyone raid embed.
- `/register` stores a user's X/Reddit profiles in a member registry sheet, updating the row if they already exist.

## Commands

- `/submit link:<url> notes:<optional>`
  - Accepts `x.com`/`twitter.com` or `reddit.com` links.
  - Writes to a monthly tab named `MM/YY` in the content sheet.
- `/register x_profile:<url or handle> reddit_profile:<url or username>`
  - Normalizes profiles and saves them into the `Member Registry` worksheet.
  - Optionally restricted to a specific channel via config.

## Configuration

Files:
- `shared/config/bot_config.json` holds Google Sheet IDs and optional channel IDs.
- `shared/credentials/google.json` is the Google service account credentials file.
- `.env` must define the Discord bot token in `DISCORD_TOKEN` (legacy `KEY` still supported).

Example `bot_config.json`:
```json
{
  "content_sheet_id": "YOUR_CONTENT_SHEET_ID",
  "content_channel_id": "YOUR_CHANNEL_ID",
  "registration_sheet_id": "YOUR_REGISTRATION_SHEET_ID",
  "registration_channel_id": "YOUR_CHANNEL_ID"
}
```

## Setup

1. Create and share the Google Sheets with the service account email.
2. Place the service account JSON at `shared/credentials/google.json`.
3. Create `.env` with `DISCORD_TOKEN=your_discord_bot_token` (or legacy `KEY=...`).
4. Install dependencies and run:
   - From `bot/` use `pip install -r requirements.txt`.
   - Start with `python bot.py` or `./start.sh`.

## Data layout

Content sheet monthly tab layout (A:P):
- Columns A-H are for X (Date, Author, URL, Impressions, Likes, Comments, Notes, Total Impressions).
- Columns I-P are for Reddit (Date, Author, URL, Views, Upvotes, Comments, Notes, Total Impressions).

Member registry layout (A:I):
- Discord username, X URL, Reddit URL, X handle, Reddit username, status, join date, last active, strikes.
