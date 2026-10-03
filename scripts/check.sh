#!/usr/bin/env bash
# Lint and test everything in containers (no local Node or Python setup needed).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Backend: ruff + pytest (Docker 'test' stage)"
docker build --target test -t famtree-test .

echo "== Frontend: typecheck, lint, unit tests"
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e NPM_CONFIG_UPDATE_NOTIFIER=false \
  -v "$PWD/frontend":/app -w /app node:22-alpine \
  sh -c "npm ci --no-audit --no-fund && npx tsc --noEmit && npx eslint src test && npx vitest run"

echo "All checks passed."
