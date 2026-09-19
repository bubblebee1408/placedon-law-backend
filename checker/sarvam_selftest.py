"""Self-test for checker/sarvam_model.py -- run through `python3 checker/sarvam_model.py`.

Split out only to keep both files under the repo's 800-line ceiling. No test here
reaches the network: `urllib.request.urlopen` is replaced for the whole run with a
function that records the attempt and fails, and the final check asserts none
happened. Every API response used here is either a doc-shape fixture (labelled, in
checker/fixtures/vendor_docs/) or built by the FakeSarvam below, which follows the
same documented shapes.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from checker import sarvam_model as sm

PUBLIC_2PAGE = sm.ROOT / "corpus" / "sources" / "gsr880e_2025.pdf"
PUBLIC_14PAGE = sm.ROOT / "corpus" / "testdocs" / "_raw" / "rm_bm_20250128.pdf"
FIXTURES = sm.ROOT / "checker" / "fixtures" / "vendor_docs"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _pdf_pages(data: bytes) -> int:
    import pypdf
    return len(pypdf.PdfReader(io.BytesIO(data)).pages)


def _multipart_file(body: bytes) -> tuple[str, bytes]:
    """(filename, bytes) of the single file part in a body built by build_multipart."""
    head, _, rest = body.partition(b'name="file"; filename="')
    fname, _, rest = rest.partition(b'"')
    _, _, rest = rest.partition(b"\r\n\r\n")
    data = rest.rsplit(b"\r\n--", 1)[0]
    return fname.decode(), data


class FakeSarvam:
    """Answers the four documented calls with the documented shapes."""

    def __init__(self, *, missing=None, empty=None, final="completed", polls_before=1,
                 created_job_id=None, status_value=None):
        self.missing = missing or {}      # job index -> page numbers left out
        self.empty = empty or {}          # job index -> page numbers with "" content
        self.final, self.polls_before = final, polls_before
        self.created_job_id, self.status_value = created_job_id, status_value
        self.jobs: list[dict] = []
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[bytes] = []

    def __call__(self, method, path, body, content_type):
        self.calls.append((method, path))
        if method == "POST" and path == "/job/digitise":
            self.bodies.append(body)
            assert content_type.startswith("multipart/form-data; boundary=")
            fname, data = _multipart_file(body)
            n = (len(zipfile.ZipFile(io.BytesIO(data)).namelist())
                 if fname.endswith(".zip") else
                 _pdf_pages(data) if fname.endswith(".pdf") else 1)
            k = len(self.jobs)
            jid = self.created_job_id or f"job-{k}"
            self.jobs.append({"id": jid, "n": n, "polls": 0, "k": k})
            return {"job_id": jid, "status": "pending", "run_id": f"run-{k}"}
        job = next(j for j in self.jobs if path.startswith(f"/job/{j['id']}/"))
        k, n = job["k"], job["n"]
        miss = set(self.missing.get(k, ()))
        if path.endswith("/status"):
            job["polls"] += 1
            st = self.status_value or ("running" if job["polls"] <= self.polls_before
                                       else self.final)
            return {"job_id": job["id"], "status": st, "pipeline": "digitise",
                    "usage": {"pages_total": n, "pages_processed": n,
                              "pages_succeeded": n - len(miss), "pages_failed": len(miss)},
                    "created_at": "2026-09-18T00:00:00Z", "updated_at": "2026-09-18T00:00:05Z"}
        if path.endswith("/results"):
            pages = [{"page_number": p,
                      "content": "" if p in self.empty.get(k, ()) else
                      f"<p>page {p} of job {k}</p>"}
                     for p in range(1, n + 1) if p not in miss]
            return {"type": "digitise", "job_id": job["id"], "status": self.final,
                    "documents": [{"file_name": "x", "pages": pages}],
                    "usage": {"pages_total": n, "pages_processed": n,
                              "pages_succeeded": n - len(miss), "pages_failed": len(miss)}}
        raise AssertionError(f"unexpected call {method} {path}")


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def run() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def attempt(fn):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001 - inspected by the test
            return e
        return None

    print("sarvam_model")
    network: list[str] = []

    def no_network(*a, **k):
        network.append("urlopen")
        raise AssertionError("a unit test tried to reach the network")

    guard = mock.patch.object(urllib.request, "urlopen", side_effect=no_network)
    guard.start()
    held = {k: os.environ.pop(k, None) for k in ("SARVAM_API_KEY", sm.OPT_OUT_NAME)}
    try:
        with tempfile.TemporaryDirectory() as td:
            _checks(check, attempt, Path(td))
    finally:
        guard.stop()
        for k, v in held.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    check(not network, f"no unit test reached the network ({len(network)} attempts)")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def _checks(check, attempt, tmp: Path) -> None:
    no_opt_out = tmp / "empty.env"
    no_opt_out.write_text("SOME_OTHER=1\n")
    private = tmp / "board_minutes_private.pdf"
    private.write_bytes(PUBLIC_2PAGE.read_bytes())      # public BYTES, private PATH
    _privacy(check, attempt, tmp, no_opt_out, private)
    _chunks_and_parts(check, attempt, tmp)
    _requests(check, attempt)
    _fixtures(check, attempt)
    _flow(check, attempt, no_opt_out)
    _errors(check, attempt, no_opt_out)


def _privacy(check, attempt, tmp, no_opt_out, private) -> None:
    # ── refused: not public, no confirmed opt-out ────────────────────────────
    os.environ[sm.OPT_OUT_NAME] = sm.OPT_OUT_VALUE      # set in the SHELL, not the file
    e = attempt(lambda: sm.privacy_check(private, env_path=no_opt_out))
    check(isinstance(e, sm.SarvamPrivacyRefused),
          "a file outside corpus/ is refused -- even when the opt-out is exported in the "
          "shell, because only the .env FILE line counts")
    check(sm.OPT_OUT_NAME in str(e) and "public" in str(e).lower(),
          "...and the refusal names both ways to be allowed")
    os.environ.pop(sm.OPT_OUT_NAME)

    c = sm.privacy_check(PUBLIC_2PAGE, env_path=no_opt_out)
    head = subprocess.run(["git", "-C", str(sm.ROOT), "rev-parse",
                           "HEAD:corpus/sources/gsr880e_2025.pdf"],
                          capture_output=True, text=True).stdout.strip()
    check(c.basis == sm.PUBLIC and c.blob == head and c.path == "corpus/sources/gsr880e_2025.pdf",
          f"the held G.S.R. 880(E) PDF is PUBLIC, pinned to its committed blob ({c.blob[:10]})")
    c14 = sm.privacy_check(PUBLIC_14PAGE, env_path=no_opt_out)
    check(c14.basis == sm.PUBLIC, "a held public testdoc is PUBLIC too")

    trav = sm.ROOT / "corpus" / "sources" / ".." / ".." / "README.md"
    e = attempt(lambda: sm.privacy_check(trav, env_path=no_opt_out))
    check(isinstance(e, sm.SarvamPrivacyRefused),
          "a path that walks out of corpus/ with '..' is refused (README.md)")
    link = tmp / "looks_private.pdf"
    link.symlink_to(PUBLIC_2PAGE)
    check(sm.privacy_check(link, env_path=no_opt_out).basis == sm.PUBLIC,
          "a symlink is judged by what it points at: this one IS the public file")
    dangling = tmp / "dangling.pdf"
    dangling.symlink_to(tmp / "nowhere.pdf")
    check(isinstance(attempt(lambda: sm.privacy_check(dangling, env_path=no_opt_out)),
                     sm.SarvamPrivacyRefused), "a dangling symlink is refused")
    check(isinstance(attempt(lambda: sm.privacy_check(sm.ROOT / "corpus" / "sources",
                                                      env_path=no_opt_out)),
                     sm.SarvamPrivacyRefused), "a directory is refused")

    def git_says(rev, hashed):
        def _g(args):
            if args[0] == "rev-parse":
                return rev
            return hashed
        return _g
    for label, g, needle in (
        ("not at HEAD", git_says((128, ""), (0, "abc")), "not a file the repo holds"),
        ("swapped bytes", git_says((0, "aaa"), (0, "bbb")), "differ"),
    ):
        e = attempt(lambda g=g: sm.privacy_check(PUBLIC_2PAGE, env_path=no_opt_out, _git=g))
        check(isinstance(e, sm.SarvamPrivacyRefused) and needle in str(e),
              f"under corpus/ but {label} -> refused ({needle!r})")

    def git_missing(args):
        raise FileNotFoundError("git")
    e = attempt(lambda: sm.privacy_check(PUBLIC_2PAGE, env_path=no_opt_out, _git=git_missing))
    check(isinstance(e, sm.SarvamPrivacyRefused) and "cannot confirm" in str(e),
          "no git to confirm the file is held -> refused, not assumed public")

    # ── allowed: the .env FILE carries the founder's line ────────────────────
    for content, allowed in (
        (f"{sm.OPT_OUT_NAME}=confirmed\n", True),
        (f'{sm.OPT_OUT_NAME}="confirmed"\n', True),
        (f"{sm.OPT_OUT_NAME}=yes\n", False),
        (f"{sm.OPT_OUT_NAME}=Confirmed\n", False),
        (f"# {sm.OPT_OUT_NAME}=confirmed\n", False),
        (f"{sm.OPT_OUT_NAME}=\n", False),
    ):
        envf = tmp / "opt.env"
        envf.write_text(content)
        r = attempt(lambda: sm.privacy_check(private, env_path=envf))
        if allowed:
            got = sm.privacy_check(private, env_path=envf)
            check(r is None and got.basis == sm.OPTED_OUT,
                  f"{content.strip()!r} in .env -> allowed as {sm.OPTED_OUT}")
        else:
            check(isinstance(r, sm.SarvamPrivacyRefused),
                  f"{content.strip()!r} in .env -> still refused (exact value only)")

    # the guard runs before the key check and before any request
    fake = FakeSarvam()
    e = attempt(lambda: sm.digitise(private, language="en-IN", env_path=no_opt_out,
                                    _transport=fake))
    check(isinstance(e, sm.SarvamPrivacyRefused) and not fake.calls,
          "digitise() on a private file is refused before any request is built")
    e = attempt(lambda: sm.digitise_images([private], language="en-IN",
                                           env_path=no_opt_out, _transport=fake))
    check(isinstance(e, sm.SarvamPrivacyRefused) and not fake.calls,
          "digitise_images() applies the same guard to every image")

    # ── missing key ──────────────────────────────────────────────────────────
    check(not sm.available(), "with no SARVAM_API_KEY, available() is False")
    e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=no_opt_out))
    check(isinstance(e, sm.SarvamUnavailable) and "SARVAM_API_KEY" in str(e),
          "with no key, digitise() of a PUBLIC file raises SarvamUnavailable")
    check(isinstance(e, sm.ModelUnavailable), "...which is a ModelUnavailable")


def _chunks_and_parts(check, attempt, tmp) -> None:
    check(sm.plan_chunks(10) == ((1, 10),), "10 pages -> one job")
    check(sm.plan_chunks(11) == ((1, 10), (11, 11)), "11 pages -> 10 + 1, nothing dropped")
    check(sm.plan_chunks(25) == ((1, 10), (11, 20), (21, 25)), "25 pages -> 10 + 10 + 5")
    check(sm.plan_chunks(1) == ((1, 1),), "1 page -> one job")
    bad_n = []
    for n in range(1, 206):
        ch = sm.plan_chunks(n)
        covered = [p for a, b in ch for p in range(a, b + 1)]
        if covered != list(range(1, n + 1)) or any(b - a + 1 > 10 for a, b in ch):
            bad_n.append(n)
    check(not bad_n, f"for every length 1-205, each page lands in exactly one job of <= 10 "
                     f"pages (failures: {bad_n[:5]})")
    check(isinstance(attempt(lambda: sm.plan_chunks(0)), ValueError), "0 pages is refused")

    parts = sm.prepare_parts(PUBLIC_14PAGE)
    check([(p.first_page, p.n_pages) for p in parts] == [(1, 10), (11, 4)],
          "the 14-page public scan is split into pages 1-10 and 11-14")
    check([_pdf_pages(p.data) for p in parts] == [10, 4],
          "...and each split PDF, re-read, really holds 10 and 4 pages")
    check(all(p.content_type == "application/pdf" for p in parts)
          and parts[1].filename == "pages-0011-0014.pdf",
          f"...named by the pages they carry ({parts[1].filename}), not by the local path")
    whole = sm.prepare_parts(PUBLIC_2PAGE)
    check(len(whole) == 1 and whole[0].data == PUBLIC_2PAGE.read_bytes(),
          "a document within the limit is sent as its ORIGINAL bytes, not rewritten")
    one = sm.prepare_parts(PUBLIC_2PAGE, page_range=(1, 1))
    check(len(one) == 1 and one[0].n_pages == 1 and _pdf_pages(one[0].data) == 1,
          "an explicit page_range sends only the pages asked for")
    two = sm.prepare_parts(PUBLIC_14PAGE, page_range=(9, 12))
    check([(p.first_page, p.n_pages) for p in two] == [(9, 4)],
          "a range is chunked on its own pages (9-12 is one 4-page job)")
    for bad in ((0, 1), (2, 1), (1, 3)):
        check(isinstance(attempt(lambda b=bad: sm.prepare_parts(PUBLIC_2PAGE, page_range=b)),
                         ValueError), f"page_range {bad} on a 2-page PDF is refused")
    txt = tmp / "note.txt"
    txt.write_text("x")
    check(isinstance(attempt(lambda: sm.prepare_parts(txt)), ValueError),
          "a format the API does not list (.txt) is refused")

    imgs = []
    for i in range(12):
        p = tmp / f"crop_{i:02d}.png"
        p.write_bytes(b"\x89PNG fake " + bytes([i]))
        imgs.append(p)
    zparts = sm.image_zip_parts(imgs)
    check([(p.first_page, p.n_pages) for p in zparts] == [(1, 10), (11, 2)],
          "12 page images -> a ZIP of 10 and a ZIP of 2")
    names = zipfile.ZipFile(io.BytesIO(zparts[1].data)).namelist()
    check(names == ["0001.png", "0002.png"] and zparts[1].content_type == "application/zip",
          f"...each ZIP flat, ordered by filename as the API orders pages ({names})")
    check(zipfile.ZipFile(io.BytesIO(zparts[1].data)).read("0002.png") == imgs[11].read_bytes(),
          "...and the image bytes inside are the originals")


def _requests(check, attempt) -> None:
    body, ctype = sm.build_multipart([("language", "hi-IN"), ("output_format", "md")],
                                     [("file", "pages-0001-0002.pdf", "application/pdf",
                                       b"%PDF-bytes")], "BOUNDARY42")
    check(ctype == "multipart/form-data; boundary=BOUNDARY42", "multipart content type")
    check(b'Content-Disposition: form-data; name="language"\r\n\r\nhi-IN\r\n' in body
          and b'name="output_format"\r\n\r\nmd\r\n' in body,
          "language and output_format are sent as form fields (S1)")
    check(b'name="file"; filename="pages-0001-0002.pdf"\r\nContent-Type: application/pdf'
          b"\r\n\r\n%PDF-bytes\r\n" in body, "the document is the `file` part (S1)")
    check(body.endswith(b"--BOUNDARY42--\r\n"), "the body is closed with the final boundary")
    check(b"content_type" not in body and b'name="model"' not in body,
          "content_type and model are NOT sent: their accepted values are undocumented")
    e = attempt(lambda: sm.build_multipart([], [("file", "a.pdf", "application/pdf",
                                                  b"x--B--y")], "B"))
    check(isinstance(e, ValueError), "a boundary that occurs inside the file is refused")

    req = sm.build_request("POST", "/job/digitise", "sk-TEST", body, ctype)
    check(req.full_url == "https://api.sarvam.ai/doc-ai/v1/job/digitise"
          and req.get_method() == "POST", f"digitise goes to the documented URL ({req.full_url})")
    check(req.get_header("Api-subscription-key") == "sk-TEST",
          "...with the `api-subscription-key` header (S1)")
    check(req.get_header("Content-type") == ctype, "...and the multipart content type")
    g = sm.build_request("GET", "/job/abc-1/status", "sk-TEST")
    check(g.full_url.endswith("/doc-ai/v1/job/abc-1/status") and g.data is None,
          "status is a GET with no body (S2)")
    check(isinstance(attempt(lambda: sm.build_request("GET", "/admin", "k")), ValueError),
          "a path outside /job/ is refused")


def _fixtures(check, attempt) -> None:
    for name in ("sarvam_digitise_create_example.json", "sarvam_status_example.json",
                 "sarvam_digitise_results_example.json", "sarvam_error_example.json"):
        prov = _fixture(name)["_provenance"]
        check(prov.startswith("shape copied from https://docs.sarvam.ai/")
              and "not a live response" in prov, f"{name} is labelled a doc-shape copy")
    jid, st, run = sm.parse_created(_fixture("sarvam_digitise_create_example.json")["example"])
    check((jid, st, run) == ("string", "string", "string"),
          "the documented 201 example parses (its values are the doc's placeholders)")
    s = sm.parse_status(_fixture("sarvam_status_example.json")["example"])
    check(s.status == "completed" and s.pages_total == 1 and s.pages_failed == 0,
          "the documented status example parses")
    pages = sm.parse_digitise_results(_fixture("sarvam_digitise_results_example.json")["example"],
                                      n_pages=2, first_page=1, output_format="html")
    check([p.status for p in pages] == ["READ", "READ"],
          "the documented digitise-results example parses to two READ pages")
    check(pages[0].text == "Policy Document\nPolicy Number: ABC-1234"
          and pages[1].text == "Terms & Conditions\n...",
          f"...HTML is reduced to text, entities decoded ({pages[1].text!r})")
    check(pages[0].content.startswith("<h1>"), "...and the raw content is kept beside it")
    res = _fixture("sarvam_digitise_results_example.json")["example"]
    e = attempt(lambda: sm.parse_digitise_results(res, n_pages=3, first_page=1,
                                                  output_format="html"))
    check(isinstance(e, sm.SarvamBadResponse),
          "'completed' with a page missing (2 of 3) is refused, not read as a short document")
    for label, mutate in (
        ("type is not digitise", lambda d: d.update(type="extract")),
        ("two documents for one file", lambda d: d.update(documents=d["documents"] * 2)),
        ("a page number past the job", lambda d: d["documents"][0]["pages"][1].update(page_number=7)),
        ("a repeated page", lambda d: d["documents"][0]["pages"][1].update(page_number=1)),
        ("non-text content", lambda d: d["documents"][0]["pages"][0].update(content=None)),
        ("a non-terminal status", lambda d: d.update(status="running")),
    ):
        d = json.loads(json.dumps(res))
        mutate(d)
        e = attempt(lambda d=d: sm.parse_digitise_results(d, n_pages=2, first_page=1,
                                                          output_format="html"))
        check(isinstance(e, sm.SarvamBadResponse), f"results: {label} -> refused")
    for bad in ({"status": "pending"}, {"job_id": "../../admin", "status": "pending"},
                {"job_id": "a/b", "status": "x"}, ["job"]):
        check(isinstance(attempt(lambda b=bad: sm.parse_created(b)), sm.SarvamBadResponse),
              f"a created-job response {bad!r} is refused (no id, or one unsafe in a URL)")
    check(sm.html_to_text("<table><tr><td>Rs 10&nbsp;crore</td></tr></table><p>A<br>B</p>")
          == "Rs 10\xa0crore\nA\nB", "table cells and <br> become lines")


def _flow(check, attempt, env) -> None:
    os.environ["SARVAM_API_KEY"] = "sk-TEST"
    try:
        clock, fake = Clock(), FakeSarvam()
        r = sm.digitise(PUBLIC_14PAGE, language="en-IN", output_format="html", env_path=env,
                        _transport=fake, _sleep=clock.sleep, _clock=clock.now)
        check([p.page for p in r.pages] == list(range(1, 15)) and r.complete,
              "a 14-page document comes back as 14 READ pages, numbered 1-14")
        check(r.pages[10].text == "page 1 of job 1",
              "page 11 is job 2's page 1: split results map back to original page numbers")
        check(len(r.jobs) == 2 and [j.n_pages for j in r.jobs] == [10, 4],
              "two jobs are recorded, of 10 and 4 pages")
        check(r.est_cost_inr == 7.0, f"estimated cost 14 x Rs 0.50 = Rs 7.0 ({r.est_cost_inr})")
        check(r.basis == sm.PUBLIC and r.pages_requested == (1, 14),
              "the result records why it was allowed and which pages were asked for")
        check(all(b'name="language"\r\n\r\nen-IN' in b for b in fake.bodies),
              "every job carries the language")
        submits = [c for c in fake.calls if c[0] == "POST"]
        check(len(submits) == 2 and all(c[1] == "/job/digitise" for c in submits),
              "one POST per chunk")
        check(fake.calls[1] == ("GET", "/job/job-0/status")
              and ("GET", "/job/job-0/results") in fake.calls,
              "then status polls, then results")
        check(len(clock.sleeps) >= len(fake.calls) - 1
              and all(s <= sm.MIN_GAP_S + 1e-9 for s in clock.sleeps)
              and round(sum(clock.sleeps), 6) >= round(sm.MIN_GAP_S * (len(fake.calls) - 1), 6),
              f"every request is paced {sm.MIN_GAP_S} s after the last (10 req/min, S4)")

        clock, fake = Clock(), FakeSarvam(missing={0: [3]}, empty={0: [5]},
                                          final="partially_completed")
        r = sm.digitise(PUBLIC_14PAGE, language="en-IN", env_path=env, _transport=fake,
                        _sleep=clock.sleep, _clock=clock.now)
        by = {p.page: p for p in r.pages}
        check(by[3].status == "FAILED" and by[3].text is None,
              "a page missing from a partial job is FAILED, with no text")
        check(by[5].status == "FAILED",
              "a partial job's page with empty content is FAILED, not a blank page")
        check(by[4].status == "READ" and len(r.pages) == 14,
              "...while its other pages are READ, and all 14 pages are accounted for")
        check(not r.complete, "...and the document result says it is not complete")

        clock, fake = Clock(), FakeSarvam(empty={0: [2]})
        r = sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env, _transport=fake,
                        _sleep=clock.sleep, _clock=clock.now)
        check(r.pages[1].status == "EMPTY" and not r.complete,
              "a 'completed' page with no text is EMPTY -- not READ, not silently blank")

        for final in ("failed", "rejected"):
            clock, fake = Clock(), FakeSarvam(final=final)
            out: list = []
            e = attempt(lambda: out.append(sm.digitise(
                PUBLIC_2PAGE, language="en-IN", env_path=env, _transport=fake,
                _sleep=clock.sleep, _clock=clock.now)))
            check(isinstance(e, sm.SarvamServiceError) and not out and "job-0" in str(e),
                  f"a {final} job raises SarvamServiceError naming the job; no result")

        clock, fake = Clock(), FakeSarvam(polls_before=10_000)
        e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env,
                                        _transport=fake, _sleep=clock.sleep,
                                        _clock=clock.now, max_wait=30))
        check(isinstance(e, sm.SarvamServiceError) and "terminal" in str(e)
              and "job-0" in str(e), "a job that never finishes times out as a service error")
        check(not any(c[1].endswith("/results") for c in fake.calls),
              "...and results were never requested for it")

        clock, fake = Clock(), FakeSarvam(status_value="queued_for_review")
        e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env,
                                        _transport=fake, _sleep=clock.sleep, _clock=clock.now))
        check(isinstance(e, sm.SarvamBadResponse) and "queued_for_review" in str(e),
              "an undocumented job status is refused, not guessed at")

        clock, fake = Clock(), FakeSarvam(created_job_id="../../x")
        e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env,
                                        _transport=fake, _sleep=clock.sleep, _clock=clock.now))
        check(isinstance(e, sm.SarvamBadResponse) and len(fake.calls) == 1,
              "a job id unsafe to put in a URL is refused before it is used in one")

        for label, kw in (("an unlisted language", dict(language="hindi")),
                          ("output_format 'markdown' (S4: returns 400)",
                           dict(language="hi-IN", output_format="markdown")),
                          ("output_format json (results content is HTML/MD only)",
                           dict(language="hi-IN", output_format="json"))):
            fake = FakeSarvam()
            e = attempt(lambda kw=kw: sm.digitise(PUBLIC_2PAGE, env_path=env,
                                                  _transport=fake, **kw))
            check(isinstance(e, ValueError) and not fake.calls, f"{label} is refused before any call")
    finally:
        os.environ.pop("SARVAM_API_KEY", None)


def _errors(check, attempt, env) -> None:
    secret = "sk-SECRET-never-print-77aa"
    os.environ["SARVAM_API_KEY"] = secret
    from checker import robots
    ctx = mock.patch.object(robots, "ssl_context", return_value=object())
    ctx.start()
    try:
        problem = _fixture("sarvam_error_example.json")["example"]

        def http(code, body):
            return urllib.error.HTTPError(sm.BASE, code, "err", {},
                                          io.BytesIO(body.encode("utf-8")))
        scenarios = {
            "HTTP 400 problem+json": (http(400, json.dumps(problem)), "10-page limit"),
            "HTTP 401 echoing the key": (http(401, json.dumps({"detail": f"bad key {secret}"})), "401"),
            "HTTP 409": (http(409, json.dumps({"title": "Conflict"})), "409"),
            "HTTP 429": (http(429, json.dumps({"title": "Too Many Requests"})), "rate"),
            "HTTP 503": (http(503, "billing down"), "503"),
            "an unreachable host": (urllib.error.URLError("no route"), "unreachable"),
            "a read timeout": (TimeoutError("timed out"), "TimeoutError"),
        }
        for label, (exc, needle) in scenarios.items():
            out: list = []
            with mock.patch.object(urllib.request, "urlopen", side_effect=exc):
                e = attempt(lambda: out.append(sm.digitise(
                    PUBLIC_2PAGE, language="en-IN", env_path=env,
                    _sleep=lambda s: None, _clock=lambda: 0.0)))
            check(isinstance(e, sm.SarvamServiceError) and not out,
                  f"{label}: SarvamServiceError, and no result object at all")
            check(needle.lower() in str(e).lower() and secret not in str(e),
                  f"{label}: the error says {needle!r} and never contains the key")
            check(not isinstance(e, LookupError), f"{label}: not a 'nothing found' type")

        class Resp:
            def __init__(self, b): self.b = b
            def read(self): return self.b
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(urllib.request, "urlopen", return_value=Resp(b"<html>")):
            e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env,
                                            _sleep=lambda s: None, _clock=lambda: 0.0))
        check(isinstance(e, sm.SarvamBadResponse), "a 200 with a non-JSON body is refused")
        with mock.patch.object(robots, "ssl_context", return_value=None):
            e = attempt(lambda: sm.digitise(PUBLIC_2PAGE, language="en-IN", env_path=env))
        check(isinstance(e, sm.SarvamUnavailable) and "unverified" in str(e),
              "no CA trust store -> refuses rather than calling unverified")
    finally:
        ctx.stop()
        os.environ.pop("SARVAM_API_KEY", None)
