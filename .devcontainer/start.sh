#!/usr/bin/env bash
set -e

if ! pgrep -f "[p]ython app.py" >/dev/null; then
  nohup python app.py > /tmp/coin-issue-ai.log 2>&1 &
fi
