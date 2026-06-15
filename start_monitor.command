#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi
python start_monitor.py
read -n 1 -s -r -p "Press any key to close this window..." || true
