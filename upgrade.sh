#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# Grace Treasury - Upgrade Script
#
# Safely updates an existing installation without deleting or
# recreating the MongoDB named volume. Refuses to overwrite
# uncommitted/local Git work or a diverged local branch.
#
# Run it from your install folder (with or without sudo):
#     cd ~/grace-treasury && ./upgrade.sh
# It finds the install it lives in. You can also point it elsewhere:
#     APP_DIR=/opt/grace-treasury ./upgrade.sh
# ============================================================

log() { echo "[Grace Treasury] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

# Where is the install? 1) APP_DIR if given, 2) the folder this script is in (it ships inside
# the repository), 3) the real user's ~/grace-treasury (install.sh's default; correct under
# sudo, where $HOME is /root), 4) this user's ~/grace-treasury.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_USER="${SUDO_USER:-$(id -un)}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
REAL_HOME="${REAL_HOME:-$HOME}"
if [ -z "${APP_DIR:-}" ]; then
  if [ -d "$SCRIPT_DIR/.git" ] && [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    APP_DIR="$SCRIPT_DIR"
  else
    APP_DIR="$REAL_HOME/grace-treasury"
  fi
fi

if [ ! -d "$APP_DIR/.git" ]; then
  fail "Grace Treasury wasn't found at $APP_DIR.
       Run this script from inside your install folder (cd /path/to/grace-treasury && ./upgrade.sh),
       or tell it where the install is: APP_DIR=/path/to/grace-treasury ./upgrade.sh"
fi
APP_DIR="$(cd "$APP_DIR" && pwd)"

# Git refuses to work as root in a folder owned by another user ("dubious ownership"),
# and files it pulled would end up owned by root. So when this runs as root (sudo or a
# root login), run Git as the folder's owner. Docker commands still run as root.
REPO_OWNER="$(stat -c %U "$APP_DIR")"
REPO_OWNER_HOME="$(getent passwd "$REPO_OWNER" | cut -d: -f6)"
git() {
  if [ "${EUID}" -eq 0 ] && [ "$REPO_OWNER" != "root" ]; then
    if command -v runuser >/dev/null 2>&1; then
      runuser -u "$REPO_OWNER" -- env HOME="$REPO_OWNER_HOME" git "$@"
    else
      sudo -u "$REPO_OWNER" -H git "$@"
    fi
  else
    command git "$@"
  fi
}

BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
DB_BACKUP_DIR="$BACKUP_DIR/pre-upgrade-$TIMESTAMP"

cd "$APP_DIR"
log "Install folder: $APP_DIR"

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed. Run install.sh on a fresh system or install Docker manually."
fi

# Use sudo automatically if the current shell has not yet picked up the docker group.
docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

if ! docker_cmd compose version >/dev/null 2>&1; then
  fail "Docker Compose is not available."
fi

if [ ! -f .env ]; then
  fail "No .env file exists in $APP_DIR. Refusing to continue."
fi

echo
echo "=========================================="
echo " Grace Treasury - Upgrade"
echo "=========================================="
echo

echo "Current Git revision:"
git rev-parse --short HEAD

echo
echo "Current containers:"
docker_cmd compose ps

# ------------------------------------------------------------
# Refuse unsafe Git states (changes inside backups/ are ignored)
# ------------------------------------------------------------

if [ -n "$(git status --porcelain -- ':!backups')" ]; then
  echo
  echo "Local Git changes were detected:"
  git status --short -- ':!backups'
  echo
  if git status --porcelain -- ':!backups' | grep -q 'docker-compose.override.yml'; then
    echo "A docker-compose.override.yml file is present. If it was only a temporary test, remove it"
    echo "(rm docker-compose.override.yml) and run this again."
  fi
  echo "Upgrade cancelled. Commit, stash, or otherwise resolve these changes first."
  echo "(Changes inside the backups/ folder are ignored and do not block upgrades.)"
  exit 1
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ -z "$CURRENT_BRANCH" ]; then
  fail "The repository is in detached HEAD state. Refusing to upgrade automatically."
fi

# ------------------------------------------------------------
# Fetch remote metadata without changing working files
# ------------------------------------------------------------

log "Checking GitHub for updates..."
git fetch --prune origin

REMOTE_REF="origin/$CURRENT_BRANCH"
if ! git show-ref --verify --quiet "refs/remotes/$REMOTE_REF"; then
  fail "No matching remote branch '$REMOTE_REF' was found."
fi

AHEAD="$(git rev-list --count "$REMOTE_REF..HEAD")"
BEHIND="$(git rev-list --count "HEAD..$REMOTE_REF")"

if [ "$AHEAD" -gt 0 ] && [ "$BEHIND" -gt 0 ]; then
  fail "Local branch and GitHub have diverged. No changes were made. Resolve the Git history manually."
fi

if [ "$AHEAD" -gt 0 ]; then
  fail "Local branch contains $AHEAD commit(s) not on GitHub. No changes were made."
fi

if [ "$BEHIND" -eq 0 ]; then
  log "Grace Treasury is already up to date. No rebuild is necessary."
  echo
  echo "Current revision: $(git rev-parse --short HEAD)"
  echo
  docker_cmd compose ps
  exit 0
fi

echo "GitHub has $BEHIND new commit(s)."

# ------------------------------------------------------------
# Back up the database before changing application code
# ------------------------------------------------------------

# The backend writes nightly backups into ./backups as its own user (UID 1000) and keeps
# the folder private. If this user can't write there, reclaim it with sudo so this backup
# can be created; the backend takes the folder back when it restarts.
if [ ! -w "$BACKUP_DIR" ] 2>/dev/null || ! mkdir -p "$DB_BACKUP_DIR" 2>/dev/null; then
  log "The backups/ folder is not writable by $(id -un) (likely created by Docker as root). Fixing ownership..."
  sudo mkdir -p "$DB_BACKUP_DIR"
  sudo chown -R "$(id -u):$(id -g)" "$BACKUP_DIR"
fi

# Older installs have no SETUP_CODE; add one so a wiped/empty database can't be claimed by
# a stranger. It is only used before the first Administrator exists.
if ! grep -qE '^SETUP_CODE=.+' .env; then
  raw="$(head -c 1024 /dev/urandom | LC_ALL=C tr -dc 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789' | cut -c1-16)"
  printf '\n# One-time code for creating the first Administrator\nSETUP_CODE=%s\n' "${raw:0:4}-${raw:4:4}-${raw:8:4}-${raw:12:4}" >> .env
  log "Added a SETUP_CODE to .env (only needed if the database is ever empty)."
fi

# Read DB_NAME from .env without sourcing the file as shell code.
DB_NAME="$(awk -F= '$1 == "DB_NAME" {print substr($0, index($0,"=")+1); exit}' .env)"
DB_NAME="${DB_NAME:-church_treasury}"

if docker_cmd compose ps --services --filter "status=running" | grep -q '^mongo$'; then
  log "Creating pre-upgrade MongoDB backup ($DB_NAME)..."

  docker_cmd compose exec -T mongo \
    mongodump \
    --db "$DB_NAME" \
    --archive \
    --gzip \
    > "$DB_BACKUP_DIR/mongodb.archive.gz"

  if [ ! -s "$DB_BACKUP_DIR/mongodb.archive.gz" ]; then
    fail "The database backup is empty. Upgrade cancelled."
  fi

  echo "Database backup created:"
  echo "    $DB_BACKUP_DIR/mongodb.archive.gz"
else
  echo
  echo "WARNING: MongoDB is not currently running, so a live database backup cannot be created."
  echo "Upgrade cancelled to avoid proceeding without the safety backup."
  exit 1
fi

# Back up .env separately as an additional safety measure.
cp -p .env "$DB_BACKUP_DIR/.env"
# The dump and .env copy hold everything (incl. secrets): readable by the owner only.
chmod 700 "$DB_BACKUP_DIR"
chmod 600 "$DB_BACKUP_DIR"/* 2>/dev/null || true

# ------------------------------------------------------------
# Fast-forward only
# ------------------------------------------------------------

log "Pulling latest code from GitHub..."
git pull --ff-only

# ------------------------------------------------------------
# Rebuild and restart
# ------------------------------------------------------------

log "Rebuilding Grace Treasury..."
if ! docker_cmd compose up -d --build; then
  echo
  echo "The rebuild/restart failed. If the message above says a network \"needs to be recreated\","
  echo "run this (your data is kept; 'down' without -v doesn't remove the database volume):"
  echo "    docker compose down && docker compose up -d"
  echo "Database backup from before this upgrade: $DB_BACKUP_DIR/mongodb.archive.gz"
  exit 1
fi

# ------------------------------------------------------------
# Wait for containers and report status
# ------------------------------------------------------------

log "Waiting for containers to initialize..."
sleep 5

echo
echo "=========================================="
echo " Upgrade complete"
echo "=========================================="
echo
echo "Git revision:"
git rev-parse --short HEAD

echo
echo "Container status:"
docker_cmd compose ps

echo
echo "Database backup:"
echo "    $DB_BACKUP_DIR/mongodb.archive.gz"
echo "Environment backup:"
echo "    $DB_BACKUP_DIR/.env"
echo
echo "To restore this pre-upgrade backup if needed:"
echo "    gunzip -c \"$DB_BACKUP_DIR/mongodb.archive.gz\" | docker compose exec -T mongo mongorestore --archive --gzip --drop"
echo
echo "MongoDB data remains in the existing Docker volume; this script does not remove it."
echo
echo "Grace Treasury should now be available."
echo
