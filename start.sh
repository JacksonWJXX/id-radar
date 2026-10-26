#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname "${BASH_SOURCE[0]}")"

missing_python() {
  printf '%s\n' '需要 Python 3.11 或更新版本：https://www.python.org/downloads/'
  printf '%s\n' 'Python 3.11+ is required: https://www.python.org/downloads/'
  exit 1
}

if [[ ! -x .venv/bin/python ]]; then
  idradar_python=''
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
      idradar_python="$candidate"
      break
    fi
  done
  [[ -n "$idradar_python" ]] || missing_python
  "$idradar_python" -m venv .venv
  touch .venv/.idradar-installing
fi
.venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 11))' || missing_python
if [[ -f .venv/.idradar-installing ]]; then
  .venv/bin/python -m pip install -r requirements.txt
  rm -- .venv/.idradar-installing
fi
exec .venv/bin/python -m idradar "$@"
