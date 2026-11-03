#!/bin/zsh
# Haseed for Mac: double-click to start. Close this window to stop.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Haseed needs Python 3. Install it from https://www.python.org/downloads/ and open this file again."
  read -k1 "?Press any key to close."; exit 1
fi
if [ ! -d .venv ]; then
  echo "First run: setting up Haseed (takes a minute)…"
  python3 -m venv .venv || exit 1
fi
# -U keeps yt-dlp current; sites change often and old versions stop working
.venv/bin/python -m pip install -q -U --disable-pip-version-check -r requirements.txt || { echo "Setup failed, see above."; read -k1; exit 1; }
.venv/bin/python server.py
