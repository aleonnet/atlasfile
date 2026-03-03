# Regras de arquivamento e retencao

## Estados

- `active`: item em uso operacional.
- `hold`: bloqueado por obrigacao legal/compliance.
- `cold_archive`: historico de baixa recorrencia.
- `eligible_disposal`: apto para descarte conforme politica.

## Regras basicas

1. Documentos em triagem nao entram em descarte.
2. Itens com `hold=true` nunca sao descartados automaticamente.
3. Descarte exige dupla aprovacao (owner + governance).
4. Toda mudanca de estado registra evento em log e indice.

## SLA sugerido

- Triagem pendente: <= 48h
- Atualizacao de indice apos decisao: <= 5 min (p95)
- Revisao de retencao: mensal
