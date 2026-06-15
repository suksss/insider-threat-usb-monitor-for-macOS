#!/usr/bin/env bash
set -euo pipefail

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Check Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 is required. Please install via Xcode Command Line Tools or Homebrew."
  exit 1
fi

# Create venv
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# Activate
source .venv/bin/activate

# Upgrade pip and install deps
python -m pip install --upgrade pip wheel
pip install -r requirements.txt

echo ""
echo "Setup complete."
echo "Next: python start_monitor.py"
