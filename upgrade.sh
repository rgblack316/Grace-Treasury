#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# Grace Treasury - Upgrade Script
#
# Safely updates an existing installation without deleting or
# recreating the MongoDB named volume. Refuses to overwrite
# uncommitted/local Git work or a diverged local branch.
#
# Run from any directory (defaults to ~/grace-treasury), or set
# APP_DIR to point at your installation:
#     ./upgrade.sh
#     APP_DIR=/opt/grace-treasury ./upgrade.sh
# ============================================================

APP_DIR="${APP_DIR:-$HOME/grace-treasury}"
BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
DB_BACKUP_DIR="$BACKUP_DIR/pre-upgrade-$TIMESTAMP"

log() { echo "[Grace Treasury] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

if [ ! -d "$APP_DIR/.git" ]; then
  fail "Grace Treasury Git repository not found: $APP_DIR (set APP_DIR to your install path)"
fi

cd "$APP_DIR"

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
# Refuse unsafe Git states
# ------------------------------------------------------------

if [ -n "$(git status --porcelain)" ]; then
  echo
  echo "Local Git changes were detected:"
  git status --short
  echo
  echo "Upgrade cancelled. Commit, stash, or otherwise resolve these changes first."
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

mkdir -p "$DB_BACKUP_DIR"

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

# ------------------------------------------------------------
# Fast-forward only
# ------------------------------------------------------------

log "Pulling latest code from GitHub..."
git pull --ff-only

# ------------------------------------------------------------
# Rebuild and restart
# ------------------------------------------------------------

log "Rebuilding Grace Treasury..."
docker_cmd compose up -d --build

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
