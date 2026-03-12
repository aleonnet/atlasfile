# Git Cheat Sheet

---

## Conventional Commits

| Prefixo | Quando usar | Exemplo |
|---------|-------------|---------|
| `feat` | Nova funcionalidade | `feat: add channel filter to UsageView` |
| `fix` | Correção de bug | `fix: session usage not saved on first turn` |
| `chore` | Manutenção (não altera código funcional) | `chore: add .code-workspace to .gitignore` |
| `refactor` | Reestruturação sem mudar comportamento | `refactor: extract session manager from main.py` |
| `docs` | Apenas documentação | `docs: update CHANGELOG for v0.6.0` |
| `test` | Apenas testes | `test: add context pressure unit tests` |
| `style` | Formatação, whitespace | `style: fix indentation in orchestrator` |
| `perf` | Melhoria de performance | `perf: cache OpenSearch client per request` |
| `ci` | Pipelines CI/CD | `ci: add Docker build to GitHub Actions` |
| `build` | Build system, dependências | `build: upgrade aiogram to 3.27` |

Formato completo: `<tipo>(<escopo opcional>): <descrição>`

```bash
git commit -m "feat(channels): add Telegram transparent pipe"
git commit -m "fix(usage): correct multi-model cost aggregation"
```

---

## Status e sincronização

```bash
# Estado atual (arquivos modificados, staged, untracked)
git status
git status --short              # versão compacta

# Comparar local vs remoto
git fetch                       # atualiza referências remotas (não altera código)
git status                      # após fetch, mostra "ahead/behind"

# Quantos commits à frente/atrás do remoto
git rev-list --left-right --count HEAD...origin/main

# Ver último commit local vs remoto
git log --oneline -1            # local
git log --oneline -1 origin/main  # remoto (após fetch)

# Diferença entre local e remoto
git diff origin/main            # o que mudou localmente
git diff origin/main --stat     # resumo (arquivos + linhas)
```

---

## Workflow diário

```bash
# Ver o que mudou
git diff                        # unstaged (working tree)
git diff --staged               # staged (pronto para commit)
git diff --stat                 # resumo compacto

# Commit rápido (arquivo específico)
git add <arquivo> && git commit -m "tipo: mensagem"

# Commit de tudo que está modificado (não inclui untracked)
git add -u && git commit -m "tipo: mensagem"

# Commit de tudo (modificados + untracked)
git add -A && git commit -m "tipo: mensagem"

# Sincronizar com remoto
git pull --rebase               # puxa + reaplica seus commits por cima
git push                        # envia para remoto
```

---

## Histórico

```bash
# Últimos N commits
git log --oneline -10

# Histórico com grafo de branches
git log --oneline --graph --all -20

# O que mudou em um commit específico
git show <hash>                 # diff completo
git show <hash> --stat          # apenas arquivos alterados

# Quem alterou cada linha de um arquivo
git blame <arquivo>

# Buscar commit por mensagem
git log --grep="usage" --oneline

# Buscar commit que alterou um texto específico
git log -S "channel_session_timeout" --oneline
```

---

## Desfazer coisas

```bash
# Descartar mudanças em um arquivo (volta ao último commit)
git checkout -- <arquivo>
# ou (Git 2.23+)
git restore <arquivo>

# Unstage um arquivo (remove do staging, mantém mudanças)
git reset HEAD <arquivo>
# ou (Git 2.23+)
git restore --staged <arquivo>

# Desfazer último commit (mantém mudanças no working tree)
git reset --soft HEAD~1

# Desfazer último commit (mantém mudanças unstaged)
git reset HEAD~1

# Desfazer último commit (descarta tudo — CUIDADO)
git reset --hard HEAD~1

# Criar commit que reverte outro (seguro para histórico público)
git revert <hash>
```

---

## Branches

```bash
# Listar branches
git branch                      # locais
git branch -a                   # locais + remotas

# Criar e trocar
git checkout -b <nome>
# ou (Git 2.23+)
git switch -c <nome>

# Trocar de branch
git checkout <nome>
git switch <nome>

# Deletar branch local
git branch -d <nome>            # seguro (só se já merged)
git branch -D <nome>            # forçado

# Deletar branch remota
git push origin --delete <nome>

# Merge
git merge <branch>

# Rebase (reaplica commits de <branch> sobre a branch atual)
git rebase <branch>
```

---

## Stash (gaveta temporária)

```bash
# Guardar mudanças temporariamente
git stash
git stash -m "WIP: ajuste no UsageView"

# Listar stashes
git stash list

# Recuperar último stash
git stash pop                   # aplica e remove
git stash apply                 # aplica e mantém

# Descartar stash
git stash drop
```

---

## Tags

```bash
# Criar tag (release)
git tag v0.6.0
git tag -a v0.6.0 -m "AtlasFile v0.6.0"

# Listar tags
git tag -l

# Push de tags
git push origin v0.6.0          # uma tag
git push origin --tags          # todas
```

---

## Inspeção rápida

```bash
# Arquivos modificados desde último commit
git diff --name-only

# Arquivos modificados entre duas versões
git diff v0.5.0..v0.6.0 --stat

# Tamanho do diff (linhas adicionadas/removidas)
git diff --shortstat

# Quem mais commitou
git shortlog -sn

# Último commit de cada arquivo
git log --oneline -1 -- <arquivo>
```

---

## Configuração útil

```bash
# Ver config atual
git config --list

# Aliases úteis (adicionar ao ~/.gitconfig)
git config --global alias.st "status --short"
git config --global alias.lg "log --oneline --graph -20"
git config --global alias.last "log -1 --format='%h %s (%cr)'"
git config --global alias.sync "!git fetch && git status"

# Após configurar:
git st                          # status compacto
git lg                          # histórico visual
git last                        # último commit
git sync                        # fetch + status
```
