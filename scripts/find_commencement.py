#!/usr/bin/env python3
"""Find which notification commenced a given section of an amending Act.

    python3 scripts/find_commencement.py --section 51 --act "Act 1 of 2018"
    python3 scripts/find_commencement.py --harvest   # cache the notifications
    python3 scripts/find_commencement.py --test

## Search by the amending Act's section, not by the date or the principal section

s.161 of the principal Act was amended by section 51 of the Companies
(Amendment) Act 2017. A commencement notification lists the *amending* Act's
sections, so:

- searching for "161" finds nothing, because no notification mentions it;
- searching by the date 2018-05-07 finds S.O. 1833(E), which does not list
  section 51 — that is how the gap was found, not how it is closed.

Only "which instrument names section 51 of Act 1 of 2018" answers the question.

## The false positive this guards against

Notifications made under **s.1(3) of the principal Act** commence sections of the
Companies Act 2013 itself. Several exist, and several list a section 51 — but
that is s.51 of the principal Act (issue of share certificates), not section 51
of the amending Act. A search that ignores the enabling provision would take one
of those as proof and assign s.161 a commencement date from an unrelated
instrument.

So each notification is first classified by *which Act it commences*, and only
those made under the amending Act are eligible to answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.commencement import (  # noqa: E402
    CACHE, Notification, from_text, parse_sections, save,
)
from checker.robots import USER_AGENT, ssl_context  # noqa: E402

API = "https://indiacode.gov.in/server/api"
IP = "45.127.74.253"
DELAY_S = 1.0

# Which Act a notification brings into force, read from its enabling words.
UNDER_AMENDMENT_2017 = "Companies (Amendment) Act, 2017"
UNDER_PRINCIPAL = "Companies Act, 2013"
UNDER_OTHER = "other"
UNDER_UNKNOWN = "unknown"

_ENABLING_AMD = re.compile(
    r"Companies\s*\(\s*Amendment\s*\)\s*Act,?\s*(\d{4})", re.I)
_ENABLING_PRINCIPAL = re.compile(
    r"[Ss]ub-?section\s*\(\s*3\s*\)\s*of\s*[Ss]ection\s*1\s*of\s*the\s*Companies\s*Act",
    re.I)


@dataclass
class Candidate:
    date: str
    uuid: str
    name: str
    identifier: str | None = None
    enabling: str = UNDER_UNKNOWN
    enabling_year: str | None = None
    sections: tuple[int, ...] = ()
    sha256: str | None = None
    url: str | None = None
    list_item: str | None = None


def _get(url: str, timeout: float = 45.0) -> bytes | None:
    ctx = ssl_context()
    if ctx is None:
        return None
    # Pin the resolved address: this machine's resolver intermittently fails on
    # indiacode.gov.in while every other host resolves. TLS verification is
    # unchanged — the certificate is still checked against the hostname.
    u = urllib.parse.urlsplit(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read() if r.status == 200 else None
    except Exception:
        return None


def _api(path: str) -> dict | None:
    b = _get(f"{API}/{path}")
    if b is None:
        return None
    try:
        return json.loads(b.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None


def enumerate_notifications(pages: int = 3) -> list[Candidate]:
    """Every commencement-notification item recorded against the Companies Act."""
    q = urllib.parse.quote('"Commencement notification" AND dc.date.act_year:2013')
    out: list[Candidate] = []
    seen: set[str] = set()
    for page in range(pages):
        d = _api(f"discover/search/objects?query={q}&size=20&page={page}")
        if not d:
            break
        objs = (d.get("_embedded", {}).get("searchResult", {})
                 .get("_embedded", {}).get("objects", []))
        if not objs:
            break
        for o in objs:
            i = o.get("_embedded", {}).get("indexableObject", {})
            name = i.get("name") or ""
            if "ommencement" not in name and "otification" not in name:
                continue
            uid = i.get("uuid")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            m = i.get("metadata", {})
            date = (m.get("dc.date.issued") or [{}])[0].get("value", "")
            out.append(Candidate(date=date, uuid=uid, name=name))
        time.sleep(DELAY_S)
    return out


def fetch_text(uuid: str) -> tuple[str, str] | None:
    """(text, content-url) from an item's TEXT bundle."""
    d = _api(f"core/items/{uuid}/bundles")
    if not d:
        return None
    for b in d.get("_embedded", {}).get("bundles", []):
        if b.get("name") != "TEXT":
            continue
        href = b.get("_links", {}).get("bitstreams", {}).get("href")
        if not href:
            continue
        bs = _get(href)
        if bs is None:
            return None
        try:
            j = json.loads(bs.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return None
        for s in j.get("_embedded", {}).get("bitstreams", []):
            url = s.get("_links", {}).get("content", {}).get("href")
            if not url:
                continue
            raw = _get(url)
            if raw is None:
                return None
            return raw.decode("utf-8", "replace"), url
    return None


def classify_enabling(text: str) -> tuple[str, str | None]:
    """Which Act this notification commences, from its own enabling words."""
    if _ENABLING_PRINCIPAL.search(text):
        return UNDER_PRINCIPAL, None
    m = _ENABLING_AMD.search(text)
    if m:
        return UNDER_AMENDMENT_2017, m.group(1)
    return UNDER_UNKNOWN, None


def list_item_for(text: str, section: int) -> str | None:
    """The numbered list entry that names this section, quoted verbatim."""
    for m in re.finditer(r"(\d+)\.\s*([^;]{0,90}?[Ss]ections?\s+[^;]{0,60})[;.]", text):
        body = m.group(2)
        nums = parse_sections(body)
        if section in nums:
            return f"item {m.group(1)}: {body.strip()}"
    return None


def harvest(limit: int | None = None) -> list[Candidate]:
    cands = enumerate_notifications()
    print(f"enumerated {len(cands)} notification item(s)", flush=True)
    done: list[Candidate] = []
    for i, c in enumerate(cands[:limit] if limit else cands):
        got = fetch_text(c.uuid)
        if got is None:
            print(f"  [{i+1}] {c.date} {c.name[:40]:<40} UNREACHABLE", flush=True)
            done.append(c)
            continue
        text, url = got
        c.enabling, c.enabling_year = classify_enabling(text)
        n = from_text(text, c.date, url)
        c.identifier, c.sections, c.sha256, c.url = (
            n.identifier, n.sections, n.sha256, url)
        # Cache only instruments that commence the amending Act; a principal-Act
        # notification keyed by date would be picked up by commencement.check()
        # and answer a question it cannot answer.
        if c.enabling == UNDER_AMENDMENT_2017:
            save(n)
        print(f"  [{i+1}] {c.date} {(c.identifier or '?'):<14} "
              f"under={c.enabling[:28]:<28} sections={len(c.sections)}", flush=True)
        done.append(c)
        time.sleep(DELAY_S)
    return done


def search(section: int, act_year: str = "2017") -> dict:
    """Which held notification, if any, commences this amending-Act section.

    Only instruments made under the Companies (Amendment) Act of `act_year` are
    eligible. Without that filter a notification under the principal Act, or
    under the 2019 or 2020 Amendment Act, could supply a section number that
    means something else entirely — which is the false positive the enabling
    classifier exists to prevent.
    """
    index_path = CACHE / "_index.json"
    eligible_dates: set[str] = set()
    if index_path.exists():
        for c in json.loads(index_path.read_text()):
            if (c.get("enabling") == UNDER_AMENDMENT_2017
                    and c.get("enabling_year") == act_year):
                eligible_dates.add(c["date"])

    hits, considered, ineligible = [], 0, 0
    for p in sorted(CACHE.glob("*.json")):
        if p.stem.startswith("_"):          # the index, not a notification
            continue
        d = json.loads(p.read_text())
        if eligible_dates and d.get("date") not in eligible_dates:
            ineligible += 1
            continue
        considered += 1
        if section in d.get("sections", []):
            hits.append({"date": d["date"], "identifier": d["identifier"],
                         "gazette_no": d.get("gazette_no"),
                         "sha256": d["sha256"], "url": d.get("url"),
                         "list_item": list_item_for(d.get("text", ""), section)})
    return {"section": section, "act_year": act_year, "considered": considered,
            "ineligible_not_under_that_act": ineligible, "hits": hits}


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

    print("find_commencement")

    amd = ("S.O. 1833(E).—In exercise of the Power conferred by Sub-Section (2) of "
           "Section 1 of the Companies (Amendment) Act, 2017 (1 of 2018), the Central "
           "Government hereby appoints the 7th May, 2018")
    prn = ("S.O. 902(E).—In exercise of the powers conferred by sub-section (3) of "
           "section 1 of the Companies Act, 2013 (18 of 2013), the Central Government "
           "hereby appoints the 1st April, 2014")
    check(classify_enabling(amd)[0] == UNDER_AMENDMENT_2017,
          "a notification under the Amendment Act is classified as such")
    check(classify_enabling(amd)[1] == "2017", "its Act year is captured")
    check(classify_enabling(prn)[0] == UNDER_PRINCIPAL,
          "a notification under s.1(3) of the principal Act is NOT the amending Act")
    check(classify_enabling("nothing relevant")[0] == UNDER_UNKNOWN,
          "an unrecognised enabling provision is UNKNOWN, not assumed")

    # The false positive this exists to prevent.
    check(classify_enabling(prn)[0] != UNDER_AMENDMENT_2017,
          "a principal-Act notification can never answer for an amending section")

    body = ("appoints the date. 1. Clause (i) of section 2; 7. Section 30 and 31; "
            "13. Sections 54 to 58 (both inclusive);")
    li = list_item_for(body, 31)
    check(li is not None and li.startswith("item 7"),
          f"the list item naming a section is quoted ({li})")
    check(list_item_for(body, 56) is not None,
          "a section inside a range is found in its item")
    check(list_item_for(body, 51) is None,
          "a section that is not listed yields no item")

    r = search(51)
    check(r["considered"] >= 1, f"eligible notifications searched ({r['considered']})")
    check(isinstance(r["hits"], list), "the result reports hits as a list")
    check(all("_index" not in str(h) for h in r["hits"]),
          "the index file is not read as a notification")
    if r["hits"]:
        h = r["hits"][0]
        check(h["date"] == "2018-02-09",
              f"section 51 is commenced by the 9 Feb 2018 instrument ({h['date']})")
        check(h["list_item"] and "51" in h["list_item"],
              f"the exact list item is quoted ({h['list_item']})")
        check(h["sha256"].startswith("sha256:"), "the source is hashed")
    # s.31 must NOT be found on that date; it commenced on 7 May.
    r31 = search(31)
    check(any(x["date"] == "2018-05-07" for x in r31["hits"]),
          "section 31 is commenced by the 7 May 2018 instrument")
    check(not any(x["date"] == "2018-02-09" for x in r31["hits"]),
          "section 31 is not attributed to the 9 Feb instrument")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--harvest", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--section", type=int)
    ap.add_argument("--act", default="Act 1 of 2018")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.test:
        _test()
    elif a.harvest:
        cs = harvest(a.limit)
        Path("corpus/sources/commencement/_index.json").write_text(
            json.dumps([asdict(c) for c in cs], indent=1, default=list) + "\n")
        amd = [c for c in cs if c.enabling == UNDER_AMENDMENT_2017]
        print(f"\n{len(amd)}/{len(cs)} are made under the Companies (Amendment) Act")
    elif a.section:
        r = search(a.section)
        print(json.dumps(r, indent=1)[:2000])
    else:
        ap.print_help()
