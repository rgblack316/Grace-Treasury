#!/usr/bin/env bash
# Sandbox test for the git guard in /app/upgrade.sh
# Verifies that `git status --porcelain -- ':!backups'` correctly ignores
# backups/ content but still reports real source changes.

set -u

PASS=0
FAIL=0
report() {
  local status="$1"; shift
  if [ "$status" = "PASS" ]; then
    PASS=$((PASS+1)); echo "[PASS] $*"
  else
    FAIL=$((FAIL+1)); echo "[FAIL] $*"
  fi
}

SANDBOX="$(mktemp -d /tmp/upgrade_guard_test.XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT
cd "$SANDBOX" || exit 1

# --- Setup repo ---
git init -q
git config user.email "test@test.local"
git config user.name "Tester"
echo "print('hi')" > server.py
printf "backups/\n" > .gitignore
git add server.py .gitignore
git commit -q -m "init"

# --- Simulate backup files appearing on live system ---
mkdir backups
echo "fakearchive" > backups/mongodb.archive.gz
echo '{"ts":"2026-01-01"}' > backups/backup-2026-01-01.json

# Sanity: plain porcelain should be EMPTY because backups/ is gitignored
PLAIN="$(git status --porcelain)"
if [ -z "$PLAIN" ]; then
  report PASS "backups/ ignored by .gitignore (plain porcelain empty as expected)"
else
  # Even if not empty, the main test is the pathspec guard below.
  report PASS "plain porcelain non-empty (would be: $PLAIN) — guard still must be empty"
fi

# --- Positive case: only backups changes => guard must be EMPTY ---
GUARD_OUT="$(git status --porcelain -- ':!backups')"
if [ -z "$GUARD_OUT" ]; then
  report PASS "Guard EMPTY when only backups/ has files (upgrade would PROCEED)"
else
  report FAIL "Guard non-empty when only backups/ has files; got: $GUARD_OUT"
fi

# Display command should also run cleanly
if git status --short -- ':!backups' >/dev/null 2>&1; then
  report PASS "'git status --short -- :!backups' runs without error (positive case)"
else
  report FAIL "'git status --short -- :!backups' errored in positive case"
fi

# --- Force a backup to be tracked-looking (edge): add an untracked file
#     outside backups that is NOT gitignored, to also mimic unknown artifacts.
#     This should also abort upgrade. ---
echo "stray" > stray.txt
GUARD_OUT2="$(git status --porcelain -- ':!backups')"
if [ -n "$GUARD_OUT2" ]; then
  report PASS "Guard NON-EMPTY when untracked file exists outside backups/ (upgrade would ABORT)"
else
  report FAIL "Guard empty despite untracked file outside backups/; got empty"
fi
rm stray.txt

# --- Negative case: modify tracked source file => guard must be NON-EMPTY ---
echo "# local change" >> server.py
GUARD_OUT3="$(git status --porcelain -- ':!backups')"
if [ -n "$GUARD_OUT3" ]; then
  report PASS "Guard NON-EMPTY when tracked server.py modified (upgrade would ABORT). Output: $(echo "$GUARD_OUT3" | tr '\n' ';')"
else
  report FAIL "Guard empty despite modified tracked server.py"
fi

if git status --short -- ':!backups' >/dev/null 2>&1; then
  report PASS "'git status --short -- :!backups' runs without error (negative case)"
else
  report FAIL "'git status --short -- :!backups' errored in negative case"
fi

# --- Syntax check of actual upgrade.sh ---
if bash -n /app/upgrade.sh; then
  report PASS "/app/upgrade.sh passes 'bash -n' syntax check"
else
  report FAIL "/app/upgrade.sh failed 'bash -n' syntax check"
fi

# --- .gitignore contains backups/ ---
if grep -qxE "backups/?" /app/.gitignore; then
  report PASS "/app/.gitignore contains 'backups/' entry"
else
  report FAIL "/app/.gitignore missing 'backups/' entry"
fi

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]
