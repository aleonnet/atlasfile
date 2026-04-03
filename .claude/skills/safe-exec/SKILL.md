---
name: safe-exec
description: >
  Classify every shell command before running it. Safe commands (read-only,
  non-destructive: ls, cat, grep, find, git status, git log, git diff,
  make test, make docker-up, pytest, npm test, npx vitest, docker ps,
  docker logs, python scripts) execute immediately without asking.
  Destructive commands (rm, rmdir, git reset, git clean, git push --force,
  docker rm, docker system prune, kill, pkill, make reset-index,
  make reset-chat, make docker-update, SQL DROP/TRUNCATE/DELETE without WHERE,
  truncate, redirect overwrite "> file") MUST stop and ask for explicit
  confirmation before running. Use this skill whenever about to run any
  Bash command — in this project or any shell context.
---

# safe-exec

Before running any shell command, classify it and act accordingly.

## Safe — execute immediately (no confirmation needed)

These commands only read state or build/test without side effects:

| Category | Examples |
|----------|----------|
| Filesystem read | `ls`, `cat`, `head`, `tail`, `find`, `stat`, `file`, `wc`, `diff` |
| Search | `grep`, `rg`, `awk`, `sed` (read-only), `jq` |
| Git read-only | `git status`, `git log`, `git diff`, `git show`, `git branch`, `git stash list`, `git remote -v` |
| Build & test | `make test`, `make test-backend`, `make test-frontend`, `pytest`, `npm test`, `npx vitest` |
| Docker read | `docker ps`, `docker logs`, `docker images`, `docker inspect`, `docker-compose ps` |
| Stack up (non-destructive) | `make docker-up` |
| Python/Node read | `python -c`, `python -m`, `node -e`, `npx` (when not destructive) |
| Utilities | `which`, `env`, `echo`, `pwd`, `date`, `curl` (GET only), `ping` |
| Linters/formatters | `ruff check`, `mypy`, `tsc --noEmit`, `eslint` |

## Destructive — STOP and ask before running

These commands can permanently delete data, overwrite files, or affect shared state:

| Category | Patterns |
|----------|----------|
| Delete files | `rm`, `rmdir`, `unlink` |
| Overwrite | `mv` targeting existing files, `cp -f`, redirect `> file` (not `>>`) |
| Truncate | `truncate`, `: > file`, `echo "" > file` |
| Git write | `git reset`, `git clean`, `git checkout --`, `git restore`, `git push --force`, `git rebase` (when altering published history) |
| Docker destroy | `docker rm`, `docker rmi`, `docker system prune`, `docker volume rm`, `docker-compose down -v` |
| Index reset | `make reset-index`, `make reset-chat` |
| Full rebuild | `make docker-update` (stops containers, rebuilds images, replaces state) |
| Process termination | `kill`, `pkill`, `killall` |
| SQL destructive | `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, `DELETE FROM` without a `WHERE` clause, `ALTER TABLE DROP COLUMN` |

## Gray zone — ask for context

For these, briefly explain what the command does and ask if the user wants to proceed:

- `git commit` / `git push` (without `--force`) — safe locally, affects shared remote
- `docker-compose down` — safe without `-v`, destructive volumes with `-v`
- `pip install --upgrade` / `npm install` — generally safe but alters the environment
- `git stash drop` / `git stash clear` — loses stashed work

## Confirmation workflow

When a destructive command is about to run:

1. **Show the exact command** in a code block
2. **Explain in one sentence** what it does and what cannot be undone
3. **Ask explicitly**: "Confirmar execução? (sim/não)"
4. **Wait for an unambiguous "yes"** — "sim", "s", "yes", "y", "confirmar", "pode"
5. Any other response (including silence or "talvez") → cancel and inform the user

Never execute a destructive command without receiving an affirmative response.
Never assume confirmation from a prior message in the conversation.
Each destructive command requires its own confirmation, even if the user approved a similar one moments ago.

## Compound commands

When a command string chains multiple commands (via `&&`, `||`, `;`, or pipes), classify the entire chain by its most destructive component. If any part is destructive, the whole chain requires confirmation.

Example: `git status && rm -rf /tmp/build` → destructive (because of `rm`).
