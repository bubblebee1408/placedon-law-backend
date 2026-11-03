"""Wait for the local gateway, then prove it is wired: Postgres store, job queue, vault.

    docker compose exec -T gateway python ops/dev/smoke.py     (what `make dev` runs)
"""
import json
import sys
import time
import urllib.request

URL = "http://localhost:8000/v1/health"
deadline = time.monotonic() + 120
while True:
    try:
        with urllib.request.urlopen(URL, timeout=5) as r:
            health = json.load(r)
        break
    except OSError as e:
        if time.monotonic() > deadline:
            sys.exit(f"FAIL: {URL} did not answer in 120 s ({e}). See `make logs`.")
        time.sleep(2)

problems = []
if health.get("store", {}).get("kind") != "postgres":
    problems.append(f"store is {health.get('store')}, not postgres")
queue = health.get("queue")
if not queue or "error" in queue:
    problems.append(f"queue is {queue}")
if not health.get("files", {}).get("configured"):
    problems.append(f"files is {health.get('files')}")
if problems:
    sys.exit("FAIL: " + "; ".join(problems))
print(f"OK: gateway up at commit {health.get('checker_commit', '?')}, "
      f"store postgres, queue {queue}, vault {health['files'].get('kind')}")
