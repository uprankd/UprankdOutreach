#!/bin/bash
# Double-click to start Almo. The first start sets things up (about a minute).
cd "$(dirname "$0")" || exit 1
LOG="$PWD/setup.log"

fail() {
  echo
  echo "$1"
  echo "Details are in setup.log in this folder. Press Enter to close."
  osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with title \"Almo\"" >/dev/null 2>&1
  read -r
  exit 1
}

# Every Python 3.9+ on this Mac, best first. The one inside Xcode is last:
# it often can't set up its own installer (ensurepip), which is what broke
# the first start for some people.
candidates() {
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
           /Library/Frameworks/Python.framework/Versions/*/bin/python3 \
           "$(command -v python3)" /usr/bin/python3; do
    [ -x "$p" ] || continue
    "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && echo "$p"
  done | awk '!seen[$0]++'
}

make_venv() {
  local py="$1"
  rm -rf .venv
  echo "  using $py ($("$py" --version 2>&1))" | tee -a "$LOG"
  if "$py" -m venv .venv >>"$LOG" 2>&1 && .venv/bin/python -m pip --version >>"$LOG" 2>&1; then
    return 0
  fi
  # Plan B: an environment without pip, then fetch pip directly.
  rm -rf .venv
  "$py" -m venv --without-pip .venv >>"$LOG" 2>&1 || return 1
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o .venv/get-pip.py >>"$LOG" 2>&1 || return 1
  .venv/bin/python .venv/get-pip.py --quiet >>"$LOG" 2>&1 || return 1
  .venv/bin/python -m pip --version >>"$LOG" 2>&1
}

REQ_HASH=$(shasum requirements.txt | cut -d' ' -f1)
if [ ! -x .venv/bin/python ] || [ "$(cat .venv/.req 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "Setting up Almo (first start only, about a minute)…"
  : > "$LOG"
  PYS=$(candidates)
  if [ -z "$PYS" ]; then
    open "https://www.python.org/downloads/macos/"
    fail "Almo needs Python 3.9 or newer. The download page is open - install it, then double-click Start Almo again."
  fi
  ok=""
  while IFS= read -r py; do
    if make_venv "$py"; then ok="$py"; break; fi
    echo "  that Python didn't work, trying the next one" | tee -a "$LOG"
  done <<< "$PYS"
  if [ -z "$ok" ]; then
    rm -rf .venv
    open "https://www.python.org/downloads/macos/"
    fail "Couldn't set up Python on this Mac. Install Python from python.org (the page is open), then double-click Start Almo again."
  fi
  .venv/bin/python -m pip install --quiet --upgrade pip >>"$LOG" 2>&1
  if ! .venv/bin/python -m pip install --quiet -r requirements.txt >>"$LOG" 2>&1; then
    fail "Couldn't download what Almo needs. Check the internet connection and try again."
  fi
  echo "$REQ_HASH" > .venv/.req
  echo "Done."
fi

echo "Almo is starting. Keep this window open while you use it - closing it stops Almo."
exec .venv/bin/python app.py
