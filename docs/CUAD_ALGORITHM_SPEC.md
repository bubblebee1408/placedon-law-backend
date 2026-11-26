# CUAD Algorithm Specification

## Overview

This document specifies the exact algorithms for the CUAD extractive QA stage.
Every algorithm is deterministic except the model call itself, which is treated
as an oracle that proposes candidates for deterministic verification.

---

## Algorithm 1: Document Windowing

**Input:** document text `D` (string), definitions threshold `D_THRESH = 2000`
**Output:** list of `Window(text, start, end, has_definitions_prefix)`

```
WINDOW_SIZE = 6000  # characters
STRIDE = 2000       # characters (1/3 overlap)

function windows(D):
    # ConReader insight: detect definitions section
    prefix = ""
    lower = D[:D_THRESH].lower()
    if "definitions" in lower or "interpretation" in lower:
        # Find the end of the definitions section (next section heading)
        prefix = D[:D_THRESH]

    result = []
    pos = 0
    if prefix:
        pos = len(prefix)  # start windowing after definitions

    while pos < len(D):
        end = min(pos + WINDOW_SIZE, len(D))
        window_text = prefix + D[pos:end] if prefix else D[pos:end]
        result.append(Window(
            text=window_text,
            start=pos,
            end=end,
            has_definitions_prefix=bool(prefix)
        ))
        pos += STRIDE
        if end == len(D):
            break

    # Edge case: empty or very short document
    if not result:
        result.append(Window(text=D, start=0, end=len(D), has_definitions_prefix=False))

    return result
```

**Invariants:**
- Every character in D[prefix_end:] appears in at least one window
- Overlap between consecutive windows is exactly `WINDOW_SIZE - STRIDE` characters
- Definitions prefix (if present) is prepended to every window, not counted in stride
- A single-window document produces exactly one window

**Complexity:** O(|D| / STRIDE) windows, each O(WINDOW_SIZE) to construct.

---

## Algorithm 2: Category Selection

**Input:** `clause_tags` (list of `Tag` from Stage 2), `CUAD_CATEGORIES` (41 entries)
**Output:** list of category names to query

```
REGEX_COVERED = {
    "Governing Law", "Non-Compete", "Anti-Assignment", "Audit Rights",
    "Insurance", "Renewal Term", "Notice to Terminate Renewal",
    "Termination for Convenience", "Cap on Liability", "Uncapped Liability"
}

function select_categories(tags, doc_class):
    # Always ask about categories not covered by regex
    uncovered = [c for c in CUAD_CATEGORIES if c.name not in REGEX_COVERED]

    # Also ask about categories where regex found something (to get exact span)
    tag_names = {t.tag for t in tags}
    regex_to_cuad = MAPPING  # the 13→41 mapping from CUAD_EXTRACTOR_PLAN.md
    matched = [cuad_name for regex_name in tag_names
               for cuad_name in regex_to_cuad.get(regex_name, [])]

    # Combine, deduplicate, sort
    return sorted(set(c.name for c in uncovered) | set(matched))
```

**Invariant:** Every CUAD category is queried either because (a) it has no regex
equivalent, or (b) the regex tagger found evidence of it. Categories the regex
tagger cannot detect are always included.

---

## Algorithm 3: Prompt Construction

**Input:** `window` (Window), `categories` (list of category names)
**Output:** prompt string

```
SYSTEM = """You are a contract clause extractor. For each category below,
extract the EXACT text from the contract that answers the question.

Rules:
1. Quote the contract VERBATIM — do not paraphrase, summarize, or add words
2. If the contract does not contain the answer, respond with "NOT_FOUND"
3. Return ONLY a JSON object mapping category name to extracted text or "NOT_FOUND"
4. For boolean categories, still extract the relevant clause text — not "Yes"/"No"
5. If multiple relevant passages exist, extract the most specific one"""

function build_prompt(window, categories):
    questions = []
    for cat_name in categories:
        cat = CUAD_CATEGORIES[cat_name]
        questions.append(f"- {cat_name}: {cat.question}")

    return f"""{SYSTEM}

Contract text:
---
{window.text}
---

Extract the following:
{newline.join(questions)}

Respond with a JSON object. Keys are category names exactly as listed above."""
```

**Invariants:**
- The prompt never includes instructions derived from the document content
  (prompt-injection resistance — see SANITIZATION_SPEC.md)
- Category names and questions are from the frozen registry, never from user input
- Document text is placed inside delimiters and treated as data

---

## Algorithm 4: Response Parsing

**Input:** model response string `R`
**Output:** list of `RawExtraction(category, quoted_text)`

```
function parse_response(R):
    # Strip markdown code fences
    text = R.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])  # remove opening fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]  # remove closing fence
    text = text.strip()

    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []  # malformed response → empty, never crash

    if not isinstance(data, dict):
        return []

    result = []
    for key, value in data.items():
        if key not in CUAD_CATEGORIES:
            continue  # unknown category → skip
        if not isinstance(value, str):
            continue
        value = value.strip()
        if not value or value == "NOT_FOUND":
            continue
        result.append(RawExtraction(category=key, quoted_text=value))

    return result
```

**Invariants:**
- Malformed JSON returns empty list, never raises
- Unknown category names are silently dropped
- NOT_FOUND and empty strings produce no extraction
- The parser never interprets value content as instructions

---

## Algorithm 5: Span Verification (PLAN_23 Gate)

**Input:** `extractions` (list of RawExtraction), `D` (original document text)
**Output:** list of `VerifiedExtraction(category, quoted_text, start, end, status)`

```
EXACT_MATCH = "VERIFIED"
FUZZY_MATCH = "FUZZY_MATCH"
NO_MATCH = "UNVERIFIED"

FUZZY_THRESHOLD = 0.5    # Jaccard, from CUAD paper
MIN_SPAN_LENGTH = 8      # from clause_tags.MIN_QUOTE

function word_set(text):
    return set(text.lower().split())

function jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

function verify_extractions(extractions, D):
    # Pre-compute sentence boundaries for fuzzy matching
    sentences = split_sentences(D)  # same regex as clause_tags._SENTENCE

    result = []
    for ext in extractions:
        # 1. Exact match
        pos = D.find(ext.quoted_text)
        if pos >= 0 and len(ext.quoted_text) >= MIN_SPAN_LENGTH:
            result.append(VerifiedExtraction(
                category=ext.category,
                quoted_text=ext.quoted_text,
                start=pos,
                end=pos + len(ext.quoted_text),
                status=EXACT_MATCH
            ))
            continue

        # 2. Normalized exact match (collapse whitespace)
        normalized_quote = " ".join(ext.quoted_text.split())
        normalized_D = " ".join(D.split())
        pos_norm = normalized_D.find(normalized_quote)
        if pos_norm >= 0 and len(normalized_quote) >= MIN_SPAN_LENGTH:
            # Map back to original offsets (approximate)
            result.append(VerifiedExtraction(
                category=ext.category,
                quoted_text=ext.quoted_text,
                start=-1,  # offset not reliable after normalization
                end=-1,
                status=EXACT_MATCH
            ))
            continue

        # 3. Fuzzy match against sentences
        ext_words = word_set(ext.quoted_text)
        best_score = 0.0
        best_sentence = ""
        best_start = -1
        best_end = -1
        for sent_text, sent_start, sent_end in sentences:
            score = jaccard(ext_words, word_set(sent_text))
            if score > best_score:
                best_score = score
                best_sentence = sent_text
                best_start = sent_start
                best_end = sent_end

        if best_score >= FUZZY_THRESHOLD and len(best_sentence) >= MIN_SPAN_LENGTH:
            result.append(VerifiedExtraction(
                category=ext.category,
                quoted_text=best_sentence,  # use the ACTUAL document sentence
                start=best_start,
                end=best_end,
                status=FUZZY_MATCH
            ))
            continue

        # 4. No match → UNVERIFIED, dropped from output
        # (logged for diagnostics, not returned)

    return result
```

**Invariants:**
- Every returned extraction has status VERIFIED or FUZZY_MATCH
- UNVERIFIED extractions are dropped — they never reach downstream
- A FUZZY_MATCH replaces the model's text with the actual document sentence
- The MIN_SPAN_LENGTH matches `clause_tags.MIN_QUOTE` (8 chars)
- The FUZZY_THRESHOLD (0.5) matches the CUAD paper's evaluation threshold

---

## Algorithm 6: Cross-Window Deduplication

**Input:** list of VerifiedExtraction from all windows
**Output:** deduplicated list

```
DEDUP_THRESHOLD = 0.8  # Jaccard

function deduplicate(extractions):
    # Group by category
    by_category = defaultdict(list)
    for ext in extractions:
        by_category[ext.category].append(ext)

    result = []
    for category, exts in by_category.items():
        # Sort by status (VERIFIED first) then by span length (longer first)
        exts.sort(key=lambda e: (0 if e.status == EXACT_MATCH else 1, -len(e.quoted_text)))

        kept = []
        for ext in exts:
            is_dup = False
            for existing in kept:
                if jaccard(word_set(ext.quoted_text), word_set(existing.quoted_text)) >= DEDUP_THRESHOLD:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(ext)

        result.extend(kept)

    return result
```

**Invariants:**
- Within a category, VERIFIED extractions are preferred over FUZZY_MATCH
- Longer spans are preferred (they carry more context)
- Two extractions from overlapping windows matching the same clause text merge
  into one
- Distinct clause instances in different parts of the document are kept separate

---

## Algorithm 7: Value Normalization

**Input:** VerifiedExtraction with category metadata
**Output:** `NormalizedExtraction` with structured `value` field

```
function normalize(ext, category_type):
    # Normalization is category-type-specific and purely deterministic
    match category_type:
        case "date":
            return parse_date(ext.quoted_text)  # reuse evidence_extractor date parsing
        case "entity":
            return ext.quoted_text.strip()  # names are already normalized
        case "boolean":
            return ext.quoted_text  # presence of text = "yes"; absence was NOT_FOUND
        case "span":
            return ext.quoted_text  # clause text, verbatim

    # Never invent a value. If parsing fails, return the raw text.
    return ext.quoted_text
```

**Invariant:** Normalization never discards or modifies the original quoted_text.
The `value` field is derived FROM it; both are stored.

---

## Complexity Summary

| Algorithm | Time | Space |
|-----------|------|-------|
| Windowing | O(|D| / STRIDE) | O(|D|) |
| Category selection | O(41 + |tags|) | O(41) |
| Prompt construction | O(|window| + |categories|) | O(|prompt|) |
| Response parsing | O(|response|) | O(|extractions|) |
| Span verification | O(|extractions| × |sentences|) | O(|sentences|) |
| Deduplication | O(|extractions|² per category) | O(|extractions|) |
| Normalization | O(|extractions|) | O(|extractions|) |

For a typical 20-page contract (~40,000 chars): ~19 windows, 41 categories per
window, O(1) model calls per window (all categories in one prompt). Total model
calls: ~19. Each verification is O(sentences), typically <500 sentences.
