#!/bin/bash
# Double-click to start Almo. The first start sets things up (about a minute).
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
  osascript -e 'display dialog "Almo needs Python 3.9 or newer. The download page will open - install it, then double-click Start Almo again." buttons {"OK"} default button 1 with title "Almo"' >/dev/null
  open "https://www.python.org/downloads/macos/"
  exit 1
fi

REQ_HASH=$(shasum requirements.txt | cut -d' ' -f1)
if [ ! -x .venv/bin/python ] || [ "$(cat .venv/.req 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "Setting up Almo (first start only)…"
  python3 -m venv .venv || { echo "Couldn't create the Python environment."; read -r; exit 1; }
  .venv/bin/python -m pip install --quiet --upgrade pip
  if ! .venv/bin/python -m pip install --quiet -r requirements.txt; then
    echo "Setup failed - check the internet connection and try again."
    read -r; exit 1
  fi
  echo "$REQ_HASH" > .venv/.req
fi

echo "Almo is starting. Keep this window open while you use it - closing it stops Almo."
exec .venv/bin/python app.py
