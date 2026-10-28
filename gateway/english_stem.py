"""Snowball English (Porter2) stemmer, stdlib only, for document excerpt ranking.

Specification: https://snowballstem.org/algorithms/english/stemmer.html (Porter2). Checked
against NLTK's SnowballStemmer("english") over every word in CUAD contracts 0-50 by
scripts/eval_document_retrieval.py --check-stemmer (a dev-machine check; NLTK is not a
dependency). R1 exceptions are the three the reference implementation uses: gener, commun,
arsen -- so "general" and "generate" stay apart, which Porter 1980 merges.

Used only to MATCH words: a stem is never shown, stored, or used as an offset. Input is one
casefolded ASCII a-z token; anything else is returned unchanged by the caller's rule.

Run `python3 -m gateway.english_stem --test` for the self-check.
"""
from __future__ import annotations

import sys

_VOWELS = frozenset("aeiouy")
_DOUBLES = ("bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt")
_LI_ENDINGS = frozenset("cdeghkmnrt")
_R1_PREFIXES = ("gener", "commun", "arsen")

_EXCEPTIONS = {
    "skis": "ski", "skies": "sky", "dying": "die", "lying": "lie", "tying": "tie",
    "idly": "idl", "gently": "gentl", "ugly": "ugli", "early": "earli", "only": "onli",
    "singly": "singl", "sky": "sky", "news": "news", "howe": "howe", "atlas": "atlas",
    "cosmos": "cosmos", "bias": "bias", "andes": "andes",
}
_AFTER_1A = frozenset({"inning", "outing", "canning", "herring", "earring",
                       "proceed", "exceed", "succeed"})

# (suffix, replacement), longest first within each step: only the longest match is tried.
_STEP2 = sorted([
    ("tional", "tion"), ("enci", "ence"), ("anci", "ance"), ("abli", "able"), ("entli", "ent"),
    ("izer", "ize"), ("ization", "ize"), ("ational", "ate"), ("ation", "ate"), ("ator", "ate"),
    ("alism", "al"), ("aliti", "al"), ("alli", "al"), ("fulness", "ful"), ("ousli", "ous"),
    ("ousness", "ous"), ("iveness", "ive"), ("iviti", "ive"), ("biliti", "ble"), ("bli", "ble"),
    ("ogi", "og"), ("fulli", "ful"), ("lessli", "less"), ("li", ""),
], key=lambda pair: -len(pair[0]))
_STEP3 = sorted([
    ("tional", "tion"), ("ational", "ate"), ("alize", "al"), ("icate", "ic"), ("iciti", "ic"),
    ("ical", "ic"), ("ful", ""), ("ness", ""), ("ative", ""),
], key=lambda pair: -len(pair[0]))
_STEP4 = sorted(["al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment",
                 "ent", "ism", "ate", "iti", "ous", "ive", "ize", "ion"], key=lambda s: -len(s))


def _is_vowel(word: str, i: int) -> bool:
    return word[i] in _VOWELS


def _region_after(word: str, start: int) -> int:
    """Index after the first non-vowel that follows a vowel, searching from `start`."""
    for i in range(start + 1, len(word)):
        if not _is_vowel(word, i) and _is_vowel(word, i - 1):
            return i + 1
    return len(word)


def _regions(word: str) -> tuple[int, int]:
    r1 = next((len(p) for p in _R1_PREFIXES if word.startswith(p)), None)
    if r1 is None:
        r1 = _region_after(word, 0)
    return r1, _region_after(word, r1)


def _ends_short_syllable(word: str) -> bool:
    n = len(word)
    if n == 2:
        return _is_vowel(word, 0) and not _is_vowel(word, 1)
    if n >= 3:
        return (not _is_vowel(word, n - 3) and _is_vowel(word, n - 2)
                and not _is_vowel(word, n - 1) and word[n - 1] not in "wxY")
    return False


def _is_short(word: str, r1: int) -> bool:
    return r1 >= len(word) and _ends_short_syllable(word)


def _has_vowel(part: str) -> bool:
    return any(c in _VOWELS for c in part)


def _step1a(word: str) -> str:
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith(("ied", "ies")):
        return word[:-3] + ("i" if len(word) > 4 else "ie")
    if word.endswith(("us", "ss")):
        return word
    if word.endswith("s") and _has_vowel(word[:-2]):
        return word[:-1]
    return word


def _step1b(word: str, r1: int) -> str:
    for suffix in ("eedly", "ingly", "edly", "eed", "ing", "ed"):
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        if suffix in ("eedly", "eed"):
            return stem + "ee" if len(stem) >= r1 else word
        if not _has_vowel(stem):
            return word
        if stem.endswith(("at", "bl", "iz")):
            return stem + "e"
        if stem.endswith(_DOUBLES):
            return stem[:-1]
        if _is_short(stem, r1):
            return stem + "e"
        return stem
    return word


def _step1c(word: str) -> str:
    if len(word) > 2 and word[-1] in "yY" and not _is_vowel(word, len(word) - 2):
        return word[:-1] + "i"
    return word


def _step2(word: str, r1: int) -> str:
    for suffix, repl in _STEP2:
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        if len(stem) < r1:
            return word
        if suffix == "ogi" and not stem.endswith("l"):
            return word
        if suffix == "li" and (not stem or stem[-1] not in _LI_ENDINGS):
            return word
        return stem + repl
    return word


def _step3(word: str, r1: int, r2: int) -> str:
    for suffix, repl in _STEP3:
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        if len(stem) < r1 or (suffix == "ative" and len(stem) < r2):
            return word
        return stem + repl
    return word


def _step4(word: str, r2: int) -> str:
    for suffix in _STEP4:
        if not word.endswith(suffix):
            continue
        stem = word[:-len(suffix)]
        if len(stem) < r2 or (suffix == "ion" and not stem.endswith(("s", "t"))):
            return word
        return stem
    return word


def _step5(word: str, r1: int, r2: int) -> str:
    if word.endswith("e"):
        stem = word[:-1]
        if len(stem) >= r2 or (len(stem) >= r1 and not _ends_short_syllable(stem)):
            return stem
    elif word.endswith("ll") and len(word) - 1 >= r2:
        return word[:-1]
    return word


def stem(word: str) -> str:
    """The Porter2 stem of one lowercase ASCII word."""
    if word in _EXCEPTIONS:
        return _EXCEPTIONS[word]
    if len(word) <= 2:
        return word
    if word.startswith("'"):
        word = word[1:]
    chars = list(word)
    for i, c in enumerate(chars):
        if c == "y" and (i == 0 or chars[i - 1] in _VOWELS):
            chars[i] = "Y"
    word = "".join(chars)
    r1, r2 = _regions(word)
    for suffix in ("'s'", "'s", "'"):
        if word.endswith(suffix):
            word = word[:-len(suffix)]
            break
    word = _step1a(word)
    if word in _AFTER_1A:
        return word
    word = _step1b(word, r1)
    word = _step1c(word)
    word = _step2(word, r1)
    word = _step3(word, r1, r2)
    word = _step4(word, r2)
    word = _step5(word, r1, r2)
    return word.replace("Y", "y")


# Reference vectors: NLTK SnowballStemmer("english") output, recorded 2026-10-28.
REFERENCE = {
    "termination": "termin", "terminate": "termin", "terminated": "termin", "terminating": "termin",
    "parties": "parti", "party": "parti", "exclusivity": "exclus", "exclusive": "exclus",
    "exclusively": "exclus", "general": "general", "generate": "generat", "news": "news",
    "notices": "notic", "notice": "notic", "assignment": "assign", "assign": "assign",
    "consign": "consign", "consigned": "consign", "consigning": "consign", "consignment": "consign",
    "consist": "consist", "consisted": "consist", "consistency": "consist", "consistent": "consist",
    "consistently": "consist", "consisting": "consist", "consists": "consist", "consolation": "consol",
    "consolations": "consol", "consolatory": "consolatori", "console": "consol", "consoled": "consol",
    "consoles": "consol", "consolidate": "consolid", "consolidated": "consolid", "consolidating": "consolid",
    "consoling": "consol", "consolingly": "consol", "consols": "consol", "consonant": "conson",
    "consort": "consort", "consorted": "consort", "consorting": "consort", "conspicuous": "conspicu",
    "conspicuously": "conspicu", "conspiracy": "conspiraci", "conspirator": "conspir",
    "conspirators": "conspir", "conspire": "conspir", "conspired": "conspir", "conspiring": "conspir",
    "constable": "constabl", "constables": "constabl", "constance": "constanc", "constancy": "constanc",
    "constant": "constant", "knack": "knack", "knackeries": "knackeri", "knacks": "knack",
    "knag": "knag", "knave": "knave", "knaves": "knave", "knavish": "knavish", "kneaded": "knead",
    "kneading": "knead", "knee": "knee", "kneel": "kneel", "kneeled": "kneel", "kneeling": "kneel",
    "kneels": "kneel", "knees": "knee", "knell": "knell", "knelt": "knelt", "knew": "knew",
    "knick": "knick", "knif": "knif", "knife": "knife", "knight": "knight", "knightly": "knight",
    "knights": "knight", "knit": "knit", "knits": "knit", "knitted": "knit", "knitting": "knit",
    "knives": "knive", "knob": "knob", "knobs": "knob", "knock": "knock", "knocked": "knock",
    "knocker": "knocker", "knockers": "knocker", "knocking": "knock", "knocks": "knock",
    "knopp": "knopp", "knot": "knot", "knots": "knot", "skies": "sky", "dying": "die",
    "proceed": "proceed", "succeeding": "succeed", "indemnification": "indemnif",
    "indemnify": "indemnifi", "liability": "liabil", "liable": "liabl", "confidentiality": "confidenti",
    "confidential": "confidenti", "governing": "govern", "governed": "govern", "renewal": "renew",
    "renewed": "renew", "warranties": "warranti", "warranty": "warranti", "obligations": "oblig",
    "obligation": "oblig", "agreement": "agreement", "agreed": "agre", "payment": "payment",
    "payable": "payabl", "insurance": "insur", "insured": "insur", "licensor": "licensor",
    "licensee": "license", "sublicense": "sublicens", "arbitration": "arbitr", "arbitrator": "arbitr",
    "jurisdiction": "jurisdict", "competition": "competit", "competitive": "competit",
}


def _test() -> int:
    failures = [(w, stem(w), want) for w, want in REFERENCE.items() if stem(w) != want]
    for word, got, want in failures:
        print(f"FAIL {word!r}: got {got!r}, want {want!r}")
    checks = len(REFERENCE) + 2
    if stem("general") == stem("generate"):
        failures.append(("general/generate", "merged", "apart"))
        print("FAIL general and generate must not merge")
    if stem("") != "" or stem("a") != "a":
        failures.append(("short", "changed", "unchanged"))
        print("FAIL words of length <= 2 are unchanged")
    print(f"english_stem: {checks - len(failures)}/{checks} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_test() if "--test" in sys.argv else 0)
