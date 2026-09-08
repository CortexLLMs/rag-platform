#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# deploy.sh – Zero-downtime production deployment for RAG Platform
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh              # full deploy
#   DOMAIN_NAME=api.x.com ./deploy.sh   # override domain at runtime
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ───────────────────────────────────────────────────
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colour helpers (no-op if not a TTY) ──────────────────────
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; NC=''
fi

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v git    >/dev/null 2>&1 || warn "git not found – skipping pull"

[ -f "$PROJECT_DIR/.env" ] || fail ".env file not found – copy .env.example and fill in secrets"
[ -f "$PROJECT_DIR/Caddyfile" ] || fail "Caddyfile not found in project root"
[ -f "$PROJECT_DIR/docker-compose.prod.yml" ] || fail "docker-compose.prod.yml not found"

# ── Step 1: Pull latest code ────────────────────────────────
info "Pulling latest code from git..."
cd "$PROJECT_DIR"
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  git pull --ff-only origin main || warn "git pull failed – continuing with local files"
else
  warn "Not a git repo or git missing – skipping pull"
fi

# ── Step 2: Build images ────────────────────────────────────
info "Building Docker images..."
docker compose $COMPOSE_FILES build --no-cache

# ── Step 3: Rolling restart (no downtime) ────────────────────
info "Restarting services..."
docker compose $COMPOSE_FILES up -d --remove-orphans

# ── Step 4: Wait for health ─────────────────────────────────
info "Waiting for services to become healthy..."
sleep 5
if docker compose $COMPOSE_FILES ps | grep -q "unhealthy\|starting"; then
  warn "Some services are still starting – check 'docker compose ps' in a moment"
else
  info "All services are up."
fi

# ── Step 5: Clean up dangling images ────────────────────────
info "Pruning dangling images..."
docker image prune -f

# ── Done ─────────────────────────────────────────────────────
DOMAIN="${DOMAIN_NAME:-localhost}"
info "Deployment complete – https://${DOMAIN}"
