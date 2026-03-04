#!/usr/bin/env bash
# Run backend and frontend tests. Exit 1 if any fail.
# Backend: usa backend/.venv se existir, senão python3. Frontend: npm run test (vitest).

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
cd "$ROOT"

echo ""
echo "=== Frontend tests (vitest) ==="
cd frontend && npm run test
cd "$ROOT"

echo ""
echo "=== All tests passed ==="
