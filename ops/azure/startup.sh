#!/bin/sh
# App Service entrypoint. Runs from the deployed git checkout so the engine can name its
# commit (checker/release_record.py reads `git rev-parse HEAD`). Dependencies live in a
# persistent venv, rebuilt only when the requirements files change.
# ponytail: worker and gateway share one box; split the worker out when load needs it.
set -e
cd "$(dirname "$0")"
# The runtime image has no git; the engine needs it to name its commit.
command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq --no-install-recommends git >/dev/null; }
git config --global --add safe.directory "$(pwd)"
# Unzipping resets file modes and mtimes: ignore modes, and refresh the stat cache once so
# the engine's own `git status` (10 s limit) is fast and reports real content changes only.
git config core.fileMode false
git update-index -q --refresh >/dev/null || true
V=/home/venv-placedon
# Azure updates the runtime Python in place; a venv bound to the old interpreter breaks,
# so the Python version is part of the hash and the venv must actually import uvicorn.
H=$( { python -V; cat requirements-gateway.txt requirements.txt; } | sha256sum | cut -c1-16)
if [ "$(cat $V/.reqhash 2>/dev/null)" != "$H" ] || ! $V/bin/python -c "import uvicorn, psycopg" 2>/dev/null; then
  rm -rf $V; python -m venv $V
  $V/bin/pip install -q --disable-pip-version-check -r requirements-gateway.txt
  echo "$H" > $V/.reqhash
fi
. $V/bin/activate
export PYTHONPATH=.
echo "engine commit: $(git rev-parse --short HEAD) dirty: $(git status --porcelain | wc -l)"
( while true; do python -m gateway.worker --serve || true; echo "worker exited; restarting in 5s"; sleep 5; done ) &
exec python -m uvicorn ops.asgi:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
