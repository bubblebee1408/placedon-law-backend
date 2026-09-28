"""The one gate between this repository's text and a third-party free-tier model.

## What this refuses, and why it has to be a type rather than a rule

The founder has no Anthropic credit, so work that used to go to a paid model now goes to
Gemini's free tier. A free tier is not free: the price is the text. Google's paid API
terms and its free-tier terms differ on whether prompts may be used to improve the
product, and the safe reading of a free tier is always that they may. Everything in this
repository that is published law can go there without a second thought. Nothing a client
typed or uploaded can.

The obvious control is a rule in a prompt or a review checklist. That is not a control.
`gemini_model.extract` takes `document: str`, and **a string has no provenance** -- by the
time the text reaches the model there is nothing left in it to say whether it came from
`corpus/companies_act/s173.json` or from a matter a company secretary pasted in. The only
enforceable version of "public corpus only" is one where the caller must NAME the public
file the text came from, and the code goes and checks.

So the rule here is not "don't send private text". It is:

    the text you are sending must appear in a file this repository publishes.

A caller that cannot name such a file cannot call the model. A caller that names one it
did not actually read from is refused, because the text is checked against that file's
contents -- naming `corpus/companies_act/s173.json` while passing a board minute does not
get past `clear_text()`.

## Lifted from sarvam_model.py, not reinvented

`checker/sarvam_model.py` already implements this exact clearance, against Sarvam's own
privacy policy (it trains on uploads by default, measured 29-07-2026). Its rule -- real
path under a public root, tracked at HEAD, bytes identical to the committed blob -- is
stricter than "is it in corpus/", and it is right:

  * **Real path, symlinks resolved.** `corpus/testdocs/link -> ~/clients/acme.pdf` is
    under a public root by string and is a client document by content.
  * **Tracked at HEAD.** A file dropped into `corpus/testdocs/` an hour ago is in a public
    directory and has never been published. The directory is not the claim; the commit is.
  * **Bytes match the committed blob.** A tracked public file whose contents were replaced
    on disk is a private document wearing a public name.

That logic is reproduced here, **minus one thing**: Sarvam's `privacy_check` has an escape
hatch -- `SARVAM_TRAINING_OPT_OUT=confirmed` in `.env`, a line only the founder writes after
opting out of training in Sarvam's dashboard, which then clears any file at all. There is no
equivalent here, because no equivalent opt-out has been verified for Gemini's free tier, and
an escape hatch nobody has checked the terms for is just a hole with a comment on it. So the
two are deliberately not the same function. What they must never disagree about is which
directories are public, and a test below asserts Sarvam's set is a subset of this one.

## What is public, and what is deliberately not

PUBLIC_ROOTS is wider than Sarvam's two directories because the research path answers out
of the statute itself:

    corpus/companies_act/   the Act, as published by the Government of India
    corpus/rules/           subordinate legislation, likewise
    corpus/reference/       ICSI SS-1 and SS-2, published standards
    corpus/sources/         the acquired source documents, with their acquisition logs
    corpus/testdocs/        public ICSI specimens and listed-company disclosures

`corpus/admission/`, `corpus/benchmark/`, `corpus/corroboration/`, `corpus/provisions/`
and `corpus/trust/` are NOT here. They are this project's own evaluation and provenance
artefacts, and while none of them is confidential today, "not confidential today" is not a
publication decision. A root is added to this tuple by a person who has looked at what is
in it, never by a glob.

## What this does not claim

This bounds what leaves for the MODEL. It says nothing about logs, about what an operator
can read, or about a scanned page whose pixels carry text no string guard can see
(CLAUDE.md, image-borne injection). And a very short string -- a single common word -- will
be found in some public file and cleared. That is not a leak: the threat is a whole private
document going out, and a whole private document does not appear in the Companies Act.

Run: PYTHONPATH=. python3 checker/public_only.py
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PUBLIC_CORPUS = "PUBLIC_CORPUS"

PUBLIC_ROOTS: tuple[Path, ...] = (
    ROOT / "corpus" / "companies_act",
    ROOT / "corpus" / "rules",
    ROOT / "corpus" / "reference",
    ROOT / "corpus" / "sources",
    ROOT / "corpus" / "testdocs",
)


class NotPublic(PermissionError):
    """This text may not leave for a third-party model. Raised, never returned.

    PermissionError rather than ValueError so it is not swallowed by the broad
    `except (ValueError, KeyError)` handlers that surround parsing code.
    """


@dataclass(frozen=True)
class Origin:
    """Where a piece of text came from, established rather than asserted."""

    basis: str          # PUBLIC_CORPUS -- the only basis there is
    path: str           # repo-relative, POSIX
    blob: str           # the git blob id at HEAD, so the clearance is quotable later


def _git(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(ROOT), *args],
                       capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout.strip()


_HOW = ("Only a file this repository PUBLISHES may be sent to a free-tier model: its real "
        "path (symlinks resolved) under one of corpus/{companies_act,rules,reference,"
        "sources,testdocs}, tracked at HEAD, and its bytes identical to the committed blob. "
        "A directory is not the claim; the commit is.")


def clear_file(path, *, git=None) -> Origin:
    """Establish that `path` is a file this repository publishes, or refuse."""
    run = git or _git
    p = Path(path)
    if not p.is_file():
        raise NotPublic(f"{p} is not a regular file. {_HOW}")
    real = p.resolve(strict=True)
    root = next((r for r in PUBLIC_ROOTS if real.is_relative_to(r.resolve())), None)
    if root is None:
        raise NotPublic(
            f"{p.name} resolves to {real}, which is not under a published corpus "
            f"directory. {_HOW}")
    rel = real.relative_to(ROOT).as_posix()
    try:
        rc, head_blob = run(["rev-parse", "--verify", "--quiet", f"HEAD:{rel}"])
        rc2, work_blob = run(["hash-object", "--", str(real)])
    except (OSError, subprocess.SubprocessError) as e:
        # Cannot establish it -> refuse. An unverifiable clearance is not a clearance.
        raise NotPublic(
            f"cannot confirm {rel} is published ({type(e).__name__}). {_HOW}") from None
    if rc != 0 or not head_blob:
        raise NotPublic(f"{rel} is not tracked at HEAD, so it has never been published. {_HOW}")
    if rc2 != 0 or work_blob != head_blob:
        raise NotPublic(
            f"{rel}: the bytes on disk differ from the committed public file, so what "
            f"would be sent is not what was published. {_HOW}")
    return Origin(PUBLIC_CORPUS, rel, head_blob)


_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def _readable(path: Path) -> str:
    """Everything in this file a caller could legitimately be quoting.

    The raw bytes are not enough. The corpus is JSON, and a section body read out of
    `s173.json` has real newlines where the file on disk has the two characters `\\n`, so
    a naive substring test against the file would refuse the corpus's own text. Every
    string value in a parsed JSON document is therefore included alongside the raw text.
    """
    raw = path.read_bytes().decode("utf-8", "replace")
    parts = [raw]
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _norm(raw)

    def walk(node) -> None:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    return _norm(" ".join(parts))


def clear_text(text: str, *, path, git=None) -> Origin:
    """Establish that `text` is text this repository publishes, at `path`, or refuse.

    `clear_file` alone would let a caller name a corpus file and send something else. This
    is the half that makes the name mean anything.
    """
    origin = clear_file(path, git=git)
    needle = _norm(text)
    if not needle:
        # Empty text clears trivially against any file, which would make an Origin
        # obtainable for nothing and then reusable. Refuse rather than return one.
        raise NotPublic("there is no text to clear; an empty string would clear against "
                        "any file and the resulting Origin would mean nothing")
    if needle not in _readable(ROOT / origin.path):
        raise NotPublic(
            f"the text given is not in {origin.path}, so naming that file does not make "
            f"it public. {len(text)} characters were offered; the first 60 are "
            f"{text[:60]!r}. {_HOW}")
    return origin


def verify(text: str, origin: Origin, *, git=None) -> Origin:
    """Re-establish a clearance from the Origin's own claims, at the point of use.

    An `Origin` is an ordinary dataclass and anyone can construct one. This re-reads the
    file it names, so a hand-built Origin buys nothing: the check is the file, never the
    object.
    """
    if not isinstance(origin, Origin):
        raise NotPublic(
            f"a public-corpus Origin is required, got {type(origin).__name__}. Build one "
            f"with public_only.clear_text(text, path=...) -- there is no way to send text "
            f"to a free-tier model without naming the published file it came from.")
    if origin.basis != PUBLIC_CORPUS:
        raise NotPublic(f"unknown basis {origin.basis!r}; the only basis is {PUBLIC_CORPUS}")
    return clear_text(text, path=ROOT / origin.path, git=git)


_BLOCK = re.compile(r"<source>[^\n]*\n(.*?)\n</source>", re.DOTALL)


def untrusted_blocks(prompt: str) -> tuple[str, ...]:
    """The delimited untrusted passages in a built prompt.

    `prompt_safety.wrap_untrusted` refuses text that carries a tag of its own, so the
    delimiters are unambiguous and this cannot be confused by the content it wraps.
    """
    return tuple(_BLOCK.findall(prompt))


def verify_prompt(prompt: str, origins) -> tuple[str, ...]:
    """Every untrusted passage in `prompt` clears against one of `origins`, or refuse.

    This is what makes a MULTI-SOURCE prompt checkable. `verify()` answers "is this one
    string public?"; a research prompt carries several provisions plus our own
    instructions, and the question becomes "is everything in here that did not come from
    us public?". Delimiting is what separates the two, and it is already required on this
    path -- the prompt is a concatenation, so CLAUDE.md says wrap, and the wrapper's own
    boundaries are then the list of things to check.

    Returns the blocks it cleared. A prompt with NO untrusted block is refused rather
    than passed: it means either the evidence was concatenated undelimited, or there is
    no evidence -- and the first is the failure this exists to catch.
    """
    origins = (origins,) if isinstance(origins, Origin) else tuple(origins)
    if not origins:
        raise NotPublic("no origin given; there is nothing to clear the prompt against")
    blocks = untrusted_blocks(prompt)
    if not blocks:
        raise NotPublic(
            "the prompt carries no delimited untrusted block. Either the evidence was "
            "concatenated without wrap_untrusted -- in which case nothing in it can be "
            "checked -- or there is no evidence in it at all.")
    for i, block in enumerate(blocks):
        for o in origins:
            try:
                clear_text(block, path=ROOT / o.path)
                break
            except NotPublic:
                continue
        else:
            raise NotPublic(
                f"untrusted block {i} of {len(blocks)} is in none of the "
                f"{len(origins)} published file(s) given "
                f"({', '.join(o.path for o in origins)}). {len(block)} characters, "
                f"beginning {block[:60]!r}. {_HOW}")
    return blocks


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def refused(fn) -> str:
        try:
            fn()
            return ""
        except NotPublic as e:
            return str(e)

    print("public_only")

    import tempfile

    # ── a published file clears, and carries its blob ────────────────────────
    pub = ROOT / "corpus" / "testdocs" / "MANIFEST.md"
    o = clear_file(pub)
    check(o.basis == PUBLIC_CORPUS and o.path == "corpus/testdocs/MANIFEST.md",
          f"a tracked public file clears ({o.path})")
    check(len(o.blob) == 40, f"...carrying the committed blob id ({o.blob[:8]})")

    # ── the statutory corpus is public, which is the whole point ─────────────
    act = ROOT / "corpus" / "companies_act" / "1220.json"
    check(clear_file(act).basis == PUBLIC_CORPUS,
          f"the Act itself clears ({act.name}) -- the research path depends on it")

    # ── a matter document does not, however it is dressed ────────────────────
    with tempfile.TemporaryDirectory() as td:
        secret = Path(td) / "acme-board-minute.txt"
        secret.write_text("The Board of Acme Private Limited resolved to acquire Beta Ltd.")
        msg = refused(lambda: clear_file(secret))
        check("not under a published corpus directory" in msg,
              "a file outside the corpus is refused")

        # ...including one SYMLINKED into the corpus, which passes a string test
        link = ROOT / "corpus" / "testdocs" / "_public_only_probe.txt"
        try:
            link.symlink_to(secret)
            msg = refused(lambda: clear_file(link))
            check("not under a published corpus directory" in msg,
                  "a symlink from inside the corpus to a client file is refused -- the "
                  "real path is checked, not the one written")
        finally:
            link.unlink(missing_ok=True)

    # ── untracked and modified files are refused ─────────────────────────────
    fresh = ROOT / "corpus" / "testdocs" / "_public_only_untracked.txt"
    try:
        fresh.write_text("dropped here a minute ago")
        check("never been published" in refused(lambda: clear_file(fresh)),
              "a file dropped into a public directory is not published by being there")
    finally:
        fresh.unlink(missing_ok=True)

    check("differ from the committed public file" in refused(
        lambda: clear_file(pub, git=lambda a: (0, "aa" * 20) if a[0] == "rev-parse"
                           else (0, "bb" * 20))),
        "a tracked public file whose bytes changed on disk is refused")

    # ── naming a public file is not enough: the TEXT is checked ──────────────
    body = pub.read_text()[:120]
    check(clear_text(body, path=pub).path == "corpus/testdocs/MANIFEST.md",
          "text that really is in the named public file clears")
    check("is not in corpus/testdocs/MANIFEST.md" in refused(
        lambda: clear_text("The Board of Acme Private Limited resolved to acquire Beta "
                           "Ltd for Rs 40 crore.", path=pub)),
        "a matter document sent while NAMING a public file is refused -- this is the "
        "hole a provenance label alone would leave open")
    check("no text to clear" in refused(lambda: clear_text("   ", path=pub)),
          "empty text does not clear against everything")

    # ── JSON: the corpus's own text, which raw-bytes matching would refuse ───
    sample = json.loads(act.read_text())["content"]
    check(clear_text(sample, path=act).basis == PUBLIC_CORPUS,
          "a section body read out of the corpus JSON clears, though its newlines are "
          "escaped in the file on disk")

    # ── verify(): a hand-built Origin buys nothing ───────────────────────────
    check(verify(body, o).blob == o.blob, "verify() re-establishes a real clearance")
    forged = Origin(PUBLIC_CORPUS, "corpus/testdocs/MANIFEST.md", "0" * 40)
    check("is not in corpus/testdocs/MANIFEST.md" in refused(
        lambda: verify("Acme Private Limited resolved to acquire Beta Ltd.", forged)),
        "an Origin constructed by hand does not clear private text -- verify() reads "
        "the file, never the object")
    check("Origin is required" in refused(lambda: verify(body, "corpus/testdocs/MANIFEST.md")),
          "a bare path string is not an Origin")
    check("unknown basis" in refused(
        lambda: verify(body, Origin("TRUST_ME", "corpus/testdocs/MANIFEST.md", o.blob))),
        "an invented basis is refused")

    # ── a multi-source prompt: everything that is not ours must be public ────
    from checker.prompt_safety import wrap_untrusted
    act2 = ROOT / "corpus" / "companies_act" / "1221.json"
    o1, o2 = clear_file(act), clear_file(act2)
    s1 = json.loads(act.read_text())["content"][:300]
    s2 = json.loads(act2.read_text())["content"][:300]
    good = ("Instructions we wrote.\n" + wrap_untrusted(s1, "s1") + "\n"
            + wrap_untrusted(s2, "s2") + "\nAnswer the question.")
    check(len(verify_prompt(good, (o1, o2))) == 2,
          "a prompt carrying two published provisions clears, block by block")
    check("is in none of the" in refused(lambda: verify_prompt(good, (o1,))),
          "...and naming only one of them refuses the other, rather than passing "
          "because SOME block cleared")
    hostile = ("Instructions we wrote.\n" + wrap_untrusted(s1, "s1") + "\n"
               + wrap_untrusted("The Board of Acme Private Limited resolved to acquire "
                                "Beta Ltd for Rs 40 crore.", "matter") + "\nAnswer.")
    check("is in none of the" in refused(lambda: verify_prompt(hostile, (o1, o2))),
          "a matter document smuggled in beside two real provisions is refused -- every "
          "block is checked, not a sample")
    check("carries no delimited untrusted block" in refused(
        lambda: verify_prompt("Instructions we wrote. " + s1, (o1,))),
        "evidence concatenated WITHOUT delimiters is refused, because nothing in it "
        "can be told apart from our own words")
    check("nothing to clear the prompt against" in refused(lambda: verify_prompt(good, ())),
          "an empty origin list clears nothing")
    check(untrusted_blocks(good) == (s1, s2),
          "the block extractor returns the passages verbatim")

    # ── the roots are a decision, not a glob ─────────────────────────────────
    named = {p.name for p in PUBLIC_ROOTS}
    present = {p.name for p in (ROOT / "corpus").iterdir() if p.is_dir()}
    check(named == {"companies_act", "rules", "reference", "sources", "testdocs"},
          f"the published roots are exactly the five decided on ({sorted(named)})")
    check(named < present,
          f"...and corpus/ holds more than that ({sorted(present - named)}), so this "
          f"tuple is a decision rather than everything under corpus/")
    check(all(r.is_dir() for r in PUBLIC_ROOTS),
          "every published root exists -- a typo'd root would silently refuse everything")

    # Two implementations of "public", on purpose (see the header). They may differ on the
    # escape hatch; they may never differ on what is published.
    from checker.sarvam_model import PUBLIC_ROOTS as SARVAM_ROOTS
    check(set(SARVAM_ROOTS) <= set(PUBLIC_ROOTS),
          "sarvam_model's published roots are a subset of these -- the two guards keep "
          "their own escape hatches, never their own idea of what is public")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
