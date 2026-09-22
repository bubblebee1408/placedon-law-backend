"""Indic OCR bake-off: Sarvam Digitise vs Gemini Flash, on the pages behind "86.3".

    python3 scripts/bakeoff_indic.py --manifest PATH                  # plan; no calls
    python3 scripts/bakeoff_indic.py --manifest PATH --run --confirm-spend
    python3 scripts/bakeoff_indic.py --test                           # offline, no network

## Where "86.3 chrF++" was measured -- not here

The router's PAGE_IMAGE evidence is arXiv 2606.29213 (v1, 28-06-2026; "Can OCR-VLMs
Read Devanagari?"), read 18-09 at https://arxiv.org/html/2606.29213:

- Gemini **2.5** Flash, corpus-level chrF++ **86.3** on "300 real printed-Devanagari
  images with transcriptions, sampled from the Sanskrit-OCR-Typed corpus (historical
  typeset scans)", "word and short-phrase level";
- "All references and hypotheses are Unicode NFC-normalised before scoring";
  "chrF++ (character n-gram F-score with word order 2)"; "VLM outputs are stripped of
  layout and grounding special tokens and of bounding-box coordinates before scoring";
- benchmark, code and models released at
  https://github.com/Aditya-PS-05/devanagari-ocr-benchmark.

UNVERIFIED: which 300 crops were sampled, and the paper's exact scorer settings
beyond "word order 2". Both should be read from that repository. The pages are NOT
in this repo, and this loop may download only from official Indian government
hosts, so obtaining them is a founder step (see "Switching it on" in
docs/MODEL_PLAN.md).

## Why the incumbent is RE-RUN rather than quoted

86.3 belongs to Gemini 2.5 Flash, which gemini_model.py records as closed to new
keys; the router pins `gemini-3.6-flash`, which has no measurement at all. And a
published corpus score has no per-page outputs, so no paired interval can be
computed against it. So the bake-off runs BOTH systems on the same pages, scores both
with the same chrF++, and prints the paper's 86.3 as context only.

## The metric

`chrf_pp()` below is sacrebleu 2.x's CHRF with its chrF++ settings (char order 6,
word order 2, beta 2, whitespace removed from character n-grams, punctuation split
off word ends, effective-order averaging, corpus statistics summed before the
F-score), re-implemented in the standard library from sacrebleu's own source
(sacrebleu/metrics/chrf.py and helpers.py on GitHub, read 18-09), plus the paper's
NFC normalisation. sacrebleu is not a dependency and is not added: the self-test pins
the formula on hand-computed cases instead. Whether this reproduces the paper's
scorer to the decimal is UNVERIFIED until 86.3 is reproduced from the released
outputs -- do that first.

## The adoption rule (printed with every run)

Sarvam is adopted for PAGE_IMAGE only if its corpus chrF++ is higher AND the paired
bootstrap 95% interval of (Sarvam - Gemini), resampling pages with seed 0 and 2,000
repetitions, lies entirely above zero. An interval that touches zero is "not
resolvable on these pages", never a win. And a win here is a win on Sanskrit typeset
crops -- not on Indian corporate paper, which no benchmark yet covers.

## Fail closed

No SARVAM_API_KEY or no Gemini credential -> exit 2. No manifest -> exit 2. A page
the privacy guard refuses -> exit 2 (the pages must be committed under corpus/testdocs/
or the .env opt-out line must exist). A service error mid-run -> exit 3, no numbers.
A page a system refused or failed to read is scored as empty AND counted, never
dropped from the corpus.
"""
from __future__ import annotations

import base64
import json
import string
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import sarvam_model as sm  # noqa: E402
from checker.interval import bootstrap_ci  # noqa: E402

PAPER = {"url": "https://arxiv.org/abs/2606.29213", "model": "gemini-2.5-flash",
         "chrf_pp": 86.3, "pages": 300,
         "benchmark": "https://github.com/Aditya-PS-05/devanagari-ocr-benchmark"}
CHAR_ORDER, WORD_ORDER, BETA = 6, 2, 2
REPS, SEED = 2000, 0
REFUSED, ABORTED = 2, 3
_PUNCTS = set(string.punctuation)       # sacrebleu's _PUNCTS is exactly this set

RULE = ("ADOPTION RULE: Sarvam replaces Gemini for PAGE_IMAGE only if its corpus chrF++ "
        "is higher AND the paired bootstrap 95% interval of (Sarvam - Gemini) lies "
        "entirely above zero. Touching zero = not resolvable, never a win.")

TRANSCRIBE = ("Transcribe the text in this image exactly as printed, in its original "
              "script. Output only the transcription: no translation, no commentary, "
              "no formatting.")


# ── chrF++ (sacrebleu 2.x CHRF, word_order=2), standard library ───────────────
def _words(s: str) -> list[str]:
    out: list[str] = []
    for w in s.split():
        if len(w) == 1:
            out.append(w)
        elif w[-1] in _PUNCTS:
            out += [w[:-1], w[-1]]
        elif w[0] in _PUNCTS:
            out += [w[0], w[1:]]
        else:
            out.append(w)
    return out


def _match(h: Counter, r: Counter) -> list[int]:
    m = sum(min(c, r[g]) for g, c in h.items() if g in r)
    return [sum(h.values()) if r else 0, sum(r.values()), m]


def chrf_stats(hyp: str, ref: str) -> list[int]:
    hyp, ref = unicodedata.normalize("NFC", hyp), unicodedata.normalize("NFC", ref)
    hc, rc = "".join(hyp.split()), "".join(ref.split())
    stats: list[int] = []
    for n in range(1, CHAR_ORDER + 1):
        stats += _match(Counter(hc[i:i + n] for i in range(len(hc) - n + 1)),
                        Counter(rc[i:i + n] for i in range(len(rc) - n + 1)))
    hw, rw = _words(hyp), _words(ref)
    for n in range(1, WORD_ORDER + 1):
        stats += _match(Counter(" ".join(hw[i:i + n]) for i in range(len(hw) - n + 1)),
                        Counter(" ".join(rw[i:i + n]) for i in range(len(rw) - n + 1)))
    return stats


def chrf_from_stats(stats: list[int]) -> float:
    factor = BETA ** 2
    avg_p = avg_r = 0.0
    eff = 0
    for i in range(CHAR_ORDER + WORD_ORDER):
        n_hyp, n_ref, n_match = stats[3 * i:3 * i + 3]
        if n_hyp > 0 and n_ref > 0:
            avg_p += n_match / n_hyp
            avg_r += n_match / n_ref
            eff += 1
    if eff == 0:
        return 0.0
    avg_p, avg_r = avg_p / eff, avg_r / eff
    if not avg_p + avg_r:
        return 0.0
    return 100 * (1 + factor) * avg_p * avg_r / (factor * avg_p + avg_r)


def chrf_pp(hyps: list[str], refs: list[str]) -> float:
    """Corpus-level chrF++: statistics summed over pages, then one F-score."""
    if len(hyps) != len(refs) or not refs:
        raise ValueError("hypotheses and references must pair up, and not be empty")
    total = [0] * (3 * (CHAR_ORDER + WORD_ORDER))
    for h, r in zip(hyps, refs):
        total = [a + b for a, b in zip(total, chrf_stats(h, r))]
    return chrf_from_stats(total)


def paired_interval(a: list[str], b: list[str], refs: list[str]) -> tuple[float, float]:
    """Bootstrap 95% CI of corpus chrF++(a) - chrF++(b), resampling pages, seeded."""
    sa = [chrf_stats(h, r) for h, r in zip(a, refs)]
    sb = [chrf_stats(h, r) for h, r in zip(b, refs)]

    def diff(idx) -> float:
        def corpus(s):
            tot = [0] * len(s[0])
            for i in idx:
                tot = [x + y for x, y in zip(tot, s[int(i)])]
            return chrf_from_stats(tot)
        return corpus(sa) - corpus(sb)
    return bootstrap_ci(list(range(len(refs))), diff, reps=REPS, seed=SEED)


def adopt(sarvam: float, gemini: float, ci: tuple[float, float]) -> bool:
    return sarvam > gemini and ci[0] > 0


# ── inputs ────────────────────────────────────────────────────────────────────
def load_manifest(path: Path) -> list[dict]:
    """JSONL: {"image": <path relative to the manifest>, "reference": <text>}."""
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        img = (path.parent / row["image"]).resolve()
        if not isinstance(row.get("reference"), str) or not img.is_file():
            raise ValueError(f"manifest line {i}: missing image or reference")
        if img.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            raise ValueError(f"manifest line {i}: {img.suffix} is not PNG/JPG")
        rows.append({"image": img, "reference": row["reference"]})
    if not rows:
        raise ValueError("the manifest is empty")
    return rows


# ── the two arms ──────────────────────────────────────────────────────────────
def sarvam_arm(rows: list[dict], language: str, **kw) -> tuple[list[str], list[str], object]:
    res = sm.digitise_images([r["image"] for r in rows], language=language,
                             output_format="html", **kw)
    return ([p.text or "" for p in res.pages], [p.status for p in res.pages], res)


def gemini_payload(image: Path) -> dict:
    from checker.prompt_safety import UNTRUSTED_CLAUSE
    mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
    return {"systemInstruction": {"parts": [{"text": UNTRUSTED_CLAUSE + "\n\n" + TRANSCRIBE}]},
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": mime,
                                "data": base64.b64encode(image.read_bytes()).decode("ascii")}},
                {"text": TRANSCRIBE}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1024}}


def gemini_read(data: dict) -> tuple[str, str]:
    """(text, status). A blocked or candidate-less reply is REFUSED, scored as empty
    and counted -- never silently skipped, never an error that drops the page."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return "", "REFUSED"
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    return text, "READ" if text else "EMPTY"


def gemini_arm(rows: list[dict], _post=None) -> tuple[list[str], list[str]]:
    from checker import gemini_model as gm
    post = _post or gm._post
    texts, statuses = [], []
    for r in rows:
        t, s = gemini_read(post(gm.FLASH, gemini_payload(r["image"])))
        texts.append(t)
        statuses.append(s)
    return texts, statuses


def render(sar: float, gem: float, ci: tuple[float, float], n: int, counts: dict) -> str:
    return "\n".join([
        f"Indic OCR bake-off, {n} pages, corpus chrF++ (NFC, word order 2)",
        f"  SARVAM  {sar:6.2f}   pages not READ: {counts['sarvam']}",
        f"  GEMINI  {gem:6.2f}   pages not READ: {counts['gemini']}",
        f"  paired bootstrap 95% CI of (Sarvam - Gemini): [{ci[0]:+.2f}, {ci[1]:+.2f}]",
        f"  -> {'ADOPT' if adopt(sar, gem, ci) else 'NOT ADOPTED'}",
        f"  context only: the paper reports {PAPER['chrf_pp']} for {PAPER['model']} on "
        f"{PAPER['pages']} crops ({PAPER['url']})", "", RULE])


def main(argv: list[str]) -> int:
    from checker import gemini_model as gm
    if not sm.available() or not gm.available():
        print("REFUSED: needs SARVAM_API_KEY and a Gemini credential in .env. Nothing "
              "was called.")
        return REFUSED
    if "--manifest" not in argv:
        print(f"REFUSED: no --manifest. The pages behind 86.3 are not in this repo; "
              f"obtain the 300-crop sample from {PAPER['benchmark']} (founder step).")
        return REFUSED
    manifest = Path(argv[argv.index("--manifest") + 1])
    language = argv[argv.index("--language") + 1] if "--language" in argv else "sa-IN"
    try:
        rows = load_manifest(manifest)
        for r in rows:
            sm.privacy_check(r["image"])
    except (OSError, ValueError, sm.SarvamPrivacyRefused) as e:
        print(f"REFUSED: {e}")
        return REFUSED
    est = round(len(rows) * sm.PRICE_INR_PER_PAGE, 2)
    print(f"Plan: {len(rows)} pages, language {language}; Sarvam ~Rs {est} at "
          f"Rs {sm.PRICE_INR_PER_PAGE}/page; Gemini {gm.FLASH} on the same pages.\n{RULE}")
    if "--run" not in argv or "--confirm-spend" not in argv:
        print("Dry plan only. Re-run with --run --confirm-spend to make the calls.")
        return 0
    try:
        sar, sar_st, res = sarvam_arm(rows, language)
        gem, gem_st = gemini_arm(rows)
    except (sm.SarvamError, sm.SarvamBadResponse, gm.ModelUnavailable, gm.ModelRefused) as e:
        print(f"ABORTED: {e}\nNo numbers are reported from a partial run.")
        return ABORTED
    refs = [r["reference"] for r in rows]
    s, g = chrf_pp(sar, refs), chrf_pp(gem, refs)
    ci = paired_interval(sar, gem, refs)
    counts = {"sarvam": sum(x != "READ" for x in sar_st), "gemini": sum(x != "READ" for x in gem_st)}
    print(render(s, g, ci, len(rows), counts))
    out = ROOT / "reports" / f"bakeoff_indic_{date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "paper": PAPER, "language": language, "n": len(rows), "rule": RULE,
        "sarvam": {"chrf_pp": s, "not_read": counts["sarvam"], "cost_inr_est": res.est_cost_inr,
                   "jobs": [j.job_id for j in res.jobs]},
        "gemini": {"model": gm.FLASH, "chrf_pp": g, "not_read": counts["gemini"]},
        "paired_ci": ci, "adopt": adopt(s, g, ci)}, indent=2) + "\n")
    print(f"Recorded: {out.relative_to(ROOT)}")
    return 0


def _test() -> None:
    import os
    import tempfile
    import urllib.request
    from unittest import mock

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("bakeoff_indic")
    network: list = []
    guard = mock.patch.object(urllib.request, "urlopen",
                              side_effect=lambda *a, **k: network.append(1) or 1 / 0)
    guard.start()
    held = {k: os.environ.pop(k, None) for k in
            ("SARVAM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT")}
    try:
        # ── chrF++ pinned on hand-worked cases ───────────────────────────────
        check(abs(chrf_pp(["नमस्ते दुनिया"], ["नमस्ते दुनिया"]) - 100.0) < 1e-9,
              "identical Devanagari scores 100")
        check(chrf_pp(["xyz"], ["abc"]) == 0.0 and chrf_pp([""], ["abc"]) == 0.0,
              "disjoint text and an empty hypothesis both score 0")
        # ab vs abc: char1 P=1 R=2/3, char2 P=1 R=1/2, word1 P=0 R=0 (eff. order 3)
        # avgP=2/3, avgR=7/18, F2 = 5PR/(4P+R) = 630/1485
        check(abs(chrf_pp(["ab"], ["abc"]) - 100 * 630 / 1485) < 1e-9,
              f"'ab' vs 'abc' = 42.4242..., hand-worked from sacrebleu's formula "
              f"({chrf_pp(['ab'], ['abc']):.4f})")
        decomposed = "क़"            # KA + NUKTA
        precomposed = "क़"                 # QA, which NFC decomposes
        check(chrf_pp([precomposed], [decomposed]) == 100.0,
              "NFC is applied, as the paper states: U+0958 equals U+0915 U+093C")
        check(0 < chrf_pp(["ab cd"], ["abcd"]) < 100,
              "whitespace is dropped from character n-grams but word n-grams still differ")
        check(_words("(hi) there,") == ["(hi", ")", "there", ","],
              "punctuation splitting matches sacrebleu (including its '(hi)' quirk)")
        two = chrf_pp(["ab", "xyz"], ["abc", "xyz"])
        mean = (chrf_pp(["ab"], ["abc"]) + chrf_pp(["xyz"], ["xyz"])) / 2
        check(abs(two - mean) > 1e-6, "corpus chrF++ sums statistics; it is not a mean of pages")

        # ── the adoption rule ────────────────────────────────────────────────
        refs = [f"पंक्ति {i} का पाठ" for i in range(30)]
        good = list(refs)
        worse = [r[:-2] for r in refs]
        ci = paired_interval(good, worse, refs)
        check(ci[0] > 0 and adopt(chrf_pp(good, refs), chrf_pp(worse, refs), ci),
              f"a consistent per-page win has a CI above zero and is adopted ({ci[0]:+.2f})")
        mixed = [g if i % 2 else w for i, (g, w) in enumerate(zip(good, worse))]
        mixed2 = [w if i % 2 else g for i, (g, w) in enumerate(zip(good, worse))]
        ci2 = paired_interval(mixed, mixed2, refs)
        check(ci2[0] <= 0 <= ci2[1] and not adopt(1.0, 0.0, ci2),
              f"a split decision touches zero and is NOT adopted ({ci2[0]:+.2f}, {ci2[1]:+.2f})")
        check(paired_interval(good, worse, refs) == ci, "the bootstrap is seeded: same CI twice")
        text = render(90.0, 86.0, ci2, 30, {"sarvam": 0, "gemini": 1})
        check("ADOPTION RULE" in text and "NOT ADOPTED" in text and "context only" in text,
              "the rule, the verdict and the paper's figure (as context) are printed")

        # ── the Gemini arm: refusals are counted, not dropped ────────────────
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "c1.png"
            img.write_bytes(b"\x89PNG fake")
            p = gemini_payload(img)
            from checker.prompt_safety import carries_clause
            check(p["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
                  and carries_clause(p["systemInstruction"]["parts"][0]["text"])
                  and p["generationConfig"]["temperature"] == 0,
                  "the page goes as inline image data, under the untrusted-content clause, "
                  "at temperature 0")
            replies = iter([{"candidates": [{"content": {"parts": [{"text": " पाठ "}]}}]},
                            {"promptFeedback": {"blockReason": "SAFETY"}},
                            {"candidates": [{"content": {"parts": [{"text": ""}]}}]}])
            texts, sts = gemini_arm([{"image": img}] * 3, _post=lambda m, pl: next(replies))
            check(texts == ["पाठ", "", ""] and sts == ["READ", "REFUSED", "EMPTY"],
                  "a blocked reply is REFUSED and an empty one EMPTY; both are scored as "
                  "empty and counted, not dropped")

            man = Path(td) / "m.jsonl"
            man.write_text(json.dumps({"image": "c1.png", "reference": "पाठ"}) + "\n")
            check(load_manifest(man)[0]["image"] == img.resolve(), "a manifest row resolves")
            man.write_text(json.dumps({"image": "nope.png", "reference": "x"}) + "\n")
            try:
                load_manifest(man)
                check(False, "a missing image is refused")
            except ValueError:
                check(True, "a manifest row whose image is missing is refused")
            check(isinstance(_privacy_refusal(img), sm.SarvamPrivacyRefused),
                  "a crop outside corpus/ is refused by Sarvam's privacy guard")

        # ── refusals ─────────────────────────────────────────────────────────
        check(main(["--manifest", "x", "--run", "--confirm-spend"]) == REFUSED and not network,
              "with no keys, --run refuses (exit 2) and calls nothing")
    finally:
        guard.stop()
        for k, v in held.items():
            if v is not None:
                os.environ[k] = v
    check(not network, "no network was touched")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def _privacy_refusal(path: Path):
    try:
        sm.privacy_check(path, env_path=path.parent / "no.env")
    except sm.SarvamPrivacyRefused as e:
        return e
    return None


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(main(sys.argv[1:]))
