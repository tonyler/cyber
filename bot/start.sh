#!/bin/bash
# Start script for Discord Bot

set -euo pipefail

cd "$(dirname "$0")"

# Check Python
if ! command -v python3 > /dev/null 2>&1; then
    echo "Error: python3 not found in PATH."
    exit 1
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
    source venv/bin/activate
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    else
        echo "Warning: requirements.txt not found; skipping dependency install."
    fi
else
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create .env with your Discord bot token:"
    echo "KEY=your_discord_bot_token_here"
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
python bot.py
