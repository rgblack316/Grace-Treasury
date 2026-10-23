#!/bin/sh
# Start as root only long enough to give the app user its backup folder, then drop privileges.
set -e
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
mkdir -p "$BACKUP_DIR"
# Own the folder and the app's own backup files (not other things an admin put there, e.g. pre-upgrade dumps).
chown app:app "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
find "$BACKUP_DIR" -maxdepth 1 -name 'church-treasury-backup-*.json' -exec chown app:app {} + -exec chmod 600 {} + 2>/dev/null || true
exec setpriv --reuid=app --regid=app --init-groups "$@"
