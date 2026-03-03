#!/usr/bin/env bash
# Run backend and frontend tests. Exit 1 if any fail.
# Use before: docker compose up -d --build

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== Backend tests (pytest) ==="
cd backend
if [ -x .venv/bin/python ]; then
  .venv/bin/python -m pytest tests/ -v
else
  python3 -m pytest tests/ -v
fi
cd ..

echo ""
echo "=== Frontend tests (vitest) ==="
cd frontend
npm run test
cd ..

echo ""
echo "=== All tests passed ==="
