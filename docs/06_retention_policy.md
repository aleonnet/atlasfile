# Regras de arquivamento e retencao

## Status na 0.7.0

Este documento descreve diretrizes e estados desejados. Ele nao representa uma automacao completa ja implementada no produto.

## Estados

- `active`: item em uso operacional.
- `hold`: bloqueado por obrigacao legal/compliance.
- `cold_archive`: historico de baixa recorrencia.
- `eligible_disposal`: apto para descarte conforme politica.

## Regras basicas

1. Documentos em triagem nao entram em descarte.
2. Itens com `hold=true` nunca sao descartados automaticamente.
3. Descarte exige dupla aprovacao (owner + governance).
4. Toda mudanca de estado deve registrar evento em log e indice quando esse fluxo for operacionalizado.

## SLA sugerido

- Triagem pendente: <= 48h
- Atualizacao de indice apos decisao: <= 5 min (p95)
- Revisao de retencao: mensal
