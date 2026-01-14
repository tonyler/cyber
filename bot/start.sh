#!/bin/bash
# Start script for Discord Bot

set -euo pipefail

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$BOT_DIR")"
ROOT_VENV="$PROJECT_ROOT/venv"
DEPS_MARKER="$ROOT_VENV/.deps_installed"

cd "$BOT_DIR"

# Check Python
if ! command -v python3 > /dev/null 2>&1; then
    echo "Error: python3 not found in PATH."
    exit 1
fi

# Ensure root venv exists and dependencies are installed
if [ ! -d "$ROOT_VENV" ]; then
    echo "Root virtual environment not found. Creating..."
    python3 -m venv "$ROOT_VENV"
fi

if ! "$ROOT_VENV/bin/python3" -m pip --version > /dev/null 2>&1; then
    "$ROOT_VENV/bin/python3" -m ensurepip --upgrade
fi

if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    if [ ! -f "$DEPS_MARKER" ]; then
        if "$ROOT_VENV/bin/python3" -m pip install -r "$PROJECT_ROOT/requirements.txt"; then
            touch "$DEPS_MARKER"
        else
            echo "Warning: dependency install failed; continuing without updating packages."
        fi
    fi
else
    echo "Warning: requirements.txt not found at $PROJECT_ROOT; skipping dependency install."
fi

# Check if .env exists (project root)
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "Error: .env file not found in project root!"
    echo "Please create $PROJECT_ROOT/.env with your Discord bot token:"
    echo "DISCORD_TOKEN=your_discord_bot_token_here"
    echo "(Legacy: KEY=your_discord_bot_token_here)"
    exit 1
fi

# Check if shared credentials exist
if [ ! -f "../shared/credentials/google.json" ]; then
    echo "Error: Google credentials not found!"
    echo "Please add your Google Sheets credentials to:"
    echo "../shared/credentials/google.json"
    exit 1
fi

echo "Starting Discord Bot..."
PYTHONUNBUFFERED=1 "$ROOT_VENV/bin/python3" -u bot.py
