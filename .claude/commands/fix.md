---
description: Short loop for a bug — reproduce, ratchet, fix, verify
argument-hint: [bug]
---

# /fix $ARGUMENTS

## 1. Reproduce it first

Do not fix what you have not seen fail. If it is a UI bug, reproduce it in a browser.

## 2. Write the check BEFORE the fix

Add it to the **module's own `_test()`**, beside the code it guards, naming this incident in the
check's label. Run that one module — `PYTHONPATH=. python3 <module>` — and **watch it fail.**

This ordering is the whole point. A check written after the fix tests the fix; a check written
before tests the bug. Only the second one stops it coming back.

## 3. Find the cause, not the symptom

```bash
python3 scripts/search_memory.py "$ARGUMENTS"
```

Ask whether the same mistake exists elsewhere. The s.4 threshold fabrication appeared in four
places; fixing one would have left three.

## 4. Fix, then verify

```bash
./scripts/verify_green.sh
```

The new check must now pass, and nothing else may have broken.

## 5. Record it

If it taught something, add it to `LESSONS.md` with the incident. Commit with the story.
