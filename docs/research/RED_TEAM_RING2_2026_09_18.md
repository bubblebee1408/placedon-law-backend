# Red team: the Ring 2 feed layer

Adversarial review of `checker/rings.py`, `checker/feeds/`, `checker/robots.py`,
`scripts/watch_gazette.py`, `scripts/watch_ofac.py`, `scripts/gazette_digest.py`, as they
stood at `c2d7c0d` on branch `wave3-e`. Every finding below is proven with a runnable
snippet (`PYTHONPATH=.`, synthetic ASTs/bytes/transports, no live network) unless marked
REASONED. Worked in the mandated lens order P1 -> P7; FATALs surfaced immediately in P1.

---

## P1 — the ring firewall (`checker/rings.py`)

### RT-01 — FATAL — any dynamic import mechanism is completely invisible to the guard

**File:** `checker/rings.py:199-215` (`_imported_names`), which only walks `ast.Import` and
`ast.ImportFrom` node types.

**Concrete input:** a Ring 0 module (e.g. `checker.obligations`) reaching a Ring 2 feed via
any of:
- `importlib.import_module("checker.feeds.ofac_sdn")` — literal string
- `importlib.import_module("checker." + "feeds" + "." + "ofac_sdn")` — built string
- `__import__("checker.feeds.ofac_sdn", fromlist=["entries"])`
- `sys.modules["checker.feeds.ofac_sdn"]` — no import statement at all, just a dict read
  against whatever some *other*, legitimate Ring 2/3 consumer already imported at process
  startup
- `exec("import checker.feeds.ofac_sdn as feed", ns)` — a real `import` statement, just
  hidden inside a string the AST walker never re-parses

**What happens:** none of these appear as `ast.Import`/`ast.ImportFrom` nodes — they are
`ast.Call` nodes (or, for `sys.modules`, a `Subscript`) — so `_imported_names` never records
them, `_leaks_upward` returns `[]`, and `violations()` reports the codebase clean while a
Ring 0 decider is reading forecast/feed data at runtime.

**PROVEN.** Ran all five against `checker.rings._leaks_upward()` directly:

```
[MISSED] importlib.import_module (literal name): leaks=[]
[MISSED] importlib.import_module (built from string parts): leaks=[]
[MISSED] __import__ builtin: leaks=[]
[MISSED] sys.modules lookup (module already imported by someone else in-process): leaks=[]
[MISSED] exec() containing a real import statement: leaks=[]
```

Full snippet in this report's appendix (§Snippets, RT-01). Every one of these is ordinary,
unremarkable Python — none require exotic bytecode tricks, and the `sys.modules` variant
requires **no import syntax whatsoever** in the offending file: it only requires that
*something else* in the running process has already imported the Ring 2 module once, which
is guaranteed the moment any Ring 2/3 consumer legitimately uses it.

**Severity reasoning:** the module's own docstring frames this guard as the structural
replacement for a code-review convention, explicitly because "an AST walk does not forget."
That claim is true only for the literal-`import` surface. The guard has zero coverage of
the entire dynamic-import surface of the language it is written in, and that surface is not
obscure — `importlib.import_module` is the standard way to do a conditional/lazy import in
any codebase, and `sys.modules` lookups are a common caching idiom. A single such call
anywhere in a Ring 0 decider defeats the firewall permanently and silently, with no
CI signal, because `violations()` returns `[]` either way.

**Minimal fix:** this is a structural limitation of any AST-only guard; closing it requires
either (a) a runtime import hook (e.g. wrapping `builtins.__import__` / registering a
`sys.meta_path` finder during tests/CI that raises when a Ring 0/1 module's call stack
crosses into a Ring 2/3 module, regardless of how it got there), or (b) also flagging, at
minimum, calls to `importlib.import_module`, `__import__`, and subscripts of `sys.modules`
appearing anywhere in a Ring 0/1 module's AST, and requiring their argument to be a
literal string checkable against the registry (reject non-literal arguments outright, since
a computed module name can't be checked statically at all). (b) is partial — it still misses
the string-in-`exec()` case — so (a) is the only complete fix.

### RT-02 — FATAL — transitive leak through an unregistered helper module

**File:** `checker/rings.py:241-267` (`violations()`) and `:218-234` (`_leaks_upward`).

**Concrete input, exactly as the task specifies:** an unregistered module
`checker._redteam_helper` that does `from checker.feeds.ofac_sdn import entries` at module
level, imported by a real, registered Ring 0 module via a completely ordinary, literal,
top-level `from checker._redteam_helper import get_signal`.

**What happens:** `violations()` iterates `REGISTRY.items()`, parses **only** the AST of
each *registered* Ring 0/1 module, and checks whether *that file's own* import statements
name a Ring 2/3 target. It never follows an import to inspect what the imported module
itself imports — there is no transitive closure anywhere in this file. Since
`checker._redteam_helper` is not in `REGISTRY` and does not fall under the `checker.feeds`
`PACKAGE_RINGS` prefix, `ring_of("checker._redteam_helper")` returns `None`, which
`_leaks_upward` explicitly never flags (`target in (RING_2, RING_3)` is `False` for `None`).
The result is a real, one-hop runtime data flow from Ring 2 into Ring 0 that the guard
cannot see even in principle, because it only checks direct import targets, and any module
not itself classified is invisible cover.

**PROVEN**, two ways:

1. Direct AST scan of the Ring 0 module's own source (what `_leaks_upward` actually sees):
   `_leaks_upward(ast.parse(ring0_src), "checker.obligations", RING_0) == []`.
2. End-to-end through the real `violations()` function against a synthetic `REPO_ROOT`
   (temp directory containing `checker/obligations.py` importing `checker/_redteam_helper.py`
   which imports `checker.feeds.ofac_sdn`; no files in the actual repository were touched —
   `REGISTRY`/`PACKAGE_RINGS`/`REPO_ROOT` were monkeypatched and restored in a `finally`):
   `violations()` returns `[]` despite the constructed leak being real and live.

Output:
```
_leaks_upward on the Ring-0 module's own AST: []  <- ring_of('checker._redteam_helper') = None
violations() against the synthetic repo: []
  (checker.obligations DOES transitively read a Ring-2 feed at runtime; violations() reports nothing)
```

**Severity reasoning:** this is worse than a missed edge case — it means the "PACKAGE_RINGS
closes the forgotten-registration hole" fix documented in the module's own comment
(`checker/rings.py:140-149`) only closes the hole for a module that is *directly* imported
by a Ring 0/1 file. It reopens the identical hole one hop away: *any* existing, innocuous,
unregistered utility module anywhere in the tree (a string helper, a date util, a cache
wrapper — nothing that has to look suspicious) becomes usable as a laundering hop the
instant it imports something from `checker.feeds`. No new "unregistered feed" is even
needed for this variant — an already-registered feed reached through one indirection is
enough.

**Minimal fix:** `violations()` needs to compute the transitive import closure of every
Ring 0/1 module (walk imports recursively through unregistered modules, stopping only at
registered/ring-classified or third-party boundaries) rather than checking one file's direct
imports. This is more expensive but tractable at this codebase's size, and it is the only
way to keep the "a feed is Ring 2 because of WHERE it lives, and cannot escape by being
forgotten" guarantee the module already claims for direct imports.

### Checked and held (P1)

- **Literal nested import inside a function**, exactly the shape the module's own
  `_test()` negative control exercises, is genuinely caught: `import
  checker.feeds.ofac_sdn` inside a function body of a Ring 0 module produces
  `[('checker.feeds.ofac_sdn', 2, 2)]`. The AST-walk-not-just-toplevel design point is real
  and works as documented, for this one import shape.
- **`from checker.feeds import ofac_sdn`** (the package-level import) is also caught,
  correctly resolving both `checker.feeds` and `checker.feeds.ofac_sdn` to Ring 2.
- **`PACKAGE_RINGS` prefix matching is on whole dotted segments, not substrings**:
  `checker.feedsX.evil` does not match the `checker.feeds` prefix (`ring_of(...) is None`,
  correctly not flagged). Confirmed directly, matching the existing test's own claim.
- A registered module whose source file is missing is reported by name, not silently
  skipped (verified by reading the existing `_test()`, not independently re-run, since it
  is already exercised by the repo's own suite at `checker/rings.py:394-401`).

---

## P2 — fail-closed in `checker/feeds/common/fetch.py`

### RT-03 — MAJOR — an empty 200 body is legal and indistinguishable from a genuine empty document

**File:** `checker/feeds/common/fetch.py:218-228` (`_finish`) and `checker/feeds/__init__.py:169-190`
(`FetchResult.__post_init__`).

**Concrete input:** an opener returning `_FakeResponse(200, b"", headers={"Content-Length": "0"})`.

**What happens:** `FetchResult.__post_init__` only forbids the inverse case (non-ACCESSIBLE with
non-empty content); it never requires ACCESSIBLE to carry non-empty content. `_finish` computes
`too_large=False, content=b""` and returns `source_behaviour=ACCESSIBLE`. **PROVEN:**
`source_behaviour='ACCESSIBLE' content=b'' http_status=200 note=''`. A WAF, load balancer, or
misconfigured origin that answers `200` with a blank body (a very common failure shape — many
WAFs return `200` with an empty or generic body for a soft-block, rather than a real 403) is
recorded exactly the same way as "the source truly published zero bytes today."

**Severity reasoning, tempered by what I found downstream:** `checker/feeds/ofac_sdn.py`'s
`entries()` calls `ET.iterparse` unconditionally, and **on empty content this raises
`xml.etree.ElementTree.ParseError: no element found`** rather than silently yielding zero
entries (proven below, RT-06). So for the OFAC feed specifically, an empty-but-ACCESSIBLE fetch
crashes loudly in `OfacSdnFeed.parse()` rather than reporting "0 sanctioned entities" — this
downgrades RT-03's practical impact on OFAC alone from FATAL to MAJOR (an uncaught exception is
still a bug — see RT-06 for what it does to the watcher — but it is not a *silent* false-clear).
`checker/feeds/egazette.py` independently guards the same class of input at the payload layer:
its `parse()` explicitly checks `if not items` and reports `listing_empty_means: "the page could
not be read as a listing; NOT 'nothing was published'"` (`egazette.py:242-246`) — a real,
deliberate defense already in place there. The residual risk is (a) any *future* Ring 2 adapter
that does not repeat one of these two guards, and (b) the fact that the guard lives in each
adapter rather than in `fetch()`/`FetchResult` itself, so it is opt-in per adapter rather than
structural.

**Minimal fix:** either reject `ACCESSIBLE` + empty `content` in `FetchResult.__post_init__`
(treat a 200-with-empty-body as its own accessibility state, distinct from a normal success), or
require every `Feed.parse()` implementation to handle it explicitly and cover that requirement
with a shared test.

### RT-04 — FATAL — a mid-transfer connection drop is accepted as a complete, correct fetch

**File:** `checker/feeds/common/fetch.py:113-138` (`_read_capped`).

**Concrete input:** a response that declares `Content-Length: 5000000` but whose `.read()`
delivers only 351 bytes and then returns `b""` forever after — exactly how a dropped TCP
connection, a proxy timeout, or a server-side abort looks to `http.client`/`urllib`, which do
not distinguish "the server said goodbye" from "the server sent everything it meant to."

**What happens:** `_read_capped` only ever compares the running total against `max_bytes` (too
large) — it never compares the final total against the *declared* `Content-Length` to detect
under-delivery. The loop's only exit conditions are "cap exceeded" and "an empty read" (`if not
chunk: break`), and an empty read from a silently-closed socket is indistinguishable from a
clean EOF at the expected length.

**PROVEN:**
```
source_behaviour='ACCESSIBLE' content_len=351 http_status=200
content tail: ...b'IED HERE, REST OF DOCUMENT NEVER ARRIVED'
```
The 351-byte truncated fragment is returned as `ACCESSIBLE`, hashed over exactly those 351
bytes (so the hash is internally self-consistent — it is not lying about its own content — but
nothing on the `FetchResult` records that 5,000,000 bytes were promised and only 351 arrived).

**Downstream severity is adapter-dependent, and this is where it gets serious:**
- Against `ofac_sdn.py`: `entries()`'s `ET.iterparse` **does** raise `ParseError` on a
  truncated/malformed XML tail (proven under RT-06 below) — so *this specific* feed converts
  the silent truncation into a loud crash, which is a real (if accidental) safety net, not a
  silent false-clear. But an uncaught `ParseError` inside `OfacSdnFeed.parse()` is never
  caught by `scripts/watch_ofac.py`'s `poll()` either (`poll()` only branches on
  `result.source_behaviour`, `stated`/`parsed` count agreement, and cache/state errors — it does
  not wrap the `_summarise()`/`feed.parse()` calls in a `try/except`), so **the watcher process
  itself crashes uncleanly on a truncated-but-ACCESSIBLE fetch, with no logged entry at all**
  (verify: `poll()`'s only `append_log` calls are guarded by prior branches; an exception from
  `_summarise(result.content)` at `watch_ofac.py:252` propagates straight out of `poll()`,
  leaving `sys.exit` code and signal to whatever invoked the script — likely non-zero from an
  uncaught traceback, but with **no line written to `corpus/.ofac_watch.jsonl`** explaining why,
  unlike every other failure mode this script deliberately logs).
- Against a hypothetical HTML/text feed (`egazette.py`'s `parse_listing` uses regexes over
  `bytes.decode(..., errors="replace")`, not a strict parser) a truncated body would NOT raise —
  regex-based scraping degrades gracefully by design, silently returning fewer rows. Whether that
  becomes a false "nothing new" or a false "went backward" depends on which rows survive the cut
  — see RT-07/RT-08 below, which show this exact class of degraded-but-still-parses read produces
  a genuinely dangerous silent gap in the gazette watcher.

**Minimal fix:** compare the final total against a declared `Content-Length` (when one was sent)
and mark the result as a distinct failure state (not `ACCESSIBLE`) when they disagree, the same
way the module already treats an over-cap body as `BLOCKED` rather than truncating silently.

### RT-05 — MINOR — a relative `Location` header is misreported as "no Location header", and always refused

**File:** `checker/feeds/common/fetch.py:184-194` (`_handle_http_error`).

**Concrete input:** a 302 with `Location: /newpath/sdn.xml` (relative, not absolute).

**What happens:** `urlsplit("/newpath/sdn.xml").netloc == ""`, so `target_host` is empty, which
takes the same branch as "no Location header at all" and is refused (`BLOCKED`). **PROVEN:**
`note='entry host ofac.example.gov redirected (302) to (no Location header), which is not in
allow_redirect_hosts...'` — factually wrong (a `Location` header WAS present), though the
*behaviour* (refuse) is safe, not a security hole. It does mean a same-host relative redirect —
a completely ordinary server behaviour — can never be trusted no matter what a caller puts in
`allow_redirect_hosts`, since `target_host` can never be non-empty for it. Availability-only bug,
flagged fully under P7 as well.

**Minimal fix:** resolve a relative `Location` against `entry_url`'s own origin
(`urllib.parse.urljoin`) before computing `target_host`, and fix the note to distinguish
"relative, resolved to entry host" from "no Location header at all".

### Checked and held (P2)

- **Double-hop redirect** (a *trusted* redirect target itself answers with a further 3xx to an
  *untrusted* third host): refused. `fetch()` only ever follows one explicitly-trusted hop; any
  `HTTPError` from that second request — including another redirect — is treated as a hard
  refusal, never chased further. **PROVEN**: `source_behaviour='BLOCKED' content=b''`.
- **302 with no `Location` header at all**: fails closed (`BLOCKED`). **PROVEN.**
- **HTTP 300 and 304** (3xx codes outside `_REDIRECT_CODES` and outside the explicit 404/5xx
  branches): both fall through to the generic `return _refused(..., BLOCKED, ...)` at the end of
  `_handle_http_error` — neither is ever treated as `ACCESSIBLE`. **PROVEN** for both codes.
- Declared-oversize and actual-oversize bodies (already covered by the module's own `_test()`)
  were re-verified conceptually against `_read_capped`'s logic and are sound: both are `BLOCKED`,
  never truncated-and-served.

---

## P3 — the watchers (`scripts/watch_gazette.py`, `scripts/watch_ofac.py`)

This is the highest-value lens, and it produced the two most serious findings in this report.

### RT-06 — checked and held, feeding into RT-04/RT-08 — `ofac_sdn.entries()` raises loudly on empty/truncated XML

**File:** `checker/feeds/ofac_sdn.py:202-207` (`entries`), consumed by `parse()` at line 334 and
by `watch_ofac.py`'s `_summarise()` at line 137.

Ran four shapes of degraded XML through the real `OfacSdnFeed.parse()`/`_summarise()` path:
empty content, mid-tag truncation, truncation immediately after one complete `<sdnEntry>` (no
dangling tag), and truncation before the header. **All four raised
`xml.etree.ElementTree.ParseError`** rather than silently returning fewer/zero entries:
```
empty:                  ParseError: no element found: line 1, column 0
mid-tag truncation:     ParseError: no element found: line 5, column 36
clean cut after 1 entry: ParseError: no element found: line 5, column 0
header lost:            ParseError: unclosed token: line 3, column 22
```
This is a genuine positive: `xml.etree`/expat's strict well-formedness requirement means a
non-well-formed truncation of this feed cannot silently masquerade as "fewer entries" the way a
lenient HTML/regex scraper can (see RT-07/RT-08). The residual problem is not in `ofac_sdn.py`
itself — it is that **nothing in `scripts/watch_ofac.py`'s `poll()` catches this exception**
(see RT-04): the crash is real and loud to a human watching stdout/exit codes, but it produces
**no log line** explaining what happened, unlike every other failure branch `poll()` already
handles deliberately (fetch failure, count mismatch, corrupt state, corrupt cache all get an
`append_log` call before returning `EXIT_POLL_NOT_TRUSTWORTHY`; an XML `ParseError` gets none).

### RT-07 — FATAL — a stale/degraded-but-parseable Gazette read that goes BACKWARD is reported as a perfectly clean poll

**File:** `scripts/watch_gazette.py:57-96` (`poll`) and `checker/feeds/egazette.py:190-213`
(`watch`).

**Concrete input:** state file already holds `high_water=500` (established over prior polls).
The next poll's HTML page — still `ACCESSIBLE`, still well-formed, still non-empty (so
`readable = obs.source_behaviour == ACCESSIBLE and p["listed"] > 0` is `True`) — happens to list
only OLD rows, topping out at serial 290. This is realistic: a CDN/proxy cache serving a stale
snapshot, a session/token hiccup landing on a stale cached homepage, or (per RT-04's mechanism)
a truncated fetch that happens to retain only earlier rows.

**What happens, PROVEN** end-to-end through the real `poll()`:
```
stale/degraded poll: code=0
  entry: listed=1 high_water=290 new_serials=[] unseen_serials=[]
  state file high_water after this poll: 500
```
The state file correctly does NOT move backward (290 is not `> 500`) — that part is sound. But
`watch()`'s gap detector (`egazette.py:197-203`) computes
`unseen = [s for s in range(last_seen_serial + 1, top + 1) if s not in listed]`. When
`top (290) < last_seen_serial (500)`, `range(501, 291)` is **empty by construction** — Python
never raises or special-cases a backward range, it just silently produces nothing. The result is
`new=[]`, `unseen_serials=[]`, exit code `0`, and the poll is logged as an ordinary, unremarkable
success. **Anything the real Gazette published between serial 290 and whatever its true current
top is right now (unknowable from this poll) is never flagged as missed, never becomes an
`unseen_serial`, and produces no signal of any kind that something is wrong with the read
itself.** This is exactly the failure mode the module's own docstring warns against by name
(`watch_gazette.py:16-17`: "A watcher that silently skips what it missed is worse than no
watcher, because it produces a clean-looking record") — except the existing tests only exercise
the *forward* gap case (a poll skipped ahead, e.g. serials 294-296 unseen between 293 and 299);
nobody tested what happens when a poll's own top is *behind* the recorded mark.

**Minimal fix:** in `watch()`, when `top < last_seen_serial`, treat the poll as untrustworthy
(the modern equivalent of `checker/feeds/common/fetch.py`'s "fail closed, don't guess") rather
than computing an empty gap range — e.g. return a `regressed: True`/`anomaly` flag that
`scripts/watch_gazette.py`'s `poll()` treats the same as an unreadable page (`readable = False`,
baseline held, exit code 1), since a listing that goes backward is strong evidence the read
itself is not trustworthy, not evidence that nothing happened.

### RT-08 — FATAL — a crash between writing state and writing the log permanently loses the pending alert, in BOTH watchers

**Files:** `scripts/watch_gazette.py:82-90` (`poll`) and `scripts/watch_ofac.py:299-311` (`poll`).

**The shared bug shape:** both scripts advance their persisted high-water state
(`state.write_text(...)` / `write_state(state_path, new_state)`) **before** appending the
human-readable record of what was actually new to their `.jsonl` log. Neither write is wrapped
in a transaction and neither script uses write-then-rename (both call `Path.write_text` directly
on the live path, not a temp file swapped in atomically — see RT-09). If the process is killed,
OOM-killed, or the container is preempted in the gap between the two calls, the state file is
left pointing PAST the new item while the log — the only place either watcher's downstream
reader (`scripts/gazette_digest.py`, or a human reading `watch_ofac.py`'s stdout/log) ever learns
what that item WAS — never receives the entry. On the next run, the item no longer qualifies as
"new" (its serial/uid is not greater than / absent from the now-already-advanced baseline), so it
is never reported, ever, by any mechanism.

**PROVEN for `watch_gazette.py`:** established baseline at serial 499; simulated a crash by
making the log's `Path.open("a")` call raise `OSError` exactly where `poll()` calls it, after
`state.write_text()` for a new Ministry-of-Corporate-Affairs instrument (serial 500) had already
succeeded:
```
state file AFTER the crash: {'high_water': 500, 'updated_at': ...}
log file AFTER the crash: (only the baseline entry -- the crashed poll appended nothing)
next poll after restart: code=0 new_serials=[] new_corporate_affairs=[]
any log line names the actual gazette id CG-DL-E-17092026-500: False
any log line mentions 'Corporate Affairs' at all: False
```
The MCA instrument's identity never appears anywhere in the log — the only trace is an anonymous
integer (`high_water: 500`) on the *next* poll's log line, with no `new_items` entry (since it no
longer qualifies as new), so `scripts/gazette_digest.py`, which reads only that log, can never
render it and no human is ever told.

**PROVEN for `watch_ofac.py`,** same shape: baseline at 1 SDN entry; a newly-sanctioned entity
(uid 999) appears; simulated a crash by making `append_log` raise immediately after
`write_state()` succeeds in the `CHANGED` branch:
```
state file after crash: record_count=2 sha256=1488d06b8b...
log has 1 line (only the baseline -- the CHANGED event was never appended)
next poll after restart: rc=0 (0=UNCHANGED)
any log line, ever, mentions uid 999: False
```
A newly-sanctioned entity is added to the SDN list, and after this exact interruption, **no
record of that addition exists anywhere in this system, ever** — not the state file (which only
ever carries a hash/count pointer, not a diff), not the log (crashed before the append), and the
next poll reports `UNCHANGED` because it diffs against the already-advanced baseline.

**Severity reasoning:** this is the single most damaging finding in this report for a product
whose entire purpose is evidence-backed, un-droppable notice of exactly this class of change.
Both scripts' own docstrings state the design intent correctly ("the high-water mark advances
only after a successful... read", "a watcher that quietly moves its own baseline on a bad read
is worse than no watcher") — the bug is that the *ordinary success path*, not a bad read, can
itself lose data, because of write ORDER on two independent files with no atomicity or ordering
guarantee between them, under a failure mode (kill/OOM/preemption) that is completely realistic
for any long-running poller.

**Minimal fix:** swap the order in both scripts — append the log entry FIRST, then advance the
state file. That does not make either operation atomic, but it changes the failure mode from
"silent, permanent loss" to "the log has a record of the change but the baseline hasn't advanced
yet, so the same change gets reported again on the next run" — a duplicate alert is a nuisance;
a dropped one is the exact failure this system exists to prevent. Combine with RT-09 (atomic
write-then-rename) so a crash mid-write to either file can never produce a half-written state
that then needs a human to intervene, and ideally a single combined transaction log (log-then-
checkpoint, replayed on startup) rather than two independent files with an implicit ordering
dependency.

### RT-09 — MAJOR — neither watcher's state write is atomic (no write-then-rename)

**Files:** `scripts/watch_gazette.py:84` (`state.write_text(...)`), `scripts/watch_ofac.py:192-195`
(`write_state`).

**REASONED** (not independently reproduced with a real mid-write kill signal, which cannot be
simulated deterministically in-process the way RT-08's "crash between two separate calls" can —
but the code itself settles the question by inspection): both call `Path.write_text` directly on
the live state path. `Path.write_text` opens the file (truncating it), writes, and closes — there
is no temporary file plus atomic `os.replace`. A process killed mid-write (disk full, OOM,
preemption at exactly the wrong instant) leaves a truncated/partial JSON file on disk.

**What happens next, and why this is "held" rather than compounding:** both scripts' own
`load_high_water`/`load_state` functions already treat a corrupt/unparseable state file as a
hard stop (`watch_gazette.py:47-53` raises `SystemExit`; `watch_ofac.py:172-179` raises
`StateCorrupt`, itself turned into `EXIT_POLL_NOT_TRUSTWORTHY` with a logged reason). So a
mid-write crash degrades to "the next run refuses to proceed until a human fixes the file" —
annoying (a real availability cost — a human must intervene before polling can resume) but not a
silent correctness failure, and this is a real, deliberate, well-tested design choice already in
this codebase (see both scripts' `_test()` corrupt-state-file cases). Rated MAJOR rather than
FATAL because the failure is loud, not silent — but it compounds RT-08: a state write that
partially lands (long enough to update the high-water number but not, say, the `sha256`/
`artifact_path` in `watch_ofac.py`'s multi-field JSON) is a plausible way to reach the same "state
says X, but nothing agrees with X" outcome that Python's dict-based JSON serialization mostly
protects against for a single `write_text` call succeeding wholly or not at all in memory, but not
against a kill signal arriving mid-`write()` syscall on the underlying file descriptor.

**Minimal fix:** write to `path.with_suffix(path.suffix + ".tmp")` (or `tempfile.NamedTemporaryFile`
in the same directory) and `os.replace()` it onto the real path. `os.replace` is atomic on both
POSIX and Windows for same-filesystem renames, and turns "half-written" into "either the old file
or the new file, never a mix."

### Checked and held (P3)

- **First-run baseline handling** (`last_seen_serial=None` / `prev_state is None`): both watchers
  correctly report everything as new and invent no gaps — verified by reading the existing,
  already-passing `_test()` functions in both scripts (not independently re-run beyond what
  RT-07/RT-08's scripts already exercise).
- **A corrupt state file stops the run rather than silently resetting to "first run ever"**, in
  both watchers — this is a real, deliberate, and correctly-implemented defense against exactly
  the failure this report is looking for (see RT-09's discussion). Confirmed by reading
  `watch_gazette.py:44-54` and `watch_ofac.py:165-189`, both of which distinguish "no file"
  (legitimate first run) from "file exists but unreadable" (hard stop) as two different return
  paths, never conflated.
- **A network/robots failure never advances either baseline** — proven already by each script's
  own `_test()` (`watch_gazette.py`'s outage case; `watch_ofac.py`'s fetch-failure case), and
  consistent with what I found independently while building RT-07/RT-08's harnesses.
- **Two processes polling at once** — REASONED, not proven: neither script takes a lock (no
  `flock`, no lockfile, no atomic check-and-set on the state file) before reading state and later
  writing it. Two concurrent invocations (e.g. an overlapping cron run because the previous
  invocation hung on a slow network read) can both read the same `prev_state`/`last_seen`, both
  fetch, and both write — the second writer's `state.write_text()` simply overwrites the first's,
  and whichever log-append happens to interleave last "wins" no ordering guarantee either way.
  This does not obviously lose data on its own (both writers likely compute the same or a
  superset delta against the same baseline, so both log entries are probably each individually
  correct) but two log lines describing overlapping-but-not-identical deltas against the same
  stated baseline is a real, plausible source of confusion for a human reading the log, and is
  untested. Not chasing a proof given the higher-value FATALs above already fully occupy this
  lens's budget.
- **Clock skew** — REASONED: `observed_at`/`_now()` is always `datetime.now(timezone.utc)`,
  used only as a label in log entries and state files, never compared against another clock or
  used in any ordering/staleness decision inside either watcher (the actual gap/delta logic is
  keyed entirely on the Gazette's own serial numbers or OFAC's own uid set, not on wall-clock
  time). Clock skew on the polling machine would produce a log with a wrong-looking timestamp but
  would not, by itself, cause a missed or duplicated alert. Lower priority than the findings above
  and not further pursued.

---

## P4 — licence / Axis D (`checker/feeds/__init__.py`)

### RT-10 — MAJOR (no live exposure found, but zero enforcement) — `is_servable_commercially()` is purely advisory; nothing calls it outside tests

**Files:** `checker/feeds/__init__.py:108-124` (`may_serve_commercially`), `:236-237`
(`Observation.is_servable_commercially`).

**What I checked:** every call site of `is_servable_commercially`/`may_serve_commercially` in the
repository:
```
checker/feeds/ofac_sdn.py:412   -- inside _test()
checker/feeds/egazette.py:320   -- inside _test()
checker/feeds/__init__.py:295-401 -- inside _test()
```
**There is no call to either function anywhere outside a `_test()` function.** No API layer, no
serving endpoint, no script that renders feed output to a person or a system checks licence
before doing so. Confirmed by also searching every file outside `checker/feeds/` for any use of
`Observation(` or `checker.feeds` imports: only `checker/rings.py` (the registry, not a consumer)
and the two watcher scripts plus `scripts/gazette_digest.py` touch this module at all, and none of
the three checks licence.

**The type-level design itself is sound and is the right answer to the question "can a licence
be inferred, defaulted, or upgraded":** No. `Observation.licence` has no default value (a
`dataclass` field with no default, positionally/keyword-required), `may_serve_commercially`
raises `ValueError` on any string not in the closed `LICENCES` tuple rather than defaulting it
permissively, and both `NONCOMMERCIAL` and `LICENCE_UNVERIFIED` refuse commercial serving —
"absence of a known restriction is not evidence of permission," exactly matching CLAUDE.md's
rule for legal claims applied here to licence terms. There is no `promote()`/upgrade path on
`Observation` at all (verified: `not hasattr(obs, "promote")` is itself one of the module's own
tests). **So the answer to "can a licence be inferred/upgraded" is a clean, well-tested no.**

**The answer to "is it enforced at any chokepoint" is: no, it is purely advisory.** It exists as a
method a caller *may* invoke, with no caller in this codebase that does, and — because Ring 2
currently has no serving/API layer at all (CLAUDE.md and `checker/rings.py`'s own docstring both
say Ring 2 has nothing built on top of it yet) — this cannot be immediately exploited to serve
`LICENCE_UNVERIFIED` content to a paying customer today, only because there is no serving path to
exploit yet. The closest thing to a "serving" surface, `scripts/gazette_digest.py`, renders
`egazette.py`'s output (`LICENCE = LICENCE_UNVERIFIED`, confirmed at `egazette.py:90`) to a human
reader without ever checking licence — grep confirms zero occurrences of `licence`/`LICENCE`/
`is_servable`/`may_serve` anywhere in that file. That specific case is arguably fine on its own
facts (it is an internal prompt-a-human-to-go-acquire-it digest, not "shown to a PAYING customer,"
which is the exact bar `may_serve_commercially`'s docstring names), but it is also live proof that
nothing in this codebase currently *forces* the check to happen before rendering feed output
anywhere — the discipline exists only where a developer remembered to call it by hand.

**Minimal fix:** the day any Ring 2 output reaches a paying customer, licence enforcement needs
to live in the boundary a customer-facing response is constructed through (e.g. `Observation` — or
whatever serializes it for an API response — refuses to serialize/render a field when
`is_servable_commercially()[0]` is `False`, structurally, the same way `rings.py` enforces the
Ring 0/1 boundary rather than trusting a convention). Until that boundary exists, this is a loaded
gun with the safety off and nothing currently pulling the trigger — worth fixing before, not
after, the first commercial-serving code lands.

---

## P5 — parsing

### RT-11 — MAJOR — a nested `<span>` inside the Ministry column can misclassify a real Ministry of Corporate Affairs gazette as non-MCA

**File:** `checker/feeds/egazette.py:138-140` (`_column`).

**Concrete input:** `_column`'s regex is
`r'id="' + span_id_prefix + r'_(\d+)"[^>]*>(.*?)</span>'` (non-greedy `.*?` up to the FIRST
`</span>`). If a Ministry cell's markup ever contains an inner `<span>...</span>` before the real
text ends — e.g. `<span id="...MinistryE_0"><span class="abbr" title="MCA">Min.</span> of
Corporate Affairs</span>`, a completely ordinary shape for a government CMS to render (a tooltip,
an abbreviation wrapper, a responsive-design span) — the non-greedy match stops at the INNER
`</span>`, capturing only `"Min."` and discarding `" of Corporate Affairs"` entirely.

**PROVEN**, through the real `parse_listing()`:
```
ministry captured: 'Min.'
corporate_affairs flag: False
```
`corporate_affairs=(... CORPORATE_AFFAIRS in ministry.casefold())` checks for the substring
`"ministry of corporate affairs"` in the captured text; with only `"Min."` captured, this is
`False`. **A real, currently-live Ministry of Corporate Affairs notification, on a page whose
markup shifts this way, is silently classified as NOT a Corporate Affairs instrument and never
sets `needs a person` (exit code 0 instead of 2).** This directly defeats the one thing this
feed exists to flag, per its own module docstring's stated purpose. The live page as measured on
2026-09-17 does not do this (confirmed by the existing `_test()`'s fixture, which uses `<font
size="2">` wrappers, not nested `<span>`s) — this is a latent fragility against a markup change
the site could make at any time, not an active exploit against today's page. Rated MAJOR rather
than FATAL for that reason: it requires the source to change, not an attacker-controlled input in
the usual sense (nobody but eGazette itself controls this page's markup).

A milder version of the same bug (proven separately) truncates a `Subject` cell's real text
(`'real subject text'` -> `'hover text'`) rather than dropping the row — lower severity since
`subject` is already documented as untrustworthy/truncated (`GazetteItem.subject`'s own docstring:
"the page TRUNCATES this... never treat it as the text").

**Minimal fix:** match balanced/nested spans properly (a small hand-rolled depth counter, or
switch to an actual HTML parser — `html.parser.HTMLParser` is stdlib and already a dependency-free
option) rather than a single non-greedy regex that assumes no nesting.

### RT-12 — MINOR (REASONED from code inspection, no crash) — a Gazette ID's embedded date and its own Date column are never cross-checked

**File:** `checker/feeds/egazette.py:161-187` (`parse_listing`).

Each `GazetteItem`'s `published` field comes from the row's Date column (`get.get("date", ...)`),
and `gazette_id` independently encodes a date in its own format (`CG-DL-E-DDMMYYYY-N`). **PROVEN**
by constructing a row where the ID encodes `17-09-2026` but the Date column reads `01-Jan-2020`:
`parse_listing` accepts both without complaint —
`gazette_id='CG-DL-E-17092026-300002' published='01-Jan-2020'` — nothing in this module compares
them. Low severity today (both fields are currently informational/display-only for a human to go
verify against the PDF), but it means a rendering glitch or a hostile/compromised page could
present internally-inconsistent metadata with no signal that something is off.

### RT-13 — MINOR (REASONED) — the IMO shape check accepts non-ASCII Unicode digits, creating a lookup-miss risk

**File:** `checker/feeds/ofac_sdn.py:106` (`_IMO_SHAPE = re.compile(r"^\d{7}$")`).

Python's `\d` in a `str` pattern matches the full Unicode `Nd` (decimal digit) category by
default, not just ASCII `0-9`, unless `re.ASCII` is passed. **PROVEN:** the fullwidth-digit string
`"７４０６７８４"` (Unicode code points U+FF17 etc., visually resembling `7406784`) matches
`_IMO_SHAPE`, and `imo_check_digit_valid` computes a correct check-digit result on it (`int()`
on a Python `str` also accepts Unicode decimal digits, so the arithmetic is internally
consistent). The practical risk is not spoofing the check digit (the arithmetic is sound either
way) but **`vessels()` keys its output dict by the exact normalised string** — a vessel published
with a fullwidth-digit IMO would be indexed under the *fullwidth* string, and
`lookup_vessel("7406784", content)` (called with an ordinary ASCII IMO, the form any real-world
caller would use) would silently MISS it, since dict key lookup is exact string equality with no
Unicode normalisation (`NFKC`) applied anywhere in this path. Realism is low (OFAC's own published
XML is very unlikely to encode digits this way), but the check-digit function is also exercised
against externally-controlled input from a live feed, so it costs little to close.

**Minimal fix:** either compile `_IMO_SHAPE` with `re.ASCII`, or apply `unicodedata.normalize
("NFKC", ...)` before validating shape, so a look-alike digit string is rejected as not
IMO-shaped rather than silently accepted and indexed under a non-canonical key.

### Checked and held (P5)

- **XML entity expansion ("billion laughs") against `ofac_sdn.entries()`**: tested a
  classical small nested-entity payload (449 bytes -> 30,000-char expansion): parsed fine,
  no issue at that scale. Escalated to an 8-level, 20x-per-level DTD (1,262 bytes on the wire,
  ~256 GB of theoretical unmitigated expansion): **`ET.iterparse` raised `ParseError: limit on
  input amplification factor (from DTD and entities) breached`** in 0.071s. **This protection is
  CPython's own built-in expat billion-laughs mitigation (active by default since Python 3.7.1,
  bpo-30208) — `ofac_sdn.py` takes no defensive action of its own** (no `defusedxml`, no DTD
  disabling, no explicit entity-expansion limit set). The 64MB `max_bytes` cap in
  `checker/feeds/common/fetch.py` bounds the WIRE size only and does nothing against
  in-memory amplification — the actual protection here is entirely incidental to using
  `xml.etree.ElementTree`, not a defence this codebase built. Noted as MINOR residual risk
  (not independently exploitable today, given the stdlib default holds) rather than a live
  finding: a future switch to a different XML library, a `lxml`-based rewrite, or a Python build
  with `pyexpat`'s protection disabled/patched out would silently remove this safety net with no
  test in this codebase that would catch the regression, since nothing here tests for it directly
  (my proof above is the first test of this property against this code, and it is not part of
  the repo's own `_test()` suite).
- **`imo_check_digit_valid` against 8-digit input, a non-numeric string, and leading zeros**: all
  handled correctly and without crashing — 8 digits (`"12345678"`) and non-numeric input both
  fail the `_IMO_SHAPE` regex cleanly (returns `False`, no exception); leading zeros (`"0123456"`)
  are handled correctly since the check-digit arithmetic operates per-character
  (`[int(c) for c in imo]`), not on the string parsed as a whole number, so no octal/int-parsing
  surprise. `"0000000"` mathematically satisfies the check-digit formula (`True`) — a real-world
  data-quality curiosity (no real ship carries this IMO) rather than a security bug, since the
  function's job is exactly this: report the arithmetic fact, not guess plausibility.
- **A non-numeric or malformed Gazette ID / IMO shape does not crash `parse_listing`/`entries`** —
  confirmed via the existing `_test()` fixture's own `"NOT-A-GAZETTE-ID"` case (dropped, not
  repaired) and independently via the cases above.

---

## P6 — TLS (`checker/robots.py`, `checker/certs/intermediates.pem`)

### RT-14 — FATAL (elsewhere in the repo, found while answering this lens's literal question) — `scripts/ingest_companies_act.py` disables TLS verification entirely

**File:** `scripts/ingest_companies_act.py:32-34`:
```python
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
```
This is the script that ingests the **Companies Act 2013 corpus itself** — the primary legal
ground truth `corpus/companies_act/` is built from (`checker/robots.py`'s own docstring states
the opposite principle in the same repository: "an unverified source is worth less than no
source: it cannot distinguish [the real source] from anyone who can answer on its behalf"). This
script fetches over plain `urllib.request.urlopen(..., context=CTX)` with hostname checking and
certificate validation both explicitly turned off, meaning any network-position attacker (a
malicious Wi-Fi AP, a compromised upstream router, a DNS-spoofing attacker, a corporate/state TLS
interception box) can serve **arbitrary fabricated statutory text** for every section this script
ingests, with zero cryptographic signal that anything is wrong. **PROVEN by direct code
inspection** (grep across the whole repo for `CERT_NONE`/`check_hostname = False`/
`_create_unverified_context` found exactly this one hit — `checker/gemini_model.py:157` and
`checker/robots.py:47` only *mention* `_create_unverified_context` in a comment, explaining why
they do NOT do it).

**Mitigating context, stated plainly:** this script targets `indiacode.nic.in`
(`ACT_PAGE`/`CONTENT_EP` at lines 26-27), which CLAUDE.md's own Verification Status section
records as a **dead domain that 403s everything** as of this repository's current state — "the
live host is `indiacode.gov.in`... any hardcoded `.nic.in` URL is dead." So this exact script,
run today, most likely fails at the network layer before TLS matters at all, and it is very
plausibly a legacy/superseded script rather than one in active use (the currently-described
ingestion pipeline uses `indiacode.gov.in`'s REST API per CLAUDE.md, not this script's endpoint).
I did not find a newer, `.gov.in`-pointed equivalent to compare against in the time available for
this review — worth a maintainer's five-minute check to confirm this file is genuinely dead code
and either delete it or fix it, because as it stands, literally copying its request pattern
(updating only the hostname to the live `indiacode.gov.in`) into a new or resumed ingestion
script would silently reintroduce a complete MITM hole against the exact corpus this entire
product is graded on. Rated FATAL on the code as it stands (a real, unconditional, unverified-TLS
fetch path exists in this repository, fetching legal source text), tempered by "not currently
reachable against a live target" rather than downgraded outright — CLAUDE.md itself never says
this script has been retired, only that its hardcoded URL is dead.

**Minimal fix:** either delete this script if it is genuinely superseded, or repoint it at
`indiacode.gov.in` AND replace `CTX` with `checker.robots.ssl_context()` (which is exactly what
it exists for) rather than a hand-rolled unverified context.

### Checked and held (P6)

- **`VERIFY_X509_PARTIAL_CHAIN` is actually cleared, not just claimed to be.** **PROVEN**:
  built a real context via `checker.robots.ssl_context()` and inspected the live flag:
  `ctx.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN == 0`. `ctx.verify_mode == ssl.CERT_REQUIRED`
  and `ctx.check_hostname == True`, both as claimed. The module's central claim — that loading
  `certs/intermediates.pem` for chain completion does NOT turn those intermediates into trust
  anchors — rests on this flag being off, and it is confirmed off in this environment. I did not
  additionally build a live end-to-end handshake against a host presenting only an intermediate
  with no root in the trust store (out of scope for "no live network" and not necessary — the
  flag check directly settles the documented mechanism OpenSSL uses to decide this).
- **`_usable`'s >1024-byte check is not, and does not claim to be, a defence against a hostile
  `SSL_CERT_FILE`.** **PROVEN**: constructed a junk-padded 2,491-byte file containing no valid
  certificate (just comments and a fake PEM-shaped blob) and confirmed `_usable()` returns `True`
  for it purely on size, and `ca_bundle()` selects it when `SSL_CERT_FILE` points there. This is
  not a new hole this module opens — `SSL_CERT_FILE` is a standard OpenSSL/Python environment
  variable already trusted by design (an attacker who controls a victim process's environment
  variables typically already controls far more than its TLS trust store) — and the function's
  own docstring only ever claims to solve the *empty-stub-file* problem (the macOS
  `Install Certificates.command` gap), never content-level trust validation. Documented here as a
  REASONED, MINOR note rather than a finding: the size check is correctly scoped to the problem it
  says it solves, and should not be read as a broader content-integrity guard.
- **No path in `checker/robots.py` or `checker/feeds/` disables verification.** Confirmed by grep:
  the only `CERT_NONE`/`check_hostname=False` hit in the entire repository is
  `scripts/ingest_companies_act.py` (RT-14, outside this lens's two named files but squarely
  inside its literal question).

---

## P7 — language

Searched every user-facing string (payload fields, log/report text, `_report()`/digest output)
in `checker/feeds/*.py`, `checker/feeds/common/*.py`, `scripts/watch_gazette.py`,
`scripts/watch_ofac.py`, and `scripts/gazette_digest.py` for language implying "not sanctioned",
"cleared", "no change in law", "amended", "complete", or similar overreach.

**I did not find a FATAL or MAJOR violation.** Every place this class of claim could plausibly
slip in is explicitly, repeatedly hedged, and the hedging is load-bearing rather than decorative:

- `ofac_sdn.py` states three times, in three different surfaces (module docstring, `screen()`'s
  own docstring, and the `Observation` payload's `empty_result_means` field), that an empty
  screening result is "not on the list as published \<date\>", **explicitly** "NOT 'not
  sanctioned'".
- `watch_ofac.py`'s `_report()` states, for every REMOVED uid, "This is NOT 'cleared' and NOT
  'not sanctioned' -- see BLINDNESS=EITHER" (`watch_ofac.py:212-214`), and the module docstring
  states the same rule in prose before any code.
- `egazette.py`'s `parse()` explicitly distinguishes "the page could not be read as a listing"
  from "nothing was published" (`egazette.py:242-246`) — the exact "empty success != nothing
  happened" distinction P2/P3 probe for structurally, stated here as a matter of language too.
- `scripts/gazette_digest.py` hedges its one legally-adjacent claim ("The Act's amendment ledger
  we hold ends \<date\>; a new MCA instrument **may not be** reflected yet") rather than
  asserting currency or completeness.
- `watch()`'s `unseen_means` field states plainly that an unseen serial is "NOT 'does not
  exist'".

**One MINOR language defect, already surfaced under P2 as RT-05**, repeated here because it is
squarely a P7 issue too: `_handle_http_error`'s refusal note claims `"(no Location header)"` for
a redirect whose `Location` header was present but relative, which is simply false as written
(the behaviour it describes — refusing the redirect — is correct; only the stated reason is
wrong). This is the only place in the reviewed surface where a diagnostic string asserts
something the code did not actually observe.

**If nothing is FATAL here, it should be said plainly rather than inflated: nothing found in
this lens rises above MINOR.** This module was written with an unusually high, consistent
discipline about exactly the class of overclaim P7 asks about — the hedging language is dense,
repeated across module docstring / function docstring / payload field / test assertion for the
same fact each time, which reads as deliberate defence-in-depth against exactly this failure
mode, not an accident.

---

## Findings table

| id | lens | severity | file:line | one-line |
|---|---|---|---|---|
| RT-01 | P1 | FATAL | `checker/rings.py:199-215` | `importlib.import_module`/`__import__`/`sys.modules`/`exec` reach Ring 2 with zero AST-import footprint; `violations()` sees nothing |
| RT-02 | P1 | FATAL | `checker/rings.py:241-267` | any unregistered helper module is an untracked laundering hop — `violations()` never follows transitive imports |
| RT-03 | P2 | MAJOR | `checker/feeds/common/fetch.py:218-228` | a 200 with an empty body is legal `ACCESSIBLE`, indistinguishable from a genuinely-empty source (mitigated for OFAC/eGazette by adapter-level guards, not by `fetch()` itself) |
| RT-04 | P2 | FATAL | `checker/feeds/common/fetch.py:113-138` | declared `Content-Length` vs. actually-delivered bytes is never compared; a dropped connection is accepted as a complete `ACCESSIBLE` fetch |
| RT-05 | P2 | MINOR | `checker/feeds/common/fetch.py:184-194` | a relative `Location` header is misreported as "no Location header"; relative redirects can never be trusted |
| RT-06 | P3 | checked/held | `checker/feeds/ofac_sdn.py:202-207` | truncated/empty XML raises `ParseError` loudly rather than silently returning fewer entries — but the exception is never caught or logged by `watch_ofac.py` |
| RT-07 | P3 | FATAL | `scripts/watch_gazette.py:57-96`, `checker/feeds/egazette.py:190-213` | a stale/degraded-but-parseable read whose top serial is BELOW the recorded high-water mark is reported as a perfectly clean poll — the backward-range gap check silently produces zero unseen serials |
| RT-08 | P3 | FATAL | `scripts/watch_gazette.py:82-90`, `scripts/watch_ofac.py:299-311` | state is written before the log in both watchers; a crash between the two permanently and silently loses the pending alert (proven for a new MCA gazette AND a newly-sanctioned OFAC entity) |
| RT-09 | P3 | MAJOR | `scripts/watch_gazette.py:84`, `scripts/watch_ofac.py:192-195` | neither state write is atomic (no write-then-rename); a mid-write crash produces a corrupt file (held loudly on next run, not silently, but requires manual recovery) |
| RT-10 | P4 | MAJOR | `checker/feeds/__init__.py:108-124,236-237` | `is_servable_commercially()`/`may_serve_commercially()` are called from nowhere outside tests — licence is purely advisory, not enforced at any chokepoint; no live exposure only because no serving layer exists yet |
| RT-11 | P5 | MAJOR | `checker/feeds/egazette.py:138-140` | a nested `<span>` in the Ministry column can misclassify a real Ministry of Corporate Affairs gazette as non-MCA, silencing the feed's core alert |
| RT-12 | P5 | MINOR | `checker/feeds/egazette.py:161-187` | a Gazette ID's embedded date and its Date column are never cross-checked for agreement |
| RT-13 | P5 | MINOR | `checker/feeds/ofac_sdn.py:106` | `_IMO_SHAPE` accepts non-ASCII Unicode digits, risking a silent vessel-lookup miss via key-string mismatch |
| RT-14 | P6 | FATAL | `scripts/ingest_companies_act.py:32-34` | TLS verification (`CERT_NONE`, `check_hostname=False`) is fully disabled on the script that ingests the Companies Act 2013 corpus itself; currently pointed at a dead `.nic.in` domain per CLAUDE.md, so not exploitable against a live target today, but live, unconditional, and one hostname edit from being reachable again |
| P7 | P7 | none above MINOR | — | language discipline in this layer is unusually strong and consistently hedged; only defect found is RT-05's misreported diagnostic text |

## Checked and held (all lenses, consolidated)

Literal nested-function Ring 2 imports; `from checker.feeds import X`; `PACKAGE_RINGS` prefix
matching on whole segments; a registered module with a missing source file; double-hop redirects
through a trusted-then-untrusted chain; a 302 with no `Location` header; HTTP 300/304; declared-
and actual-oversize bodies; first-run baseline handling in both watchers; corrupt state files
stopping both watchers rather than silently resetting; network/robots failures never advancing
either baseline; `ofac_sdn.entries()` failing loudly (not silently) on truncated/empty XML;
CPython's built-in billion-laughs mitigation holding at 256 GB of theoretical unmitigated
expansion; IMO check-digit arithmetic on 8-digit/non-numeric/leading-zero input; malformed Gazette
IDs dropped rather than repaired; `VERIFY_X509_PARTIAL_CHAIN` genuinely cleared;
`checker/robots.py`/`checker/feeds/` themselves never disabling TLS verification; the P7 language
audit turning up nothing above MINOR.

## Final report

**Commit:** see the commit this file ships in (`docs: red team of the Ring 2 feed layer`).

**Findings, id / severity / one-line:**
- RT-01 FATAL — dynamic imports (`importlib`, `__import__`, `sys.modules`, `exec`) bypass the ring firewall completely; it only sees literal `ast.Import`/`ast.ImportFrom` nodes.
- RT-02 FATAL — the ring firewall checks only direct imports of registered Ring 0/1 files, never the transitive closure, so any unregistered helper module launders a Ring 2 import invisibly.
- RT-03 MAJOR — an empty-but-`ACCESSIBLE` 200 response is legal and structurally indistinguishable from a genuine empty source at the `fetch()`/`FetchResult` level.
- RT-04 FATAL — `fetch()` never checks delivered bytes against the declared `Content-Length`, so a dropped connection is served as a complete, correct fetch.
- RT-05 MINOR — a relative `Location` header is misdiagnosed as absent (safe outcome, wrong stated reason).
- RT-06 checked/held (with a gap) — OFAC's XML parser fails loudly on truncation, but `watch_ofac.py` never catches or logs that failure.
- RT-07 FATAL — a Gazette poll whose listing regresses below the recorded high-water mark is reported as a clean, unremarkable success with zero gap signal.
- RT-08 FATAL — both watchers write state before logging; a crash between the two permanently and silently drops the pending alert — proven for both a Ministry of Corporate Affairs gazette and a newly-sanctioned OFAC entity.
- RT-09 MAJOR — neither watcher's state write is atomic; a mid-write crash corrupts the file (loudly, requiring manual recovery, not silently).
- RT-10 MAJOR — licence enforcement (`is_servable_commercially`) is called from nowhere but tests; it is advisory, not structural, with no live exposure yet only because nothing serves Ring 2 output commercially today.
- RT-11 MAJOR — a nested `<span>` in the Ministry column can hide a real Corporate Affairs gazette from the feed's own alerting logic.
- RT-12 MINOR — a Gazette ID's embedded date is never cross-checked against its own Date column.
- RT-13 MINOR — the IMO shape regex accepts non-ASCII digits, risking a silent vessel-lookup miss.
- RT-14 FATAL — `scripts/ingest_companies_act.py` fetches the Companies Act corpus over completely unverified TLS; dormant only because its hardcoded domain is currently dead.

**The single most important fix:** RT-08 (state-before-log write ordering in both watchers).
Every other FATAL either requires an unusual trigger (RT-01/RT-02 need a developer to write a
dynamic import or an unregistered helper; RT-14 needs someone to repoint a dead URL; RT-07 needs a
stale/degraded read) or degrades gracefully in practice today (RT-04 is caught loudly by OFAC's
own strict XML parser, even if the watcher then mishandles the exception). RT-08 requires only an
ordinary process kill — the single most common failure mode for any long-running poller run under
cron, systemd, containers, or CI — landing at exactly the wrong instant, and it converts that
ordinary event into the **permanent, silent loss of the one alert this entire subsystem exists to
generate**, with no crash, no error, no log line, and no way to reconstruct after the fact what
was missed. Swapping the write order (log first, then advance state) turns that failure mode from
"data gone forever" into "one duplicate alert on the next run" — a nuisance instead of a breach of
the system's core promise.
