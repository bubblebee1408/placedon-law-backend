"""
Send the rendered letters through the Gmail API, using your own OAuth client.

## Why this exists

The Gmail connector available to the assistant can read, draft and label. It cannot send — there
is no such tool. So sending is either manual (open each `.eml`) or this: a local script running
under your own Google credentials, which you control and can revoke.

At 31 Karnataka letters this is roughly break-even against clicking. At 30 more states it is not
close.

## Setup, once

1. Google Cloud Console → **APIs & Services → Library** → enable **Gmail API**.
2. **OAuth consent screen** → External → add your own address as a **Test user**. Leave it in
   Testing; `gmail.send` is a *sensitive* scope, not a restricted one, so no Google review is
   needed for your own account. You will see an "unverified app" warning once.
3. **Credentials → Create credentials → OAuth client ID → Desktop app.** Desktop, not Web: a
   local script has no redirect URI, and a Web client is what led to a secret being pasted into
   a chat window.
4. Download the JSON to `~/.placedon/gmail_credentials.json`. **Do not open it, print it, or
   paste it anywhere.** This script reads it from disk and never logs its contents.

    pip install google-auth-oauthlib google-api-python-client

## Use

    python3 scripts/draft_letters.py --batch 1 --write     # render six
    python3 scripts/send_letters.py --dry-run              # show what would go, send nothing
    python3 scripts/send_letters.py --send                 # actually send, then mark asked

`--send` is required. There is no default that sends, because the default should never be the
irreversible one.

## What it refuses

- To send to a district already marked ASKED. Re-sending is worse than not sending: it reads as
  a mail loop to an official you can approach roughly once.
- To send more than `--max` in a run (default 6). Twenty-nine near-identical mails from one Gmail
  account in a burst is a spam-filter shape, and most of these inboxes are themselves Gmail.
- To mark the register before the API confirms the send. `asked_on` means it went out.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import date
from email import policy
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTBOX = ROOT / "outbox"
REGISTER = ROOT / "corpus/reference/notified_dates.json"
CREDENTIALS = Path.home() / ".placedon/gmail_credentials.json"
TOKEN = Path.home() / ".placedon/gmail_token.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]   # send only. Not read, not modify.


def _service():
    try:
        from google.auth.transport.requests import Request     # noqa: PLC0415
        from google.oauth2.credentials import Credentials      # noqa: PLC0415
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
        from googleapiclient.discovery import build            # noqa: PLC0415
    except ImportError:
        raise SystemExit("REFUSED: pip install google-auth-oauthlib google-api-python-client")

    if not CREDENTIALS.exists():
        raise SystemExit(f"REFUSED: no credentials at {CREDENTIALS}. See this file's docstring.")

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS), SCOPES).run_local_server(port=0)
        TOKEN.parent.mkdir(parents=True, exist_ok=True)
        TOKEN.write_text(creds.to_json())
        TOKEN.chmod(0o600)
    return build("gmail", "v1", credentials=creds)


def pending() -> list[tuple[str, Path, str, str]]:
    """(code, eml path, recipient, subject) for rendered letters not yet marked asked."""
    if not OUTBOX.exists():
        raise SystemExit("REFUSED: outbox/ is empty. Run scripts/draft_letters.py --write first.")
    status = {r["jurisdiction"]: r["status"]
              for r in json.loads(REGISTER.read_text())["districts"]}
    out = []
    for f in sorted(OUTBOX.glob("*.eml")):
        code = f.stem
        if status.get(code) != "UNASKED":
            continue                       # already asked, or unknown to the register
        msg = BytesParser(policy=policy.default).parsebytes(f.read_bytes())
        out.append((code, f, msg["To"], msg["Subject"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--send", action="store_true", help="actually send. Required.")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent")
    ap.add_argument("--max", type=int, default=6, help="most to send in one run (default 6)")
    ap.add_argument("--pause", type=float, default=20.0, help="seconds between sends")
    args = ap.parse_args()

    todo = pending()
    if not todo:
        print("  Nothing pending. Every rendered letter is already marked asked.")
        return 0
    if len(todo) > args.max:
        print(f"  {len(todo)} rendered, sending the first {args.max}. "
              f"Raise --max only if you have a reason.")
        todo = todo[: args.max]

    for code, _f, to, subject in todo:
        print(f"    {code:<12} {to:<32} {subject[:44]}…")

    if not args.send or args.dry_run:
        print(f"\n  Dry run — nothing sent. Add --send to send these {len(todo)}.")
        return 0

    svc = _service()
    doc = json.loads(REGISTER.read_text())
    today = str(date.today())
    sent = 0
    for i, (code, f, to, _s) in enumerate(todo):
        raw = base64.urlsafe_b64encode(f.read_bytes()).decode()
        try:
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        except Exception as exc:                                # noqa: BLE001
            print(f"  FAILED {code}: {type(exc).__name__}. Stopping; "
                  f"{sent} sent and marked.", file=sys.stderr)
            break
        # Mark only after the API confirms. asked_on means it went out.
        for r in doc["districts"]:
            if r["jurisdiction"] == code:
                r["status"], r["asked_on"] = "ASKED", today
        REGISTER.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        f.unlink()                                              # don't re-send on the next run
        sent += 1
        print(f"  sent {code} → {to}")
        if i + 1 < len(todo):
            time.sleep(args.pause)

    print(f"\n  {sent} sent and marked asked on {today}.")
    print("  Commit the register: git add corpus/reference/notified_dates.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
