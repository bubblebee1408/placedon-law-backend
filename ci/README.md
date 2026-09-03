# CI, parked

`tests.yml.pending` is a GitHub Actions workflow. It is not at
`.github/workflows/tests.yml` because GitHub refuses a push that creates or
modifies a workflow file from a token without the `workflow` scope, and the
scope has not been granted. Rather than leave 128 commits on one machine
waiting for an auth flow, the file was moved out of the magic directory and
everything else was pushed.

Nothing about the workflow is wrong. It runs `scripts/run_tests.sh` — the same
script the pre-commit hook runs, never a reimplementation, because two copies of
the definition of "green" drift and the drift is found as a false green. It asks
for `contents: read` and no token.

## To turn it back on

    gh auth login --scopes workflow
    git mv ci/tests.yml.pending .github/workflows/tests.yml
    git commit -m "ci: restore the test workflow"
    git push

Until then the suite runs locally and in the pre-commit hook, which is where it
has always actually run. What is missing is the check on a pull request, not the
check itself.
