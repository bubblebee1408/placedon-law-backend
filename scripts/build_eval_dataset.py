"""Build annotated evaluation dataset from CUAD test.json for bakeoff_cuad.py.

Converts SQuAD 2.0 format → EvalRecord-compatible JSON, with document-level
80/20 train/test split (seed=42, no contract split across sets).

Usage:
    PYTHONPATH=. python3 scripts/build_eval_dataset.py           # build
    PYTHONPATH=. python3 scripts/build_eval_dataset.py --test     # self-test

Run: PYTHONPATH=. python3 scripts/build_eval_dataset.py --test
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

CUAD_PATH = Path("corpus/benchmark/cuad/test.json")
OUT_DIR = Path("corpus/benchmark/cuad")
SEED = 42
TRAIN_RATIO = 0.8


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]


def build():
    with open(CUAD_PATH) as f:
        cuad = json.load(f)

    records: list[dict] = []
    doc_ids: set[str] = set()

    for entry in cuad["data"]:
        title = entry["title"]
        doc_id = _slugify(title)
        doc_ids.add(doc_id)

        for para in entry["paragraphs"]:
            context = para["context"]
            doc_hash = hashlib.sha256(context.encode()).hexdigest()[:16]

            for qa in para["qas"]:
                answers = qa.get("answers", [])
                is_impossible = qa.get("is_impossible", False)
                first_answer = answers[0] if answers else {}

                records.append({
                    "document_id": doc_id,
                    "document_type": "contract",
                    "document_hash": doc_hash,
                    "question_id": qa["id"],
                    "question": qa["question"],
                    "context": context[:500],
                    "expected_answer": first_answer.get("text", "") if not is_impossible else "",
                    "expected_party": "",
                    "expected_modality": "",
                    "expected_evidence": first_answer.get("text", ""),
                    "expected_source_offsets": (
                        [first_answer["answer_start"],
                         first_answer["answer_start"] + len(first_answer["text"])]
                        if first_answer.get("text") and "answer_start" in first_answer
                        else None
                    ),
                    "expected_abstention": is_impossible,
                    "annotation_version": "cuad-v1",
                })

    # Document-level split
    all_docs = sorted(doc_ids)
    rng = random.Random(SEED)
    rng.shuffle(all_docs)
    split_idx = int(len(all_docs) * TRAIN_RATIO)
    train_docs = set(all_docs[:split_idx])
    test_docs = set(all_docs[split_idx:])

    train = [r for r in records if r["document_id"] in train_docs]
    test = [r for r in records if r["document_id"] in test_docs]

    # Write
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "eval_dataset.json", "w") as f:
        json.dump({"version": "cuad-v1", "total": len(records),
                    "train_docs": len(train_docs), "test_docs": len(test_docs),
                    "records": records}, f, indent=2)
    with open(OUT_DIR / "eval_train.json", "w") as f:
        json.dump(train, f, indent=2)
    with open(OUT_DIR / "eval_test.json", "w") as f:
        json.dump(test, f, indent=2)

    abstain_count = sum(1 for r in records if r["expected_abstention"])
    print(f"Built: {len(records)} questions from {len(all_docs)} contracts")
    print(f"Train: {len(train)} questions ({len(train_docs)} docs)")
    print(f"Test:  {len(test)} questions ({len(test_docs)} docs)")
    print(f"Abstention rate: {abstain_count / len(records):.1%}")
    return records, train, test


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("build_eval_dataset")

    records, train, test = build()

    check(len(records) > 0, f"records built ({len(records)})")

    # Document-level split: no overlap
    train_docs = {r["document_id"] for r in train}
    test_docs = {r["document_id"] for r in test}
    check(len(train_docs & test_docs) == 0, "no document overlap train/test")

    # All records accounted for
    check(len(train) + len(test) == len(records), "train+test=total")

    # Schema valid
    required_keys = {"document_id", "document_type", "document_hash",
                     "question_id", "question", "context", "expected_answer",
                     "expected_abstention", "annotation_version"}
    sample = records[0]
    check(required_keys.issubset(sample.keys()), "schema keys present")

    # Abstention rate reasonable (CUAD has many is_impossible)
    abstain = sum(1 for r in records if r["expected_abstention"])
    rate = abstain / len(records)
    check(0.1 < rate < 0.9, f"abstention rate plausible ({rate:.1%})")

    # Files exist
    for name in ("eval_dataset.json", "eval_train.json", "eval_test.json"):
        p = OUT_DIR / name
        check(p.exists() and p.stat().st_size > 100, f"{name} exists")

    # Offsets valid where present
    with_offsets = [r for r in records if r["expected_source_offsets"]]
    if with_offsets:
        s = with_offsets[0]
        check(isinstance(s["expected_source_offsets"], list), "offsets are list")
        check(len(s["expected_source_offsets"]) == 2, "offsets are [start, end]")
        check(s["expected_source_offsets"][0] < s["expected_source_offsets"][1],
              "start < end")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    build()
