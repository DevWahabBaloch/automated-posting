#!/usr/bin/env bash
# Create .venv with Python >= 3.11 and install all dependencies.
# Usage: ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

is_supported() {  # $1 = interpreter path
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3 \
      /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
      /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 \
      "$HOME/.pyenv/shims/python3" \
      /Library/Frameworks/Python.framework/Versions/3.1[1-9]/bin/python3; do
    local path
    path=$(command -v "$candidate" 2>/dev/null) || continue
    if is_supported "$path"; then echo "$path"; return 0; fi
  done
  return 1
}

if PY=$(find_python); then
  echo "Using $PY ($("$PY" --version))"
  "$PY" -m venv .venv
elif command -v uv >/dev/null 2>&1; then
  echo "No Python >= 3.11 found; letting uv provide Python 3.12"
  uv venv --seed -p 3.12 .venv
else
  cat >&2 <<'MSG'
ERROR: Python 3.11 or newer is required but was not found.
Install it with ONE of:
  brew install python@3.12          (Homebrew)
  https://www.python.org/downloads/ (official installer)
Then run this task again.
MSG
  exit 1
fi

.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt
[ -f .env ] || cp .env.example .env
echo "Ready: $(.venv/bin/python --version). Next: run the 'Run API' task."
