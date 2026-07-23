# projects_root_self_healing_v0400 — self-healing da raiz de projetos esvaziada (v0.40.0 → v0.40.2)

Concluído em 2026-07-23, branch `feature/taxonomy-essential-types-v0390` (commits `71da2da`, `4717339`, `7cc01d3`).

## Problema

O teste destrutivo do usuário (deletar `PROJECTS_HOST_ROOT` com o stack no ar) revelou que a resiliência da v0.38 cobria só metade do cenário: a deleção da pasta host sob bind mount se manifesta de **dois modos distintos** no Docker/macOS (VirtioFS):

1. **Mount fantasma** (`emptied`): o container continua vendo `/projects` como diretório saudável e VAZIO — a sonda da v0.38 aprovava, nenhum aviso aparecia, e qualquer escrita iria para um inode deletado (perda silenciosa).
2. **Mount quebrado** (`unavailable`): `Operation not permitted` no listdir — a sonda reprovava, mas o próprio `/api/setup/status` respondia 503 via handler de OSError, então a UI nunca recebia o estado e nenhuma recuperação era oferecida.

Além disso, a recuperação exigia passos manuais do usuário (mkdir + docker compose restart), o que ele rejeitou: "o sistema deve ser self healing".

## Fatos validados com probes reais (Docker Desktop/macOS)

- `docker run`/`docker restart` com a pasta host do bind ausente **recria a pasta** no host com o dono correto (`alessandro`, não root) e o mount volta funcional (arquivo escrito no container aparece no host).
- Um container **não** consegue re-vincular o próprio mount sem reinício (limite do runtime) — mas pode se encerrar de propósito e deixar a política de restart fazer o resto.

## Solução (v0.40.0)

- **Marcador `.atlasfile_root`** gravado no startup (único momento em que o mount está garantidamente vinculado ao host). Estado novo em `projects_root.py`: `projects_root_state(has_prior_data)` → `ok` | `unavailable` | `emptied`. `emptied` = raiz saudável SEM marcador + evidência de vida anterior (índice de busca com documentos); instância nova de verdade continua `ok` (wizard normal).
- **`POST /api/system/restart`**: encerra a API graciosamente (SIGTERM em si mesma via `threading.Timer`); política `restart: unless-stopped` adicionada aos 5 serviços do compose religa o container.
- **Modal de recuperação** (`RootRecoveryModal`): explica o estado, bloqueia nada além do necessário e oferece **[Recriar pasta e reiniciar]** (restart → poll de health → reconcile global limpa órfãos → reload no onboarding) e **[Restaurei manualmente — revalidar]**.
- **Guard anti-limbo**: `upload`, `scan` e `initialize` retornam `503 PROJECTS_ROOT_EMPTIED` enquanto o estado persistir; onboarding nunca é sugerido sobre mount fantasma.

## Correção de campo (v0.40.1)

- `/api/setup/status` **nunca mais 503**: com EPERM no listdir ele reporta `projects_root_state: "unavailable"` (era o que impedia o modal de aparecer no modo mount-quebrado).
- Modal abre nos **dois** estados (`emptied` e `unavailable`) — a cura é a mesma. Banner passivo da v0.38 removido (mensagem manual morreu; o botão faz o trabalho).

## Acabamento (v0.40.2)

- 409 benigno da triagem (`TRIAGE_ALREADY_DECIDED`/`TRIAGE_DECISION_IN_PROGRESS`, card desatualizado ou duplo clique) vira mensagem informativa localizada + refetch da fila — não mais "Falha ao registrar decisão"; erros reais mostram a mensagem específica da API.
- `ModalActions` com `flex-wrap` (botões longos não vazam do painel).
- Default de modelo custo-consciente: instância nova seleciona `openai/gpt-5.1` para agente e triagem (preferência explícita → primeiro openai → primeiro da lista); backend `LLMPolicy.model` gpt-4.1 → gpt-5.1; seleção salva do usuário nunca é sobrescrita.

## Arquivos principais

`backend/app/projects_root.py`, `backend/app/main.py` (setup_status, guards, `/api/system/restart`, handler OSError), `docker-compose.yml` (restart policy), `frontend/src/features/recovery/RootRecoveryModal.tsx`, `frontend/src/App.tsx`, `frontend/src/contexts/SettingsContext.tsx`, `frontend/src/components/ui/modal-shell.tsx`, i18n ×2 (`painel.json`, `errors.json`), `backend/tests/unit/test_projects_root_resilience.py` (7 testes novos), `frontend/src/features/recovery/RootRecoveryModal.test.tsx`, `frontend/src/contexts/SettingsContext.test.tsx`, `App.test.tsx`.

## Decisões e limites

- Recuperação restaura **estrutura e consistência**, não os dados excluídos.
- Em Linux puro o auto-create do bind nasce como root (documentado; o `install.sh` faz o mkdir na instalação — só afeta quem deleta depois).
- O marcador passa a existir a partir do primeiro boot desta versão (migração automática e silenciosa).
- Teste E2E real executado pelo usuário nos dois modos de falha durante o desenvolvimento.
