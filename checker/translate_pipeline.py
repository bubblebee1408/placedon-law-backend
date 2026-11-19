"""Four-pass legal translation pipeline for Indian languages.

Pass 1 — EXTRACT: OCR/vision reads the source document into text blocks with layout.
Pass 2 — LOCK:    Glossary locks legal terms to canonical translations (legal_glossary.py).
Pass 3 — TRANSLATE: Model translates each block, with locked terms injected as constraints.
Pass 4 — VERIFY:  Back-translate a sample and compare against the original to catch drift.

The pipeline is MODEL-AGNOSTIC: `translate_fn` and `back_translate_fn` are injected callables
so tests run without network, and production can route through any provider.

Tier discipline: a translation is NEVER VERIFIED — it is always MACHINE_TRANSLATED with an
optional BACK_TRANSLATION_CHECKED flag. Only a human reviewer can upgrade it.

Run: PYTHONPATH=. python3 checker/translate_pipeline.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.legal_glossary import load_glossary, Glossary, EIGHTH_SCHEDULE_LANGUAGES

__all__ = [
    "TextBlock", "TranslatedBlock", "TranslationResult",
    "translate_document", "MACHINE_TRANSLATED", "BACK_TRANSLATION_CHECKED",
]

MACHINE_TRANSLATED = "MACHINE_TRANSLATED"
BACK_TRANSLATION_CHECKED = "BACK_TRANSLATION_CHECKED"

TranslateFn = Callable[[str, str, str, dict[str, str]], str]
# (text, source_lang, target_lang, locked_terms) -> translated text


@dataclass(frozen=True)
class TextBlock:
    """A block of source text with its position in the document."""
    text: str
    page: int = 0
    block_index: int = 0


@dataclass(frozen=True)
class TranslatedBlock:
    text: str
    source_text: str
    locked_terms_applied: tuple[str, ...] = ()
    back_translation: str | None = None
    drift_score: float | None = None


@dataclass(frozen=True)
class TranslationResult:
    source_lang: str
    target_lang: str
    blocks: tuple[TranslatedBlock, ...]
    status: str
    glossary_coverage: float
    sample_drift_scores: tuple[float, ...] = ()


def _pass2_lock(text: str, glossary: Glossary, target_lang: str) -> tuple[str, dict[str, str], list[str]]:
    """Find glossary terms in text and return the locked term map for the translator."""
    locked: dict[str, str] = {}
    applied: list[str] = []
    all_terms = glossary.all_for_language(target_lang)
    for eng, translation in all_terms.items():
        if eng.lower() in text.lower():
            locked[eng] = translation
            applied.append(eng)
    return text, locked, applied


def _pass4_drift(original: str, back_translated: str) -> float:
    """Word-overlap drift score: 0.0 = identical, 1.0 = no overlap."""
    orig_words = set(original.lower().split())
    back_words = set(back_translated.lower().split())
    if not orig_words:
        return 0.0
    overlap = orig_words & back_words
    return 1.0 - (len(overlap) / max(len(orig_words), 1))


def translate_document(
    blocks: list[TextBlock],
    source_lang: str,
    target_lang: str,
    *,
    translate_fn: TranslateFn,
    back_translate_fn: TranslateFn | None = None,
    glossary: Glossary | None = None,
    sample_rate: float = 0.3,
) -> TranslationResult:
    """Run the four-pass pipeline on a list of text blocks.

    translate_fn(text, source_lang, target_lang, locked_terms) -> translated text
    back_translate_fn: same signature, translates back to source_lang for verification.
    sample_rate: fraction of blocks to back-translate (0.0-1.0).
    """
    if target_lang not in EIGHTH_SCHEDULE_LANGUAGES:
        raise ValueError(f"Unsupported target language: {target_lang}")

    g = glossary or load_glossary()
    translated_blocks: list[TranslatedBlock] = []
    drift_scores: list[float] = []
    total_terms_possible = 0
    total_terms_locked = 0

    sample_every = max(1, int(1 / sample_rate)) if sample_rate > 0 else 0

    for i, block in enumerate(blocks):
        _, locked, applied = _pass2_lock(block.text, g, target_lang)
        total_terms_possible += len(g.all_for_language(target_lang))
        total_terms_locked += len(applied)

        translated_text = translate_fn(block.text, source_lang, target_lang, locked)

        back_text = None
        drift = None
        if back_translate_fn and sample_every and (i % sample_every == 0):
            back_text = back_translate_fn(translated_text, target_lang, source_lang, {})
            drift = _pass4_drift(block.text, back_text)
            drift_scores.append(drift)

        translated_blocks.append(TranslatedBlock(
            text=translated_text,
            source_text=block.text,
            locked_terms_applied=tuple(applied),
            back_translation=back_text,
            drift_score=drift,
        ))

    coverage = total_terms_locked / max(total_terms_possible, 1)
    status = BACK_TRANSLATION_CHECKED if drift_scores else MACHINE_TRANSLATED

    return TranslationResult(
        source_lang=source_lang,
        target_lang=target_lang,
        blocks=tuple(translated_blocks),
        status=status,
        glossary_coverage=coverage,
        sample_drift_scores=tuple(drift_scores),
    )


# ── self-test ──────────────────────────────────────────────────────────────

def _self_test() -> None:
    passed = failed = 0

    def check(name: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    # Mock translator that prefixes "[HI]" and respects locked terms
    def mock_translate(text: str, src: str, tgt: str, locked: dict[str, str]) -> str:
        result = text
        for eng, trans in locked.items():
            result = result.replace(eng, trans)
        return f"[{tgt.upper()}] {result}"

    def mock_back_translate(text: str, src: str, tgt: str, locked: dict[str, str]) -> str:
        clean = text.replace(f"[{src.upper()}] ", "")
        return clean

    blocks = [
        TextBlock("The Board of Directors held an Annual General Meeting.", page=1, block_index=0),
        TextBlock("A Special Resolution was passed for Arbitration.", page=1, block_index=1),
        TextBlock("The CIN of the company is U12345.", page=2, block_index=0),
    ]

    result = translate_document(
        blocks, "en", "hi",
        translate_fn=mock_translate,
        back_translate_fn=mock_back_translate,
        sample_rate=1.0,
    )

    check("correct source lang", result.source_lang == "en")
    check("correct target lang", result.target_lang == "hi")
    check("3 blocks translated", len(result.blocks) == 3)
    check("status is BACK_TRANSLATION_CHECKED", result.status == BACK_TRANSLATION_CHECKED)

    b0 = result.blocks[0]
    check("Board of Directors locked",
          "Board of Directors" in b0.locked_terms_applied)
    check("Hindi Board term in output",
          "निदेशक मंडल" in b0.text)
    check("AGM locked",
          "Annual General Meeting" in b0.locked_terms_applied)

    b1 = result.blocks[1]
    check("Special Resolution locked",
          "Special Resolution" in b1.locked_terms_applied)
    check("Arbitration locked",
          "Arbitration" in b1.locked_terms_applied)

    b2 = result.blocks[2]
    check("CIN preserved (not translated)",
          "CIN" in b2.text)

    check("back translations present",
          all(b.back_translation is not None for b in result.blocks))
    check("drift scores present",
          all(b.drift_score is not None for b in result.blocks))
    check("drift scores are floats in [0,1]",
          all(0.0 <= s <= 1.0 for s in result.sample_drift_scores))
    check("glossary coverage > 0", result.glossary_coverage > 0)

    # Without back-translation
    result2 = translate_document(
        blocks, "en", "hi",
        translate_fn=mock_translate,
        sample_rate=0.0,
    )
    check("no back-translate: status is MACHINE_TRANSLATED",
          result2.status == MACHINE_TRANSLATED)
    check("no back-translate: no drift scores",
          len(result2.sample_drift_scores) == 0)

    # Unsupported language raises
    raised = False
    try:
        translate_document(blocks, "en", "zz", translate_fn=mock_translate)
    except ValueError:
        raised = True
    check("unsupported lang raises ValueError", raised)

    # Sample rate < 1.0: not all blocks back-translated
    result3 = translate_document(
        [TextBlock(f"Block {i}") for i in range(10)],
        "en", "hi",
        translate_fn=mock_translate,
        back_translate_fn=mock_back_translate,
        sample_rate=0.25,
    )
    back_count = sum(1 for b in result3.blocks if b.back_translation is not None)
    check("sample_rate 0.25: ~25% back-translated", 1 <= back_count <= 5)

    # drift score: identical text → 0.0
    check("identical drift is 0.0", _pass4_drift("hello world", "hello world") == 0.0)
    check("no overlap drift is 1.0", _pass4_drift("hello world", "foo bar") == 1.0)
    check("partial overlap between 0 and 1",
          0.0 < _pass4_drift("hello world foo", "hello bar baz") < 1.0)

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
