#!/bin/bash
# YouTube Shorts auto-deploy — daily cron wrapper
# Add to crontab with: crontab -e
# Example: 0 9 * * * /path/to/run.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$HOME/.shorts-pipeline/logs"

mkdir -p "$LOG_DIR"

cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "[$(date)] Starting YouTube Shorts pipeline..." >> "$LOG_DIR/cron.log"

python -m pipeline run --discover --auto-pick >> "$LOG_DIR/cron.log" 2>&1

echo "[$(date)] Pipeline finished." >> "$LOG_DIR/cron.log"
