"""
The review terminal: the 30 open items, one at a time, beside the gazette.

`corpus/admission/review_queue.json` holds 30 items that block every downstream target from
becoming servable. Nobody reviews a raw JSON file against a 22-page gazette by hand, and the
absence of a tool is the likeliest reason the review has not happened. This is that tool.

The thing it does that a JSON file cannot: for a RULE or FORM item it prints the **extracted
text beside the gazette page text for the same pages**. The question a reviewer is answering is
"does this match the source", and that question is unanswerable from the extraction alone -- read
on its own, a wrong extraction looks like law.

What it deliberately does not do:

  - It never supplies a decision. Every field of a ReviewDecision comes from a keystroke, and a
    run with no terminal attached refuses to decide rather than defaulting to approval. A queue
    that a script can clear is not a review.
  - It never writes an admission transition of its own. State changes go through
    `review_queue.apply_to_admission()` and nowhere else, so this cannot become a second path to
    production -- including by inventing a record for a target that has none.
  - It does not repair the source. Gazette text is verbatim apart from non-printable bytes, which
    are a property of the terminal and not of the evidence; the count stripped is printed.

Clock discipline follows `checker/review_queue.py`: nothing under test reads the clock. `now()` is
called once per interactive session and passed down as an argument.

Run: python3 scripts/review.py --list
     python3 scripts/review.py --show ri-board_rules_2014-004
     python3 scripts/review.py --next
     python3 scripts/review.py --status
     python3 scripts/review.py --test
"""
from __future__ import annotations

import re
import argparse
import json
import shutil
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import admission as adm          # noqa: E402
from checker import review_queue as rq        # noqa: E402
from checker.pdf_text import extract_pages    # noqa: E402

PDF = ROOT / "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
RULES_DOC = ROOT / "corpus/rules/board_powers_2014.json"

PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Which admission record a review item's decision lands on. Mirrors scripts/seed_admission.py:
# rules and their form tails are RULE records; preamble links point at Act PROVISIONs.
SCOPE_TARGET_TYPE = {"INSTRUMENT": "INSTRUMENT", "RULE": "RULE", "FORM": "RULE",
                     "EXTRACTION_DEFECT": "RULE", "LINK": "PROVISION"}

CHOICES = {"approve": rq.APPROVED, "a": rq.APPROVED,
           "limited": rq.LIMITED, "l": rq.LIMITED,
           "reject": rq.REJECTED, "r": rq.REJECTED,
           "escalate": rq.ESCALATED, "e": rq.ESCALATED}
SKIPS = ("skip", "s")
QUITS = ("quit", "q")
MENU = "approve/limited/reject/escalate/skip"

DEFAULT_LINES = 60          # per column; a screenful and a half, then say how much is left
GUTTER = " | "


class NotInteractive(RuntimeError):
    """A decision was requested without a human at the keyboard."""


class Quit(Exception):
    """The reviewer asked to stop."""


# --------------------------------------------------------------------------- data


def load_rules_doc() -> dict:
    return json.loads(RULES_DOC.read_text()) if RULES_DOC.is_file() else {}


_PAGES: list[str] | None = None


def pages() -> list[str]:
    """Gazette page text, extracted once per process. [] when the artifact is absent."""
    global _PAGES
    if _PAGES is None:
        _PAGES = extract_pages(PDF) if PDF.is_file() else []
    return _PAGES


def rule_for(target_id: str, doc: dict) -> dict | None:
    for r in doc.get("rules", []):
        if r["rule_id"] == target_id:
            return r
    return None


def record_for(item: rq.ReviewItem) -> adm.AdmissionRecord | None:
    return adm.load(SCOPE_TARGET_TYPE.get(item.scope, item.scope), item.target_id)


def find_item(items: list[rq.ReviewItem], item_id: str) -> rq.ReviewItem:
    for i in items:
        if i.review_item_id == item_id:
            return i
    raise rq.ReviewError(f"no review item {item_id!r} in the queue "
                         f"({len(items)} item(s); run --list to see them)")


def rank(item: rq.ReviewItem) -> tuple:
    """Highest priority first; an escalated item has already had a look, so it waits."""
    return (PRIORITY_ORDER.get(item.priority, 9),
            1 if item.status == rq.ESCALATED else 0,
            item.review_item_id)


def next_open(items: list[rq.ReviewItem]) -> rq.ReviewItem | None:
    ordered = sorted((i for i in items if i.is_open), key=rank)
    return ordered[0] if ordered else None


# --------------------------------------------------------------------------- text


def printable(text: str) -> tuple[str, int]:
    """Terminal-safe text plus the number of characters dropped.

    Gazette pages carry control bytes from subset-font encodings. Stripping them is a display
    concession, never an edit to the record -- the count is reported so the reviewer knows the
    page held bytes this view could not show.
    """
    kept = [c for c in text if c.isprintable() or c in "\n\t"]
    return "".join(kept), len(text) - len(kept)


def page_slice(all_pages: list[str], page_start: int | None, page_end: int | None
               ) -> list[tuple[int, str]]:
    """The (1-indexed) gazette pages an item points at. Empty when it points at none."""
    if page_start is None:
        return []
    end = page_end if page_end is not None else page_start
    lo, hi = max(1, page_start), min(len(all_pages), end)
    return [(n, all_pages[n - 1]) for n in range(lo, hi + 1)]


def wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, width) or [""])
    return out


def two_columns(left: list[str], right: list[str], *, width: int, max_lines: int,
                left_title: str, right_title: str) -> str:
    col = max(20, (width - len(GUTTER)) // 2)
    head = [f"{left_title[:col]:<{col}}{GUTTER}{right_title[:col]}",
            f"{'-' * col}{GUTTER}{'-' * col}"]
    shown_l, shown_r = left[:max_lines], right[:max_lines]
    rows = []
    for n in range(max(len(shown_l), len(shown_r))):
        l = shown_l[n] if n < len(shown_l) else ""
        r = shown_r[n] if n < len(shown_r) else ""
        rows.append(f"{l:<{col}}{GUTTER}{r}".rstrip())
    over_l, over_r = len(left) - len(shown_l), len(right) - len(shown_r)
    if over_l or over_r:
        rows.append(f"... truncated: extraction +{over_l} line(s), gazette +{over_r} line(s). "
                    "Re-run with --full.")
    return "\n".join(head + rows)


def term_width(override: int | None = None) -> int:
    if override:
        return max(60, override)
    return max(80, min(140, shutil.get_terminal_size((100, 24)).columns))


# --------------------------------------------------------------------------- rendering


def summarise(items: list[rq.ReviewItem]) -> dict:
    op = [i for i in items if i.is_open]
    scopes = sorted({i.scope for i in items})
    prios = sorted({i.priority for i in items}, key=lambda p: PRIORITY_ORDER.get(p, 9))
    statuses: dict[str, int] = {}
    for i in items:
        statuses[i.status] = statuses.get(i.status, 0) + 1
    return {
        "total": len(items), "open": len(op), "resolved": len(items) - len(op),
        "by_scope": {s: (sum(1 for i in op if i.scope == s),
                         sum(1 for i in items if i.scope == s)) for s in scopes},
        "by_priority": {p: (sum(1 for i in op if i.priority == p),
                            sum(1 for i in items if i.priority == p)) for p in prios},
        "by_status": statuses,
        "targets": len({i.target_id for i in items}),
    }


EMPTY_QUEUE = (
    "The review queue is empty.\n"
    f"  {rq.QUEUE.relative_to(ROOT) if rq.QUEUE.is_relative_to(ROOT) else rq.QUEUE} "
    "is missing or holds no items.\n"
    "  Nothing to review. Build it with: python3 scripts/seed_admission.py")


def render_summary(items: list[rq.ReviewItem]) -> str:
    if not items:
        return EMPTY_QUEUE
    s = summarise(items)
    out = ["REVIEW QUEUE  corpus/admission/review_queue.json",
           f"{s['total']} item(s) across {s['targets']} target(s): "
           f"{s['open']} OPEN, {s['resolved']} resolved", ""]
    out.append("BY SCOPE            open/total")
    for scope, (o, t) in s["by_scope"].items():
        out.append(f"  {scope:<18}{o:>4}/{t}")
    out.append("BY PRIORITY         open/total")
    for p, (o, t) in s["by_priority"].items():
        out.append(f"  {p:<18}{o:>4}/{t}")
    out.append("BY STATUS")
    for st, n in sorted(s["by_status"].items()):
        out.append(f"  {st:<18}{n:>4}")
    nxt = next_open(items)
    out.append("")
    if nxt:
        out.append(f"NEXT  {nxt.review_item_id}  {nxt.priority}  {nxt.scope}  {nxt.target_id}")
        out.append("      python3 scripts/review.py --next")
    else:
        out.append("Every item is resolved. python3 scripts/review.py --status")
    return "\n".join(out)


def _header(item: rq.ReviewItem, rec: adm.AdmissionRecord | None, width: int) -> list[str]:
    out = ["=" * width,
           f"{item.review_item_id}   {item.scope}   priority {item.priority}   "
           f"status {item.status}",
           f"target    {item.target_id}",
           f"admission {render_state(rec)}"]
    if item.page_start:
        out.append(f"pages     {item.page_start}-{item.page_end or item.page_start} of "
                   f"{PDF.relative_to(ROOT)}")
    if item.reviewer_id:
        out.append(f"reviewer  {item.reviewer_id}")
    if item.note:
        out.extend(f"note      {l}" for l in wrap(item.note, width - 10))
    return out


def _decision_block(item: rq.ReviewItem, width: int) -> list[str]:
    d = item.decision
    if not d:
        return []
    out = ["", f"DECISION  {d.decision} by {d.reviewer_id} at {d.at}"]
    if d.restriction_codes:
        out.append(f"          restrictions: {', '.join(d.restriction_codes)}")
    if d.notes:
        out.extend(f"          {l}" for l in wrap(d.notes, width - 10))
    return out


def _questions(item: rq.ReviewItem, width: int) -> list[str]:
    out = ["", f"QUESTIONS ({item.scope})"]
    for n, q in enumerate(item.questions, start=1):
        out.extend(f"  {n}. {l}" if n2 == 0 else f"     {l}"
                   for n2, l in enumerate(wrap(q, width - 6)))
    return out


def _align_offset(page_text: str, heading: str) -> int:
    """Where in the page this rule's heading starts, or 0.

    Without this the gazette column opens at the top of the page while the extracted column shows
    the rule, so a reviewer comparing r.15 on p.17 is reading r.12 beside it and has to hunt for
    the comparison point. Alignment is the difference between a view that can be reviewed and one
    that merely contains the right pages.

    Matching tolerates the extraction's intra-word splits ("relatio nship") by allowing an optional
    space between characters -- the same artifact scripts/acquire_rules.py handles for titles.
    """
    # Keep short words. Dropping them and then requiring the survivors to be adjacent is why an
    # earlier version never matched: "Contract or arrangement with a related party" became
    # Contract+arrangement+with+related, which are not consecutive in the source.
    words = re.findall(r"[A-Za-z]+", heading)[:5]
    if not words:
        return 0
    # Each character may be followed by a stray space (the extraction splits words at line wraps),
    # and words may be separated by any run of non-letters.
    pattern = r"[^A-Za-z]{0,3}".join(
        r"\s?".join(re.escape(ch) for ch in w) for w in words)
    m = re.search(pattern, page_text, re.I)
    if m:
        return m.start()
    # Fall back to the first three words, then two -- a heading may be split across a page break.
    for n in (3, 2):
        if len(words) > n:
            short = r"[^A-Za-z]{0,3}".join(
                r"\s?".join(re.escape(ch) for ch in w) for w in words[:n])
            m = re.search(short, page_text, re.I)
            if m:
                return m.start()
    return 0


def _gazette_lines(item: rq.ReviewItem, all_pages: list[str], col: int,
                   heading: str = "") -> tuple[list[str], int]:
    lines: list[str] = []
    dropped = 0
    pages = page_slice(all_pages, item.page_start, item.page_end)
    for i, (n, raw) in enumerate(pages):
        clean, lost = printable(raw)
        dropped += lost
        label = f"--- p.{n} "
        if i == 0 and heading:
            off = _align_offset(clean, heading)
            if off:
                clean = clean[off:]
                label = f"--- p.{n} (from the rule heading) "
        lines.append(label + "-" * max(0, col - len(label)))
        lines.extend(wrap(clean, col))
    return lines, dropped


def render_item(item: rq.ReviewItem, *, doc: dict, all_pages: list[str], width: int = 100,
                max_lines: int = DEFAULT_LINES, rec: adm.AdmissionRecord | None = None) -> str:
    """One item in full. For RULE and FORM, extraction beside the gazette pages it claims."""
    col = max(20, (width - len(GUTTER)) // 2)
    out = _header(item, rec, width)

    if item.scope in ("RULE", "FORM", "EXTRACTION_DEFECT"):
        rule = rule_for(item.target_id, doc)
        if rule is None:
            out.append(f"\n(no parsed rule {item.target_id} in {RULES_DOC.relative_to(ROOT)})")
        else:
            out.append(f"rule      r.{rule['rule_number']} -- {rule['heading']}")
            out.append(f"sub-rules {len(rule.get('sub_rules', []))}   "
                       f"act links {', '.join(l['to_section'].split(':')[-1] for l in rule.get('act_links', [])) or 'none'}")
            if rule.get("text_reading") != rule.get("text_raw"):
                out.append("          text_reading differs from text_raw (extraction joins "
                           "split words); text_raw is shown -- it is the unmodified extraction")
            left = wrap(rule["text_raw"], col)
            right, dropped = _gazette_lines(item, all_pages, col,
                                            heading=rule.get('heading', ''))
            if not right:
                right = ["(gazette page text unavailable: "
                         f"{PDF.relative_to(ROOT)} not readable or pages out of range)"]
            out.append("")
            out.append(two_columns(left, right, width=width, max_lines=max_lines,
                                   left_title="EXTRACTED  text_raw",
                                   right_title="GAZETTE  pdf_text.extract_pages"))
            if dropped:
                out.append(f"({dropped} non-printable character(s) hidden for display only; "
                           "the stored page text is unchanged)")

    elif item.scope == "INSTRUMENT":
        out.append("")
        out.append("INSTRUMENT AS PARSED")
        for k in ("short_title", "gazette", "gazette_date", "source_artifact",
                  "source_artifact_sha256", "pages", "status", "production_usable"):
            if k in doc:
                out.append(f"  {k:<24}{doc[k]}")
        made = doc.get("made_under", [])
        if made:
            out.append(f"  {'made_under':<24}{len(made)} section(s): " +
                       ", ".join(m["to_section"].split(':')[-1] for m in made))
            out.append("  preamble evidence:")
            out.extend(f"    {l}" for l in wrap(made[0]["evidence_text"], width - 6))
        out.append("  (no page bounds on this item -- check the preamble on the gazette's "
                   "first rules page)")

    elif item.scope == "LINK":
        out.append("")
        out.append("LINK AS PARSED")
        section = item.target_id.split(":")[-1]
        for m in doc.get("made_under", []):
            if m["to_section"] == item.target_id:
                out.append(f"  relation   {m['relation']}  confidence {m['confidence']}")
                out.append("  evidence (the Rules' preamble):")
                out.extend(f"    {l}" for l in wrap(m["evidence_text"], width - 6))
        cites = [(r, l) for r in doc.get("rules", []) for l in r.get("act_links", [])
                 if l["to_section"] == item.target_id]
        out.append(f"  {section} is named in the body of {len(cites)} rule(s)"
                   + (":" if cites else " -- the preamble is the only evidence"))
        for r, l in cites:
            out.append(f"    r.{r['rule_number']} (p.{r['page_start']}-{r['page_end']}) "
                       f"{l['relation']}")
            out.extend(f"      {x}" for x in wrap(l["evidence_text"], width - 8))

    out.extend(_decision_block(item, width))
    out.extend(_questions(item, width))
    return "\n".join(out)


def render_state(rec: adm.AdmissionRecord | None) -> str:
    if rec is None:
        return "(no admission record for this target)"
    bits = [rec.state, "servable" if rec.production_usable else "NOT servable"]
    if rec.restriction_codes:
        bits.append("restrictions: " + ", ".join(rec.restriction_codes))
    if rec.open_review_items:
        bits.append(f"{len(rec.open_review_items)} review item(s) open")
    return "  |  ".join(bits)


def render_status(items: list[rq.ReviewItem]) -> str:
    """Admission state of every target the queue touches, plus every record on disk."""
    seen: list[tuple[str, str]] = []
    for i in items:
        key = (SCOPE_TARGET_TYPE.get(i.scope, i.scope), i.target_id)
        if key not in seen:
            seen.append(key)
    on_disk = sorted(adm.STORE.glob("*.json")) if adm.STORE.is_dir() else []
    for p in on_disk:
        if p.name == "review_queue.json":
            continue
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        key = (d.get("target_type", "?"), d.get("target_id", p.stem))
        if key not in seen:
            seen.append(key)

    rows = [f"{'STATE':<36} {'SERVE':<6} {'OPEN':<5} TARGET",
            f"{'-' * 36} {'-' * 6} {'-' * 5} {'-' * 40}"]
    missing = 0
    for ttype, tid in sorted(seen, key=lambda k: (k[0], k[1])):
        rec = adm.load(ttype, tid)
        n_open = sum(1 for i in items if i.target_id == tid and i.is_open)
        if rec is None:
            missing += 1
            rows.append(f"{'(no admission record)':<36} {'-':<6} {n_open:<5} {tid}")
            continue
        codes = f"  [{','.join(rec.restriction_codes)}]" if rec.restriction_codes else ""
        rows.append(f"{rec.state:<36} {'yes' if rec.production_usable else 'no':<6} "
                    f"{n_open:<5} {tid}{codes}")
    if missing:
        rows += ["",
                 f"{missing} target(s) have review items but no admission record. Deciding those "
                 "items records the judgement in the queue and moves nothing: this tool will not "
                 "create an admission record, because that would be a second path to production."]
    return "\n".join(rows)


# --------------------------------------------------------------------------- deciding


def interactive_guard(is_tty: bool) -> None:
    """Refuse to collect a decision when there is no human to give one."""
    if not is_tty:
        raise NotInteractive(
            "refusing to record a decision: stdin is not a terminal.\n"
            "  A review decision is a person's judgement about whether an extraction matches the "
            "gazette.\n  There is no flag to supply one non-interactively, and there will not be: "
            "a queue that\n  can be cleared by a script is not a review. Run --show to read an "
            "item without deciding.")


def build_decision(kind: str, *, reviewer_id: str, at: str, notes: str,
                   codes: tuple[str, ...] = ()) -> rq.ReviewDecision:
    """Construct a decision, letting review_queue enforce its own rules about notes and codes."""
    return rq.ReviewDecision(kind, reviewer_id, at, notes=notes, restriction_codes=codes)


def apply_decision(items: list[rq.ReviewItem], item_id: str, decision: rq.ReviewDecision,
                   rec: adm.AdmissionRecord | None, *, actor: str, at: str
                   ) -> tuple[list[rq.ReviewItem], adm.AdmissionRecord | None]:
    """Record the decision and recompute the target's admission state.

    The admission half goes through review_queue.apply_to_admission() and nowhere else. This
    module builds no transition of its own, so there is exactly one road to PRODUCTION_USABLE.
    """
    updated = list(items)
    for n, i in enumerate(updated):
        if i.review_item_id == item_id:
            updated[n] = rq.decide(i, decision)
            break
    else:
        raise rq.ReviewError(f"no review item {item_id!r} in the queue")
    if rec is None:
        return updated, None
    return updated, rq.apply_to_admission(rec, updated, actor=actor, at=at)


def prompt_decision(item: rq.ReviewItem, *, reviewer_id: str, at: str, ask, say
                    ) -> rq.ReviewDecision | None:
    """Ask a person. Returns their decision, or None if they skipped.

    Every field comes from `ask`. Nothing here has a default and nothing infers an answer; the
    only way out with a decision is for someone to type one and confirm it.
    """
    while True:
        raw = ask(f"decision for {item.review_item_id} [{MENU}]: ").strip().lower()
        if raw in QUITS:
            raise Quit()
        if raw in SKIPS:
            return None
        if raw not in CHOICES:
            say(f"  {raw!r} is not one of {MENU} (or 'quit')")
            continue
        kind = CHOICES[raw]

        codes: tuple[str, ...] = ()
        if kind == rq.LIMITED:
            entered = ask("  restriction codes, comma-separated "
                          "(e.g. NO_AUTO_SERVE_FORM_TAIL): ")
            codes = tuple(c.strip().upper().replace(" ", "_") for c in entered.split(",")
                          if c.strip())
        need_note = kind in (rq.LIMITED, rq.REJECTED, rq.ESCALATED)
        notes = ask("  reason (required): " if need_note else "  note (optional): ").strip()

        try:
            decision = build_decision(kind, reviewer_id=reviewer_id, at=at, notes=notes,
                                      codes=codes)
        except rq.ReviewError as e:
            say(f"  refused: {e}")          # review_queue's rule, in review_queue's words
            continue

        say(f"  -> {decision.decision}"
            + (f"  restrictions={','.join(codes)}" if codes else "")
            + (f"  note={notes!r}" if notes else ""))
        if ask("  record this decision? [y/N]: ").strip().lower() not in ("y", "yes"):
            say("  not recorded.")
            continue
        return decision


def review_session(items: list[rq.ReviewItem], *, reviewer_id: str, at: str, doc: dict,
                   all_pages: list[str], width: int, max_lines: int, ask, say,
                   persist=True) -> list[rq.ReviewItem]:
    """Walk the open items in priority order, prompting for each."""
    skipped: set[str] = set()
    while True:
        pending = [i for i in sorted((x for x in items if x.is_open), key=rank)
                   if i.review_item_id not in skipped]
        if not pending:
            say("\nNo open items left to review in this session.")
            return items
        item = pending[0]
        rec = record_for(item)
        say("")
        say(render_item(item, doc=doc, all_pages=all_pages, width=width,
                        max_lines=max_lines, rec=rec))
        say("")
        try:
            decision = prompt_decision(item, reviewer_id=reviewer_id, at=at, ask=ask, say=say)
        except Quit:
            say("stopped. Nothing further was recorded.")
            return items
        if decision is None:
            skipped.add(item.review_item_id)
            say(f"skipped {item.review_item_id} (still open).")
            continue

        items, moved = apply_decision(items, item.review_item_id, decision, rec,
                                      actor=reviewer_id, at=at)
        if persist:
            rq.save_queue(items)
            if moved is not None:
                adm.save(moved)
        say(f"recorded. queue saved ({sum(1 for i in items if i.is_open)} item(s) still open)")
        if moved is None:
            say(f"admission: {item.target_id} has no admission record -- the decision is "
                "stored, nothing was promoted.")
        else:
            say(f"admission: {moved.target_id}  ->  {render_state(moved)}")
        if ask("\nreview the next item? [Y/n]: ").strip().lower() in ("n", "no", "q", "quit"):
            return items


def now() -> str:
    """The only clock read in this file, and it is never called from a tested function."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Review the admission queue against the gazette.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="queue summary")
    g.add_argument("--show", metavar="ID", help="one item in full, beside the gazette")
    g.add_argument("--next", action="store_true", help="highest-priority open item, then prompt")
    g.add_argument("--status", action="store_true", help="admission state of every target")
    g.add_argument("--test", action="store_true", help="run this module's self-test")
    ap.add_argument("--reviewer", metavar="ID", help="reviewer id recorded on decisions")
    ap.add_argument("--full", action="store_true", help="do not truncate the side-by-side view")
    ap.add_argument("--width", type=int, help="override terminal width")
    a = ap.parse_args(argv)

    if a.test:
        _test()
        return 0

    items = rq.load_queue()
    width = term_width(a.width)
    max_lines = 10 ** 6 if a.full else DEFAULT_LINES

    if a.list:
        print(render_summary(items))
        return 0

    if a.status:
        if not items:
            print(EMPTY_QUEUE)
            return 1
        print(render_status(items))
        return 0

    if not items:
        print(EMPTY_QUEUE)
        return 1

    doc = load_rules_doc()

    if a.show:
        try:
            item = find_item(items, a.show)
        except rq.ReviewError as e:
            print(e, file=sys.stderr)
            return 1
        print(render_item(item, doc=doc, all_pages=pages(), width=width,
                          max_lines=max_lines, rec=record_for(item)))
        return 0

    # --next: the only path that records anything, and it requires a person.
    item = next_open(items)
    if item is None:
        print("Nothing open. Every review item is resolved.")
        print(render_status(items))
        return 0
    try:
        interactive_guard(sys.stdin.isatty())
    except NotInteractive as e:
        print(render_item(item, doc=doc, all_pages=pages(), width=width,
                          max_lines=max_lines, rec=record_for(item)))
        print()
        print(e, file=sys.stderr)
        return 2

    reviewer = (a.reviewer or "").strip()
    while not reviewer:
        try:
            reviewer = input("reviewer id (recorded on every decision): ").strip()
        except EOFError:
            print("\nno reviewer id; nothing recorded.", file=sys.stderr)
            return 2
    try:
        review_session(items, reviewer_id=reviewer, at=now(), doc=doc, all_pages=pages(),
                       width=width, max_lines=max_lines, ask=input, say=print)
    except EOFError:
        print("\ninput ended mid-item; nothing further recorded.", file=sys.stderr)
        return 2
    return 0


# --------------------------------------------------------------------------- test


def _test() -> None:
    import hashlib
    import tempfile

    ok = fail = 0
    T = "2026-08-21T00:00:00Z"

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    real_queue_before = (hashlib.sha256(rq.QUEUE.read_bytes()).hexdigest()
                         if rq.QUEUE.is_file() else None)

    items = rq.create_items("T2014", [
        {"scope": "INSTRUMENT", "target_id": "RULE:T", "priority": "HIGH"},
        {"scope": "RULE", "target_id": "RULE:T:R1", "priority": "HIGH",
         "page_start": 2, "page_end": 3, "note": "6 words split"},
        {"scope": "RULE", "target_id": "RULE:T:R15", "priority": "MEDIUM",
         "page_start": 3, "page_end": 3},
        {"scope": "FORM", "target_id": "RULE:T:R15", "priority": "HIGH",
         "page_start": 3, "page_end": 3, "note": "annexure tail"},
        {"scope": "LINK", "target_id": "ACT:X:S173", "priority": "MEDIUM"},
    ])
    doc = {"short_title": "Test Rules", "gazette": "G.S.R. 1(E)",
           "made_under": [{"to_section": "ACT:X:S173", "relation": "MADE_UNDER",
                           "confidence": "HIGH", "evidence_text": "section 173"}],
           "rules": [{"rule_id": "RULE:T:R1", "rule_number": "1", "heading": "Short title",
                      "text_raw": "(1) These rules may be called the Test Rul es, 2014.",
                      "text_reading": "(1) These rules may be called the Test Rules, 2014.",
                      "page_start": 2, "page_end": 3, "sub_rules": ["1"], "act_links": []},
                     {"rule_id": "RULE:T:R15", "rule_number": "15", "heading": "Related party",
                      "text_raw": "(1) A company shall not enter", "text_reading": "x",
                      "page_start": 3, "page_end": 3, "sub_rules": [],
                      "act_links": [{"to_section": "ACT:X:S173", "relation": "REFERS_TO",
                                     "confidence": "HIGH", "evidence_text": "section 173 of"}]}]}
    fake_pages = ["page one text", "PAGE TWO shall the company",
                  "PAGE THREE\x01\x02 board of directors", "page four"]

    # -- summarisation
    s = summarise(items)
    check((s["total"], s["open"], s["resolved"]) == (5, 5, 0), "summary counts every item as open")
    check(s["by_scope"]["FORM"] == (1, 1) and s["by_scope"]["RULE"] == (2, 2),
          "summary splits by scope")
    check(s["by_priority"]["HIGH"] == (3, 3), "summary splits by priority")
    check(s["targets"] == 4, "two items on one target count as one target")
    check(all(x in render_summary(items) for x in ("5 item(s)", "BY SCOPE", "NEXT")),
          "the summary renders")
    check(render_summary([]) == EMPTY_QUEUE and "seed_admission" in EMPTY_QUEUE,
          "an empty queue says so and says how to fix it")

    resolved_one = [rq.decide(items[0], rq.ReviewDecision(rq.APPROVED, "c", T))] + items[1:]
    check(summarise(resolved_one)["open"] == 4, "a resolved item leaves the open count")

    # -- ordering
    check(next_open(items).review_item_id == "ri-t2014-001", "highest priority comes first")
    esc = rq.decide(items[1], rq.ReviewDecision(rq.ESCALATED, "c", T, notes="counsel"))
    ordered = sorted([esc, items[3]], key=rank)
    check(ordered[0].review_item_id == items[3].review_item_id,
          "an escalated item waits behind a fresh one of the same priority")

    # -- page selection
    check(page_slice(fake_pages, 2, 3) == [(2, fake_pages[1]), (3, fake_pages[2])],
          "page bounds are 1-indexed and inclusive")
    check(page_slice(fake_pages, 2, None) == [(2, fake_pages[1])],
          "a missing page_end means the single page")
    check(page_slice(fake_pages, None, None) == [], "an item with no pages selects none")
    check(page_slice(fake_pages, 3, 99) == [(3, fake_pages[2]), (4, fake_pages[3])],
          "a page_end past the document clamps instead of raising")
    check(page_slice([], 2, 3) == [], "no extracted pages selects none")

    clean, dropped = printable("ab\x01c\x02")
    check((clean, dropped) == ("abc", 2), "control bytes are hidden and counted")

    # -- side by side
    view = render_item(items[1], doc=doc, all_pages=fake_pages, width=100, max_lines=40)
    check("EXTRACTED" in view and "GAZETTE" in view, "a RULE item shows both columns")
    check("--- p.2" in view and "--- p.3" in view, "both claimed pages are marked")
    check("PAGE TWO" in view and "Test Rul es" in view,
          "the gazette text and the extraction appear in the same view")
    check("text_reading differs" in view, "a divergent reading is flagged, raw is shown")
    check("non-printable" in view, "hidden control bytes are reported to the reviewer")
    check("QUESTIONS (RULE)" in view and "Is the numbered rule boundary correct?" in view,
          "the scope's own questions are printed")
    check("Where does the operative rule text end" in
          render_item(items[3], doc=doc, all_pages=fake_pages, width=100),
          "a FORM item asks the FORM questions on the same pages")
    check("G.S.R. 1(E)" in render_item(items[0], doc=doc, all_pages=fake_pages, width=100),
          "an INSTRUMENT item shows the gazette identity instead of a page slice")
    link_view = render_item(items[4], doc=doc, all_pages=fake_pages, width=100)
    check("named in the body of 1 rule(s)" in link_view and "r.15" in link_view,
          "a LINK item shows where the section is actually cited")

    narrow = two_columns(["a"] * 30, ["b"] * 5, width=80, max_lines=10,
                         left_title="L", right_title="R")
    check("truncated: extraction +20 line(s)" in narrow and narrow.count("\n") < 20,
          "a long view truncates and says how much it hid")
    check(GUTTER in narrow, "the two columns are separated")

    # -- refusal to decide
    try:
        interactive_guard(False)
        check(False, "a non-interactive run must refuse")
    except NotInteractive as e:
        check("refusing to record a decision" in str(e) and "not a terminal" in str(e),
              "with no terminal attached the tool refuses to decide")
    check(interactive_guard(True) is None, "with a terminal it proceeds")

    answers: list[str] = []
    said: list[str] = []

    def scripted(_prompt: str) -> str:
        if not answers:                      # what input() does on a closed stdin
            raise EOFError
        return answers.pop(0)

    try:
        prompt_decision(items[1], reviewer_id="c1", at=T, ask=scripted, say=said.append)
        check(False, "an exhausted input must not yield a decision")
    except EOFError:
        check(True, "input running out raises; it never falls through to an approval")

    answers[:] = ["skip"]
    check(prompt_decision(items[1], reviewer_id="c1", at=T, ask=scripted,
                          say=said.append) is None, "skip returns no decision")
    answers[:] = ["approve", "looks right", "n", "skip"]
    check(prompt_decision(items[1], reviewer_id="c1", at=T, ask=scripted,
                          say=said.append) is None,
          "declining the confirmation records nothing")
    answers[:] = ["approve", "checked p.2 vs gazette", "y"]
    d = prompt_decision(items[1], reviewer_id="c1", at=T, ask=scripted, say=said.append)
    check(d is not None and d.decision == rq.APPROVED and d.reviewer_id == "c1",
          "a typed and confirmed approval becomes a decision")
    said.clear()
    answers[:] = ["limited", "", "", "limited", "NO_AUTO_SERVE_FORM_TAIL", "tail unbounded", "y"]
    d = prompt_decision(items[3], reviewer_id="c1", at=T, ask=scripted, say=said.append)
    check(any("written reason" in s for s in said),
          "review_queue's own rule is surfaced, not restated")
    check(d.decision == rq.LIMITED and d.restriction_codes == ("NO_AUTO_SERVE_FORM_TAIL",),
          "a limited approval must carry codes and a note before it is accepted")

    # -- the decision moves the admission record, and only through apply_to_admission
    rec = adm.AdmissionRecord("RULE", "RULE:T:R1", adm.HUMAN_REVIEW_PENDING)
    approve = rq.ReviewDecision(rq.APPROVED, "c1", T)
    upd, moved = apply_decision(items, "ri-t2014-002", approve, rec, actor="c1", at=T)
    check(upd[1].status == rq.APPROVED and items[1].status == rq.PENDING,
          "the queue list is rebuilt, not mutated in place")
    check(moved.state == adm.PRODUCTION_USABLE and moved.production_usable,
          "resolving a target's only item promotes it to production")
    r15 = adm.AdmissionRecord("RULE", "RULE:T:R15", adm.HUMAN_REVIEW_PENDING)
    upd2, moved2 = apply_decision(items, "ri-t2014-003", approve, r15, actor="c1", at=T)
    check(not moved2.production_usable and moved2.open_review_items == ("ri-t2014-004",),
          "a target with two items does not move until both are decided")
    upd3, moved3 = apply_decision(upd2, "ri-t2014-004", rq.ReviewDecision(
        rq.LIMITED, "c1", T, notes="tail", restriction_codes=("NO_AUTO_SERVE_FORM_TAIL",)),
        r15, actor="c1", at=T)
    check(moved3.state == adm.DEFECT_FLAGGED_PRODUCTION_LIMITED and
          moved3.restriction_codes == ("NO_AUTO_SERVE_FORM_TAIL",),
          "a limited approval lands in limited production with its code")
    _, rejected = apply_decision(items, "ri-t2014-002", rq.ReviewDecision(
        rq.REJECTED, "c1", T, notes="wrong page"), rec, actor="c1", at=T)
    check(rejected.state == adm.REJECTED, "a rejection rejects the target")
    _, none_rec = apply_decision(items, "ri-t2014-005", approve, None, actor="c1", at=T)
    check(none_rec is None, "a target with no admission record is decided but not invented")
    try:
        apply_decision(items, "nope", approve, rec, actor="c1", at=T)
        check(False, "an unknown item id must raise")
    except rq.ReviewError:
        check(True, "an unknown item id raises rather than silently doing nothing")
    try:
        find_item(items, "ri-nope")
        check(False, "find_item must raise")
    except rq.ReviewError as e:
        check("no review item" in str(e), "--show with a bad id explains itself")

    # -- persistence, on a temp copy: the real queue is never touched by a test
    original = rq.QUEUE
    tmp = Path(tempfile.mkdtemp(prefix="review-test-")) / "review_queue.json"
    try:
        rq.QUEUE = tmp
        rq.save_queue(upd3)
        back = rq.load_queue()
        check(len(back) == 5 and back[3].decision.restriction_codes ==
              ("NO_AUTO_SERVE_FORM_TAIL",), "a decided queue round-trips through disk")
        check(summarise(back)["open"] == 3, "the reloaded queue reports the right open count")
    finally:
        rq.QUEUE = original

    # -- a session records only what was typed
    script = ["approve", "read p.2 against the gazette", "y", "n"]
    said.clear()
    after = review_session(list(items), reviewer_id="c1", at=T, doc=doc, all_pages=fake_pages,
                           width=90, max_lines=20, ask=lambda p: script.pop(0),
                           say=said.append, persist=False)
    check(sum(1 for i in after if not i.is_open) == 1,
          "a session resolves exactly the items a person answered")
    check(any("admission:" in s for s in said),
          "the reviewer is shown the admission consequence of the decision")

    check(real_queue_before is None or
          hashlib.sha256(rq.QUEUE.read_bytes()).hexdigest() == real_queue_before,
          "the real review queue is byte-identical after the tests")

    # -- the real corpus, when present
    live = rq.load_queue()
    if live and PDF.is_file():
        target = next((i for i in live if i.scope == "RULE" and i.page_start), None)
        v = render_item(target, doc=load_rules_doc(), all_pages=pages(), width=100,
                        max_lines=40, rec=record_for(target))
        check("GAZETTE" in v and f"--- p.{target.page_start}" in v,
              f"{target.review_item_id} renders against the real gazette")
        check("Meetings of Board" in v or "Board" in v, "real gazette words reach the view")
        check("HUMAN_REVIEW_PENDING" in v, "the real admission state is shown on the item")
        check("(no admission record)" in render_status(live),
              "targets without an admission record are reported, not hidden")
    else:
        print("[SKIP] live queue or gazette PDF not present")

    # --- gazette alignment -------------------------------------------------------------------
    # Without alignment the gazette column opens at the top of the page while the extracted column
    # shows the rule, so a reviewer comparing r.15 on p.17 reads r.12 beside it. The view then
    # technically contains the right pages and cannot actually be reviewed.
    page = ("some earlier rule text here. Contract or arrangement with a related party.- "
            "A company shall enter into any contract")
    off = _align_offset(page, "Contract or arrangement with a related party")
    check(off > 0 and page[off:].startswith("Contract or arrangement"),
          "the gazette column starts at the rule heading, not the top of the page")

    # Short words must be kept: dropping them and requiring the survivors to be adjacent is why an
    # earlier version of this never matched a real heading.
    check(_align_offset("x Loans to Director etc. under section 185.- (1) Any loan",
                        "Loans to Director etc. under section 185") == 2,
          "a heading with short words ('to', 'etc') still aligns")

    # The extraction splits words at line wraps; alignment must survive that.
    check(_align_offset("intro Committees of the Bo ard.- The Board", "Committees of the Board") > 0,
          "alignment tolerates the extraction's intra-word split")

    check(_align_offset("nothing relevant on this page at all", "Special Resolution") == 0,
          "an absent heading falls back to the top of the page rather than guessing an offset")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
