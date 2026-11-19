"""Legal terminology glossary for Indian law across 22 Eighth Schedule languages.

A legal term must translate the same way every time it appears in a document.
"Memorandum of Association" in a Companies Act translation cannot become
"Memorandum" on page 3 and "Association Deed" on page 7. This module locks
terms to their canonical translations per language.

Three tiers:
  STATUTORY — terms defined in legislation (Companies Act, Contract Act, etc.)
              These have ONE correct translation per language, usually the one
              the official translation of the Act uses.
  STANDARD  — terms with widely accepted translations across Indian legal practice.
  PRESERVE  — terms that should NOT be translated (CIN, DIN, PAN, proper nouns).

Usage:
  glossary = load_glossary()
  locked = glossary.lock("Memorandum of Association", "hi")
  # -> "पार्षद सीमानियम" (the Hindi term used in the official Hindi Companies Act)

Run: PYTHONPATH=. python3 checker/legal_glossary.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

__all__ = ["Term", "Glossary", "load_glossary", "EIGHTH_SCHEDULE_LANGUAGES"]

EIGHTH_SCHEDULE_LANGUAGES = (
    "as", "bn", "bo", "doi", "gu", "hi", "kn", "ks", "kok", "mai",
    "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur",
)

STATUTORY = "STATUTORY"
STANDARD = "STANDARD"
PRESERVE = "PRESERVE"
TIERS = (STATUTORY, STANDARD, PRESERVE)


@dataclass(frozen=True)
class Term:
    english: str
    tier: str
    translations: dict[str, str]
    source: str = ""
    note: str = ""


@dataclass(frozen=True)
class Glossary:
    terms: tuple[Term, ...]
    _by_english: dict[str, Term] = None

    def __post_init__(self):
        idx = {t.english.lower(): t for t in self.terms}
        object.__setattr__(self, "_by_english", idx)

    def lock(self, english: str, lang: str) -> str | None:
        """Return the locked translation, or None if not in glossary."""
        t = self._by_english.get(english.lower())
        if t is None:
            return None
        if t.tier == PRESERVE:
            return english
        return t.translations.get(lang)

    def tier_of(self, english: str) -> str | None:
        t = self._by_english.get(english.lower())
        return t.tier if t else None

    def all_for_language(self, lang: str) -> dict[str, str]:
        """All locked terms for a language. Keys are English, values are translations."""
        out = {}
        for t in self.terms:
            if t.tier == PRESERVE:
                out[t.english] = t.english
            elif lang in t.translations:
                out[t.english] = t.translations[lang]
        return out


# Companies Act 2013 terms — Hindi translations from the official Hindi text
_COMPANIES_ACT_TERMS = [
    Term("Memorandum of Association", STATUTORY,
         {"hi": "पार्षद सीमानियम", "mr": "संघटन ज्ञापन", "bn": "সংঘস্মারক", "ta": "சங்க ஒப்புறுதிப் பத்திரம்", "te": "సంఘ జ్ఞాపన పత్రం"},
         source="Companies Act 2013 s.2(56)"),
    Term("Articles of Association", STATUTORY,
         {"hi": "पार्षद अंतर्नियम", "mr": "संघटन लेख", "bn": "সংঘবিধি", "ta": "சங்க விதிகள்", "te": "సంఘ నియమావళి"},
         source="Companies Act 2013 s.2(5)"),
    Term("Board of Directors", STATUTORY,
         {"hi": "निदेशक मंडल", "mr": "संचालक मंडळ", "bn": "পরিচালক পর্ষদ", "ta": "இயக்குநர் குழு", "te": "డైరెక్టర్ల బోర్డు", "gu": "નિયામક મંડળ", "kn": "ನಿರ್ದೇಶಕ ಮಂಡಳಿ"},
         source="Companies Act 2013 s.2(10)"),
    Term("Annual General Meeting", STATUTORY,
         {"hi": "वार्षिक साधारण सभा", "mr": "वार्षिक सर्वसाधारण सभा", "bn": "বার্ষিক সাধারণ সভা", "ta": "ஆண்டுப் பொதுக்கூட்டம்", "te": "వార్షిక సాధారణ సభ"},
         source="Companies Act 2013 s.96"),
    Term("Extraordinary General Meeting", STATUTORY,
         {"hi": "असाधारण साधारण सभा", "mr": "विशेष सर्वसाधारण सभा", "bn": "অসাধারণ সাধারণ সভা", "ta": "அசாதாரணப் பொதுக்கூட்டம்"},
         source="Companies Act 2013 s.100"),
    Term("Special Resolution", STATUTORY,
         {"hi": "विशेष संकल्प", "mr": "विशेष ठराव", "bn": "বিশেষ সংকল্প", "ta": "சிறப்புத் தீர்மானம்", "te": "ప్రత్యేక తీర్మానం"},
         source="Companies Act 2013 s.114"),
    Term("Ordinary Resolution", STATUTORY,
         {"hi": "साधारण संकल्प", "mr": "साधारण ठराव", "bn": "সাধারণ সংকল্প", "ta": "சாதாரணத் தீர்மானம்"},
         source="Companies Act 2013 s.114"),
    Term("Registrar of Companies", STATUTORY,
         {"hi": "कंपनी रजिस्ट्रार", "mr": "कंपनी निबंधक", "bn": "কোম্পানি নিবন্ধক", "ta": "நிறுவனப் பதிவாளர்"},
         source="Companies Act 2013 s.2(75)"),
    Term("Paid-up Share Capital", STATUTORY,
         {"hi": "प्रदत्त अंश पूंजी", "mr": "भरणा झालेले भाग भांडवल", "bn": "পরিশোধিত শেয়ার মূলধন"},
         source="Companies Act 2013 s.2(64)"),
    Term("Authorized Capital", STATUTORY,
         {"hi": "प्राधिकृत पूंजी", "mr": "अधिकृत भांडवल", "bn": "অনুমোদিত মূলধন"},
         source="Companies Act 2013 s.2(8)"),
]

# Indian Contract Act 1872 terms
_CONTRACT_ACT_TERMS = [
    Term("Consideration", STATUTORY,
         {"hi": "प्रतिफल", "mr": "मोबदला", "bn": "প্রতিদান", "ta": "எதிர்ப்பயன்"},
         source="Indian Contract Act 1872 s.2(d)"),
    Term("Free Consent", STATUTORY,
         {"hi": "स्वतंत्र सहमति", "mr": "मुक्त संमती", "bn": "স্বাধীন সম্মতি"},
         source="Indian Contract Act 1872 s.14"),
    Term("Indemnity", STATUTORY,
         {"hi": "क्षतिपूर्ति", "mr": "नुकसानभरपाई", "bn": "ক্ষতিপূরণ", "ta": "இழப்பீடு"},
         source="Indian Contract Act 1872 s.124"),
    Term("Guarantee", STATUTORY,
         {"hi": "प्रत्याभूति", "mr": "हमी", "bn": "জামিন"},
         source="Indian Contract Act 1872 s.126"),
    Term("Void Agreement", STATUTORY,
         {"hi": "शून्य करार", "mr": "शून्य करार", "bn": "শূন্য চুক্তি"},
         source="Indian Contract Act 1872 s.2(g)"),
]

# Terms that should NEVER be translated
_PRESERVE_TERMS = [
    Term("CIN", PRESERVE, {}, note="Corporate Identity Number — alphanumeric identifier"),
    Term("DIN", PRESERVE, {}, note="Director Identification Number"),
    Term("PAN", PRESERVE, {}, note="Permanent Account Number"),
    Term("TAN", PRESERVE, {}, note="Tax Deduction Account Number"),
    Term("GSTIN", PRESERVE, {}, note="GST Identification Number"),
    Term("ISIN", PRESERVE, {}, note="International Securities Identification Number"),
    Term("SEBI", PRESERVE, {}, note="Securities and Exchange Board of India"),
    Term("RBI", PRESERVE, {}, note="Reserve Bank of India"),
    Term("NCLT", PRESERVE, {}, note="National Company Law Tribunal"),
    Term("NCLAT", PRESERVE, {}, note="National Company Law Appellate Tribunal"),
    Term("MCA", PRESERVE, {}, note="Ministry of Corporate Affairs"),
    Term("ROC", PRESERVE, {}, note="Registrar of Companies (abbreviation)"),
]

# Standard legal practice terms (not statutory definitions)
_STANDARD_TERMS = [
    Term("Arbitration", STANDARD,
         {"hi": "मध्यस्थता", "mr": "लवाद", "bn": "সালিশ", "ta": "நடுவர் தீர்ப்பு", "te": "మధ్యవర్తిత్వం"},
         source="Arbitration and Conciliation Act 1996"),
    Term("Stamp Duty", STANDARD,
         {"hi": "स्टाम्प शुल्क", "mr": "मुद्रांक शुल्क", "bn": "স্ট্যাম্প শুল্ক", "ta": "முத்திரைத் தீர்வை"},
         source="Indian Stamp Act 1899"),
    Term("Power of Attorney", STANDARD,
         {"hi": "मुख्तारनामा", "mr": "मुखत्यारपत्र", "bn": "মোক্তারনামা", "ta": "அதிகாரப் பத்திரம்"},
         source="Powers of Attorney Act 1882"),
    Term("Affidavit", STANDARD,
         {"hi": "शपथपत्र", "mr": "प्रतिज्ञापत्र", "bn": "শপথপত্র", "ta": "சத்தியப் பிரமாணம்"},
         source="common legal practice"),
    Term("Vakalatnama", STANDARD,
         {"hi": "वकालतनामा", "mr": "वकालतनामा", "bn": "ওকালতনামা"},
         source="common legal practice", note="advocate engagement deed"),
    Term("Liquidated Damages", STANDARD,
         {"hi": "निर्धारित हर्जाना", "mr": "निश्चित नुकसानभरपाई", "bn": "নির্ধারিত ক্ষতিপূরণ"},
         source="Indian Contract Act 1872 s.74"),
    Term("Force Majeure", STANDARD,
         {"hi": "अप्रत्याशित घटना", "mr": "अनपेक्षित परिस्थिती"},
         source="common contract practice", note="not a statutory Indian term"),
    Term("Non-Disclosure Agreement", STANDARD,
         {"hi": "गोपनीयता करार", "mr": "गोपनीयता करारनामा", "bn": "গোপনীয়তা চুক্তি"},
         source="common legal practice"),
    Term("Due Diligence", STANDARD,
         {"hi": "सम्यक परिश्रम", "mr": "उचित परिश्रम"},
         source="common legal practice"),
]


def load_glossary() -> Glossary:
    """Load the built-in Indian legal glossary."""
    all_terms = _COMPANIES_ACT_TERMS + _CONTRACT_ACT_TERMS + _PRESERVE_TERMS + _STANDARD_TERMS
    return Glossary(terms=tuple(all_terms))


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

    g = load_glossary()

    # statutory term locks
    check("MoA Hindi", g.lock("Memorandum of Association", "hi") == "पार्षद सीमानियम")
    check("AoA Hindi", g.lock("Articles of Association", "hi") == "पार्षद अंतर्नियम")
    check("Board Hindi", g.lock("Board of Directors", "hi") == "निदेशक मंडल")
    check("AGM Marathi", g.lock("Annual General Meeting", "mr") == "वार्षिक सर्वसाधारण सभा")
    check("Special Resolution Bengali", g.lock("Special Resolution", "bn") == "বিশেষ সংকল্প")

    # case insensitive
    check("case insensitive", g.lock("memorandum of association", "hi") == "पार्षद सीमानियम")
    check("UPPER case", g.lock("BOARD OF DIRECTORS", "hi") == "निदेशक मंडल")

    # preserve terms return English
    check("CIN preserved", g.lock("CIN", "hi") == "CIN")
    check("SEBI preserved", g.lock("SEBI", "ta") == "SEBI")
    check("DIN preserved in any lang", g.lock("DIN", "mr") == "DIN")

    # unknown term returns None
    check("unknown term", g.lock("Foobar Legal Term", "hi") is None)

    # unknown language returns None for translatable term
    check("unknown lang", g.lock("Board of Directors", "xx") is None)

    # tier lookup
    check("MoA is STATUTORY", g.tier_of("Memorandum of Association") == STATUTORY)
    check("CIN is PRESERVE", g.tier_of("CIN") == PRESERVE)
    check("Arbitration is STANDARD", g.tier_of("Arbitration") == STANDARD)
    check("unknown tier is None", g.tier_of("Foobar") is None)

    # all_for_language
    hi_terms = g.all_for_language("hi")
    check("Hindi glossary has MoA", "Memorandum of Association" in hi_terms)
    check("Hindi glossary has CIN (preserved)", "CIN" in hi_terms)
    check("Hindi glossary count >= 20", len(hi_terms) >= 20)

    # contract act terms
    check("Consideration Hindi", g.lock("Consideration", "hi") == "प्रतिफल")
    check("Indemnity Tamil", g.lock("Indemnity", "ta") == "இழப்பீடு")

    # standard terms
    check("Arbitration Hindi", g.lock("Arbitration", "hi") == "मध्यस्थता")
    check("Stamp Duty Marathi", g.lock("Stamp Duty", "mr") == "मुद्रांक शुल्क")
    check("Vakalatnama Hindi", g.lock("Vakalatnama", "hi") == "वकालतनामा")

    # Kannada and Gujarati coverage
    check("Board Kannada", g.lock("Board of Directors", "kn") == "ನಿರ್ದೇಶಕ ಮಂಡಳಿ")
    check("Board Gujarati", g.lock("Board of Directors", "gu") == "નિયામક મંડળ")

    # Telugu coverage
    check("MoA Telugu", g.lock("Memorandum of Association", "te") == "సంఘ జ్ఞాపన పత్రం")
    check("Arbitration Telugu", g.lock("Arbitration", "te") == "మధ్యవర్తిత్వం")

    # no duplicate English terms
    seen = set()
    dupes = []
    for t in g.terms:
        low = t.english.lower()
        if low in seen:
            dupes.append(t.english)
        seen.add(low)
    check("no duplicate terms", not dupes)

    # all terms have valid tiers
    check("all tiers valid", all(t.tier in TIERS for t in g.terms))

    # language codes are valid
    all_langs = set()
    for t in g.terms:
        all_langs.update(t.translations.keys())
    check("all language codes in Eighth Schedule",
          all_langs <= set(EIGHTH_SCHEDULE_LANGUAGES))

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
