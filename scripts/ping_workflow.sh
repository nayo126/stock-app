#!/bin/zsh
# Mac-local fallback: GitHub cron が遅延した時のために 10 分おきに workflow_dispatch を叩く。
# 既存スナップショットが 10 分以内ならスキップ。
set -u

LOG=/tmp/stock-app-ping.log
exec >>"$LOG" 2>&1
echo "==== $(date '+%F %T') start ===="

cd "$HOME/repos/stock-app" || { echo "cd failed"; exit 1; }

# 直近snapshotのage(分)を見る — 10分以内なら何もしない
git fetch origin main --quiet 2>/dev/null || true
LAST_TS=$(git log -1 --pretty=%ct origin/main -- data/snapshot.json 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE_MIN=$(( (NOW - LAST_TS) / 60 ))
echo "snapshot age = ${AGE_MIN} min"

if [ "$AGE_MIN" -lt 10 ]; then
  echo "fresh — skip dispatch"
  exit 0
fi

echo "dispatching workflow_dispatch..."
/opt/homebrew/bin/gh workflow run snapshot.yml --repo nayo126/stock-app && echo "dispatched OK" || echo "dispatch FAILED"
