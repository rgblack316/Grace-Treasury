#!/usr/bin/env bash

set -euo pipefail

# ============================================================
# Grace Treasury - Initial Installation
#
# Fresh Ubuntu/Debian installation helper.
# Installs required host dependencies, clones the repository,
# creates .env, and starts the Docker Compose stack.
#
# Run as your normal user (NOT root). The script uses sudo
# only where it is needed:
#     ./install.sh
# ============================================================

REPO_URL="${REPO_URL:-https://github.com/rgblack316/Grace-Treasury.git}"
# Leave empty by default; it is resolved to the real user's home below so that
# running via sudo does not accidentally install into /root.
INSTALL_DIR="${INSTALL_DIR:-}"

log() { echo "[Grace Treasury] $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

if [ "${EUID}" -eq 0 ]; then
  TARGET_USER="${SUDO_USER:-root}"
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
else
  TARGET_USER="$(id -un)"
  TARGET_HOME="$HOME"
fi

if [ "$TARGET_USER" = "root" ]; then
  fail "Run this script as your normal user, not as root. It will use sudo when needed."
fi

# Resolve the install directory against the real user's home (handles sudo).
if [ -z "${INSTALL_DIR}" ]; then
  INSTALL_DIR="$TARGET_HOME/grace-treasury"
fi

if ! command -v sudo >/dev/null 2>&1; then
  fail "sudo is required. Install it first with: apt-get update && apt-get install -y sudo"
fi

sudo -v

if ! command -v apt-get >/dev/null 2>&1; then
  fail "This installer currently supports Ubuntu/Debian systems using apt."
fi

if [ -r /etc/os-release ]; then
  . /etc/os-release
else
  fail "Cannot determine the operating system."
fi

case "${ID:-}" in
  ubuntu|debian)
    ;;
  *)
    fail "Unsupported OS: ${PRETTY_NAME:-unknown}. This installer supports Ubuntu and Debian."
    ;;
esac

if [ "${ID}" = "ubuntu" ] && [ "${VERSION_ID%%.*}" -lt 22 ]; then
  fail "Ubuntu 22.04 or newer is required."
fi

if [ "${ID}" = "debian" ] && [ "${VERSION_ID%%.*}" -lt 12 ]; then
  fail "Debian 12 or newer is required."
fi

echo
echo "=========================================="
echo " Grace Treasury - Initial Installation"
echo "=========================================="
echo
log "Installing/checking required host packages..."

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  git \
  openssl \
  gnupg

install_docker_repo() {
  local arch codename repo_url
  arch="$(dpkg --print-architecture)"

  if [ "$ID" = "ubuntu" ]; then
    codename="${VERSION_CODENAME:-$(. /etc/os-release && echo "$VERSION_CODENAME")}"
  else
    codename="${VERSION_CODENAME:-$(lsb_release -cs 2>/dev/null || echo bookworm)}"
  fi

  sudo install -m 0755 -d /etc/apt/keyrings
  sudo rm -f /etc/apt/keyrings/docker.asc
  sudo curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc

  repo_url="https://download.docker.com/linux/${ID}"
  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] ${repo_url} ${codename} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update
}

# Docker Engine
if ! command -v docker >/dev/null 2>&1; then
  log "Docker is not installed. Installing Docker Engine and Compose..."
  install_docker_repo
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
else
  log "Docker is already installed: $(docker --version)"

  # Prefer the modern Compose plugin. If it is missing, install it without
  # replacing an existing Docker installation.
  if ! docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin is missing. Installing it..."
    if ! sudo apt-get install -y docker-compose-plugin >/dev/null 2>&1; then
      log "Compose plugin was not available from the current repositories; adding Docker's repository."
      install_docker_repo
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin
    fi
  fi
fi

sudo systemctl enable --now docker

# Allow the normal user to run Docker without sudo after the next login.
if ! getent group docker >/dev/null 2>&1; then
  sudo groupadd docker
fi
sudo usermod -aG docker "$TARGET_USER" || true

# The current shell may not yet have the newly-added group. Use sudo for Docker
# commands when necessary, otherwise use the user's normal Docker access.
docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

if ! docker_cmd compose version >/dev/null 2>&1; then
  fail "Docker Compose is still unavailable after installation."
fi

# ------------------------------------------------------------
# Clone repository
# ------------------------------------------------------------

if [ -e "$INSTALL_DIR" ]; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    fail "A Grace Treasury Git repository already exists at $INSTALL_DIR. Use upgrade.sh for an existing installation."
  else
    fail "The installation directory already exists and is not a Git repository: $INSTALL_DIR"
  fi
fi

log "Cloning Grace Treasury into $INSTALL_DIR ..."
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

# ------------------------------------------------------------
# Create environment file
# ------------------------------------------------------------

if [ ! -f .env ]; then
  log "Creating .env..."
  cp env.example .env

  JWT_SECRET="$(openssl rand -hex 32)"
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env

  # The React frontend uses the same-origin /api path, so CORS_ORIGINS only
  # needs to list the browser origin(s) allowed to call the API. localhost is a
  # safe default for a first-run installation; change it for a remote server.
  sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost:8080|' .env

  log ".env created with a generated JWT secret."
else
  log ".env already exists. Leaving it unchanged."
fi

# ------------------------------------------------------------
# Create backup directory
# ------------------------------------------------------------

mkdir -p backups

# If the script was run via sudo, make sure the normal user owns everything.
if [ "${EUID}" -eq 0 ]; then
  chown -R "$TARGET_USER":"$TARGET_USER" "$INSTALL_DIR"
fi

# ------------------------------------------------------------
# Build and start
# ------------------------------------------------------------

log "Building and starting Grace Treasury..."
docker_cmd compose up -d --build

# ------------------------------------------------------------
# Show status
# ------------------------------------------------------------

echo
echo "=========================================="
echo " Installation complete"
echo "=========================================="
echo
echo "Docker:  $(docker_cmd --version)"
echo "Compose: $(docker_cmd compose version)"
echo
docker_cmd compose ps

echo
echo "Grace Treasury should now be available at:"
echo "    http://localhost:8080"
echo
echo "For a remote server, replace localhost with the server's IP address or hostname,"
echo "and update CORS_ORIGINS in $INSTALL_DIR/.env to match, then run: docker compose up -d --build"
echo
echo "IMPORTANT: The user '$TARGET_USER' was added to the docker group."
echo "Log out and back in (or start a new SSH session) before running Docker without sudo."
echo
