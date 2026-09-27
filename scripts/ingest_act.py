#!/usr/bin/env python3
"""
Ingest one Central Act from India Code, for any Act in the register below.

Generalised from `scripts/ingest_companies_act.py` on 2026-09-27 (Harvey-for-India plan, Day 1),
which this file replaces. Every property that file had been taught the hard way is carried, and
each is named where it lives, because the reason is what stops it being undone:

  * **TLS is verified and the user agent is honest (RT-14).** Both were disabled here until
    2026-09-18 -- `CERT_NONE`, `check_hostname = False`, and a spoofed Chrome UA -- on the one
    fetch in this repository where a man-in-the-middle rewrites the statute. Not exploitable that
    day only because the hostname was dead. Now from `checker.robots`, which fails closed: no CA
    bundle means no fetch.
  * **An empty enumeration is a failed enumeration, never a corpus of nothing.** The manifest
    write used to happen before the fetch loop, unconditionally, so a page parsing to zero
    section ids replaced the record of what the corpus should contain with `count: 0` and a FRESH
    timestamp, and exited 0. The section files survived, so the damage was invisible. It is
    reachable: measured 2026-09-26, `indiacode.gov.in/handle/123456789/2114` answers 200
    `text/html`, 6,762 bytes -- the DSpace Angular shell -- with zero `sectionId=` matches. The
    payload guard in `checker/robots.py` cannot catch it, because HTML is what that page IS. The
    shape of the result is the only evidence, so the check belongs here.
  * **Section ids are enumerated off the act page, never by counting integers.** Inserted
    sections carry high ids -- s.3A is 48973 -- so iterating 1..N silently fetches the wrong law.

## Why most Acts in the register refuse to run

**An India Code `actid` is not guessable and must never be guessed.** A wrong id fetches a
different statute, and the result would look exactly like a successful ingest: well-formed JSON,
real section text, a clean hash. Nothing downstream could tell. So an Act whose `act_id` has not
been confirmed against India Code by a person is `PENDING_ID` and this script refuses it, naming
what to do. Filling one in is a deliberate act with a URL recorded beside it.

Run:  python3 scripts/ingest_act.py --list
      python3 scripts/ingest_act.py companies_act [--limit N]
      python3 scripts/ingest_act.py --test
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from checker.robots import USER_AGENT, ssl_context      # noqa: E402

UA = {"User-Agent": USER_AGENT}
PAUSE = 0.4                      # be a polite client
CONTENT_EP = "https://www.indiacode.nic.in/SectionPageContent?actid={act}&sectionID={sid}"

# A corpus directory name, and nothing that could escape `corpus/`.
_KEY_OK = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


@dataclass(frozen=True)
class Act:
    """One Central Act. `act_id` is None until a person has confirmed it on India Code."""

    key: str                     # corpus/<key>/ -- validated against _KEY_OK
    title: str
    act_id: str | None
    handle: str | None           # the act page whose HTML carries every sectionId=
    note: str = ""

    @property
    def pending(self) -> bool:
        return not (self.act_id and self.handle)


# ── The register. Order is PLAN order: the Harvey-for-India plan's §3 list. ───────────────────
ACTS: dict[str, Act] = {a.key: a for a in (
    Act("companies_act", "Companies Act, 2013",
        "AC_CEN_22_29_00008_201318_1517807327856",
        "https://www.indiacode.nic.in/handle/123456789/2114",
        "Held. 527 sections, hash-stamped. The only Act ingested through this path so far."),

    # Everything below is DECLARED in the plan and PENDING_ID here. Confirm the actid and the
    # handle URL on India Code, paste both, and record where you found them. Do not guess:
    # a wrong actid returns a different Act's sections and every downstream check passes.
    Act("llp2008", "Limited Liability Partnership Act, 2008", None, None,
        "PLAN body 4. Needs actid + handle from India Code."),
    Act("fema1999", "Foreign Exchange Management Act, 1999", None, None,
        "PLAN body 5. FDI rules move by press note and are NOT part of the Act ingest."),
    Act("ibc2016", "Insolvency and Bankruptcy Code, 2016", None, None,
        "PLAN body 6. Needs actid + handle."),
    Act("comp2002", "Competition Act, 2002", None, None,
        "PLAN body 7. Needs actid + handle."),
    Act("dpdp2023", "Digital Personal Data Protection Act, 2023", None, None,
        "PLAN body 8. Declared in scope by the plan; note DPDP was previously ruled OUT "
        "(BUSINESS_PLAN 2026-08-16). The plan supersedes that -- confirm with the founder "
        "before acquiring, because it reverses a recorded decision."),
)}


def known_keys() -> list[str]:
    return sorted(ACTS)


def corpus_dir(act: Act, root: Path = ROOT) -> Path:
    """`corpus/<key>/`, with the key validated so it cannot climb out of corpus/."""
    if not _KEY_OK.match(act.key):
        raise ValueError(f"unusable corpus key {act.key!r}: must match {_KEY_OK.pattern}")
    return root / "corpus" / act.key


def _get(url: str, tries: int = 3) -> str:
    ctx = ssl_context()
    if ctx is None:
        raise RuntimeError("no CA bundle available; refusing to fetch a statute over an "
                           "unverified connection (RT-14)")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def enumerate_sections(act: Act, get=_get) -> list[str]:
    """Section ids in document order, parsed off the act page. One fetch returns all of them."""
    html = get(act.handle)
    ids: list[str] = []
    seen: set[str] = set()
    for sid in re.findall(r"sectionI[dD]=(\d+)", html):
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def fetch_section(act: Act, sid: str, get=_get) -> dict:
    url = CONTENT_EP.format(act=act.act_id, sid=sid)
    data = json.loads(get(url))
    content = data.get("content") or ""
    return {
        "section_id": sid,
        "act_key": act.key,
        "act_id": act.act_id,
        "act_title": act.title,
        "content": content,
        "footnote": data.get("footnote") or "",
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def ingest(act: Act, *, limit: int | None = None, root: Path = ROOT,
           enumerate_fn=enumerate_sections, fetch_fn=fetch_section) -> int:
    """Ingest one Act. Returns a process exit code: 0 ok, 1 refused.

    The two callables are injected rather than patched, so a test can drive the whole path
    without a network and without reassigning module globals -- which the previous version's
    tests had to do, and which meant a test could pass while the real call site was wrong.
    """
    if act.pending:
        print(f"REFUSED: {act.key} ({act.title}) has no confirmed India Code actid.\n"
              f"  {act.note}\n"
              f"  An actid is not guessable. A wrong one returns a DIFFERENT Act's sections and "
              f"every check downstream would pass, because the result is well-formed. Confirm it "
              f"on India Code, then record the actid and the handle URL in ACTS.", flush=True)
        return 1

    out = corpus_dir(act, root)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "_manifest.json"

    ids = enumerate_fn(act)
    print(f"{act.key}: enumerated {len(ids)} section ids", flush=True)

    # An empty enumeration is a failed enumeration. See the module docstring: this is the check
    # that stops a soft-404 overwriting the record of what the corpus should contain.
    if not ids:
        print(f"REFUSED: {act.handle} parsed to 0 section ids. A page that yields no sections is "
              f"a source we could not read, not an Act with no sections -- the manifest is left "
              f"as it was.", flush=True)
        return 1

    # `act_key` and `act_id` are both written, so a manifest can never be read as another Act's.
    # The old single-Act manifest carried act_id alone, which was unambiguous only while there
    # was exactly one corpus.
    manifest.write_text(json.dumps(
        {"act_key": act.key, "act_id": act.act_id, "act_title": act.title,
         "section_ids": ids, "count": len(ids),
         "enumerated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2))

    if limit:
        ids = ids[:limit]

    fetched = skipped = failed = 0
    for n, sid in enumerate(ids, 1):
        path = out / f"{sid}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            path.write_text(json.dumps(fetch_fn(act, sid), ensure_ascii=False, indent=2))
            fetched += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {sid}: {type(e).__name__}", flush=True)
        if n % 25 == 0:
            print(f"  {n}/{len(ids)} fetched={fetched} skipped={skipped} failed={failed}",
                  flush=True)
        time.sleep(PAUSE)

    print(f"{act.key}: done. fetched={fetched} skipped={skipped} failed={failed}", flush=True)
    # A per-section failure is not a failed run: it is reported and the manifest is already
    # correct. Only an unreadable enumeration, or an unconfirmed actid, refuses.
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if "--list" in argv or not args:
        print("Acts in the register:\n")
        for k in known_keys():
            a = ACTS[k]
            print(f"  {k:16s} {'READY     ' if not a.pending else 'PENDING_ID'} {a.title}")
            if a.note:
                print(f"                   {a.note}")
        print(f"\nRun: python3 scripts/ingest_act.py <key> [--limit N]")
        return 0 if "--list" in argv else 1

    key = args[0]
    if key not in ACTS:
        print(f"REFUSED: {key!r} is not in the register. Known: {', '.join(known_keys())}.\n"
              f"  Add it to ACTS with a CONFIRMED India Code actid and handle URL. An Act this "
              f"script has never been told about is not an Act with no sections.", flush=True)
        return 1

    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    return ingest(ACTS[key], limit=limit)


def _test() -> int:
    """No network. Both fetchers are injected, so nothing here can reach India Code."""
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("ingest_act")
    CA = ACTS["companies_act"]

    # ── the register ─────────────────────────────────────────────────────────
    check(not CA.pending, "the Companies Act is READY -- it has a confirmed actid and handle")
    pend = [k for k in known_keys() if ACTS[k].pending]
    check(len(pend) == 5 and "companies_act" not in pend,
          f"every other body is PENDING_ID until a person confirms its actid ({pend})")
    check(all(ACTS[k].act_id is None for k in pend),
          "no PENDING body carries a guessed actid -- a wrong one is undetectable downstream")
    check(all(k == ACTS[k].key for k in ACTS),
          "the register is keyed by each Act's own key, so a lookup cannot return another Act")

    # ── the corpus path cannot escape corpus/ ────────────────────────────────
    check(corpus_dir(CA, Path("/tmp/x")) == Path("/tmp/x/corpus/companies_act"),
          "the corpus directory is derived from the key")
    for bad in ("../etc", "/abs", "Dot.Dot", "AB", "x"):
        try:
            corpus_dir(Act(bad, "t", "a", "h"))
            check(False, f"a key of {bad!r} must be refused")
        except ValueError:
            check(True, f"a key of {bad!r} is refused before it becomes a path")

    # ── an unconfirmed actid refuses, and never fetches ──────────────────────
    calls: list = []
    with tempfile.TemporaryDirectory() as d:
        rc = ingest(ACTS["ibc2016"], root=Path(d),
                    enumerate_fn=lambda a: calls.append(a) or ["1"],
                    fetch_fn=lambda a, s: calls.append(s) or {})
        check(rc == 1, "a PENDING_ID Act refuses")
        check(calls == [], "...and nothing was fetched -- the refusal is before the first call")
        check(not (Path(d) / "corpus").exists(),
              "...and no corpus directory was created for it")

    # ── an empty enumeration leaves the manifest exactly as it was ───────────
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "corpus/companies_act"
        out.mkdir(parents=True)
        good = {"act_key": "companies_act", "act_id": CA.act_id, "act_title": CA.title,
                "section_ids": ["1", "2"], "count": 527,
                "enumerated_at": "2026-08-18T22:15:46+00:00"}
        (out / "_manifest.json").write_text(json.dumps(good, indent=2))
        rc = ingest(CA, root=Path(d), enumerate_fn=lambda a: [],
                    fetch_fn=lambda a, s: {"unreachable": True})
        after = json.loads((out / "_manifest.json").read_text())
        check(rc == 1, "an empty enumeration exits non-zero")
        check(after == good, "the manifest is byte-identical after a zero-section enumeration")
        check(after["enumerated_at"] == good["enumerated_at"],
              "...including enumerated_at -- no fresh timestamp on a failure")

    # ── the happy path, and what it records ─────────────────────────────────
    with tempfile.TemporaryDirectory() as d:
        seen: list[str] = []

        def fake_fetch(a: Act, sid: str) -> dict:
            seen.append(sid)
            return {"section_id": sid, "act_key": a.key, "content": "x"}

        rc = ingest(CA, root=Path(d), enumerate_fn=lambda a: ["11", "12", "13"],
                    fetch_fn=fake_fetch)
        m = json.loads((Path(d) / "corpus/companies_act/_manifest.json").read_text())
        check(rc == 0, "a real enumeration exits 0")
        check(m["count"] == 3 and m["section_ids"] == ["11", "12", "13"],
              "the ids are written in document order")
        check(m["act_key"] == "companies_act" and m["act_id"] == CA.act_id,
              "the manifest names WHICH Act it is -- it cannot be read as another's")
        check(seen == ["11", "12", "13"], "every enumerated section was fetched")
        check((Path(d) / "corpus/companies_act/12.json").exists(),
              "...and written to <section_id>.json")

    # ── resumability: a section already on disk is skipped, not refetched ────
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "corpus/companies_act"
        out.mkdir(parents=True)
        (out / "11.json").write_text('{"already": true}')
        seen = []
        ingest(CA, root=Path(d), enumerate_fn=lambda a: ["11", "12"],
               fetch_fn=lambda a, s: seen.append(s) or {"section_id": s})
        check(seen == ["12"], "a section already on disk is skipped, not refetched")
        check(json.loads((out / "11.json").read_text()) == {"already": True},
              "...and the file on disk is left untouched")

    # ── --limit truncates the FETCH, never the manifest ──────────────────────
    with tempfile.TemporaryDirectory() as d:
        seen = []
        ingest(CA, limit=1, root=Path(d), enumerate_fn=lambda a: ["11", "12", "13"],
               fetch_fn=lambda a, s: seen.append(s) or {"section_id": s})
        m = json.loads((Path(d) / "corpus/companies_act/_manifest.json").read_text())
        check(seen == ["11"], "--limit truncates what is fetched")
        check(m["count"] == 3,
              "...but the manifest still records all 3 -- a partial fetch is not a smaller Act")

    # ── an unknown key refuses and names what is known ──────────────────────
    check(main(["no_such_act"]) == 1, "an unknown key refuses")
    check(main(["--list"]) == 0, "--list exits 0")
    check(main([]) == 1, "no argument is a usage error, not a default Act")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main(sys.argv[1:]))
