#!/bin/bash
# Run X + Reddit scrapers on a fixed interval.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ROOT_VENV="$PROJECT_ROOT/venv"

RUNNER="${PYTHON_BIN:-$ROOT_VENV/bin/python3}"
SCRAPER_SCRIPT="$PROJECT_ROOT/scrapers/run_scrapers.py"
INTERVAL_MINUTES="${SCRAPER_INTERVAL_MINUTES:-30}"
PLAYWRIGHT_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"

if [ ! -x "$RUNNER" ] && ! command -v "$RUNNER" > /dev/null 2>&1; then
    echo "Error: $RUNNER not found in PATH."
    exit 1
fi

if [ ! -f "$SCRAPER_SCRIPT" ]; then
    echo "Error: scraper entrypoint missing at $SCRAPER_SCRIPT"
    exit 1
fi

if ! [[ "$INTERVAL_MINUTES" =~ ^[0-9]+$ ]] || [ "$INTERVAL_MINUTES" -le 0 ]; then
    echo "Error: SCRAPER_INTERVAL_MINUTES must be a positive integer."
    exit 1
fi

if [ ! -d "$PLAYWRIGHT_CACHE" ]; then
    echo "Playwright browsers not found; installing Chromium..."
    if ! "$RUNNER" -m playwright install chromium; then
        echo "Error: Playwright browser install failed."
        exit 1
    fi
fi

sleep_seconds=$((INTERVAL_MINUTES * 60))

echo "Scraper daemon started; interval=${INTERVAL_MINUTES}m"

while true; do
    echo ""
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Running scrapers..."
    if ! "$RUNNER" "$SCRAPER_SCRIPT"; then
        echo "⚠️  Scrapers exited with a non-zero status."
    fi
    echo "Sleeping for ${INTERVAL_MINUTES} minutes..."
    sleep "$sleep_seconds"
done
