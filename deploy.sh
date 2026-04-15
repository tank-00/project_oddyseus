#!/usr/bin/env bash
# deploy.sh — build, push, and deploy all Shield services to Railway.
#
# Prerequisites:
#   - Docker + buildx
#   - Railway CLI (`npm i -g @railway/cli` then `railway login`)
#   - DOCKER_REGISTRY env var set to your container registry (e.g. ghcr.io/yourorg)
#
# Usage:
#   export DOCKER_REGISTRY=ghcr.io/yourorg/shield
#   ./deploy.sh
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REGISTRY="${DOCKER_REGISTRY:-}"
TAG="${DOCKER_TAG:-latest}"
SERVICES=("gateway" "policy" "registry")

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "▶  $*"; }
die()  { echo "✗  $*" >&2; exit 1; }
ok()   { echo "✓  $*"; }

# ── Preflight checks ─────────────────────────────────────────────────────────
command -v docker   >/dev/null 2>&1 || die "docker not found"
command -v railway  >/dev/null 2>&1 || die "railway CLI not found — run: npm i -g @railway/cli"

if [[ -z "$REGISTRY" ]]; then
  die "DOCKER_REGISTRY is not set. Example: export DOCKER_REGISTRY=ghcr.io/yourorg/shield"
fi

log "Checking Railway authentication…"
railway whoami >/dev/null 2>&1 || die "Not logged in to Railway. Run: railway login"
ok "Railway authenticated"

# ── Build & push images ───────────────────────────────────────────────────────
for svc in "${SERVICES[@]}"; do
  IMAGE="${REGISTRY}/${svc}:${TAG}"
  log "Building ${svc} → ${IMAGE}"
  docker buildx build \
    --platform linux/amd64 \
    --tag "${IMAGE}" \
    --push \
    "./${svc}"
  ok "Pushed ${IMAGE}"
done

# ── Deploy to Railway ─────────────────────────────────────────────────────────
log "Deploying to Railway (railway up)…"
railway up --detach
ok "Deployment triggered"

# ── Print public URL ─────────────────────────────────────────────────────────
log "Fetching public gateway URL…"
GATEWAY_URL=$(railway domain 2>/dev/null || echo "")
if [[ -n "$GATEWAY_URL" ]]; then
  ok "Gateway URL: https://${GATEWAY_URL}"
else
  echo "ℹ  Could not retrieve domain automatically."
  echo "   Run 'railway domain' or check the Railway dashboard for the public URL."
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Deployment complete."
echo "  Gateway: ${GATEWAY_URL:+https://}${GATEWAY_URL:-<see Railway dashboard>}"
echo "═══════════════════════════════════════════════════"
