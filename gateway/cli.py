"""`placedon` -- the third surface, generated from the same verb table as the other two.

Not a convenience wrapper around the REST API: it calls the SAME handler the route calls,
so a CLI answer and an HTTP answer cannot differ by a transport. The parser is built from
`gateway.verbs.cli_spec()`, so adding a flag here is impossible -- you add an input to the
verb, and all three surfaces move together (PLAN_22 D6).

    placedon ask --question "how many board meetings must a company hold"
    placedon runs-get --run-id r1
    placedon documents-upload --text "..." --name nda.txt

Output is the same JSON object the REST route returns, on stdout, one object. Exit code is
0 when the verb answered and 1 when it refused, so a shell can branch on it without
parsing.

Run: PYTHONPATH=. python3 gateway/cli.py --help
     PYTHONPATH=. python3 gateway/cli.py --test
"""
from __future__ import annotations

import argparse
import json
import sys

from gateway.verbs import Context, VERBS, by_name, cli_command, cli_flag

PROG = "placedon"


def build_parser(verbs=None) -> argparse.ArgumentParser:
    """One subcommand per verb, one flag per input. Nothing hand-listed."""
    verbs = VERBS if verbs is None else verbs
    p = argparse.ArgumentParser(prog=PROG, description="Placedon, from the command line.")
    subs = p.add_subparsers(dest="command", metavar="VERB")
    for v in verbs:
        sp = subs.add_parser(cli_command(v), help=v.summary)
        for f in v.inputs:
            sp.add_argument(cli_flag(f), dest=f.name, required=f.required,
                            help=f.describes or f.name)
    return p


DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"


def default_context() -> Context:
    """A context backed by whatever gateway.store.select() chooses.

    With PLACEDON_DATABASE_URL set this is Postgres, and a run written by one invocation is
    readable by the next. Without it the store is in-memory and dies with the process --
    so `placedon review-contract` followed by `placedon runs-trace` will NOT find the run.
    That is not a bug to work around; it is the reason the Postgres store exists, and the
    CLI says so rather than appearing to lose data.
    """
    from gateway.store import select
    return Context(tenant=DEFAULT_TENANT, actor=DEFAULT_TENANT,
                   store=select(tenant_id=DEFAULT_TENANT))


def run(argv: list[str], *, ctx: Context | None = None) -> tuple[int, dict]:
    """(exit code, payload). Pure enough to test: no printing, no sys.exit."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return 2, {"error": "bad_request", "detail": "no verb given"}
    wanted = {cli_command(v): v for v in VERBS}[args.command]
    supplied = {f.name: getattr(args, f.name) for f in wanted.inputs
                if getattr(args, f.name, None) is not None}
    out = wanted.run(supplied, ctx or default_context()) if wanted.run else {
        "error": "not_implemented", "detail": wanted.name}
    refused = isinstance(out, dict) and (out.get("status") == "REFUSED"
                                         or "error" in out)
    return (1 if refused else 0), out


def main(argv: list[str] | None = None) -> int:
    code, payload = run(list(sys.argv[1:] if argv is None else argv))
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return code


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

    from gateway.verbs import cli_spec, rest_spec

    p = build_parser()
    # argparse keeps its subcommands on the subparsers action
    subs = [a for a in p._subparsers._group_actions][0].choices   # noqa: SLF001
    check(set(subs) == {cli_command(v) for v in VERBS},
          f"one subcommand per verb, generated ({sorted(subs)})")
    check(set(subs) == {c["command"] for c in cli_spec().values()},
          "...and they are exactly what cli_spec() describes, so the parser and the spec "
          "cannot disagree")

    for v in VERBS:
        sp = subs[cli_command(v)]
        flags = {o for a in sp._actions for o in a.option_strings}   # noqa: SLF001
        want = {cli_flag(f) for f in v.inputs}
        check(want <= flags, f"{cli_command(v)} takes {sorted(want)}")
        required = {a.dest for a in sp._actions if a.required}       # noqa: SLF001
        check(required == {f.name for f in v.inputs if f.required},
              f"...and requires exactly what the verb requires ({sorted(required)})")

    # ── the CLI calls the SAME handler, not a copy ──────────────────────────
    ctx = Context()
    code, out = run(["documents-upload", "--text", "a contract"], ctx=ctx)
    check(code == 0 and len(out["sha256"]) == 64,
          f"documents-upload answers with the same object the route returns ({code})")
    check(len(ctx.documents) == 1,
          "...and wrote to the context it was given, not to a private store of its own")

    from gateway.store import MEMORY, MemoryBackend
    dc = default_context()
    check(dc.store is not None and dc.store.kind in (MEMORY, "postgres"),
          f"the default context is backed by the SELECTED store ({dc.store.kind})")

    # end to end, in ONE process: review a contract, then read its trace back
    from agents import review_contract as _rc
    # A model is INJECTED: the gate reaches no network, and this asserts the CLI's
    # plumbing rather than a model's reading.
    shared = Context(store=MemoryBackend(),
                     model_for=lambda origins: _rc.fixture_model(_rc.fixtures()[0]))
    fx = _rc.fixtures()[0]
    c1, o1 = run(["review-contract", "--text", fx.text, "--name", fx.id,
                  "--test-data", "yes"], ctx=shared)
    check(c1 == 0 and o1.get("run_id"), "review-contract answers and returns a run id")
    c2, o2 = run(["runs-trace", "--run-id", o1["run_id"]], ctx=shared)
    check(c2 == 0 and [s["capability"] for s in o2["steps"]]
          == ["intake", "document", "playbook"],
          "...and runs-trace reads that run back through the CLI, same store")
    c3, o3 = run(["runs-trace", "--run-id", o1["run_id"]],
                 ctx=Context(store=MemoryBackend()))
    check(c3 == 1 and o3["code"] == "NOT_FOUND",
          "...while a DIFFERENT in-memory store does not have it -- which is what two CLI "
          "invocations are without Postgres, and why the Postgres store exists")

    code, out = run(["runs-get", "--run-id", "r1"], ctx=Context())
    check(code == 1 and out["code"] == "NO_STORE",
          f"a refusal exits 1 and says which refusal ({code}, {out.get('code')})")

    code, out = run([], ctx=Context())
    check(code == 2 and "no verb" in out["detail"],
          "no verb at all exits 2 -- distinct from a verb that ran and refused")

    # ── parity with the other two surfaces, from the generated specs ────────
    rest = rest_spec()
    for name, spec in cli_spec().items():
        cli_names = {f.lstrip("-").replace("-", "_") for f in spec["flags"]}
        rest_names = set(rest[name]["body"]) | set(rest[name]["path_params"])
        check(cli_names == rest_names,
              f"{name}: the CLI flags and the REST inputs are the same set")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(main())
