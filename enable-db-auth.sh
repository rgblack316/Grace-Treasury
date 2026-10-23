#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# Grace Treasury - Turn on MongoDB password protection
#
# For EXISTING installs. New installs made with install.sh already have it.
#
# MongoDB only creates its accounts automatically when a database is brand new,
# so simply adding passwords to .env would lock the app out of existing data.
# This script does it in a safe order:
#
#   1. Makes a safety backup of the database and .env
#   2. Creates two MongoDB accounts while the database is still open:
#        - an administrator account (for backups/maintenance)
#        - the app's own account (read/write on its database only)
#   3. Confirms the app account can sign in and see your data
#   4. Saves the passwords to .env and restarts with login required
#   5. Confirms: no login = refused, app account = works, app = healthy, same data
#   If anything in steps 4-5 fails, it puts .env back and restarts the old way.
#
# Usage (from your install folder, after upgrading to this version):
#     ./enable-db-auth.sh            # turn it on (asks for confirmation)
#     ./enable-db-auth.sh --check    # check that it is working
#     ./enable-db-auth.sh --disable  # turn it off again (accounts stay, harmlessly)
#
# TRY THIS ON A COPY OR SNAPSHOT OF YOUR SERVER FIRST.
# ============================================================

APP_DIR="${APP_DIR:-$HOME/grace-treasury}"
MODE="enable"
ASSUME_YES=""
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --disable) MODE="disable" ;;
    --yes) ASSUME_YES=1 ;;
    -h|--help) sed -n '5,30p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

log() { echo "[Grace Treasury] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

[ -d "$APP_DIR" ] || fail "Install folder not found: $APP_DIR (set APP_DIR to your install path)"
cd "$APP_DIR"
[ -f .env ] || fail "No .env file in $APP_DIR."
grep -q 'MONGO_INITDB_ROOT_USERNAME' docker-compose.yml \
  || fail "This install hasn't been upgraded to a version that supports database passwords yet. Run ./upgrade.sh first."

# Read/write .env without sourcing it as shell code.
env_get() { awk -F= -v k="$1" '$1 == k {print substr($0, index($0,"=")+1); exit}' .env; }
env_set() {
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}
env_unset() { sed -i "/^$1=/d" .env; }

DB_NAME="$(env_get DB_NAME)"; DB_NAME="${DB_NAME:-church_treasury}"

# Run mongosh inside the mongo container. Credentials travel as environment variables,
# never on this host's command line.
mongosh_noauth() {
  docker_cmd compose exec -T mongo mongosh --quiet "$DB_NAME" --eval "$1"
}
mongosh_as() {  # $1=user $2=password $3=js
  GT_U="$1" GT_P="$2" docker_cmd compose exec -T -e GT_U -e GT_P mongo \
    sh -c 'exec mongosh --quiet --username "$GT_U" --password "$GT_P" --authenticationDatabase admin "$0" --eval "$1"' \
    "$DB_NAME" "$3"
}

COUNT_JS='print("COUNTS " + db.users.countDocuments({}) + " " + db.transactions.countDocuments({}))'

app_health() {
  # Ask the backend itself (inside its container) whether it can read the database.
  docker_cmd compose exec -T backend python -c \
    "import urllib.request,sys; r=urllib.request.urlopen('http://localhost:8001/api/auth/setup-status', timeout=10).read().decode(); print(r); sys.exit(0 if '\"needs_setup\":false' in r.replace(' ','') else 1)" \
    >/dev/null 2>&1
}

wait_for() {  # $1=description, then a command; retries for up to 90 seconds
  local what="$1"; shift
  for _ in $(seq 1 45); do
    if "$@"; then return 0; fi
    sleep 2
  done
  echo "Timed out waiting for: $what" >&2
  return 1
}

mongo_running() { docker_cmd compose ps --services --filter "status=running" | grep -q '^mongo$'; }

# ------------------------------------------------------------
# --check
# ------------------------------------------------------------
run_checks() {
  local ok=0
  local ru rp au ap
  ru="$(env_get MONGO_ROOT_USERNAME)"; rp="$(env_get MONGO_ROOT_PASSWORD)"
  au="$(env_get MONGO_APP_USERNAME)"; ap="$(env_get MONGO_APP_PASSWORD)"
  if [ -z "$rp" ] || [ -z "$ap" ]; then
    echo "Database password protection is OFF (no MongoDB passwords in .env)."
    return 1
  fi
  if mongosh_noauth 'db.getCollectionNames()' >/dev/null 2>&1; then
    echo "  [FAIL] MongoDB still answers without a login."; ok=1
  else
    echo "  [ OK ] MongoDB refuses access without a login."
  fi
  if out="$(mongosh_as "$au" "$ap" "$COUNT_JS" 2>/dev/null)" && echo "$out" | grep -q '^COUNTS '; then
    echo "  [ OK ] The app's account can sign in and read data ($(echo "$out" | awk '/^COUNTS/{print $2" users, "$3" transactions"}'))."
  else
    echo "  [FAIL] The app's account can't sign in."; ok=1
  fi
  if mongosh_as "$ru" "$rp" 'db.adminCommand({ping:1}).ok' >/dev/null 2>&1; then
    echo "  [ OK ] The administrator account can sign in."
  else
    echo "  [FAIL] The administrator account can't sign in."; ok=1
  fi
  if app_health; then
    echo "  [ OK ] Grace Treasury is running and reading the database."
  else
    echo "  [FAIL] Grace Treasury can't read the database. See: docker compose logs backend"; ok=1
  fi
  return $ok
}

if [ "$MODE" = "check" ]; then
  mongo_running || fail "MongoDB isn't running. Start it with: docker compose up -d"
  run_checks && { echo; echo "All checks passed."; exit 0; } || { echo; echo "Some checks failed."; exit 1; }
fi

# ------------------------------------------------------------
# --disable
# ------------------------------------------------------------
if [ "$MODE" = "disable" ]; then
  [ -n "$(env_get MONGO_ROOT_PASSWORD)" ] || { echo "Database password protection is already off."; exit 0; }
  cp -p .env ".env.before-disable-$(date '+%Y-%m-%d_%H-%M-%S')"
  for k in MONGO_ROOT_USERNAME MONGO_ROOT_PASSWORD MONGO_APP_USERNAME MONGO_APP_PASSWORD; do env_unset "$k"; done
  log "Restarting without database passwords..."
  docker_cmd compose up -d
  wait_for "Grace Treasury to start" app_health || fail "Grace Treasury didn't come back up. See: docker compose logs backend"
  echo "Database password protection is OFF. The MongoDB accounts still exist but are no longer required."
  exit 0
fi

# ------------------------------------------------------------
# enable
# ------------------------------------------------------------
if [ -n "$(env_get MONGO_APP_PASSWORD)" ] || [ -n "$(env_get MONGO_ROOT_PASSWORD)" ]; then
  echo "Database passwords are already set in .env. Checking that everything works:"
  run_checks && exit 0 || fail "Something isn't right. Your previous .env copies are in backups/pre-db-auth-*."
fi

mongo_running || fail "MongoDB isn't running. Start Grace Treasury first: docker compose up -d"
app_health || fail "Grace Treasury isn't healthy right now, so this won't continue. Fix that first (docker compose logs backend)."
# (ping works even with login required, so test something that needs access.)
mongosh_noauth 'db.getCollectionNames()' >/dev/null 2>&1 \
  || fail "MongoDB already requires a login, but .env has no passwords. Restore your .env from a backup, or ask for help."

cat <<EOF

This will turn on password protection for the Grace Treasury database.

  - A safety backup of the database and .env is made first.
  - Grace Treasury restarts once (about a minute of downtime).
  - The new passwords are saved in .env. Keep your .env backed up: without it,
    the app can't open its database. (In-app backups don't include these passwords.)
  - If any check fails, .env is put back and the app restarts the old way.

Have you tried this on a copy or snapshot of this server first? (Recommended.)
EOF
if [ -z "$ASSUME_YES" ]; then
  read -r -p "Type YES to continue: " answer
  [ "$answer" = "YES" ] || { echo "Cancelled. Nothing was changed."; exit 1; }
fi

TS="$(date '+%Y-%m-%d_%H-%M-%S')"
SAFE_DIR="backups/pre-db-auth-$TS"
if ! mkdir -p "$SAFE_DIR" 2>/dev/null; then
  sudo mkdir -p "$SAFE_DIR"
  sudo chown "$(id -u):$(id -g)" "$SAFE_DIR"
fi

log "Step 1/5: Safety backup of the database and .env..."
docker_cmd compose exec -T mongo mongodump --db "$DB_NAME" --archive --gzip > "$SAFE_DIR/mongodb.archive.gz"
[ -s "$SAFE_DIR/mongodb.archive.gz" ] || fail "The safety backup is empty. Nothing was changed."
cp -p .env "$SAFE_DIR/.env"
chmod 700 "$SAFE_DIR"; chmod 600 "$SAFE_DIR"/*
echo "    $SAFE_DIR/"

BEFORE="$(mongosh_noauth "$COUNT_JS" | awk '/^COUNTS/{print $2" "$3}')"
[ -n "$BEFORE" ] || fail "Couldn't read the current data counts. Nothing was changed."

log "Step 2/5: Creating the MongoDB accounts..."
hexpw() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
ROOT_USER="gtadmin"; ROOT_PASS="$(hexpw)"
APP_USER="treasury"; APP_PASS="$(hexpw)"
[ "${#ROOT_PASS}" -eq 48 ] && [ "${#APP_PASS}" -eq 48 ] || fail "Couldn't generate passwords. Nothing was changed."

GT_RU="$ROOT_USER" GT_RP="$ROOT_PASS" GT_AU="$APP_USER" GT_AP="$APP_PASS" GT_DB="$DB_NAME" \
  docker_cmd compose exec -T -e GT_RU -e GT_RP -e GT_AU -e GT_AP -e GT_DB mongo mongosh --quiet admin --eval '
    const admin = db.getSiblingDB("admin");
    function upsert(user, pwd, roles) {
      if (admin.getUser(user)) { admin.updateUser(user, { pwd, roles }); }
      else { admin.createUser({ user, pwd, roles }); }
    }
    upsert(process.env.GT_RU, process.env.GT_RP, [{ role: "root", db: "admin" }]);
    upsert(process.env.GT_AU, process.env.GT_AP, [{ role: "readWrite", db: process.env.GT_DB }]);
    print("ACCOUNTS_READY");
  ' | grep -q ACCOUNTS_READY || fail "Couldn't create the MongoDB accounts. Nothing else was changed; the app is still running as before."

log "Step 3/5: Checking the app's account can sign in and see your data..."
CHECK="$(mongosh_as "$APP_USER" "$APP_PASS" "$COUNT_JS" 2>/dev/null | awk '/^COUNTS/{print $2" "$3}')"
[ "$CHECK" = "$BEFORE" ] || fail "The app's account couldn't read the data (expected '$BEFORE', got '$CHECK'). Nothing else was changed; the app is still running as before."

rollback() {
  echo
  echo "!! $1"
  log "Rolling back: restoring the previous .env and restarting the old way..."
  cp -p "$SAFE_DIR/.env" .env
  docker_cmd compose up -d || true
  if wait_for "Grace Treasury to come back" app_health; then
    echo "Rolled back. Grace Treasury is running as before (no database password)."
    echo "Your data was not changed. The two new MongoDB accounts remain but are not used."
  else
    echo "Rollback restarted the containers, but the app isn't answering yet."
    echo "Check: docker compose ps / docker compose logs backend"
    echo "Safety backup: $SAFE_DIR/"
  fi
  exit 1
}

log "Step 4/5: Saving passwords to .env and restarting with login required..."
env_set MONGO_ROOT_USERNAME "$ROOT_USER"
env_set MONGO_ROOT_PASSWORD "$ROOT_PASS"
env_set MONGO_APP_USERNAME "$APP_USER"
env_set MONGO_APP_PASSWORD "$APP_PASS"
chmod 600 .env
docker_cmd compose up -d || rollback "Restart failed."

log "Step 5/5: Verifying..."
wait_for "MongoDB to accept the administrator login" mongosh_as "$ROOT_USER" "$ROOT_PASS" 'db.adminCommand({ping:1}).ok' \
  || rollback "MongoDB didn't come back with login required."
if mongosh_noauth 'db.getCollectionNames()' >/dev/null 2>&1; then
  rollback "MongoDB still answers without a login, so protection isn't active."
fi
AFTER="$(mongosh_as "$APP_USER" "$APP_PASS" "$COUNT_JS" 2>/dev/null | awk '/^COUNTS/{print $2" "$3}')"
[ "$AFTER" = "$BEFORE" ] || rollback "Data counts differ after restart (before '$BEFORE', after '$AFTER')."
wait_for "Grace Treasury to read the database" app_health || rollback "Grace Treasury can't read the database with its new account."

cat <<EOF

==========================================
 Database password protection is ON
==========================================
  - MongoDB now refuses connections without a login.
  - Grace Treasury signs in with its own account (read/write on '$DB_NAME' only).
  - Same data as before: $(echo "$BEFORE" | awk '{print $1" users, "$2" transactions"}').
  - Passwords are in $APP_DIR/.env (MONGO_* lines). Keep .env backed up somewhere safe.
  - Safety backup from before the change: $SAFE_DIR/

Check any time:  ./enable-db-auth.sh --check
Turn it off:     ./enable-db-auth.sh --disable
EOF
