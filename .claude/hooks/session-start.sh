#!/usr/bin/env bash
# SessionStart hook: make `import mento` work in a fresh Linux/cloud session.
#
# On Windows the rame-env conda environment already has everything installed and
# this exits immediately. In a Claude Code web session the container starts with a
# bare interpreter and without mento's dependencies (pint, pandas, matplotlib, ...),
# so every test run and every interactive check fails. Here we build a local .venv
# on a Python that satisfies requires-python (>=3.12) and install mento into it.
set -euo pipefail

# Git Bash's `python` is not rame-env, and a venv there has Scripts/, not bin/, so
# probing it would fail and the install below would abort on `.venv/bin/python`.
case "${OSTYPE:-}" in
  msys* | cygwin* | win32*) exit 0 ;;
esac

cd "$(dirname "$0")/../.."

if python -c "import mento" >/dev/null 2>&1; then
  echo "mento already importable with the default interpreter; nothing to do."
  exit 0
fi

if [ -x .venv/bin/python ] && .venv/bin/python -c "import mento" >/dev/null 2>&1; then
  echo "mento already installed in .venv; nothing to do."
  exit 0
fi

# requires-python is >=3.12, and cloud containers often default to an older one.
INTERPRETER=""
for candidate in python3.13 python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    INTERPRETER="$candidate"
    break
  fi
done

if [ -z "$INTERPRETER" ]; then
  echo "No Python >= 3.12 found; skipping the mento install." >&2
  exit 0
fi

echo "Creating .venv with $INTERPRETER and installing mento (editable, dev extras)..."
[ -x .venv/bin/python ] || "$INTERPRETER" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[dev]"
.venv/bin/python -c "import mento; print('mento', mento.__version__, 'ready in .venv')"
