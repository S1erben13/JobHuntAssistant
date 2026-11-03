#!/usr/bin/env bash
# Дневной запуск для Linux/macOS. Cron: 0 9 * * * /path/to/JobHuntAssistant/scripts/daily.sh --with-letters
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
OUT="${OUTPUT_DIR:-$(grep -E '^\s*OUTPUT_DIR\s*=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)}"
OUT="${OUT:-$HOME/Documents/JobHunt}"
mkdir -p logs
LOG="logs/daily-$(date +%F).log"
"$PY" run.py >>"$LOG" 2>&1
if [ "${1:-}" = "--with-letters" ] && command -v claude >/dev/null; then
  claude -p "Выполни скилл job-letters. Сбор вакансий уже сделан, начни с шага 3." \
    --allowedTools Read Write Edit Glob --add-dir "$OUT" >>"$LOG" 2>&1
fi
