# Portas de host configuráveis (`ATLASFILE_PORT` e família)

**Status:** CONCLUÍDO em 2026-07-31 · **Sem bump** (parte da 1.0.0 interna —
decisão nominal do dono; chega ao usuário final na release re-emitida do
fechamento) · Branch `portas-configuraveis-env-flag` a partir da main
`7040a5a`. Subplano pós-Fase-4b, precedendo o plano do website.

## Contexto

Bindings literais no compose, zero mecanismo de override, conflito de porta =
beco sem saída ("free it before installing"), edição manual do compose não
durável (bundle da release o substitui). Benchmark de 8 produtos self-hosted
(fontes oficiais): interpolação `${VAR:-default}` no compose alimentada pelo
`.env` é o padrão dominante; convenção `<PRODUTO>_PORT` unânime; **nenhum**
faz auto-increment (quebra URL impressa/bookmark/webhook/idempotência);
consenso de não expor banco/índice no host (o Docker publica portas por cima
do firewall).

## Decisões (do plano aprovado)

- D1: `ATLASFILE_PORT` (8000, todas as interfaces — UI acessível da LAN por
  decisão); `OPENSEARCH_PORT`+`OPENSEARCH_BIND` (default **127.0.0.1**:9200 —
  mudança de comportamento declarada; restore de 1 linha); `DASHBOARDS_PORT`
  (5601, sem 127.0.0.1 — o SSO deriva `host:porta` para acesso remoto);
  **9600 removida** (zero consumidores; roadmap já registrava a intenção).
- D2: `--port N` / `-Port N` públicos com validação cedo; precedência
  `flag > env > .env > default`; portas secundárias só por env/`.env`.
- D3: conflito continua check-and-fail com o remédio na mensagem (nunca
  auto-increment).
- D4: persiste no `.env` só o que o usuário pediu (não pina default).
- D5: no Windows, o browser lê a porta real da instalação (`.env` via WSL).
- D6: sem bump; registro na própria `[1.0.0]` do CHANGELOG.

## O que os testes acharam (defeitos reais, corrigidos na fase)

1. **`af_env_lookup` com chave ausente matava o instalador em silêncio** —
   `set -euo pipefail` + rc do grep atravessando a atribuição. Pego pelo
   cenário de FORMA REAL da bancada (as funções isoladas passavam); correção
   `|| true` + comentário com a lição.
2. **A guarda de portas era cega no Linux sem root** — `lsof` não enxerga
   socket de outro usuário; no E2E da lima a porta 22 (sshd) atravessou a
   guarda e o erro só apareceu no bind do Docker. Nasceu `af_port_busy`:
   `ss` primeiro (vê tudo sem privilégio), `lsof` de fallback (macOS).
   Re-testado na VM: conflito barrado na fase 1, stack intocada.
3. **`set_env` vivia abaixo do gate de biblioteca** — invisível para a
   bancada; movida para a zona de funções.
4. Fixture: tar do macOS injeta AppleDouble (`._*`) no bundle — o validador
   da 4a recusou (funcionando como desenhado); fixtures usam
   `COPYFILE_DISABLE=1`.
5. Armadilhas das guardas exercitadas de novo: `esac` em comentário corta a
   fatia do `check_flags`; em dash em comentário novo do ps1 reprova o
   `check_ascii_only`. As duas reprovações foram da guarda fazendo o
   trabalho.

## Relatório de testes (entrega pedida nominalmente na aprovação)

| # | Suíte/canal | Resultado |
|---|---|---|
| T1 | `docker compose config` (4 casos) | ✔ defaults: 8000 + **127.0.0.1**:9200 + 5601, **9600 ausente**; overrides ATLASFILE_PORT/OPENSEARCH_BIND+PORT/DASHBOARDS_PORT renderizam |
| T2 | pytest backend | ✔ baseline 755 → **756 passed** (novo: porta do Dashboards no SSO; `test_dashboards_setup` intacto — só usa URL interna) |
| T3 | vitest frontend | ✔ **253/253** (nada funcional: UI é same-origin) |
| T4 | check_consistency | ✔ verde; reprovou 2 defeitos meus no caminho (esac em comentário; em dashes) — guardas vivas |
| T5 | bancada sh (local mac) | baseline **291/0** → vermelho **296/14** (14 = só grupos novos) → verde **310/0** (3 rodadas; a última com a guarda ss) |
| T6 | bancada win (VM prlctl/SYSTEM) | **235/0**, zero nomes da baseline 4b (228) perdidos |
| T7 | mutantes | **8/8 mortos pela guarda-alvo, zero colateral** — A: guarda re-hardcoded, painel re-hardcoded, persist no-op, SSO :5601 re-hardcoded; B: `\|\| true` removido (morte silenciosa); C: forward `--port` removido, validação removida, resolução do `.env` ignorada. Restaurações byte-exatas verificadas |
| T8 | E2E real (VM lima, release local da branch + imagem publicada 1.0.0) | ✔ install **1m11s** com painel inteiro em `:8090`; health 200 em 8090 e conexão recusada em 8000; `ss`: 9200 **só** em 127.0.0.1, 9600 inexistente; `ATLASFILE_PORT=8090` persistido; re-run idempotente (33s/36s) mantém a porta sem flag; **conflito real (sshd:22) barrado pela guarda** com stack intocada e `.env` preservado; `--uninstall --keep-data` limpo (5 removed, 0 containers, documentos intactos) |
| T9 | grep de bindings/docs | ✔ zero binding literal órfão; única menção a 9600 é o comentário da remoção |
| T10 | CI (7 jobs) | roda no push do PR (pós-ordem) |

## Arquivos

`docker-compose.yml` (interpolação + 127.0.0.1 + 9600 fora +
`DASHBOARDS_PUBLIC_PORT`), `.env.example` (seção de portas),
`install.sh` (`--port`, resolvedores `af_resolve_app_port`/`af_resolve_os_port`
/`af_valid_port`/`af_env_lookup`/`af_persist_port`/`af_port_busy`, guarda e
doctor com portas efetivas + mensagem-remédio, URLs todas derivadas,
`set_env` realocada), `install.ps1` (`-Port` + validação cedo + forward +
leitura da porta do `.env` via WSL para o browser),
`backend/app/{config,observability_sso}.py` (`dashboards_public_port`),
testes (`run.sh` +19 asserções, `win/run.ps1` +7, sso +1), docs
(INSTALL/READMEs/CLAUDE.md/CHANGELOG em `[1.0.0]`), cosmético
`chat.json` EN+PT sem porta fixa.

## Limitações declaradas

- O doctor sem root em Linux herda a visão do `ss` (completa) — mas em
  sistemas sem `ss` e sem privilégio o `lsof` segue parcial (fallback).
- `scripts/e2e_layout_scenarios.py:10` segue com URL fixa (cosmético,
  declarado fora do escopo).
- A imagem publicada 1.0.0 atual não contém o compose novo — o bundle da
  release re-emitida no fechamento é o veículo (o E2E provou com bundle da
  branch + imagem publicada, que é exatamente a combinação da re-emissão).
