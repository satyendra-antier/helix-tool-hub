#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[tool-hub]${NC} $*"; }
warn() { echo -e "${YELLOW}[tool-hub]${NC} $*"; }
err()  { echo -e "${RED}[tool-hub]${NC} $*" >&2; }

if ! command -v docker &>/dev/null; then
  err "Docker is required but not installed."
  exit 1
fi

if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
  err "Docker Compose is required but not installed."
  exit 1
fi

COMPOSE_CMD="docker compose"
if ! docker compose version &>/dev/null; then
  COMPOSE_CMD="docker-compose"
fi

# Isolated project name — does not touch crm-* or other stacks
COMPOSE_PROJECT="toolhub"
COMPOSE_FILE="infra/docker-compose.yml"

if [[ ! -f .env ]]; then
  warn ".env not found — copying from .env.example"
  cp .env.example .env
  warn "Edit .env and add your API keys (OPENAI_API_KEY, GITHUB_TOKEN, etc.)"
fi

# shellcheck disable=SC1091
source .env 2>/dev/null || true
WEB_PORT="${WEB_HOST_PORT:-3200}"
VIDEO_PORT="${VIDEO_SCRAPER_HOST_PORT:-8101}"
MARKET_PORT="${MARKET_DEPTH_HOST_PORT:-8102}"
LEADS_PORT="${LEAD_INTELLIGENCE_HOST_PORT:-8103}"
BUILD_PORT="${BUILD_READINESS_HOST_PORT:-8104}"

compose() {
  $COMPOSE_CMD -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" --env-file .env "$@"
}

MODE="${1:-up}"

case "$MODE" in
  up|start)
    log "Building and starting Tool Hub (project: $COMPOSE_PROJECT)..."
    log "Host ports — dashboard:$WEB_PORT video:$VIDEO_PORT market:$MARKET_PORT leads:$LEADS_PORT build:$BUILD_PORT"
    compose up --build -d
    log "Waiting for services..."
    sleep 10
    log ""
    log "Tool Hub is running (CRM stack on 3000 untouched):"
    log "  Dashboard:  http://localhost:$WEB_PORT"
    log "  Video API:  http://localhost:$VIDEO_PORT/docs"
    log "  Market API: http://localhost:$MARKET_PORT/docs"
    log "  Leads API:  http://localhost:$LEADS_PORT/docs"
    log "  Build API:  http://localhost:$BUILD_PORT/docs"
    log ""
    log "View logs:  ./start.sh logs"
    log "Stop:       ./start.sh down  (only stops toolhub project)"
    ;;
  down|stop)
    log "Stopping Tool Hub stack (project: $COMPOSE_PROJECT only)..."
    compose down
    ;;
  logs)
    compose logs -f
    ;;
  restart)
    compose restart
    ;;
  build)
    compose build
    ;;
  *)
    echo "Usage: ./start.sh [up|down|logs|restart|build]"
    exit 1
    ;;
esac
