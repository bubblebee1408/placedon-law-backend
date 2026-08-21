#!/bin/sh
# Point git at the version-controlled hooks in .githooks/.
#
# WHY core.hooksPath AND NOT .git/hooks
# .git/hooks is untracked and per-clone. A gate that lives there is invisible in review, absent on
# every fresh clone, and silently different between two developers' machines. .githooks/ is in the
# repo, so the gate is reviewable and every clone gets the same one after running this script.
#
# Still opt-in by design: git will not adopt a repo's hooks without a local command, and it should
# not -- executing code from a clone on `git commit` is how a repository attacks you.
#
# Idempotent: safe to run on every pull.

set -u

repo_root=$(git rev-parse --show-toplevel) || exit 1
cd "$repo_root" || exit 1

hooks_dir=.githooks
want=.githooks

if [ ! -d "$hooks_dir" ]; then
    echo "install_hooks: $hooks_dir/ does not exist. Nothing installed." >&2
    exit 1
fi

echo "Repository: $repo_root"
echo

# --- 1. config -----------------------------------------------------------------------------
current=$(git config --local --get core.hooksPath || true)
if [ "$current" = "$want" ]; then
    printf '  %-16s already %s (no change)\n' "core.hooksPath" "$want"
else
    git config --local core.hooksPath "$want" || exit 1
    if [ -n "$current" ]; then
        printf '  %-16s %s -> %s (CHANGED)\n' "core.hooksPath" "$current" "$want"
    else
        printf '  %-16s (unset) -> %s (CHANGED)\n' "core.hooksPath" "$want"
    fi
fi

# --- 2. executable bits --------------------------------------------------------------------
# A hook without +x is skipped by git without a word, which is the worst possible failure for a
# gate: it looks installed and enforces nothing.
for hook in "$hooks_dir"/*; do
    [ -f "$hook" ] || continue
    name=${hook##*/}
    if [ -x "$hook" ]; then
        printf '  %-16s already executable (no change)\n' "$name"
    else
        chmod +x "$hook" || exit 1
        printf '  %-16s chmod +x (CHANGED)\n' "$name"
    fi
done

# --- 3. warn about hooks this shadows -------------------------------------------------------
# core.hooksPath replaces .git/hooks wholesale; anything real left in there stops running now.
# --git-dir, not `--git-path hooks`: once core.hooksPath is set, --git-path resolves to the new
# location and the check would report our own hook as shadowed. Also handles a linked worktree,
# where .git is a file rather than a directory.
git_dir=$(git rev-parse --git-dir)
shadowed=$(ls "$git_dir/hooks" 2>/dev/null | grep -v '\.sample$' || true)
if [ -n "$shadowed" ]; then
    echo
    echo "  NOTE: these hooks in .git/hooks are now IGNORED (core.hooksPath replaces the whole"
    echo "        directory, it does not merge). Port anything you still want into $hooks_dir/:"
    printf '%s\n' "$shadowed" | sed 's/^/          /'
fi

cat <<'EOF'

Installed. `git commit` now runs ./scripts/run_tests.sh first and refuses the commit if any
suite is red. CI runs the same script on push and pull_request.

  Bypass once:  SKIP_TESTS=1 git commit ...     (prints a loud UNVERIFIED banner)
  Uninstall:    git config --unset core.hooksPath
  Verify:       git config --get core.hooksPath   ->  .githooks
EOF
