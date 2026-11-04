#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$repo_root/backend"
web_dir="$repo_root/frontend/web"
desktop_dir="$repo_root/frontend/desktop"
artifacts_dir="$repo_root/build/dist"

echo "=== VibeSolver build (Linux) ==="

(
  cd "$backend_dir"
  uv sync
  uv run pytest
  uv run ruff check .
  uv run mypy app
)

(
  cd "$web_dir"
  npm ci
  npm run lint
  npm run test
  npm run build
)

(
  cd "$desktop_dir"
  npm ci
  npm run build
  node scripts/copy-web.mjs
  npx electron-builder --linux AppImage
)

mkdir -p "$artifacts_dir"
cp "$desktop_dir"/release/*.AppImage "$artifacts_dir/"

echo "Build finished."
echo "Artifact: $artifacts_dir"
