#!/usr/bin/env python3
"""Which law answered: the corpus by content, and the instruments that amended it.

T1. `as_of` already said WHEN the corpus was fetched and whether a point in time could be
verified. It could not say WHICH corpus. Two deployments that fetched on the same day, one
of them re-ingested after a correction, produced identical `law_version` blocks and
different answers -- and nothing in a trace distinguished them.

## ONE identity, and it is not mine

Every hash here is a **git blob id** -- `sha1("blob <len>\0" + bytes)` -- because
`008_decision_evidence.sql` already established that identity for `runs.law_versions`:

  > The same identity `public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer
  > cache) compare one thing.

My first version used an independent sha256 of the bytes. That would have been a SECOND
identity for the same fact, which is the thing 008 spent a paragraph preventing, and the
failure is quiet: the cache keys on one, a dispute is argued on the other, and they agree
until the day they do not. `corpus_hash` is therefore a hash OF the blob ids, never of the
bytes directly, so the whole-corpus marker and the per-record map cannot disagree by
construction. `.claude/loops/DECISION_law_versions_on_runs.md` has the whole of it.

## Why a hash and not a version number

A version number is a promise someone has to keep. Nobody increments it on a re-ingest, a
hand-correction, or a partially failed fetch, and the one time it matters is the one time it
was not bumped. A content hash cannot be forgotten: it changes because the bytes changed,
which is the only question a reader of an old answer actually has -- *was the law I am
looking at now the law that answered then?*

## What is hashed, and what is deliberately not

Every `*.json` record under `corpus/companies_act`, by (relative path, sha256 of bytes),
sorted. So:

  - a changed provision changes the hash
  - an ADDED or REMOVED provision changes the hash, because the path list is part of it
  - the order files happen to be listed in does not, because it is sorted
  - mtimes, permissions and the directory's own inode do not, because a re-clone of the same
    content must hash the same or the hash is useless across machines

`_index.json` and `_manifest.json` ARE included: they decide which records are reachable, so
a corpus whose index changed is a different corpus even if every provision is byte-identical.

## Instruments

`instruments_for` reports the amending instruments carried by the provisions that answered,
from the records themselves -- never from memory, and never a guess. A provision whose
record names no instrument contributes nothing rather than an "unamended" claim: this
repository holds one Act and does not hold a complete amendment history, so "no instrument
found" and "never amended" are different statements and only the first is true.

Run: PYTHONPATH=. python3 checker/law_versions.py --test
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus/companies_act"

# Shown instead of a hash when the corpus is not on disk at all. NOT a hash of nothing:
# a reader must be able to tell "this deployment has no corpus" from "this corpus hashes
# to e3b0c442…", which is what sha256 of zero bytes would have said.
NO_CORPUS = "NO_CORPUS"


def _records(corpus_dir: Path) -> list[Path]:
    return sorted(p for p in corpus_dir.glob("*.json") if p.is_file())


def blob_id(data: bytes) -> str:
    """Git's own blob id for these bytes. THE identity for held text in this repository.

    `008_decision_evidence.sql` fixed this formula for `runs.law_versions` and
    `public_only.Origin.blob` carries the same one, so recall (O7) and the answer cache (O9)
    compare one thing. Anything that hashes held text differently is a second identity for
    one fact.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def blob_ids(paths, root: Path | None = None) -> dict:
    """{repo-relative path: git blob id} for the held text a run READ.

    The shape `runs.law_versions` takes. A path that cannot be read RAISES: a missing version
    is not an empty one, and 008 says NULL means "not recorded" while `{}` would claim the run
    read no law.
    """
    base = Path(root or ROOT)
    out = {}
    for rel in paths:
        out[str(rel)] = blob_id((base / str(rel)).read_bytes())
    return out


def corpus_hash(corpus_dir: Path | None = None) -> str:
    """`sha256:<12 hex>` over the corpus content, or NO_CORPUS.

    Twelve characters, not sixty-four: this goes in every envelope and every run row, it is
    compared for equality by eye as often as by code, and 48 bits is ample for telling two
    corpora apart when there are a handful in the world. The full digest is available from
    `corpus_digest()` for anyone who needs to be certain.
    """
    full = corpus_digest(corpus_dir)
    return full if full == NO_CORPUS else f"sha256:{full[:12]}"


def _fingerprint(corpus_dir: Path) -> tuple:
    """A cheap stand-in for "has anything changed": (path, size, mtime) per record.

    This is the CACHE KEY, never the hash. Keying the cache on the directory path alone was
    wrong and my own test caught it: a changed byte returned the previous digest, which
    defeats the single question the hash exists to answer -- *was the law I am looking at now
    the law that answered then?* A corpus re-ingested in place would have gone on reporting
    the hash of the corpus it replaced.

    537 `stat` calls, not 537 reads, so this is cheap enough to do on every envelope.
    """
    return tuple((p.name, st.st_size, st.st_mtime_ns)
                 for p in _records(corpus_dir)
                 for st in (p.stat(),))


@lru_cache(maxsize=8)
def _digest_cached(corpus_dir: str, _fp: tuple) -> str:
    d = Path(corpus_dir)
    if not d.is_dir():
        return NO_CORPUS
    files = _records(d)
    if not files:
        return NO_CORPUS
    h = hashlib.sha256()
    for p in files:
        # The PATH goes in as well as the blob id, so adding or removing a record changes the
        # hash even when no remaining record changed. The per-file identity is the GIT BLOB
        # ID, not a second hash of the bytes -- see the module docstring.
        h.update(p.relative_to(d).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(blob_id(p.read_bytes()).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def corpus_digest(corpus_dir: Path | None = None) -> str:
    """The full 64-character digest, or NO_CORPUS. Cached on a stat fingerprint."""
    d = Path(corpus_dir or CORPUS_DIR)
    if not d.is_dir():
        return NO_CORPUS
    return _digest_cached(str(d), _fingerprint(d))


# Both shapes a provision arrives in, because BOTH are real and I found the second one by
# printing a live envelope rather than by reading the code:
#   `s.92`, `s.92(1)`, `ss.92 and 96`   -- the display and query form
#   `ACT:COMPANIES_ACT_2013:S92`        -- the evidence pack's `usable_keys`, which is what
#                                          `ask_read` actually passes in
# Matching only the first returned [] for every real question while the fixtures passed.
_SECTION_FORMS = (__import__("re").compile(r"s\.\s*(\d+[A-Z]?)", __import__("re").I),
                  __import__("re").compile(r":S(\d+[A-Z]?)\b", __import__("re").I))


def _sections_in(provisions) -> set:
    """The section numbers named by a list of provisions, in either shape."""
    out = set()
    for p in provisions or ():
        text = str(p)
        for pat in _SECTION_FORMS:
            out.update(m.group(1).upper() for m in pat.finditer(text))
    return out


def _section_files(corpus_dir: Path) -> dict:
    """section number -> record path, via `_index.json`.

    Falls back to a record's own `section_number` field when there is no index, so a
    hand-built fixture corpus works too. Never guesses from the file name: `184.json` is
    s.1, and treating the stem as a section number would silently answer about s.184.
    """
    out: dict[str, Path] = {}
    index = corpus_dir / "_index.json"
    if index.is_file():
        try:
            entries = (json.loads(index.read_text(encoding="utf-8")).get("entries") or {})
        except (ValueError, OSError):
            entries = {}
        for number, meta in entries.items():
            sid = str((meta or {}).get("section_id") or "").strip()
            if sid:
                out[str(number)] = corpus_dir / f"{sid}.json"
        if out:
            return out
    for rec in _records(corpus_dir):
        if rec.name.startswith("_"):
            continue
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        number = str(data.get("section_number") or data.get("section") or "").strip()
        if number:
            out[number] = rec
    return out


def instruments_for(provisions, corpus_dir: Path | None = None) -> list[dict]:
    """The amending instruments the given provisions' own records name.

    Read from the records, never from memory. A provision whose record names none
    contributes nothing: this repository does not hold a complete amendment history, so
    "no instrument found" is not "never amended" and must not be rendered as one.
    """
    import re
    d = Path(corpus_dir or CORPUS_DIR)
    if not d.is_dir():
        return []
    wanted = _sections_in(provisions)
    if not wanted:
        return []
    # A record is named by its India Code `section_id`, NOT by its section number: the file
    # for s.1 is `184.json`. `_index.json` holds the mapping and `evidence_pack` already
    # goes through it. My first version looked for a `section_number` key INSIDE the record,
    # which no record has -- so `instruments` came back empty for every question while 201
    # of 527 records carried a citation. Found by counting, not by reading the code again.
    by_number = _section_files(d)
    found: dict[str, dict] = {}
    for section in sorted(wanted):
        rec = by_number.get(section)
        if rec is None or not rec.is_file():
            continue
        try:
            data = json.loads(rec.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for ins in _instruments_in(data):
            found.setdefault(ins, {"instrument": ins, "sections": []})
            found[ins]["sections"].append(section)
    for v in found.values():
        v["sections"] = sorted(set(v["sections"]), key=lambda s: (len(s), s))
    return [found[k] for k in sorted(found)]


_INSTRUMENT = __import__("re").compile(
    # G.S.R. 880(E), S.O. 1234(E), and Act-style citations the records carry verbatim.
    r"(?:G\.S\.R\.|S\.O\.)\s*\d+\s*\(E\)|Act\s+\d+\s+of\s+\d{4}")


def _instruments_in(data) -> list[str]:
    """Every instrument citation anywhere in one record, found by pattern on its own text."""
    out = []

    def walk(node) -> None:
        if isinstance(node, str):
            out.extend(m.group(0).strip() for m in _INSTRUMENT.finditer(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(data)
    return out


def records_read(provisions, corpus_dir: Path | None = None) -> dict:
    """{repo-relative path: git blob id} for the records these provisions were read from.

    What goes in `runs.law_versions` for an ask, in the shape 008 defined. Only the records
    actually resolved: a map covering the whole corpus would claim the run read 527 records.
    """
    d = Path(corpus_dir or CORPUS_DIR)
    if not d.is_dir():
        return {}
    by_number = _section_files(d)
    paths = sorted({by_number[n] for n in _sections_in(provisions)
                    if n in by_number and by_number[n].is_file()})
    try:
        rel = [p.relative_to(ROOT).as_posix() for p in paths]
    except ValueError:
        # A corpus outside the repository (a fixture in /tmp): key on the name, since a
        # repo-relative path does not exist. Never silently empty.
        return {p.name: blob_id(p.read_bytes()) for p in paths}
    return blob_ids(rel)


def law_versions(provisions=(), corpus_dir: Path | None = None) -> dict:
    """The block that goes in an envelope and on a run row."""
    return {"corpus_hash": corpus_hash(corpus_dir),
            "record_count": len(_records(Path(corpus_dir or CORPUS_DIR)))
                            if Path(corpus_dir or CORPUS_DIR).is_dir() else 0,
            "instruments": instruments_for(provisions, corpus_dir),
            "note": ("the corpus hash identifies the law that answered, by content. "
                     "`instruments` lists only what the answering provisions' own records "
                     "name -- a provision with none is not a provision that was never "
                     "amended, and this repository does not hold a complete amendment "
                     "history")}


def _test() -> int:
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

    print("law_versions")

    # ── the real corpus ─────────────────────────────────────────────────────
    h = corpus_hash()
    check(h.startswith("sha256:") and len(h) == len("sha256:") + 12,
          f"the held corpus hashes to a short, readable identifier ({h})")
    check(corpus_hash() == h, "the hash is STABLE across calls on unchanged bytes")
    check(len(corpus_digest()) == 64, f"the full digest is available for certainty "
                                      f"({corpus_digest()[:16]}…)")

    # ── two corpora are distinguishable: the whole point of T1 ──────────────
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        pa, pb = Path(a), Path(b)
        (pa / "1.json").write_text('{"section_number": "96", "text": "annual general"}')
        (pb / "1.json").write_text('{"section_number": "96", "text": "annual general"}')
        check(corpus_hash(pa) == corpus_hash(pb),
              f"two corpora with IDENTICAL content hash the SAME -- a re-clone on another "
              f"machine must match, or the hash is useless ({corpus_hash(pa)})")
        (pb / "1.json").write_text('{"section_number": "96", "text": "annual  general"}')
        check(corpus_hash(pa) != corpus_hash(pb),
              f"a single changed byte changes the hash ({corpus_hash(pa)} vs "
              f"{corpus_hash(pb)})")
        (pb / "1.json").write_text('{"section_number": "96", "text": "annual general"}')
        check(corpus_hash(pa) == corpus_hash(pb), "...and changing it back changes it back")
        (pb / "2.json").write_text('{"section_number": "97", "text": "tribunal"}')
        check(corpus_hash(pa) != corpus_hash(pb),
              "an ADDED record changes the hash, because the path list is hashed too -- a "
              "corpus that grew a provision is not the corpus that answered")

    # ── an absent corpus says so, rather than hashing nothing ───────────────
    with tempfile.TemporaryDirectory() as e:
        check(corpus_hash(Path(e)) == NO_CORPUS,
              f"an empty corpus is {NO_CORPUS}, not the sha256 of zero bytes -- "
              f"'no corpus' and 'a corpus that happens to hash to e3b0c442' are different "
              f"facts ({corpus_hash(Path(e))})")
        check(corpus_hash(Path(e) / "nope") == NO_CORPUS,
              "a missing directory says the same")

    # ── instruments are READ, never remembered ──────────────────────────────
    with tempfile.TemporaryDirectory() as t:
        p = Path(t)
        (p / "a.json").write_text(json.dumps(
            {"section_number": "96", "text": "substituted by G.S.R. 880(E) dated 2016"}))
        (p / "b.json").write_text(json.dumps(
            {"section_number": "97", "text": "no instrument is named here at all"}))
        got = instruments_for(["s.96"], p)
        check([i["instrument"] for i in got] == ["G.S.R. 880(E)"],
              f"an instrument in the record is reported ({got})")
        check(instruments_for(["s.97"], p) == [],
              f"a provision whose record names none contributes NOTHING -- an 'unamended' "
              f"claim would be a statement this repository cannot support "
              f"({instruments_for(['s.97'], p)})")
        check(instruments_for([], p) == [],
              "no provisions asked about means no instruments claimed")
        check(instruments_for(["s.999"], p) == [],
              "a provision not in the corpus contributes nothing, rather than erroring")
        both = instruments_for(["s.96", "s.97"], p)
        check(len(both) == 1 and both[0]["sections"] == ["96"],
              f"...and the instrument names WHICH section carried it ({both})")

    # ── against the REAL corpus, because a fixture proved nothing here ──────
    # The first version of `instruments_for` read a `section_number` key from inside each
    # record. No record has one -- a record is named by its India Code `section_id`, so s.1
    # is `184.json` -- and every fixture test above still passed, because the fixtures I
    # wrote had the key the code expected. `instruments` came back EMPTY for every real
    # question while 201 of 527 records carried a citation. Measured, not re-read.
    real = instruments_for(["s.92"])
    check(len(real) >= 3,
          f"a real, heavily amended provision reports its instruments -- s.92 (annual "
          f"return) has been amended three times by Act and once by order "
          f"({[i['instrument'] for i in real]})")
    check(all(i["sections"] == ["92"] for i in real),
          f"...each naming the section it was read from ({real[:1]})")
    check(instruments_for(["s.96"]) and instruments_for(["s.135"]),
          "two other real provisions resolve too, so this is the index working rather than "
          "one lucky record")
    carriers = sum(1 for rec in _records(CORPUS_DIR)
                   if not rec.name.startswith("_")
                   and _instruments_in(json.loads(rec.read_text(encoding="utf-8"))))
    check(carriers > 150,
          f"and {carriers} of the corpus's records carry at least one instrument citation. "
          f"This is the number that made the bug visible: a feature returning [] for every "
          f"question, over a corpus where 38% of records have something to say")

    # ── the shape `ask_read` really passes, found by printing a live envelope ──
    check(_sections_in(["ACT:COMPANIES_ACT_2013:S92"]) == {"92"},
          f"an evidence-pack `usable_keys` entry resolves to its section. This is the shape "
          f"the ONLY caller passes, and matching just `s.92` made the envelope report no "
          f"instruments for every question ({_sections_in(['ACT:COMPANIES_ACT_2013:S92'])})")
    check(_sections_in(["s.96(1)"]) == {"96"} and _sections_in(["ss.92 and 96"]) == {"92"},
          f"the display form still resolves ({_sections_in(['s.96(1)'])}) -- `ss.92 and 96` "
          f"gives only 92 because 96 carries no `s.` prefix, which is honest about what was "
          f"matched rather than clever ({_sections_in(['ss.92 and 96'])})")
    check(instruments_for(["ACT:COMPANIES_ACT_2013:S92"]) == instruments_for(["s.92"]),
          "both shapes give the same answer, so the envelope and a hand query agree")

    # ── ONE identity: the gateway and this module must not differ ───────────
    # `008_decision_evidence.sql` fixed the identity for `runs.law_versions` -- "the same
    # identity `public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer cache)
    # compare one thing" -- and move 6's first draft added a second sha256 of the same bytes.
    # Two identities for one fact agree until the day they do not.
    # The check that the GATEWAY agrees with this module lives in `gateway/verbs.py`, not
    # here: `checker/rings.py` refuses a Ring 0 module that reaches Ring 2, and it caught
    # this import even inside `_test()`. Ring 2 may import Ring 0, so the check belongs on
    # that side. The firewall working is worth more than the convenience of one import.
    _sample = ["corpus/reference/SS-1.txt"]
    _mine = blob_ids(_sample)[_sample[0]]
    check(len(_mine) == 40 and all(c in "0123456789abcdef" for c in _mine),
          f"...and it is a git blob id -- 40 hex, the shape `runs.law_versions` already "
          f"stores and `public_only.Origin.blob` already carries ({_mine[:12]}…)")
    _read = records_read(["ACT:COMPANIES_ACT_2013:S92"])
    check(len(_read) == 1 and all(len(v) == 40 for v in _read.values())
          and all(k.startswith("corpus/companies_act/") for k in _read),
          f"a run's `law_versions` covers the records it READ, keyed on the repo-relative "
          f"path -- not all 527, which would claim it read the whole Act ({_read})")
    check(records_read([]) == {},
          "no provisions means an empty map, which the caller turns into NULL: 008 says "
          "NULL is 'not recorded' and `{}` would claim the run read no law")
    # And the corpus hash is a hash OF those blob ids, so it cannot drift from them.
    import inspect as _lv_inspect
    _src = _lv_inspect.getsource(_digest_cached)
    check("blob_id(" in _src and "sha256(p.read_bytes())" not in _src,
          "the corpus hash is built from the blob ids, never from a second hash of the "
          "bytes -- the two cannot disagree by construction rather than by agreement")

    # ── the envelope block ──────────────────────────────────────────────────
    blk = law_versions(["s.96(1)"])
    check(set(blk) == {"corpus_hash", "record_count", "instruments", "note"},
          f"the block has a fixed shape, so a reader can rely on the keys ({sorted(blk)})")
    check(blk["record_count"] > 500,
          f"...and reports how many records that hash covers ({blk['record_count']})")
    check("never amended" in blk["note"],
          "...and says in words that a missing instrument is not an absence of amendment")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
