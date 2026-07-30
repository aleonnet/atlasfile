#!/usr/bin/env bash
# Guarda de reprodutibilidade (Fase 1 do plano de distribuição).
# Roda IGUAL no CI (job `pins`) e localmente: bash scripts/check_pins.sh
#
# FATO que a motivou (v0.56.5): 9 deps do backend com piso `>=` sem teto e
# `lucide-react: "latest"` faziam o artefato instalado divergir do testado.
set -u
cd "$(dirname "$0")/.."

fail=0

# 1) requirements do backend (produto e extra opcional): tudo pinado com `==`,
#    sem ranges. O lock e o requirements-dev ficam de fora: o lock é gerado
#    (pip freeze) e o dev aponta para ele com ferramentas de teste em piso.
for req in backend/requirements.txt backend/requirements-local-embeddings.txt; do
  while IFS= read -r line; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    if printf '%s' "$line" | grep -qE '>=|<=|~=|!=|[<>]'; then
      echo "FAIL $req: range aberto: $line"
      fail=1
    elif ! printf '%s' "$line" | grep -q '=='; then
      echo "FAIL $req: sem pin ==: $line"
      fail=1
    fi
  done < "$req"
done

# 2) Nenhum package.json com dependência em "latest" ou "*".
for pj in $(git ls-files '*package.json'); do
  hits="$(grep -nE '":[[:space:]]*"(latest|\*)"' "$pj" || true)"
  if [ -n "$hits" ]; then
    echo "FAIL $pj: dependência sem versão (latest/*):"
    echo "$hits"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "OK: pins fechados (requirements.txt so ==, package.json sem latest/*)"
fi
exit "$fail"
