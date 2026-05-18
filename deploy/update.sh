#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/opt/jcc/jcc_git"
BACKUP_DIR="/opt/jcc/backups"
SERVICE_NAME="jcc"
HEALTH_URL="https://jcc.np5.top/api/health"

cd "$PROJECT_DIR"

mkdir -p "$BACKUP_DIR"
if [ -f "instance/lineups.sqlite3" ]; then
  cp "instance/lineups.sqlite3" "$BACKUP_DIR/lineups.$(date +%Y%m%d-%H%M%S).sqlite3"
fi

git fetch origin main
git reset --hard origin/main

source .venv/bin/activate
pip install -r requirements.txt
python migrate.py

systemctl restart "$SERVICE_NAME"
curl -fsS "$HEALTH_URL"
echo "JCC update completed"
