# Auto-ingest + widget único de processamento — fim dos botões "Processar INBOX" e "Reconciliar INDEX" (v0.50.0)

**Concluído em 2026-07-25.** Origem: sequência de perguntas do usuário no teste da
v0.49.0 — "por que dois mecanismos de processando?", "por que inline no card E
widget?", "se o widget aparece sozinho, pra que o botão?".

## Fatos que fundaram o plano (verificados no código/ambiente)

- `watcher.py` era **código morto**: zero chamadores desde sempre — auto-ingest de
  filesystem NÃO existia; o botão era o único caminho para drops via pasta.
  `auto_scan_on_startup` era outra constante órfã (removida).
- Auto-reconcile **já rodava** (600s, todos os projetos, mesmo escopo do botão) —
  a premissa "sistema sempre reconciliado" já era verdade; o CTA era redundante.
- **Medição decisiva no container**: eventos inotify ATRAVESSAM o bind mount
  VirtioFS do Docker Desktop, mas a criação de arquivo no host chega como
  `modified` — o handler antigo (`on_created`) perderia todos os drops do host.
- O endpoint de scan tinha corrida check→set no flag `running` (fechada com lock).

## Decisões

- **Auto-ingest** (`app/auto_ingest.py`): watcher por inbox (escuta ampla) marca o
  projeto sujo → quiescência de 4s → scan (mesmo núcleo do endpoint, extraído em
  `_run_inbox_scan` + `_ingest_run_lock`). Guarda de estabilidade: arquivo com
  mtime < 5s não é ingerido (OneDrive/sync progressivo). Sweep de 60s cobre
  inotify mudo (WSL2), arquivos caídos com a API desligada e projetos criados em
  runtime. Anti-loop: sobra de falha (arquivo fica na inbox) só re-tenta se
  (size, mtime) mudar. Parâmetros com base medida — docstring do módulo.
  `AUTO_INGEST_ENABLED` desliga (manutenção).
- **Bug real pego por teste**: candidato imaturo disparava scan e era registrado
  como sobra → nunca mais ingerido ao amadurecer. Corrigido separando
  "pronto" (dispara) de "pendente" (mantém sujo) e nunca registrando imaturo
  como sobra.
- **Widget único** (GlobalDropPortal): superfície única de processamento — fila
  de upload E fase real do scan via SSE (antes: spinner genérico no widget +
  monitor inline no card do Painel narrando a mesma fase). Aparece sozinho em
  runs do auto-ingest, com toast de resultado ao fim. 409 do scan pós-upload
  (INGEST_IN_PROGRESS) virou info honesta ("auto-ingest processa em seguida"),
  não erro. `InboxScanCard` deletado.
- **Reconcile sem CTA**: fica a linha "Última reconciliação" + escape hatch
  discreto "Reconciliar agora" (mesma semântica de escopo da v0.44.0 nos
  titles). Divergência aceita pelo usuário: run automático NÃO pede autorização
  (operações idempotentes/recuperáveis, já rodavam silenciosas) — só ANUNCIA
  quando corrigiu algo (`fixes > 0`); run manual sempre anuncia.

## Validações

- Backend 681/681 (7 novos em `test_auto_ingest.py`: boot sweep, quiescência,
  estabilidade/maturação, anti-loop de sobra, lock ocupado re-agenda, descoberta
  de projeto em runtime, dotfile ignorado).
- Frontend 249/249 (novo: widget aparece sozinho em run automático com fase,
  progresso, arquivo e projeto; testes do botão de reconcile reescritos para o
  escape hatch preservando as asserções de escopo) + tsc limpo.
- E2E vivo na stack dev (OneDrive real): `cp` de arquivo na `_INBOX_DROP` pelo
  host → widget aparece sem clique → documento processado.
