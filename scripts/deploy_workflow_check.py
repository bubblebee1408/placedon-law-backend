#!/usr/bin/env python3
"""Hold .github/workflows/deploy.yml to the properties that make it safe to leave in the repo.

    python3 scripts/deploy_workflow_check.py      # the gate runs this; prints N/M passed

Text checks, not a YAML parse: no YAML library is pinned, and each property below is a line
an edit could silently drop. The deploy itself is proved only by running it (docs/deploy/AZURE.md).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows" / "deploy.yml"


def _test() -> int:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        passed, failed = passed + bool(cond), failed + (not cond)

    wf = WF.read_text()
    on = wf.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    check(on.strip() == "workflow_dispatch:", "manual trigger only: no push, PR or schedule deploys")
    check("environment: production" in wf, "the job waits on the `production` environment (its reviewer)")
    check("id-token: write" in wf and "azure/login@" in wf and "client-secret" not in wf,
          "Azure login is OIDC: no client secret or password is stored")
    check(re.search(r'GITHUB_REF" != "refs/heads/main"', wf) is not None,
          "only main can be deployed")
    secrets = set(re.findall(r"secrets\.([A-Z_]+)", wf))
    guard = wf.split("- name: Refuse unless configured", 1)[1].split("- name:", 1)[0]
    check(secrets and all(s in guard for s in secrets),
          f"the first step refuses unless every referenced secret is set ({len(secrets)})")
    check(wf.index("Refuse unless configured") < wf.index("azure/login@"),
          "...and it runs before anything touches Azure")
    check("persist-credentials: false" in wf, "the zip ships .git without a GitHub token in it")
    cleanup = wf.split("- name: Close the temporary firewall rule", 1)[1].split("- name:", 1)[0]
    check("if: always()" in cleanup and "firewall-rule delete" in cleanup,
          "the temporary firewall rule is deleted even when a step fails")
    check(wf.index("firewall-rule create") < wf.index("migrate.py --apply")
          < wf.index("Close the temporary firewall rule") < wf.index("az webapp deploy"),
          "order: open rule, migrate, close rule, then deploy")
    check("--backup-url" in wf and "--plan" in wf,
          "migrations print the plan, then back up as the admin before applying")
    check("cancel-in-progress: false" in wf, "a running deploy is never cancelled mid-migration")
    check(not re.search(r"(password|PASSWORD)\s*[:=]\s*['\"][^$'\"]", wf),
          "no literal credential in the workflow")
    startup = (ROOT / "ops" / "azure" / "startup.sh").read_text()
    check("ops.asgi:app" in startup and (ROOT / "ops" / "asgi.py").exists(),
          "the shipped startup script serves ops/asgi.py, which is in the repo")
    check("ops/azure/startup.sh startup.sh" in wf and "printf 'startup.sh\\n" in wf,
          "startup.sh is copied to the bundle root and excluded so the commit reads clean")

    print(f"{passed}/{passed + failed} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_test())
