"""Hold the gate's single-run lock, so two overlapping gates cannot clobber each other.

The gate used to be serialised by a fixed test port -- `serve_ask` bound 127.0.0.1:8021 with
`allow_reuse_port = False`, so a second overlapping gate failed to bind and reported a
spurious RED (CLAUDE.md records the incident). The test servers all bind port 0 now, so that
implicit guard is gone. This is the explicit replacement, and it is honest: a second gate is
not a failure, it is a second gate.

`run_tests.sh` opens a file descriptor on `.gate.lock` and calls this to take an EXCLUSIVE,
NON-BLOCKING `flock` on it. The lock lives on the open file description, which the shell
keeps open for the whole run (`exec 9>.gate.lock`), so it is held until the gate exits and
released automatically then -- a crashed gate does not leave it stuck.

    python3 scripts/gate_lock.py <fd>    # exit 0 = acquired, 1 = already held

`flock(1)` is not on macOS, which is why this is Python (`fcntl.flock` is everywhere Python
is). An inherited fd locked by this short-lived child stays locked after it exits, because
the shell still holds the same open file description -- the standard `exec 9>; flock 9` idiom.
"""
from __future__ import annotations

import fcntl
import sys


def acquire(fd: int) -> bool:
    """Take an exclusive, non-blocking lock on `fd`. True if acquired, False if already held."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        # EWOULDBLOCK (another holder) or EBADF (no such fd). Either way, not acquired.
        return False


def _test() -> None:
    import os
    import tempfile

    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, ".gate.lock")
        # Two SEPARATE opens of the same file are two open file descriptions, and flock
        # treats them independently -- so the second must be refused while the first holds
        # the lock. That is exactly the two-gates case.
        fd_a = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        fd_b = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            check(acquire(fd_a) is True, "the first gate takes the lock")
            check(acquire(fd_b) is False,
                  "a SECOND overlapping gate is refused the lock (it does not clobber)")
            # Releasing the first lets the next one in -- the lock is not stuck.
            fcntl.flock(fd_a, fcntl.LOCK_UN)
            check(acquire(fd_b) is True,
                  "once the first releases, the next gate acquires it")
        finally:
            os.close(fd_a)
            os.close(fd_b)

        # A bad fd is 'not acquired', never a crash -- the caller prints a clean message.
        check(acquire(9999) is False, "a bad fd is reported as not-acquired, not an error")

    print(f"{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: gate_lock.py <fd>", file=sys.stderr)
        return 2
    try:
        fd = int(argv[1])
    except ValueError:
        print(f"fd must be an integer, got {argv[1]!r}", file=sys.stderr)
        return 2
    return 0 if acquire(fd) else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        sys.exit(main(sys.argv))
