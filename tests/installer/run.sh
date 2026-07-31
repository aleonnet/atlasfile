#!/usr/bin/env bash
# Installer unit tests — pure bash runner (no bats dependency, no network).
# Sources install.sh as a library (ATLASFILE_INSTALL_LIB=1 stops it before the
# banner) and exercises the decision functions against a PATH of stubs that
# record every call. Run: bash tests/installer/run.sh
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
PASS=0; FAILED=0

t() { # t "name" — followed by asserts that call ok/no
  CURRENT="$1"
  # A bancada e SILENCIOSA por desenho: `ok` nao imprime nada, so o placar final
  # e os FAIL saem. Isso a torna cega quando ela TRAVA — foi exatamente o que
  # aconteceu no job macOS do CI (2026-07-29): seis horas ate o teto do GitHub,
  # e no log so os broken pipes que vinham do stderr, nenhuma pista de ONDE
  # parou. Com AF_BENCH_TRACE=1 cada teste anuncia o nome em STDERR (que nao
  # concorre com as assercoes que capturam stdout), e a ultima linha do log
  # passa a ser o ponto de parada.
  [ "${AF_BENCH_TRACE:-0}" = "1" ] && printf 'TRACE: %s\n' "$1" >&2
  return 0
}
ok() { PASS=$((PASS+1)); }
no() { FAILED=$((FAILED+1)); printf 'FAIL: %s — %s\n' "$CURRENT" "$1"; }
assert_eq() { if [ "$1" = "$2" ]; then ok; else no "expected [$2] got [$1]"; fi; }

# O plano quebra linha para caber no trilho, entao uma frase pode chegar partida
# em duas linhas, cada uma com a sua calha. As assercoes abaixo testam o SENTIDO
# do plano, nao o layout: `achata` desfaz a quebra antes de comparar. Sem isto
# uma mudanca de largura reprovaria testes que continuam corretos.
achata() { printf '%s' "$1" | tr '\n' ' ' | sed -e 's/│//g' -e 's/  */ /g'; }
assert_contains() { if grep -q "$2" "$1" 2>/dev/null; then ok; else no "calls log missing [$2]"; fi; }
assert_not_contains() { if grep -q "$2" "$1" 2>/dev/null; then no "calls log has forbidden [$2]"; else ok; fi; }

make_sandbox() {
  SANDBOX="$(mktemp -d)"
  CALLS="${SANDBOX}/calls.log"; : > "$CALLS"
  mkdir -p "${SANDBOX}/bin"
  # stub factory: records invocation, exits per STUB_RC_<name>
  # curl entrou na fase 4a (o instalador baixa o bundle da release); tar fica
  # FORA de proposito — a extracao do bundle usa o tar real, e stubar o tar
  # transformaria a fixture de release em teatro.
  for name in brew docker git sudo apt-get dnf systemctl open ollama curl; do
    cat > "${SANDBOX}/bin/${name}" <<EOF
#!/usr/bin/env bash
echo "${name} \$*" >> "${CALLS}"
rc_var="STUB_RC_${name//-/_}"
exit "\${!rc_var:-0}"
EOF
    chmod +x "${SANDBOX}/bin/${name}"
  done
}

run_case() { # run_case <extra_env...> -- <bash body>; PATH already sandboxed
  local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" CALLS="$CALLS" \
    SANDBOX="$SANDBOX" REPO_ROOT="$REPO_ROOT" ${envs[@]+"${envs[@]}"} \
    bash -c 'set -u
      export ATLASFILE_INSTALL_LIB=1
      # shellcheck disable=SC1091
      source "$REPO_ROOT/install.sh"
      '"$*"
}

# ── detect_os ───────────────────────────────────────────────────────────────
make_sandbox
t "detect_os identifies the platform and package manager"
out="$(run_case -- 'detect_os; echo "$OS_KIND:$PKG:$BREW_PREFIX"')"
case "$(uname -s)" in
  Darwin)
    exp_prefix="/usr/local"; [ "$(uname -m)" = "arm64" ] && exp_prefix="/opt/homebrew"
    # `brew` do sandbox esta no PATH, entao o esperado e brew — e nao o "none"
    # que esta asserção afirmava antes, ABENCOANDO o defeito que uma execucao
    # real do --doctor expos. Um teste que codifica o bug e pior que teste
    # nenhum: ele da o verde que impede a descoberta.
    assert_eq "$out" "mac:brew:${exp_prefix}" ;;
  *)
    printf '%s' "$out" | grep -q '^linux:' && ok || no "expected linux:* got [$out]" ;;
esac

# O ramo Darwin so era exercitado pelo job do macOS. Com `uname` stubado os DOIS
# runners entram nele, que e onde o defeito do PKG vivia.
make_sandbox
cat > "${SANDBOX}/bin/uname" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in -s) echo Darwin ;; -m) echo "${STUB_ARCH:-arm64}" ;; -r) echo 25.5.0 ;; *) echo Darwin ;; esac
EOF
chmod +x "${SANDBOX}/bin/uname"

t "detect_os: macOS com Homebrew no PATH reporta brew, nao none"
out="$(run_case -- 'detect_os; echo "$OS_KIND:$PKG"')"
assert_eq "$out" "mac:brew"

# Homebrew instalado mas FORA do PATH (shell recem-aberto): o brew sai do PATH
# do sandbox e reaparece so no prefixo. Roda o detect_os de verdade — quem move
# o alvo e BREW_BIN, a mesma costura de DOCKER_APP_PATH.
mkdir -p "${SANDBOX}/prefix/bin"
mv "${SANDBOX}/bin/brew" "${SANDBOX}/prefix/bin/brew"

t "detect_os: macOS com Homebrew fora do PATH, mas no prefixo, reporta brew"
out="$(run_case BREW_BIN="${SANDBOX}/prefix/bin/brew" -- 'detect_os; echo "$OS_KIND:$PKG"')"
assert_eq "$out" "mac:brew"

t "detect_os: macOS sem Homebrew algum continua none"
out="$(run_case BREW_BIN="${SANDBOX}/prefix/bin/ausente" -- 'detect_os; echo "$OS_KIND:$PKG"')"
assert_eq "$out" "mac:none"

# ── confirm policy ──────────────────────────────────────────────────────────
make_sandbox
t "confirm: --yes without --install-deps refuses (conservative policy)"
run_case -- 'ASSUME_YES=1; INSTALL_DEPS=0; TTY_DEV=/dev/null
  if confirm "q?"; then exit 0; else exit 1; fi' && no "confirm said yes" || ok

t "confirm: --install-deps authorizes headless"
run_case -- 'ASSUME_YES=1; INSTALL_DEPS=1; TTY_DEV=/dev/null
  confirm "q?"' && ok || no "confirm refused with --install-deps"

t "confirm: interactive yes via TTY_DEV"
make_sandbox
printf 'y\n' > "${SANDBOX}/tty_in"
run_case -- 'ASSUME_YES=0; INSTALL_DEPS=0; TTY_DEV="$SANDBOX/tty_in"
  confirm "q?"' && ok || no "interactive y not accepted"

t "confirm: interactive default is no"
printf '\n' > "${SANDBOX}/tty_in"
run_case -- 'ASSUME_YES=0; INSTALL_DEPS=0; TTY_DEV="$SANDBOX/tty_in"
  confirm "q?"' && no "empty answer accepted as yes" || ok

# ── ensure_* contract: 100 = already present, presence checked FIRST ────────
make_sandbox
t "ensure_git returns 100 when git is present (no install attempted)"
rc=0; run_case -- 'detect_os; ensure_git' || rc=$?
assert_eq "$rc" "100"
assert_not_contains "$CALLS" "brew install git"
assert_not_contains "$CALLS" "apt-get install"

t "ensure_docker_mac returns 100 with cask present, installs when absent"
make_sandbox
rc=0; run_case STUB_RC_brew=0 DOCKER_APP_PATH=/nonexistent \
  -- 'OS_KIND=mac; BREW_PREFIX=/nonexistent; ensure_docker_mac' || rc=$?
# stub brew answers 0 to `brew list --cask docker-desktop` → already present
assert_eq "$rc" "100"
assert_not_contains "$CALLS" "brew install --cask docker-desktop"

make_sandbox
t "ensure_docker_mac installs via cask when nothing is present"
rc=0; run_case STUB_RC_brew=1 DOCKER_APP_PATH=/nonexistent -- '
  OS_KIND=mac; BREW_PREFIX=/nonexistent; IS_TTY=0; LOG_FILE="$SANDBOX/log"
  # brew stub fails `list` (rc 1) then fails install too — forces the install
  # path and the rc=1 return (a flat stub cannot distinguish subcommands)
  ensure_docker_mac' || rc=$?
assert_eq "$rc" "1"
assert_contains "$CALLS" "brew list --cask docker-desktop"

# Measured on a clean macOS VM: Docker Desktop installed but never opened means
# `command -v docker` fails (no CLI link yet) while ensure_docker_mac returns
# 100. The old `ensure_docker_mac || fail` aborted the install with a false
# "could not install Docker Desktop".
make_sandbox
t "an app present but never opened is not treated as an install failure"
out="$(run_case STUB_RC_brew=0 -- 'OS_KIND=mac; BREW_PREFIX=/nonexistent
  docker_rc=0; ensure_docker_mac || docker_rc=$?
  printf "rc=%s state=%s" "$docker_rc" "$(host_get docker)"')"
assert_eq "$out" "rc=100 state=preexisting"

# Achado pelo CI num runner Ubuntu: sem upgrade pendente, a última linha do ramo
# apt/dnf é um teste falso, a função devolvia 1 e o `set -e` matava o instalador
# logo após os pré-requisitos — antes de clonar. No macOS nunca aparecia.
make_sandbox
t "hint_upgrades nunca derruba o instalador quando nao ha upgrade pendente"
rc=0; run_case -- 'OS_KIND=linux; PKG=apt; hint_upgrades' >/dev/null || rc=$?
assert_eq "$rc" "0"
rc=0; run_case -- 'OS_KIND=linux; PKG=dnf; hint_upgrades' >/dev/null || rc=$?
assert_eq "$rc" "0"
rc=0; run_case -- 'OS_KIND=mac; PKG=none; DOCKER_APP_PATH=/nonexistent; hint_upgrades' >/dev/null || rc=$?
assert_eq "$rc" "0"

# ── Ollama saiu do instalador ───────────────────────────────────────────────
# ensure_ollama, ollama_pull_model e maybe_setup_ollama nao existem mais: puxar
# um modelo eram varios GB dentro de uma instalacao que precisa ter duracao
# previsivel. O UNINSTALL continua sabendo reverter um Ollama de versoes
# anteriores, e isso segue coberto pelos testes de plano mais abaixo.
make_sandbox
t "o instalador nao instala Ollama, mas NAO quebra quem colou o comando antigo"
# O site publica --with-ollama ha meses, e responder "Unknown flag" a um comando
# que nos mesmos publicamos quebraria o usuario na primeira linha. As flags sao
# aceitas, avisam e seguem.
for flag in --with-ollama --no-ollama; do
  if bash "$REPO_ROOT/install.sh" "$flag" --help >/dev/null 2>&1; then ok
  else no "o parser recusa ${flag}, que o site ainda publica"; fi
done
if bash "$REPO_ROOT/install.sh" --ollama-model x --help >/dev/null 2>&1; then ok
else no "o parser recusa --ollama-model (e ele consome um valor)"; fi
out="$(cat "$REPO_ROOT/install.sh" | bash -s -- --help 2>&1)"
case "$out" in *"Deprecated"*) ok ;; *) no "a ajuda nao explica que a flag foi depreciada" ;; esac
# E a flag depreciada nao pode fazer NADA de Ollama acontecer.
make_sandbox
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --with-ollama --doctor --dir "${SANDBOX}/nada" 2>&1 || true)"
case "$out" in *"no longer used"*) ok ;; *) no "nao avisou que a flag foi ignorada: [$out]" ;; esac
assert_not_contains "$CALLS" "ollama pull"

# ── flag parser (full script run with --help exits before any action) ───────
t "flag parser accepts the new flags (--help path proves parse phase)"
if bash "$REPO_ROOT/install.sh" --install-deps --bootstrap-only --help >/dev/null 2>&1; then ok; else no "--help with new flags failed"; fi

t "flag parser accepts the uninstall flags"
if bash "$REPO_ROOT/install.sh" --uninstall --purge-data --keep-data --remove-deps --force --help >/dev/null 2>&1; then ok; else no "--help with uninstall flags failed"; fi

t "unknown flag still fails"
if bash "$REPO_ROOT/install.sh" --nope >/dev/null 2>&1; then no "unknown flag accepted"; else ok; fi

# --help used to be `grep '^#' "$0"`, which prints nothing under `curl | bash`
t "--help works when the script arrives on stdin (curl | bash path)"
out="$(cat "$REPO_ROOT/install.sh" | bash -s -- --help 2>&1)"
case "$out" in *"AtlasFile installer"*) ok ;; *) no "piped --help did not print the usage" ;; esac
case "$out" in *"--uninstall"*) ok ;; *) no "usage does not document --uninstall" ;; esac

# ── banner: composition is a pure function, so it is testable without a TTY ──
make_sandbox
t "the banner has no face any more"
out="$(run_case -- 'af_frame_plain 25')"
case "$out" in *'‿'*) no "the mouth is still there" ;; *) ok ;; esac
case "$out" in *'AtlasFile'*) ok ;; *) no "wordmark missing from the still frame" ;; esac
case "$out" in *'Your documents have gravity.'*) ok ;; *) no "website call phrase missing" ;; esac

t "every frame has exactly 7 lines"
bad=""
for f in 0 4 5 12 17 21 24 25; do
  lines="$(run_case -- "af_frame_plain $f" | wc -l | tr -d ' ')"
  [ "$lines" = "7" ] || bad="${bad}frame ${f}=${lines} "
done
[ -z "$bad" ] && ok || no "wrong line count: $bad"

t "the orbit is a closed ring of 16 distinct cells"
out="$(run_case -- 'i=0; while [ $i -lt 17 ]; do af_cell "$AF_ORBIT" $(( i % AF_ORBIT_N )); echo "$AF_CELL_ROW,$AF_CELL_COL"; i=$((i+1)); done')"
uniq_n="$(printf '%s\n' "$out" | head -16 | sort -u | wc -l | tr -d ' ')"
assert_eq "$uniq_n" "16"
first="$(printf '%s\n' "$out" | head -1)"; last="$(printf '%s\n' "$out" | tail -1)"
assert_eq "$last" "$first"

t "no moon or comet ever overwrites an orb glyph"
# grep -o conta OCORRENCIAS do glifo; `tr -cd` contava BYTES e o resultado
# variava entre plataformas, porque `●` (E2 97 8F) compartilha o byte E2 com os
# blocos e `•` (E2 80 A2) compartilha E2 e 80 — o CI Linux pegou isso.
orb_glyphs() { grep -o -e '█' -e '▄' -e '▀' -e '▐' -e '▌' | wc -l | tr -d ' '; }
base="$(run_case -- 'af_frame_plain 25' | orb_glyphs)"
bad=""
for f in 5 9 13 17 20 24; do
  n="$(run_case -- "af_frame_plain $f" | orb_glyphs)"
  [ "$n" = "$base" ] || bad="${bad}frame ${f}=${n}(want ${base}) "
done
[ -z "$bad" ] && ok || no "orb glyph count changed: $bad"

t "the comet only exists inside its declared window"
run_case -- 'af_frame_plain 0' | grep -q '·' && no "comet visible on frame 0" || ok
run_case -- 'af_frame_plain 21' | grep -q '·' && ok || no "no comet on frame 21"
run_case -- 'af_frame_plain 25' | grep -q '·' && no "comet still visible on the still frame" || ok

t "the comet tail is contiguous behind the head (never sampled with gaps)"
out="$(run_case -- 'af_frame_plain 24' | grep '●')"
case "$out" in *'···●'*) ok ;; *) no "expected a 3-cell contiguous tail, got [$out]" ;; esac

t "the wordmark reveal grows monotonically and completes"
prev=0; bad=""
for f in 17 19 21 23 25; do
  n="$(run_case -- "af_frame_plain $f" | sed -n '4p' | sed 's/^ *//' | wc -c | tr -d ' ')"
  [ "$n" -ge "$prev" ] || bad="${bad}frame ${f} shrank (${n} < ${prev}) "
  prev="$n"
done
[ -z "$bad" ] && ok || no "$bad"
full="$(run_case -- 'af_frame_plain 25' | grep -c 'Your documents have gravity.')"
assert_eq "$full" "1"

t "NO_COLOR emits no ANSI escape at all"
esc="$(run_case NO_COLOR=1 -- 'af_frame_paint 25' | grep -c "$(printf '\033')" || true)"
assert_eq "$esc" "0"

t "truecolor is used only when the terminal announces it"
out="$(run_case COLORTERM=truecolor TERM=xterm-256color -- 'COLOR_OK=1; TRUECOLOR=1; AF_INIT_DONE=0; af_frame_paint 25' | head -3)"
case "$out" in *'[38;2;'*) ok ;; *) no "truecolor ramp not used with COLORTERM=truecolor" ;; esac
out="$(run_case TERM=xterm-256color -- 'COLOR_OK=1; TRUECOLOR=0; AF_INIT_DONE=0; af_frame_paint 25' | head -3)"
case "$out" in *'[38;5;'*) ok ;; *) no "256 fallback not used without COLORTERM" ;; esac
case "$out" in *'[38;2;'*) no "24-bit escapes leaked into the 256 fallback" ;; *) ok ;; esac

t "rendering is deterministic and the animation stays inside its time budget"
a="$(run_case -- 'af_frame_plain 21')"; b="$(run_case -- 'af_frame_plain 21')"
assert_eq "$a" "$b"
budget="$(run_case -- 'awk -v n="$AF_LAST" -v d="$AF_DELAY" "BEGIN { printf \"%d\", (n * d * 1000) }"')"
if [ "$budget" -le 1200 ]; then ok; else no "animation budget ${budget}ms exceeds 1200ms"; fi

# ── manifest: `created` is a one-way door, and unknown always reads safe ─────
make_sandbox
t "manifest never downgrades created to preexisting"
out="$(run_case -- 'f="$SANDBOX/m"; manifest_set "$f" docker created; manifest_set "$f" docker preexisting; manifest_get "$f" docker')"
assert_eq "$out" "created"

t "manifest upgrades preexisting to created (a later run that installs it)"
out="$(run_case -- 'f="$SANDBOX/m2"; manifest_set "$f" git preexisting; manifest_set "$f" git created; manifest_get "$f" git')"
assert_eq "$out" "created"

t "an absent key and an absent file both read empty (never created)"
out="$(run_case -- 'manifest_get "$SANDBOX/nope" docker; manifest_get "$SANDBOX/m" ghost')"
assert_eq "$out" ""


# ── uninstall plan ──────────────────────────────────────────────────────────
PLAN_FACTS='OS_KIND=mac; PKG=none; UN_DIR="$SANDBOX/inst"; UN_PROJECT=testproj; UN_COMPOSE_FILE=1
  UN_CONTAINERS=5; UN_VOLUME=testproj_opensearch_data; UN_IMAGES="testproj-api "
  UN_CLONE_STATE=created; UN_DIR_DIRTY=0; UN_PROJECTS_ROOT="$SANDBOX/docs"
  UN_PROJECTS_CREATED=preexisting; UN_PROJECTS_FILES=42; UN_OTHER_ARTIFACTS=""'

make_sandbox
t "with everything preexisting, no system package is ever removed"
out="$(run_case -- "${PLAN_FACTS}
  host_set docker preexisting; host_set git preexisting; host_set ollama preexisting
  un_build_plan 0 1 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *brew-cask:*|*pkg-docker*|*pkg-git*) no "planned a removal for preexisting deps: [$out]" ;; *) ok ;; esac
case "$out" in *compose-down*) ok ;; *) no "the stack itself should still be removed" ;; esac

make_sandbox
t "docker installed by AtlasFile is planned with the /Applications warning"
out="$(run_case -- "${PLAN_FACTS}
  host_set docker created
  un_build_plan 0 1 0; printf '%s|%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_REMOVE\"")"
case "$out" in *"brew-cask:docker-desktop"*) ok ;; *) no "cask removal not planned" ;; esac
case "$out" in *"DELETES THE APP FROM /Applications"*) ok ;; *) no "missing the destructive warning" ;; esac

make_sandbox
t "another AtlasFile install on the host keeps Docker off the removal list"
out="$(run_case -- "${PLAN_FACTS}
  UN_OTHER_ARTIFACTS='atlasfile-dev_opensearch_data'
  host_set docker created
  un_build_plan 0 1 0; printf '%s|%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *brew-cask:docker-desktop*) no "would have removed shared Docker" ;; *) ok ;; esac
case "$out" in *"another AtlasFile install still uses it"*) ok ;; *) no "no explanation for keeping Docker" ;; esac

make_sandbox
t "without a manifest nothing system-wide is removable (legacy install)"
out="$(run_case -- "${PLAN_FACTS}
  un_build_plan 0 1 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *brew*|*pkg-*|*ollama-rm*|*gpasswd*) no "removed a dep it cannot prove it installed: [$out]" ;; *) ok ;; esac

make_sandbox
t "Homebrew is never an executable action, only an instruction"
out="$(run_case -- "${PLAN_FACTS}
  host_set homebrew created
  un_build_plan 0 1 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *homebrew*"|"*) no "Homebrew ended up in the actions" ;; *) ok ;; esac
case "$(achata "$out")" in *"NEVER removed automatically"*) ok ;; *) no "no note about Homebrew" ;; esac

make_sandbox
t "a projects root with files is never in the removal list"
out="$(run_case -- "${PLAN_FACTS}
  UN_PROJECTS_CREATED=created; UN_PROJECTS_FILES=1
  un_build_plan 0 1 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-projects-root*) no "planned to remove a non-empty documents folder" ;; *) ok ;; esac

make_sandbox
t "a projects root created by the installer and still empty is removed"
out="$(run_case -- "${PLAN_FACTS}
  UN_PROJECTS_CREATED=created; UN_PROJECTS_FILES=0
  un_build_plan 0 1 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-projects-root*) ok ;; *) no "empty folder created by the installer was not planned" ;; esac

make_sandbox
t "the data volume follows the decision, never a default"
out="$(run_case -- "${PLAN_FACTS}
  un_build_plan 0 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *purge-volume*) no "kept data still planned a purge" ;; *) ok ;; esac
out="$(run_case -- "${PLAN_FACTS}
  un_build_plan 1 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *purge-volume*) ok ;; *) no "--purge-data did not plan the volume removal" ;; esac

make_sandbox
t "--yes alone never removes system dependencies (symmetry with --install-deps)"
out="$(run_case -- "${PLAN_FACTS}
  host_set docker created; host_set git created
  un_build_plan 0 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *brew*|*pkg-*) no "removed deps without --remove-deps" ;; *) ok ;; esac

make_sandbox
t "a clone with local changes is preserved unless --force"
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR_DIRTY=1; un_build_plan 0 0 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *rm-clone*) no "removed a dirty clone" ;; *) ok ;; esac
case "$out" in *"local changes"*) ok ;; *) no "no explanation for keeping the dirty clone" ;; esac
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR_DIRTY=1; un_build_plan 0 0 1; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-clone*) ok ;; *) no "--force did not allow removing the dirty clone" ;; esac

make_sandbox
t "a directory the installer did not create is never removed"
out="$(run_case -- "${PLAN_FACTS}
  UN_CLONE_STATE=unknown; un_build_plan 0 0 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *rm-clone*) no "removed a directory it did not create" ;; *) ok ;; esac
case "$out" in *"not created by this installer"*) ok ;; *) no "no explanation" ;; esac

# The plan must not claim a stack was touched when there is no compose file
# (seen for real on the macOS VM, where the install died before cloning).
make_sandbox
t "with no stack to remove, the plan does not claim one was touched"
out="$(run_case -- "${PLAN_FACTS}
  UN_COMPOSE_FILE=0; UN_CLONE_STATE=unknown; UN_VOLUME=\"\"
  un_build_plan 0 0 0; printf '%s' \"\$UN_PLAN_KEEP\"")"
case "$out" in *"only the stack above was touched"*) no "claimed a stack was touched when there is none" ;; *) ok ;; esac
case "$out" in *"not created by this installer"*) ok ;; *) no "lost the explanation for keeping the directory" ;; esac

make_sandbox
t "the stack is never touched by container name (fixed atlasfile-* names)"
out="$(run_case -- "${PLAN_FACTS}
  un_build_plan 1 1 1; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *"docker rm "*|*"atlasfile-api"*) no "planned a removal by container name" ;; *) ok ;; esac

t "the project name honours COMPOSE_PROJECT_NAME, not just the folder name"
make_sandbox
mkdir -p "${SANDBOX}/MyDir"
printf 'COMPOSE_PROJECT_NAME=chosen-name\n' > "${SANDBOX}/MyDir/.env"
out="$(run_case -- 'un_project_name "$SANDBOX/MyDir"')"
assert_eq "$out" "chosen-name"
rm -f "${SANDBOX}/MyDir/.env"
out="$(run_case -- 'un_project_name "$SANDBOX/MyDir"')"
assert_eq "$out" "mydir"

t "un_dir_is_safe refuses anything that is not an install directory"
make_sandbox
mkdir -p "${SANDBOX}/notinstall"
run_case -- 'un_dir_is_safe /' && no "accepted /" || ok
run_case -- 'un_dir_is_safe "$HOME"' && no "accepted \$HOME" || ok
run_case -- 'un_dir_is_safe "$SANDBOX/notinstall"' && no "accepted a folder with no .git and no compose file" || ok
run_case -- 'mkdir -p "$SANDBOX/notinstall/.git"; un_dir_is_safe "$SANDBOX/notinstall"' && ok || no "rejected a real clone"

# Found by the real E2E: a fresh install left .atlasfile-install-manifest
# untracked, the dirty guard fired, and the clone could never be removed.
t "the installer's own artifacts do not count as local changes"
make_sandbox
mkdir -p "${SANDBOX}/clone"
( cd "${SANDBOX}/clone" && git init -q . && git config user.email t@t && git config user.name t \
  && printf 'x\n' > tracked.txt && git add tracked.txt && git commit -qm init ) >/dev/null 2>&1
printf 'secret\n' > "${SANDBOX}/clone/.env"
printf 'schema\t1\n' > "${SANDBOX}/clone/.atlasfile-install-manifest"
# PATH without the sandbox: this case needs the REAL git, not the stub that
# always answers empty (which would make the assertions pass vacuously).
out="$(run_case PATH=/usr/bin:/bin -- 'un_collect "$SANDBOX/clone"; printf "%s" "$UN_DIR_DIRTY"')"
assert_eq "$out" "0"
printf 'real work\n' > "${SANDBOX}/clone/user_file.txt"
out="$(run_case PATH=/usr/bin:/bin -- 'un_collect "$SANDBOX/clone"; printf "%s" "$UN_DIR_DIRTY"')"
assert_eq "$out" "1"

# A run that installed Docker and died before cloning leaves no directory but a
# valid host manifest. Refusing would strand the user with a Docker they never
# had and no way back.
t "an install that died before cloning can still revert its system dependencies"
make_sandbox
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash -c 'export ATLASFILE_INSTALL_LIB=1; source "'"$REPO_ROOT"'/install.sh"
    host_set docker created
    OS_KIND=mac; PKG=none
    UN_DIR="'"$SANDBOX"'/gone"; UN_PROJECT=gone; UN_COMPOSE_FILE=0
    UN_CLONE_STATE=unknown; UN_DIR_DIRTY=0; UN_PROJECTS_ROOT=""; UN_PROJECTS_FILES=0
    UN_OTHER_ARTIFACTS=""; UN_VOLUME=""; UN_CONTAINERS=0; UN_IMAGES=""
    un_build_plan 0 1 0; printf "%s" "$UN_ACTIONS"')"
case "$out" in *brew-cask:docker-desktop*) ok ;; *) no "would not revert a Docker installed by a half-finished run: [$out]" ;; esac
if [ -f "${SANDBOX}/.atlasfile/host-prereqs" ]; then ok; else no "host manifest not written outside the install dir"; fi

t "headless uninstall refuses to guess what to do with the data volume"
make_sandbox
mkdir -p "${SANDBOX}/inst"
cp "$REPO_ROOT/docker-compose.yml" "${SANDBOX}/inst/" 2>/dev/null || printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
cat > "${SANDBOX}/bin/docker" <<EOF
#!/usr/bin/env bash
echo "docker \$*" >> "${CALLS}"
case "\$1 \$2" in
  "volume ls") echo "inst_opensearch_data" ;;
  "ps -aq") echo "deadbeef" ;;
esac
exit 0
EOF
chmod +x "${SANDBOX}/bin/docker"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --uninstall --dir "${SANDBOX}/inst" --yes 2>&1 || true)"
case "$out" in *"--purge-data"*) ok ;; *) no "did not demand an explicit data decision: [$out]" ;; esac

# A consolidação renomeou o serviço para `atlasfile`: se o un_collect seguir
# casando só api/web/mcp, o uninstall reporta sucesso e deixa a imagem nova
# (~centenas de MB) no disco. Os nomes antigos continuam no plano porque um
# upgrade de 0.56.x ainda os carrega.
# v1.0.0: a stack passou a rodar imagem NOMEADA (ghcr.io/aleonnet/atlasfile
# ou atlasfile-local do overlay de build) — `down --rmi local` não remove
# imagem com `image:` no compose, então elas TÊM de entrar no UN_IMAGES; as
# upstream (opensearchproject/*) continuam fora (compartilhadas, só keep-note).
t "uninstall enxerga a imagem consolidada, as legadas de 0.56.x e as nomeadas da v1.0.0"
make_sandbox
mkdir -p "${SANDBOX}/inst"
printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
cat > "${SANDBOX}/bin/docker" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
  "image inspect")
    case "\$3" in inst-atlasfile|inst-api) exit 0 ;; *) exit 1 ;; esac ;;
  "images --format")
    printf 'ghcr.io/aleonnet/atlasfile:1.0.0\natlasfile-local:dev\nopensearchproject/opensearch:2.17.1\n' ;;
esac
exit 0
EOF
chmod +x "${SANDBOX}/bin/docker"
out="$(run_case -- 'un_collect "$SANDBOX/inst"; printf "%s" "$UN_IMAGES"')"
case "$out" in *inst-atlasfile*) ok ;; *) no "imagem consolidada fora do plano de remoção: [$out]" ;; esac
case "$out" in *inst-api*) ok ;; *) no "imagem legada 0.56.x fora do plano de remoção: [$out]" ;; esac
case "$out" in *"ghcr.io/aleonnet/atlasfile:1.0.0"*) ok ;; *) no "imagem publicada (GHCR) fora do plano de remoção: [$out]" ;; esac
case "$out" in *"atlasfile-local:dev"*) ok ;; *) no "imagem do overlay de build fora do plano de remoção: [$out]" ;; esac
case "$out" in *opensearchproject*) no "imagem upstream compartilhada entrou indevidamente no plano de remoção: [$out]" ;; *) ok ;; esac

# ── UI: calha vertical, barra viva e trap que não vaza ─────────────────────
make_sandbox
t "toda mensagem pendura na calha vertical"
out="$(run_case -- 'info hello; warn hello; ok hello' 2>&1)"
bad=""
while IFS= read -r linha; do
  case "$linha" in "│ "*) ;; *) bad="${bad}[${linha}] " ;; esac
done <<EOF
$out
EOF
[ -z "$bad" ] && ok || no "linha fora da calha: $bad"

# O comprimento da regua e uma PROPRIEDADE, nao um detalhe: no mac_env_install.sh
# todos os estagios fecham na mesma coluna, e era isso que faltava aqui. A
# primeira versao distribuia os tracos com divisao inteira e descartava o resto,
# entao cada fase parava num lugar diferente.
t "toda regua fecha na MESMA coluna, em qualquer locale"
for loc in en_US.UTF-8 C; do
  larguras="$(env -i HOME="$SANDBOX" TERM=xterm-256color COLORTERM=truecolor LC_ALL=$loc \
      PATH=/usr/bin:/bin REPO_ROOT="$REPO_ROOT" bash -c '
    export ATLASFILE_INSTALL_LIB=1; source "$REPO_ROOT/install.sh"
    COLOR_OK=1; TRUECOLOR=1; IS_TTY=0
    rule_sweep "[1/4] Checking and preparing prerequisites"
    rule_sweep "[3/4] Configuring"
    rule_sweep "Removal plan — /tmp/x"
    rule_close' | python3 -c "
import sys,re
for l in re.sub(rb'\x1b\[[0-9;]*m',b'',sys.stdin.buffer.read()).split(b'\n'):
    if l.strip(): print(len(l.decode('utf-8','replace')))" | sort -u | tr '\n' ' ')"
  n="$(printf '%s' "$larguras" | wc -w | tr -d ' ')"
  if [ "$n" = "1" ]; then ok
  else no "sob locale ${loc} as reguas tem comprimentos diferentes: ${larguras}"; fi
done

# Varredura mecanica: NENHUMA linha de mensagem pode escapar da calha. Tres
# vezes seguidas um ponto esquecido apareceu na tela do usuario — a pergunta da
# pasta, e depois as cinco linhas da fase 3.
t "nenhum printf de mensagem comeca com espaco literal em vez da calha"
# So ACIMA da marca AF-FIM-DO-TRILHO: depois dela o trilho ja fechou e o
# relatorio final sai sem calha, que e o desenho do mac-env.
# Dois trechos sao relatorio final e saem sem calha de proposito: o corpo do
# un_report e tudo abaixo da marca AF-FIM-DO-TRILHO.
corte="$(grep -n 'AF-FIM-DO-TRILHO' "$REPO_ROOT/install.sh" | head -1 | cut -d: -f1)"
[ -n "$corte" ] || corte=99999
# QUALQUER quantidade de espaco literal abrindo o formato, nao so `  %s`: o
# --dry-run imprimia o plano de instalacao com `printf '    • …'` e passava
# batido por essa varredura, deixando quatro linhas sem calha no meio do bloco
# mais importante da tela. A regra e a propriedade ("o formato nao pode comecar
# por espaco"), nao um prefixo especifico.
#
# COMENTARIO NAO E CODIGO: sem descartar as linhas de `#`, a guarda casa com o
# proprio comentario que explica o defeito e reprova o codigo ja corrigido — foi
# o que aconteceu aqui, e e a mesma armadilha que o check_gutter_holes registra.
fora="$(head -n "$corte" "$REPO_ROOT/install.sh" \
  | awk '/^un_report\(\) \{/{pula=1} pula&&/^\}/{pula=0; next} !pula' \
  | grep -vE "^[[:space:]]*#" \
  | grep -nE "printf '[ ]{2,}" | grep -v 'GUT' | grep -v '^[0-9]*:note()' || true)"
[ -z "$fora" ] && ok || no "linha(s) fora da calha: $fora"

# Linha VAZIA dentro do trilho e um buraco na calha — foi o que o usuario viu em
# tres pontos de uma desinstalacao real (depois do [y/N], e antes do ╰──). No
# mac_env_install.sh a linha em branco do trilho e `echo -e "${GUT}"`, nunca "".
t "nenhuma linha em branco crua dentro do trilho"
corte="$(grep -n 'AF-FIM-DO-TRILHO' "$REPO_ROOT/install.sh" | head -1 | cut -d: -f1)"
[ -n "$corte" ] || corte=99999
# un_report e print_banner vivem FORA do trilho de proposito: um e o relatorio
# depois do fechamento, o outro e o banner antes da abertura.
# rail_end sai da varredura porque a folga dele e DEPOIS do `╰──`: quem fecha o
# trilho esta, por definicao, fora dele.
cru="$(head -n "$corte" "$REPO_ROOT/install.sh" \
  | awk '/^(un_report|print_banner)\(\) \{/{pula=1} pula&&/^\}/{pula=0; next} !pula' \
  | grep -n "printf '\\\\n'" | grep -v 'rail_end()' || true)"
[ -z "$cru" ] && ok || no "linha em branco sem calha dentro do trilho: $cru"

# Sem TERM (env -i) o tput falha e o term_cols cai no fallback de 72 colunas —
# valor deterministico, e a funcao real, sem stub por cima.
t "af_wrap: bullet de 156 colunas nao estoura a largura nem perde a calha"
out="$(run_case -- '
  UN_DIR=/tmp/x
  un_add_remove "data volume atlasfile_opensearch_data — THE SEARCH INDEX IS ERASED (rebuildable with Reconcile: your documents and the journal on disk are the source)"
  un_add_keep "your documents in /Users/alessandro/Documents/AtlasFileProjectsTest (133 item(s)), including the _ATLASFILE state — never touched"
  un_print_plan' 2>&1)"
ruim="$(printf '%s\n' "$out" | python3 -c "
import sys, re
ruim = []
for l in sys.stdin.read().split('\n'):
    t = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', l)
    if not t.strip():
        continue
    if len(t) > 72:
        ruim.append('largura %d: %s' % (len(t), t[:40]))
    if not t.startswith(('│', '├', '╰')):
        ruim.append('sem calha: %s' % t[:40])
print('; '.join(ruim))")"
[ -z "$ruim" ] && ok || no "$ruim"

# O plano contem literalmente `opensearchproject/*`. A quebra divide o texto em
# palavras; sem `set -f` o glob expandiria isso contra o diretorio corrente e o
# plano listaria arquivos da maquina de quem rodou.
t "af_wrap nao expande glob do texto que recebe"
# A quebra divide o texto em palavras, e sem `set -f` a divisao tambem faz
# expansao de caminho. O caminho de instalacao e a pasta de documentos vem de
# --dir e --projects-root, ou seja, sao TEXTO DO USUARIO: um `*` ali entraria no
# plano e viraria uma lista de arquivos da maquina.
#
# O padrao precisa CASAR com algo, senao o bash o devolve intacto por conta
# propria e o teste passa sem provar nada. (Foi o que aconteceu na primeira
# versao deste caso: usei o texto real do plano, `(opensearchproject/*)`, cujos
# parenteses impedem qualquer casamento — verde pelo motivo errado.)
mkdir -p "${SANDBOX}/docs" && touch "${SANDBOX}/docs/a.pdf" "${SANDBOX}/docs/b.pdf"
out="$(run_case -- 'cd "$SANDBOX"; af_wrap "│   • " "│     " 6 "your documents in docs/* are never touched"' 2>&1)"
printf '%s' "$out" | grep -q 'docs/\*' && ok || no "glob expandido: $out"

# O plano lista o volume em destaque ("THE SEARCH INDEX IS ERASED") e a execucao
# nao o citava: o `compose down --volumes` o levava junto e o unico rotulo na
# tela falava de "containers, network, local images". Confirmar destruicao de
# dado nao pode depender do usuario deduzir.
make_sandbox
t "volume apagado junto com a stack e confirmado PELO NOME na execucao"
out="$(run_case -- '
  UN_VOLUME=atlasfile_opensearch_data
  UN_DIR="$SANDBOX"; LOG_FILE="$SANDBOX/log"
  UN_ACTIONS="compose-down
purge-volume"
  un_execute
  printf "CONTAGEM:%s" "$UN_OK"' 2>&1)"
printf '%s' "$out" | grep -q 'volume atlasfile_opensearch_data erased' \
  && ok || no "a execucao nao citou o volume: $out"
t "e o placar conta o volume, para bater com o que o plano prometeu"
case "$out" in *CONTAGEM:2*) ok ;; *) no "esperava 2 removidos (stack + volume): $out" ;; esac

t "quando a stack NAO sai, o volume e removido de verdade, nao so anunciado"
out="$(run_case -- '
  UN_VOLUME=atlasfile_opensearch_data
  UN_DIR="$SANDBOX"; LOG_FILE="$SANDBOX/log"
  UN_ACTIONS="purge-volume"
  un_execute' 2>&1)"
printf '%s' "$(cat "$CALLS")" | grep -q 'docker volume rm atlasfile_opensearch_data' \
  && ok || no "nao chamou docker volume rm: $(cat "$CALLS")"

# backup_env_once cria um .env.backup a cada instalacao que sobrescreve um .env
# existente. Ate aqui: (a) a chave do manifesto era sobrescrita, entao so o mais
# novo tinha dono; (b) os arquivos sujavam o clone, e a pasta ficava presa PARA
# SEMPRE com a tela dizendo "has local changes" — culpando o usuario por um
# arquivo que o instalador escreveu.
make_sandbox
t "o manifesto acumula os backups em vez de esquecer os anteriores"
out="$(run_case -- '
  cd "$SANDBOX"; git init -q 2>/dev/null; printf "X=1\n" > .env
  AF_MANIFEST="$SANDBOX/.atlasfile-install-manifest"; ENV_STATE=preexisting
  backup_env_once >/dev/null
  AF_ENV_BACKED_UP=0; sleep 1; backup_env_once >/dev/null
  manifest_get "$AF_MANIFEST" env_backup')"
case "$out" in *,*) ok ;; *) no "guardou so um backup: [$out]" ;; esac

# O clone vive num SUBdiretorio: o proprio sandbox guarda os stubs em bin/, que
# o git veria como nao rastreado e sujaria tudo. A primeira versao destes dois
# casos rodava na raiz do sandbox — o teste do "arquivo do usuario" passava por
# causa do bin/, nao do arquivo. Verde pelo motivo errado.
t "backup nosso NAO trava a remocao da pasta"
out="$(run_case PATH=/usr/bin:/bin -- '
  mkdir -p "$SANDBOX/clone2"; cd "$SANDBOX/clone2"; git init -q 2>/dev/null
  touch .env.backup.20260101000000
  manifest_set "$SANDBOX/clone2/$AF_MANIFEST_NAME" env_backup .env.backup.20260101000000
  un_collect "$SANDBOX/clone2"; printf "%s" "$UN_DIR_DIRTY"')"
assert_eq "$out" "0"

# O contrario e igualmente importante: proveniencia vem do MANIFESTO, nunca do
# padrao do nome. Um arquivo que so PARECE nosso continua sendo do usuario.
t "arquivo que so parece backup nosso continua travando a remocao"
out="$(run_case PATH=/usr/bin:/bin -- '
  mkdir -p "$SANDBOX/clone3"; cd "$SANDBOX/clone3"; git init -q 2>/dev/null
  touch .env.backup.meu-arquivo
  manifest_set "$SANDBOX/clone3/$AF_MANIFEST_NAME" env_backup .env.backup.20260101000000
  un_collect "$SANDBOX/clone3"; printf "%s" "$UN_DIR_DIRTY"')"
assert_eq "$out" "1"

t "o plano cita TODOS os backups, nao so o do manifesto mais novo"
out="$(run_case -- '
  UN_DIR="$SANDBOX"; touch "$SANDBOX/.env.backup.20260101000000" "$SANDBOX/.env.backup.20260202000000"
  UN_ENV_BACKUP=".env.backup.20260101000000,.env.backup.20260202000000"
  UN_CLONE_STATE=preexisting; UN_COMPOSE_FILE=1
  un_build_plan 0 0 0; printf "%s" "$UN_PLAN_KEEP"')"
n="$(printf '%s' "$out" | grep -c 'env.backup' || true)"
[ "$n" = "2" ] && ok || no "citou $n backup(s), esperava 2"

t "quando a pasta inteira vai, o plano avisa que os backups vao junto"
out="$(run_case -- '
  UN_DIR="$SANDBOX"; touch "$SANDBOX/.env.backup.20260101000000"
  UN_ENV_BACKUP=".env.backup.20260101000000"
  UN_CLONE_STATE=created; UN_DIR_RECORDED="$SANDBOX"; UN_COMPOSE_FILE=1
  un_build_plan 0 0 0; printf "%s" "$UN_PLAN_REMOVE"')"
case "$(achata "$out")" in *"backup(s) inside"*"OpenSearch password and API key"*) ok ;;
  *) no "nao avisou que os backups vao junto: $out" ;; esac

# O trilho ABRIA com `├──` e nunca fechava no --doctor nem nos dois --dry-run.
t "todo modo que abre o trilho tambem o fecha"
# O `--uninstall` REAL entrou na lista. A guarda cobria so os tres modos que ja
# tinham sido consertados, e as tres saidas normais da desinstalacao (nada a
# fazer, cancelado, falhou) retornavam sem `╰──`: a tela terminava pendurada
# numa calha. Medido no caminho "nothing to do", que e o que este sandbox
# produz — sem .git e sem docker-compose.yml, o plano nao tem acao nenhuma.
for modo in "--doctor" "--dry-run" "--uninstall --dry-run" "--uninstall --keep-data"; do
  saida="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TERM=dumb \
      TTY_DEV=/dev/null REPO_ROOT="$REPO_ROOT" \
      bash "$REPO_ROOT/install.sh" $modo --dir "$SANDBOX" 2>&1 || true)"
  abriu="$(printf '%s' "$saida" | grep -c '├──' || true)"
  fechou="$(printf '%s' "$saida" | grep -c '╰──' || true)"
  if [ "$abriu" -gt 0 ] && [ "$fechou" -lt 1 ]; then
    no "modo ${modo} abriu ${abriu} regua(s) e nunca fechou o trilho"
  else
    ok
  fi
done

# "has local changes" sozinho nao e acionavel: numa maquina real o que travava a
# pasta era um backup do PROPRIO instalador, e nao havia como o usuario saber
# disso pela tela — ele precisou de ajuda para descobrir.
make_sandbox
# ── O volume que o --keep-data guardou tem de poder VOLTAR ──────────────────
# O plano promete, em letras, "a future reinstall reuses it". A instalacao
# seguinte recusava o volume como "de outra instancia", e os dois remedios da
# mensagem nao devolvem o dado: `--dir` diferente muda o nome do projeto compose
# (o volume preservado fica orfao) e `docker volume rm` apaga o que se pediu
# para guardar. Medido numa VM Ubuntu: --keep-data era um beco sem saida.
make_sandbox
t "o volume preservado e reconhecido na instalacao seguinte, no MESMO diretorio"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!senha9
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/AtlasFile && printf REUSA')"
case "$out" in *REUSA*) ok ;; *) no "nao reconheceu o proprio registro: $out" ;; esac

# A SENHA e obrigatoria, nao acessorio: o indice de seguranca do OpenSearch nasce
# com a senha da primeira subida e nao muda. Reusar o volume com senha nova
# levanta cinco containers que nao funcionam — "Authentication finally failed
# for admin" —, que e PIOR do que a falha alta que existia antes. Medido na VM.
t "e a senha do volume volta junto, senao o reuso sobe quebrado"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile "Af!senhaDoVolume9"
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/AtlasFile
  printf "SENHA:%s" "$AF_KEPT_VOLUME_PASS"')"
case "$out" in *"SENHA:Af!senhaDoVolume9"*) ok ;; *) no "a senha nao voltou: $out" ;; esac

# A guarda que faltava: eu tinha testado so as funcoes de registro, e o mutante
# que faz o .env ignorar a senha do volume — o defeito EXATO que sobe cinco
# containers quebrados — passou verde. O ponto de consumo tem de ser alcancavel.
t "a senha do volume reusado e a que vai para o .env"
out="$(run_case -- 'AF_REUSE_OS_PASS="Af!doVolume9"; af_os_password')"
case "$out" in *"Af!doVolume9"*) ok ;; *) no "o .env ignoraria a senha do volume: $out" ;; esac

t "e sem reuso ela e gerada, nunca vazia"
out="$(run_case -- 'p="$(af_os_password)"; case "$p" in Af!??????????*9) printf GERADA ;; esac')"
case "$out" in *GERADA*) ok ;; *) no "senha gerada fora do formato: $out" ;; esac

# ── O gerador de aleatorio tem de TERMINAR ──────────────────────────────────
# Foi aqui que a bancada travou no runner macOS do CI, ate o teto de 6h do
# GitHub, tres execucoes seguidas. O padrao antigo era
# `(tr -dc ... < /dev/urandom) | head -c N`: o `tr` le /dev/urandom PARA SEMPRE
# e so morre quando o `head` fecha o pipe e o SIGPIPE chega. Naquele runner nao
# chegava. Nao reproduz em macOS local (300 geracoes limpas) nem no runner
# Linux, entao guarda de TELA nao pega — a regressao so aparece num ambiente que
# a bancada nao alcanca. Por isso, excepcionalmente, uma guarda de FONTE.
# A guarda mira o REDIRECIONAMENTO `< /dev/urandom`, que e o que faz o leitor
# nunca parar. A primeira versao desta assertiva filtrava linhas com `head -c` e
# por isso passava verde no mutante: o padrao defeituoso TAMBEM tem `head -c` —
# na saida, que e justamente onde ele nao resolve. O jeito certo de ler a fonte
# e `head -c N /dev/urandom` (limite na ENTRADA, sem `<`).
t "nenhuma leitura sem limite de /dev/urandom (o gerador nao pode depender de SIGPIPE)"
# Comentarios ficam de fora porque o proprio af_random_token DOCUMENTA o padrao
# defeituoso para explicar por que ele saiu — a guarda mira codigo, nao prosa.
sem_limite="$(grep -n '< *\/dev\/urandom' "$REPO_ROOT/install.sh" | grep -v '^[0-9]*:[[:space:]]*#' || true)"
if [ -z "$sem_limite" ]; then ok; else no "leitura infinita de /dev/urandom: $sem_limite"; fi

t "af_random_token entrega o comprimento pedido"
out="$(run_case -- 'printf "%s" "$(af_random_token 20)" | wc -c | tr -d " "')"
assert_eq "$out" "20"
out="$(run_case -- 'printf "%s" "$(af_random_token 48)" | wc -c | tr -d " "')"
assert_eq "$out" "48"

t "e respeita a classe de caracteres pedida"
out="$(run_case -- 'case "$(af_random_token 32 "a-z0-9")" in *[!a-z0-9]*) printf SUJO ;; *) printf LIMPO ;; esac')"
assert_eq "$out" "LIMPO"

t "e o registro nasce ilegivel para os outros"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!senha9
  ls -l "$AF_KEPT_VOLUMES" | cut -c1-10')"
case "$out" in *-rw-------*) ok ;; *) no "permissao frouxa num arquivo com senha: $out" ;; esac

# O diretorio faz parte da chave: reconhecer so o nome do volume seria a adocao
# silenciosa que a guarda existe para impedir.
t "mas NAO em outro diretorio — adocao silenciosa continua barrada"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!s9
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/Outro || printf BARRADO')"
case "$out" in *BARRADO*) ok ;; *) no "adotou volume de outro diretorio: $out" ;; esac

t "e o reuso e de UMA vez, nao permissao eterna"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!s9
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/AtlasFile >/dev/null
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/AtlasFile || printf CONSUMIDO')"
case "$out" in *CONSUMIDO*) ok ;; *) no "o registro sobreviveu ao reuso: $out" ;; esac

# Apagado o indice, nao ha reuso a prometer.
t "apagar o volume esquece o registro"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!s9
  af_kept_volume_forget atlasfile_opensearch_data
  af_kept_volume_claim  atlasfile_opensearch_data /home/x/AtlasFile || printf ESQUECIDO')"
case "$out" in *ESQUECIDO*) ok ;; *) no "registro sobreviveu ao purge: $out" ;; esac

# O registro so vale se SOBREVIVER ao rm-state, que apaga o manifesto no fim da
# desinstalacao. Ele mora no mesmo diretorio de proposito: o `rmdir` falha com
# ele dentro, e e isso que o mantem vivo para a instalacao seguinte.
t "o registro sobrevive ao rm-state da desinstalacao"
out="$(run_case -- '
  AF_STATE_DIR="$SANDBOX/estado"; AF_KEPT_VOLUMES="$AF_STATE_DIR/kept-volumes"
  AF_HOST_MANIFEST="$AF_STATE_DIR/host-prereqs"
  mkdir -p "$AF_STATE_DIR"; printf "docker\tcreated\n" > "$AF_HOST_MANIFEST"
  af_kept_volume_record atlasfile_opensearch_data /home/x/AtlasFile Af!s9
  UN_ACTIONS="rm-state"; LOG_FILE="$SANDBOX/log"; un_execute
  test -f "$AF_HOST_MANIFEST" || printf "MANIFESTO_FOI "
  test -f "$AF_KEPT_VOLUMES" && printf "REGISTRO_VIVO"')"
case "$out" in *"MANIFESTO_FOI REGISTRO_VIVO"*) ok ;; *) no "o registro nao sobreviveu: $out" ;; esac

# ── O socket do Docker que so responde com sudo ─────────────────────────────
# Medido numa VM Ubuntu limpa: logo apos instalar, o grupo `docker` ainda nao
# vale nesta sessao e `docker info` falha sem sudo. O un_collect trancava TODO o
# retrato atras dele, entao o plano dizia "0 container(s)" com cinco no ar e o
# VOLUME sumia das duas secoes — junto com a garantia de que o usuario decide
# sobre o indice. E a janela exata em que alguem desinstala.
make_sandbox
t "o shim alcanca o socket quando ele so responde com sudo"
out="$(run_case STUB_RC_docker=1 -- 'af_docker_shim_linux && docker info && printf SHIM_OK' 2>&1)"
case "$out" in *SHIM_OK*) ok ;; *) no "nao instalou o shim: $out" ;; esac

t "e desiste calado quando nem com sudo responde"
out="$(run_case STUB_RC_docker=1 STUB_RC_sudo=1 -- 'af_docker_shim_linux || printf SEM_SHIM' 2>&1)"
case "$out" in *SEM_SHIM*) ok ;; *) no "devia desistir: $out" ;; esac

# O shim e READ-ONLY: quem desinstala nao pode adicionar ninguem a grupo nenhum
# nem gravar artefato. Isso separa af_docker_shim_linux de
# ensure_docker_group_linux, que faz as duas coisas de proposito.
# USER vem definido de proposito: sem ele o `env -i` da bancada faz um usermod
# introduzido por engano morrer em "unbound variable", e a guarda reprovaria
# pelo motivo ERRADO — parecendo verde sobre um efeito colateral que ela nunca
# chegou a medir.
t "o shim nao mexe em grupo nem escreve manifesto"
out="$(run_case STUB_RC_docker=1 USER=teste -- '
  AF_HOST_MANIFEST="$SANDBOX/host-prereqs"
  af_docker_shim_linux
  printf "USERMOD:%s " "$(grep -c usermod "$CALLS" || true)"
  printf "MANIFESTO:%s" "$(test -f "$AF_HOST_MANIFEST" && echo sim || echo nao)"' 2>&1)"
case "$out" in *"USERMOD:0 MANIFESTO:nao"*) ok ;; *) no "teve efeito colateral: $out" ;; esac

# A stack nao saiu: apagar o clone e o manifesto DEPOIS disso deixa containers,
# volume e imagens orfaos SEM ferramenta para remove-los. Medido numa VM Ubuntu.
t "a execucao PARA quando a stack nao sai, e o clone sobrevive"
out="$(run_case -- '
  C="$SANDBOX/c9"; mkdir -p "$C/.git"; printf "x\n" > "$C/docker-compose.yml"
  AF_STATE_DIR="$SANDBOX/estado"; AF_HOST_MANIFEST="$AF_STATE_DIR/host-prereqs"
  mkdir -p "$AF_STATE_DIR"; printf "docker\tcreated\n" > "$AF_HOST_MANIFEST"
  UN_DIR="$C"; LOG_FILE="$SANDBOX/log"
  un_compose_down() { return 1; }
  UN_ACTIONS="compose-down
rm-clone
rm-state"
  un_execute
  test -d "$C" && printf "CLONE_VIVO "
  test -f "$AF_HOST_MANIFEST" && printf "MANIFESTO_VIVO"' 2>&1)"
case "$out" in *"CLONE_VIVO MANIFESTO_VIVO"*) ok ;; *) no "seguiu apagando apos a falha: $out" ;; esac

t "e diz que parou de proposito, em vez de sumir com o assunto"
printf '%s' "$out" | grep -q 'stopping here, on purpose' && ok || no "nao explicou a parada: $out"

t "o plano diz O QUE suja o clone, nao so que esta sujo"
out="$(run_case PATH=/usr/bin:/bin -- '
  C="$SANDBOX/c1"; mkdir -p "$C"; cd "$C"; git init -q
  git config user.email t@t; git config user.name t
  printf "x\n" > docker-compose.yml; git add -A; git commit -qm base
  touch meu_rascunho.md
  un_collect "$C"
  UN_DIR="$C"; UN_CLONE_STATE=created; UN_DIR_RECORDED="$C"; UN_COMPOSE_FILE=1
  un_build_plan 0 0 0; printf "%s" "$UN_PLAN_KEEP"')"
printf '%s' "$out" | grep -q 'meu_rascunho.md' && ok || no "nao nomeou o que suja: $out"

t "e resume acima do teto, em vez de empurrar o plano para fora da tela"
out="$(run_case PATH=/usr/bin:/bin -- '
  C="$SANDBOX/c2"; mkdir -p "$C"; cd "$C"; git init -q
  git config user.email t@t; git config user.name t
  printf "x\n" > docker-compose.yml; git add -A; git commit -qm base
  for i in 1 2 3 4 5 6 7 8; do touch "arquivo_$i.md"; done
  un_collect "$C"; UN_DIR="$C"; un_dirty_lines')"
n="$(printf '%s\n' "$out" | grep -c ' - arquivo_' || true)"
[ "$n" = "5" ] && ok || no "mostrou $n caminho(s), esperava o teto de 5"
printf '%s' "$out" | grep -q 'and 3 more' && ok || no "nao resumiu o resto: $out"

# Item que o plano promete em SEPARADO se confirma em separado, mesmo sumindo
# junto com outra coisa. Mesma regra ja aplicada ao volume.
t "backups removidos com a pasta sao confirmados na execucao"
out="$(run_case -- '
  C="$SANDBOX/c3"; mkdir -p "$C/.git"; printf "x\n" > "$C/docker-compose.yml"
  touch "$C/.env.backup.20260101000000" "$C/.env.backup.20260202000000"
  UN_DIR="$C"; LOG_FILE="$SANDBOX/log"
  UN_ENV_BACKUP=".env.backup.20260101000000,.env.backup.20260202000000"
  UN_ACTIONS="rm-clone"
  un_execute; printf "CONTAGEM:%s" "$UN_OK"' 2>&1)"
printf '%s' "$out" | grep -q '2 .env backup(s) removed with the folder' \
  && ok || no "nao confirmou os backups: $out"
case "$out" in *CONTAGEM:2*) ok ;; *) no "esperava 2 no placar (pasta + backups): $out" ;; esac

# Sem backup nenhum a linha nao pode aparecer: confirmar o que nao aconteceu e
# tao ruim quanto calar o que aconteceu.
t "sem backups, nenhuma linha de backup e inventada"
out="$(run_case -- '
  C="$SANDBOX/c4"; mkdir -p "$C/.git"; printf "x\n" > "$C/docker-compose.yml"
  UN_DIR="$C"; LOG_FILE="$SANDBOX/log"; UN_ENV_BACKUP=""
  UN_ACTIONS="rm-clone"
  un_execute' 2>&1)"
printf '%s' "$out" | grep -q 'backup' && no "inventou linha de backup: $out" || ok

# Quem fecha o trilho e quem o ABRIU. Delegado, o trilho e do install.ps1 e o
# diagnostico roda dentro de uma regua dele — um `╰──` aqui fecharia a tela do
# orquestrador no meio. Foi uma REGRESSAO introduzida ao fazer o --doctor fechar
# o trilho, e so apareceu auditando o ps1 antes do teste no Windows.
t "delegado, o lado WSL nunca fecha o trilho do orquestrador"
for modo in "--doctor" "--dry-run"; do
  saida="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TERM=dumb \
      TTY_DEV=/dev/null bash "$REPO_ROOT/install.sh" $modo --delegated --dir "$SANDBOX" 2>&1 || true)"
  if printf '%s' "$saida" | grep -q '╰──'; then
    no "modo ${modo} --delegated fechou o trilho que nao e dele"
  else
    ok
  fi
done

# `pull --ff-only` recusa historico divergente, e recusar esta certo — morrer
# ali e que nao. Num Windows 11 real o clone estava num commit de um historico
# reescrito e a instalacao parou em "Not possible to fast-forward, aborting".
make_sandbox
af_repo_divergente() { # <dir_do_clone> — remoto com historico REESCRITO
  # HEAD do bare fixado em main: sem isto o nome do ramo default vem da config
  # da MAQUINA (init.defaultBranch). Num runner sem config global o bare nasce
  # apontando para master, o clone sai SEM working tree e o --ff-only avanca
  # sozinho — o cenario nem chega a divergir, e o teste passava por acidente.
  ( cd "$SANDBOX" && git init -q --bare "remoto_$1.git" \
    && git -C "remoto_$1.git" symbolic-ref HEAD refs/heads/main
    git clone -q "remoto_$1.git" "origem_$1" 2>/dev/null
    cd "origem_$1" && git config user.email t@t && git config user.name t
    printf 'v1\n' > f.txt && git add -A && git commit -qm v1 && git branch -M main && git push -q origin main
  ) >/dev/null 2>&1
  git clone -q "$SANDBOX/remoto_$1.git" "$SANDBOX/$1" >/dev/null 2>&1
  ( cd "$SANDBOX/origem_$1" && git checkout -q --orphan novo \
    && printf 'v2\n' > f.txt && git add -A && git commit -qm v2 \
    && git branch -M main && git push -qf origin main ) >/dev/null 2>&1
}

t "clone divergente e LIMPO e realinhado ao remoto"
af_repo_divergente c_limpo
out="$(run_case PATH=/usr/bin:/bin -- '
  AF_RESET_MARK="$SANDBOX/marca"
  af_update_clone "$SANDBOX/c_limpo" main >/dev/null 2>&1
  printf "%s|%s" "$(cat "$SANDBOX/c_limpo/f.txt")" "$([ -f "$SANDBOX/marca" ] && echo marcado || echo sem-marca)"')"
assert_eq "$out" "v2|marcado"

# O contrario importa mais: realinhar a forca por cima de trabalho do usuario
# seria destruicao silenciosa.
t "clone divergente com trabalho SEU e recusado, nomeando o arquivo"
af_repo_divergente c_sujo
touch "$SANDBOX/c_sujo/meu_trabalho.md"
out="$(run_case PATH=/usr/bin:/bin -- '
  rc=0; saida="$(af_update_clone "$SANDBOX/c_sujo" main 2>&1)" || rc=$?
  printf "rc=%s|%s|%s" "$rc" \
    "$(printf "%s" "$saida" | grep -c meu_trabalho.md)" \
    "$(cat "$SANDBOX/c_sujo/f.txt")"')"
assert_eq "$out" "rc=1|1|v1"

# Artefato NOSSO dentro do clone nao pode impedir o realinhamento: e a mesma
# lista que o plano de remocao consulta, e por isso ela e uma so.
t "artefato do proprio instalador nao impede o realinhamento"
af_repo_divergente c_nosso
touch "$SANDBOX/c_nosso/.env" "$SANDBOX/c_nosso/.env.backup.20260101000000"
mkdir -p "$SANDBOX/c_nosso/config" && touch "$SANDBOX/c_nosso/config/api_keys.json"
out="$(run_case PATH=/usr/bin:/bin -- '
  manifest_set "$SANDBOX/c_nosso/$AF_MANIFEST_NAME" env_backup .env.backup.20260101000000
  af_update_clone "$SANDBOX/c_nosso" main >/dev/null 2>&1
  printf "%s" "$(cat "$SANDBOX/c_nosso/f.txt")"')"
assert_eq "$out" "v2"

# O orquestrador ja MOSTROU o plano (via --plan-only) e o usuario ja confirmou.
# Reimprimi-lo na execucao fazia a mesma lista aparecer duas vezes na tela do
# Windows, com a pergunta no meio.
make_sandbox
t "delegado e ja autorizado, o plano nao e reimpresso"
out="$(run_case -- "${PLAN_FACTS}
  DELEGATED=1; ASSUME_YES=1; PURGE_DATA=--keep-data; TTY_DEV=/dev/null
  run_uninstall" 2>&1 || true)"
n="$(printf '%s\n' "$out" | grep -c 'WILL BE REMOVED' || true)"
[ "$n" = "0" ] && ok || no "reimprimiu o plano ${n}x na execucao ja confirmada"

t "mas quem NAO delega continua vendo o plano antes de confirmar"
out="$(run_case -- "${PLAN_FACTS}
  DELEGATED=0; ASSUME_YES=1; PURGE_DATA=--keep-data; TTY_DEV=/dev/null
  run_uninstall" 2>&1 || true)"
printf '%s' "$out" | grep -q 'WILL BE REMOVED' && ok || no "sumiu o plano de quem confirma na tela"

# Desinstalar com nada instalado NAO e erro. Abortar com codigo 1 fazia o
# orquestrador dizer "could not read the removal plan" e parar, deixando o
# Docker Desktop instalado — medido num Windows 11 real.
make_sandbox
t "delegado e sem instalacao, o plano sai e o codigo e 0"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TERM=dumb TTY_DEV=/dev/null \
    bash "$REPO_ROOT/install.sh" --uninstall --delegated --remove-deps --plan-only \
    --dir "$SANDBOX/nao-existe" 2>&1)"
rc=$?
[ "$rc" = "0" ] && ok || no "saiu com $rc em vez de 0"
printf '%s' "$out" | grep -q 'ATLASFILE_FACT: actions=0' && ok || no "nao declarou actions=0: $out"
printf '%s' "$out" | grep -q 'ATLASFILE_UNINSTALL: plan-only' && ok || no "sem a sentinela"

t "sem delegacao, continua sendo erro nomear a pasta errada"
env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TERM=dumb TTY_DEV=/dev/null \
    bash "$REPO_ROOT/install.sh" --uninstall --plan-only --dir "$SANDBOX/nao-existe" >/dev/null 2>&1 \
    && no "aceitou calado uma pasta que nao existe" || ok

# Sob captura (que e como o install.ps1 roda a desinstalacao, para ler o plano e
# a sentinela) `[ -t 1 ]` e falso e a cor sumia inteira — a tela saia branca do
# "Execute the plan above?" em diante. Quem tem o console e o orquestrador.
make_sandbox
t "cor informada pelo orquestrador acende sem tty"
out="$(env -i HOME="$SANDBOX" PATH=/usr/bin:/bin TERM=xterm-256color COLORTERM=truecolor \
    ATLASFILE_FORCE_COLOR=1 REPO_ROOT="$REPO_ROOT" bash -c '
    export ATLASFILE_INSTALL_LIB=1; source "$REPO_ROOT/install.sh"
    printf "%s|%s|%s" "$COLOR_OK" "$TRUECOLOR" "$IS_TTY"')"
assert_eq "$out" "1|1|0"

# E so a COR: forcar interatividade seria acordar barra e spinner numa saida que
# ninguem esta olhando ao vivo.
t "mas a interatividade continua medida, nao informada"
out="$(env -i HOME="$SANDBOX" PATH=/usr/bin:/bin TERM=xterm-256color COLORTERM=truecolor \
    ATLASFILE_FORCE_COLOR=1 REPO_ROOT="$REPO_ROOT" bash -c '
    export ATLASFILE_INSTALL_LIB=1; source "$REPO_ROOT/install.sh"
    bar_capable && echo capaz || echo incapaz')"
assert_eq "$out" "incapaz"

t "sem a variavel, nada muda para quem nao tem tty"
out="$(env -i HOME="$SANDBOX" PATH=/usr/bin:/bin TERM=xterm-256color COLORTERM=truecolor \
    REPO_ROOT="$REPO_ROOT" bash -c '
    export ATLASFILE_INSTALL_LIB=1; source "$REPO_ROOT/install.sh"
    printf "%s" "$COLOR_OK"')"
assert_eq "$out" "0"

# NO_COLOR continua mandando: informar capacidade nao pode atropelar a vontade
# explicita de quem roda.
t "NO_COLOR vence a cor informada"
out="$(env -i HOME="$SANDBOX" PATH=/usr/bin:/bin TERM=xterm-256color COLORTERM=truecolor \
    ATLASFILE_FORCE_COLOR=1 NO_COLOR=1 REPO_ROOT="$REPO_ROOT" bash -c '
    export ATLASFILE_INSTALL_LIB=1; source "$REPO_ROOT/install.sh"
    printf "%s" "$COLOR_OK"')"
assert_eq "$out" "0"

# Rede fora nao e defeito da maquina de quem instala, e despejar doze linhas de
# Dockerfile e stack de Go faz parecer que e.
make_sandbox
t "falha de rede e explicada, nao despejada"
printf 'target mcp: failed to solve: failed to fetch anonymous token: dial tcp [2606::1]:443: connect: network is unreachable\n' > "$SANDBOX/log_rede"
out="$(run_case -- 'LOG_FILE="$SANDBOX/log_rede"; ( fail_with_log "building images" ) 2>&1 || true')"
printf '%s' "$out" | grep -q 'NETWORK problem' && ok || no "nao reconheceu a rede: $out"
printf '%s' "$out" | grep -q 're-running continues' && ok || no "nao disse que reexecutar e seguro"

t "e um erro comum NAO vira falha de rede"
printf 'ERROR: syntax error in Dockerfile line 3\n' > "$SANDBOX/log_comum"
out="$(run_case -- 'LOG_FILE="$SANDBOX/log_comum"; ( fail_with_log "building images" ) 2>&1 || true')"
printf '%s' "$out" | grep -q 'NETWORK problem' && no "falso positivo: $out" || ok

t "o rabo do log continua saindo, em qualquer caso"
printf '%s' "$out" | grep -q 'last log lines' && ok || no "escondeu o log"

t "a barra viva é apagada antes de qualquer mensagem"
# Sem isto a barra vira sujeira no meio do texto — a mesma disciplina que mantém
# o spinner longe da saída de terceiro.
out="$(run_case -- 'BAR_VISIBLE=1; info hello' 2>&1 | head -1)"
case "$out" in $'\r'*) ok ;; *) no "a mensagem não apagou a barra antes: [$out]" ;; esac

# Um trap de EXIT registrado no corpo da biblioteca acompanharia quem faz
# `source` — e um EXIT trap num shell já morto por SIGPIPE vira "write error"
# no meio dos testes. O trap é do instalador rodando, não da biblioteca.
t "carregar como biblioteca nao instala trap de EXIT em quem carregou"
out="$(run_case -- 'trap -p EXIT' 2>&1)"
[ -z "$out" ] && ok || no "o source vazou um trap: [$out]"

# ── Fatos do outro lado da fronteira (install.ps1 → --host-extra) ───────────
# O plano impresso aqui descrevia SÓ a distro, enquanto o install.ps1 removia
# pacotes do Windows logo depois: numa máquina real ele disse "Docker preserved"
# segundos antes de apagar o Docker Desktop, e o Ollama não apareceu em NENHUMA
# das duas seções. Agora os fatos do outro lado entram no mesmo plano.
make_sandbox
t "um fato do Windows marcado created entra em REMOVED, sem gerar ação"
out="$(run_case -- "${PLAN_FACTS}
  HOST_EXTRA='docker=created'
  un_build_plan 0 1 0; printf 'R:%s|A:%s' \"\$UN_PLAN_REMOVE\" \"\$UN_ACTIONS\"")"
case "$out" in *"Docker Desktop (Windows side), installed by AtlasFile"*) ok ;; *) no "fato do Windows ausente do plano: [$out]" ;; esac
case "$out" in *"brew-cask"*|*"pkg-docker"*) no "o lado Linux planejou ação para um pacote do Windows" ;; *) ok ;; esac

t "o lado Linux não contradiz o fato do Windows sobre o mesmo Docker"
case "$out" in *"Docker was already on this machine"*) no "duas frases sobre o mesmo Docker no mesmo plano" ;; *) ok ;; esac

make_sandbox
t "um fato do Windows marcado preexisting entra em PRESERVED"
out="$(run_case -- "${PLAN_FACTS}
  HOST_EXTRA='docker=preexisting,wsl=created'
  un_build_plan 0 1 0; printf 'K:%s|A:%s' \"\$UN_PLAN_KEEP\" \"\$UN_ACTIONS\"")"
case "$out" in *"Docker Desktop (Windows side) was already on this machine"*) ok ;; *) no "preexisting não foi preservado explicitamente: [$out]" ;; esac
case "$out" in *"WSL2 — never removed automatically"*) ok ;; *) no "o WSL precisa aparecer como preservado, não como aviso pós-ação" ;; esac

make_sandbox
t "sem --remove-deps o fato do Windows aparece, dizendo como reverter"
out="$(run_case -- "${PLAN_FACTS}
  HOST_EXTRA='ollama=created'
  un_build_plan 0 0 0; printf '%s' \"\$UN_PLAN_KEEP\"")"
case "$out" in *"Ollama (Windows side), installed by AtlasFile"*) ok ;; *) no "sumiu do plano sem --remove-deps: [$out]" ;; esac
case "$out" in *"--remove-deps"*) ok ;; *) no "não disse como revertê-lo" ;; esac

# Era ASSIM que o Ollama sumia: chave ausente do manifesto caía fora de todos os
# ramos e não produzia frase nenhuma, nem em REMOVED nem em PRESERVED.
make_sandbox
t "chave desconhecida com a ferramenta presente produz frase, nunca silêncio"
out="$(run_case -- "${PLAN_FACTS}
  UN_OLLAMA_PRESENT=1
  un_build_plan 0 1 0; printf '%s' \"\$UN_PLAN_KEEP\"")"
case "$out" in *"Ollama is on this machine but was not installed by AtlasFile"*) ok ;; *) no "chave desconhecida seguiu silenciosa: [$out]" ;; esac

make_sandbox
t "sem Ollama na máquina o plano não inventa uma linha sobre ele"
out="$(run_case -- "${PLAN_FACTS}
  UN_OLLAMA_PRESENT=0
  un_build_plan 0 1 0; printf '%s' \"\$UN_PLAN_KEEP\"")"
case "$out" in *Ollama*) no "falou de um Ollama que não existe aqui: [$out]" ;; *) ok ;; esac

# ── Fluxo completo do uninstall: plan-only, cancelamento e delegação ────────
# Monta uma instalação de mentira com volume, para o plano ter o que dizer.
make_uninstall_sandbox() {
  make_sandbox
  mkdir -p "${SANDBOX}/inst"
  printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
  cat > "${SANDBOX}/bin/docker" <<EOF
#!/usr/bin/env bash
echo "docker \$*" >> "${CALLS}"
case "\$1 \$2" in
  "volume ls") echo "inst_opensearch_data" ;;
  "ps -aq") echo "deadbeef" ;;
esac
exit 0
EOF
  chmod +x "${SANDBOX}/bin/docker"
}

run_uninstaller() { # <args...> — script inteiro, TTY_DEV é um arquivo de respostas
  env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV="${SANDBOX}/tty_in" \
    bash "$REPO_ROOT/install.sh" --uninstall --dir "${SANDBOX}/inst" "$@" 2>&1
}

# A sentinela e conversa entre os dois instaladores; numa desinstalacao direta
# quem le a tela e uma pessoa. E a barra conta FASES da instalacao: nos fluxos
# sem fase ela aparecia como "fase 0/5" depois da ultima mensagem.
make_uninstall_sandbox
printf 'n\n' > "${SANDBOX}/tty_in"
t "desinstalacao direta nao vaza linha de protocolo nem barra de fase"
out="$(run_uninstaller || true)"
case "$out" in *ATLASFILE_UNINSTALL*) no "vazou a sentinela para o usuario" ;; *) ok ;; esac
case "$out" in *"fase 0/"*) no "desenhou barra de fase num fluxo sem fase" ;; *) ok ;; esac
case "$out" in *"nothing was touched"*) ok ;; *) no "nao disse que nada foi tocado: [$out]" ;; esac

make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "--uninstall --dry-run mostra o plano de remocao sem tocar em nada"
out="$(run_uninstaller --dry-run || true)"
case "$out" in *"Removal plan"*) ok ;; *) no "nao imprimiu o plano: [$out]" ;; esac
case "$out" in *"nothing was touched"*) ok ;; *) no "nao declarou que nada foi tocado" ;; esac
# As linhas de maquina sao do PROTOCOLO entre os dois instaladores; na tela de
# quem digitou --dry-run elas sao ruido.
case "$out" in *ATLASFILE_FACT*|*ATLASFILE_UNINSTALL*) no "vazou linha de protocolo para o usuario" ;; *) ok ;; esac
assert_not_contains "$CALLS" "compose.*down"

make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "--plan-only imprime o plano, não pergunta nada e não executa nada"
out="$(run_uninstaller --plan-only || true)"
case "$out" in *"Removal plan"*) ok ;; *) no "não imprimiu o plano: [$out]" ;; esac
case "$out" in *"ATLASFILE_UNINSTALL: plan-only"*) ok ;; *) no "sem a sentinela de plan-only" ;; esac
case "$out" in *"Execute the plan above?"*) no "perguntou no modo que existe para não perguntar" ;; *) ok ;; esac
case "$out" in *"still your call"*) ok ;; *) no "escondeu que a decisão do volume segue aberta" ;; esac
assert_not_contains "$CALLS" "compose.*down"

# O defeito que motivou tudo: responder "n" devolvia 0, e o install.ps1 leu isso
# como sucesso e apagou o Docker Desktop de uma máquina cujo dono tinha dito não.
make_uninstall_sandbox
printf 'n\n' > "${SANDBOX}/tty_in"
t "cancelar devolve código próprio (10) e a sentinela de cancelado"
rc=0; out="$(run_uninstaller --delegated)" || rc=$?
assert_eq "$rc" "10"
case "$out" in *"ATLASFILE_UNINSTALL: cancelled"*) ok ;; *) no "sem a sentinela de cancelamento: [$out]" ;; esac
case "$out" in *"nothing was touched"*) ok ;; *) no "não disse que nada foi tocado" ;; esac
assert_not_contains "$CALLS" "compose.*down"

make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "execução confirmada emite a sentinela que o orquestrador exige"
rc=0; out="$(run_uninstaller --yes --keep-data --delegated)" || rc=$?
assert_eq "$rc" "0"
case "$out" in *"ATLASFILE_UNINSTALL: confirmed"*) ok ;; *) no "sem a sentinela de confirmação: [$out]" ;; esac
assert_contains "$CALLS" "compose --env-file.*down"

# Dois banners e dois vereditos na mesma execução: o primeiro veredito era falso,
# porque o lado Windows ainda tinha pacotes para remover.
make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "--delegated não desenha banner nem dá o veredito final"
out="$(run_uninstaller --yes --keep-data --delegated || true)"
case "$out" in *"Your documents have gravity"*) no "desenhou o banner numa execução delegada" ;; *) ok ;; esac
case "$out" in *"AtlasFile removed. What already existed"*) no "deu o veredito final que é do orquestrador" ;; *) ok ;; esac
case "$out" in *"ATLASFILE_UNINSTALL: confirmed"*) ok ;; *) no "a sentinela some quando delegado" ;; esac

# ── Leitura de linha: tecla de seta nao pode entrar na resposta ────────────
# Medido na maquina do usuario: com `read -r` puro as setas viraram bytes de
# escape DENTRO da resposta, o .env recebeu
# `PROJECTS_HOST_ROOT=\033[C\033[D\033[C...` e o compose derrubou a instalacao
# com "service api refers to undefined volume :".
make_sandbox
t "byte de controle nunca sobrevive a uma resposta"
printf '\033[C\033[D/Users/eu/Docs\033[D\n' > "${SANDBOX}/tty_in"
out="$(run_case -- 'TTY_DEV="$SANDBOX/tty_in"; af_read_line; printf "%s" "$AF_LINE"')"
assert_eq "$out" "/Users/eu/Docs"

t "resposta feita SO de tecla de seta vira vazio, e o default assume"
printf '\033[C\033[D\033[C\n' > "${SANDBOX}/tty_in"
out="$(run_case -- 'TTY_DEV="$SANDBOX/tty_in"; af_read_line; printf "[%s]" "${AF_LINE:-DEFAULT}"')"
assert_eq "$out" "[DEFAULT]"

t "resposta normal passa intacta"
printf '~/Desktop/Teste\n' > "${SANDBOX}/tty_in"
out="$(run_case -- 'TTY_DEV="$SANDBOX/tty_in"; af_read_line; printf "%s" "$AF_LINE"')"
assert_eq "$out" "~/Desktop/Teste"

# A funcao NAO pode escrever o valor no stdout: chamada dentro de $( ), o eco do
# readline ia para a substituicao e a digitacao do usuario sumia da tela.
make_sandbox
t "af_read_line nao imprime nada no stdout (o valor sai por AF_LINE)"
printf 'meu/caminho\n' > "${SANDBOX}/tty_in"
out="$(run_case -- 'TTY_DEV="$SANDBOX/tty_in"; af_read_line')"
assert_eq "$out" ""
out="$(run_case -- 'TTY_DEV="$SANDBOX/tty_in"; af_read_line; printf "%s" "$AF_LINE"')"
assert_eq "$out" "meu/caminho"

# A prova de verdade: sob um terminal real, o que se digita TEM de aparecer.
# Sem pty este caminho e intestavel — e foi exatamente ele que quebrou.
t "sob pty: a digitacao aparece, e o backspace nao come o prompt"
# Quatro defeitos seguidos moraram nesta unica pergunta, e nenhum deles e
# alcancavel sem um terminal de verdade. O ultimo: com o prompt impresso por
# fora, o readline achava que a linha comecava na coluna 0 e, ao apagar,
# redesenhava por cima do proprio prompt — a linha inteira sumia.
if command -v python3 >/dev/null 2>&1; then
  res="$(python3 - "$REPO_ROOT" <<'PYEOF'
import os, pty, select, time, sys, re
repo = sys.argv[1]
pid, fd = pty.fork()
if pid == 0:
    os.environ["ATLASFILE_INSTALL_LIB"] = "1"
    os.execv("/bin/bash", ["/bin/bash", "-c",
        'source "%s/install.sh"; TTY_DEV=/dev/tty; af_read_line "$(ask "pasta: ")"; printf "\\nFIM[%%s]" "$AF_LINE"' % repo])
buf = b""; passo = 0; fim = time.time() + 12
while time.time() < fim:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try: d = os.read(fd, 4096)
        except OSError: break
        if not d: break
        buf += d
        if passo == 0 and b"pasta:" in buf:
            time.sleep(0.3); os.write(fd, b"/tmp/errado"); passo = 1
            time.sleep(0.4); os.write(fd, b"\x7f" * 6)
            time.sleep(0.4); os.write(fd, b"certo\n"); passo = 2
    elif passo == 2 and b"FIM" in buf:
        break
try: os.waitpid(pid, os.WNOHANG)
except ChildProcessError: pass
t = buf.decode("utf-8", "replace")
limpo = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", t)
m = re.search(r"FIM\[(.*?)\]", limpo, re.S)
valor = m.group(1) if m else ""
# o prompt so pode ter sido desenhado UMA vez: redesenhar significa ter apagado
print("valor=%s|promptvezes=%d|ecoou=%s" % (valor, limpo.count("pasta:"), "sim" if "/tmp/errado" in limpo else "nao"))
PYEOF
)"
  case "$res" in *"valor=/tmp/certo|"*) ok ;; *) no "backspace nao editou direito: [$res]" ;; esac
  case "$res" in *"|promptvezes=1|"*) ok ;; *) no "o prompt foi redesenhado (readline nao sabia a largura dele): [$res]" ;; esac
  case "$res" in *"ecoou=sim"*) ok ;; *) no "a digitacao nao apareceu na tela: [$res]" ;; esac
else
  ok; ok; ok   # sem python3 nao da para abrir pty; o contrato de stdout acima ja cobre
fi

# ── O portao do caminho: TODA origem passa por ele ─────────────────────────
# Duas instalacoes seguidas morreram em "service api refers to undefined volume"
# porque so a RESPOSTA da pergunta era validada. Na primeira o lixo entrou no
# .env; na segunda o `.env already exists - preserved` releu esse lixo e nem
# chegou a perguntar. Sao QUATRO origens (--projects-root, .env anterior, default
# e resposta) e o portao e um so.
make_sandbox
t "sequencia de tecla de seta e recusada, venha de onde vier"
run_case -- 'af_sane_path "$(printf "\033[C\033[D\033[C")"' >/dev/null 2>&1 \
  && no "aceitou um caminho feito so de escape" || ok

t "til e expandido a mao (nao expande dentro de variavel)"
out="$(run_case -- 'HOME=/tmp/casa af_sane_path "~/Docs"')"
assert_eq "$out" "/tmp/casa/Docs"

t "caminho relativo e recusado (viraria montagem errada no compose)"
run_case -- 'af_sane_path "Desktop/relativo"' >/dev/null 2>&1 \
  && no "aceitou caminho relativo" || ok

t "caminho absoluto normal passa intacto"
out="$(run_case -- 'af_sane_path "/Users/eu/Documentos"')"
assert_eq "$out" "/Users/eu/Documentos"

# O plano de remocao tambem le esse valor do .env: um .env corrompido nao pode
# fazer o plano falar de um caminho que nao existe.
t "un_collect nao propaga caminho corrompido vindo do .env"
make_sandbox
mkdir -p "${SANDBOX}/inst"
printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
printf 'PROJECTS_HOST_ROOT=\033[C\033[D\n' > "${SANDBOX}/inst/.env"
out="$(run_case -- 'un_collect "$SANDBOX/inst"; printf "[%s]" "$UN_PROJECTS_ROOT"')"
assert_eq "$out" "[]"

# ── Registros da ida e da volta: chave gravada tem de virar decisão ─────────
# `install_dir` era gravado e NUNCA lido — a garantia que o CHANGELOG anunciava
# ("a pasta só some se bater com o install_dir registrado") não existia.
make_sandbox
t "pasta que nao bate com o install_dir registrado nao e removida"
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR_RECORDED=/outro/lugar
  un_build_plan 0 0 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *rm-clone*) no "removeu uma pasta que o manifesto nao aponta" ;; *) ok ;; esac
case "$(achata "$out")" in *"records the install at /outro/lugar"*) ok ;; *) no "nao explicou por que preservou: [$out]" ;; esac

t "quando bate, a remocao segue normal"
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR_RECORDED=\"\$UN_DIR\"
  un_build_plan 0 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-clone*) ok ;; *) no "deixou de remover uma pasta legitima: [$out]" ;; esac

# api_keys.json guarda uma CHAVE DE API VIVA. Num clone preexistente a pasta
# inteira e preservada — e a chave ficava em disco depois de desinstalar.
make_sandbox
mkdir -p "${SANDBOX}/inst/config"
printf '{}\n' > "${SANDBOX}/inst/config/api_keys.json"
printf 'X=1\n' > "${SANDBOX}/inst/.env"
t "artefatos nossos dentro de pasta preservada entram no plano"
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR=\"\$SANDBOX/inst\"; UN_CLONE_STATE=unknown
  UN_APIKEYS_CREATED=created; UN_ENV_CREATED=created
  un_build_plan 0 0 0; printf 'A:%s|R:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_REMOVE\"")"
case "$out" in *rm-apikeys*) ok ;; *) no "a chave de API ficaria em disco: [$out]" ;; esac
case "$out" in *"holds a live API key"*) ok ;; *) no "nao disse que e uma credencial" ;; esac
case "$out" in *rm-env*) ok ;; *) no "o .env que criamos ficaria para tras" ;; esac

t "se a pasta inteira vai embora, nao ha acao separada para os arquivos"
out="$(run_case -- "${PLAN_FACTS}
  UN_DIR=\"\$SANDBOX/inst\"; UN_CLONE_STATE=created; UN_DIR_RECORDED=\"\$SANDBOX/inst\"
  UN_APIKEYS_CREATED=created; UN_ENV_CREATED=created
  un_build_plan 0 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-apikeys*|*rm-env*) no "acao redundante com o rm-clone: [$out]" ;; *) ok ;; esac

# `pending`: o instalador comecou a instalar e nao se sabe se terminou. Nao da
# para provar que criou — entao PRESERVA e diz, em vez de deixar orfao calado.
make_sandbox
t "estado pending preserva, explica, e nunca vira acao"
out="$(run_case -- "${PLAN_FACTS}
  host_set docker pending
  un_build_plan 0 1 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *brew-cask:docker-desktop*) no "removeu algo que nao pode provar ter criado" ;; *) ok ;; esac
case "$out" in *"interrupted while installing it"*) ok ;; *) no "nao avisou que mexeu ali: [$out]" ;; esac

# O unico mecanismo do mac_env_install.sh que faltava aqui: backup datado antes
# de reescrever um arquivo do usuario.
make_sandbox
mkdir -p "${SANDBOX}/clone"
printf 'PROJECTS_HOST_ROOT=/antigo\n' > "${SANDBOX}/clone/.env"
t "um .env preexistente e copiado antes de ser reescrito"
# `ls` sem -a NAO lista dotfile, e .env.backup.* comeca com ponto — a primeira
# versao deste teste contava zero e ainda "passava" a segunda assertiva por
# casar com a linha do info.
out="$(run_case -- 'cd "$SANDBOX/clone"; ENV_STATE=preexisting; AF_MANIFEST="$SANDBOX/clone/mf"
  backup_env_once >/dev/null; backup_env_once >/dev/null
  ls -a "$SANDBOX/clone" | grep -c "^\.env\.backup\."')"
assert_eq "$out" "1"
out="$(run_case -- 'cd "$SANDBOX/clone"; ENV_STATE=preexisting; AF_MANIFEST="$SANDBOX/clone/mf2"
  backup_env_once >/dev/null; manifest_get "$AF_MANIFEST" env_backup')"
case "$out" in .env.backup.*) ok ;; *) no "o backup nao foi registrado no manifesto: [$out]" ;; esac

t "um .env que nasceu agora nao gera backup"
make_sandbox
mkdir -p "${SANDBOX}/clone"
printf 'X=1\n' > "${SANDBOX}/clone/.env"
out="$(run_case -- 'cd "$SANDBOX/clone"; ENV_STATE=created; AF_MANIFEST="$SANDBOX/clone/mf"
  backup_env_once >/dev/null; ls -a "$SANDBOX/clone" | grep -c "^\.env\.backup\." || true')"
assert_eq "$out" "0"

# ── Modos de diagnóstico: leem a máquina, não a mudam ───────────────────────
make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "--doctor relata e nao muda nada"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --doctor --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in *"Prerequisites"*) ok ;; *) no "sem a secao de pre-requisitos: [$out]" ;; esac
case "$out" in *"Install manifest"*) ok ;; *) no "sem a secao do manifesto" ;; esac
case "$out" in *"Diagnosis"*) ok ;; *) no "sem o placar do diagnostico" ;; esac
assert_not_contains "$CALLS" "compose.*down"
assert_not_contains "$CALLS" "clone"

t "--doctor devolve != 0 quando algo esta quebrado"
# Um doctor que sempre sai 0 nao serve para automacao nenhuma.
#
# A ferramenta e quebrada pelo CODIGO DE SAIDA, nao removendo o stub: o runner
# Linux traz /usr/bin/docker, entao apagar o stub do sandbox nao simula ausencia
# nenhuma — o teste passava no macOS e reprovava no Linux. E a mesma licao que a
# bancada do Windows ja tinha aprendido com o ATLASFILE_FAKE_MISSING.
make_sandbox
rc=0; env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null STUB_RC_docker=1 \
  bash "$REPO_ROOT/install.sh" --doctor --dir "${SANDBOX}/nada" >/dev/null 2>&1 || rc=$?
[ "$rc" != "0" ] && ok || no "doctor saiu 0 com o docker quebrado"

make_sandbox
t "--dry-run diz o que faria e nao instala nada"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --dry-run --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in *"Install plan"*) ok ;; *) no "sem o plano de instalacao: [$out]" ;; esac
case "$out" in *"nothing was installed"*) ok ;; *) no "nao declarou que nada foi instalado" ;; esac
assert_not_contains "$CALLS" "clone"
assert_not_contains "$CALLS" "compose build"

# ── O --dry-run nao pode se contradizer sobre os pre-requisitos ────────────
# A tela mostrava `✘ Docker is installed but the daemon does not answer` e,
# quatro linhas abaixo, `✔ none — everything needed is already here`. A causa
# eram DUAS fontes de verdade sobre o mesmo fato: doc_prereqs pergunta ao daemon
# (e exige que a ferramenta RESPONDA --version, ver doc_version), enquanto o
# bloco de prerequisites do --dry-run repergunta com `command -v docker`, que
# tem sucesso com o daemon morto — e ate com um binario mudo.
#
# Stubs que respondem --version de verdade: sem isso doc_version os declara
# "not found" e o teste mediria a contradicao errada.
stub_ferramentas_reais() { # <dir de bin> — git e docker que se comportam
  cat > "${1}/git" <<'STUB'
#!/usr/bin/env bash
[ "$1" = "--version" ] && echo "git version 2.45.0"
exit 0
STUB
  cat > "${1}/docker" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  info)    exit "${STUB_DOCKER_INFO_RC:-0}" ;;
  compose) [ "$2" = "version" ] && echo "Docker Compose version v2.30.0"; exit 0 ;;
  *)       echo "Docker version 27.0.0, build abcdefg" ;;
esac
exit 0
STUB
  chmod +x "${1}/git" "${1}/docker"
}

make_sandbox
stub_ferramentas_reais "${SANDBOX}/bin"
t "--dry-run com o daemon morto nao anuncia que esta tudo pronto"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  STUB_DOCKER_INFO_RC=1 \
  bash "$REPO_ROOT/install.sh" --dry-run --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in
  *"daemon does not answer"*) ok ;;
  *) no "nao avisou que o daemon nao responde: [$out]" ;;
esac
case "$out" in
  *"everything needed is already here"*)
    no "contradicao: daemon morto E 'everything needed is already here' na mesma tela" ;;
  *) ok ;;
esac

# O contrapositivo, que impede a correcao preguicosa: com tudo no lugar a frase
# TEM de continuar aparecendo. Sem esta assercao, apagar a mensagem passaria.
make_sandbox
stub_ferramentas_reais "${SANDBOX}/bin"
t "--dry-run com tudo no lugar segue dizendo que nada falta"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --dry-run --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in
  *"everything needed is already here"*) ok ;;
  *) no "sumiu com a frase em vez de torna-la verdadeira: [$out]" ;;
esac

# ── Fase 4a: bundle da release + pull (sem clone) ───────────────────────────
# O caminho padrao deixa de clonar e compilar: baixa o bundle da release (4
# arquivos) e faz `docker compose pull`. A "release" da bancada e LOCAL: um
# tar.gz real com SHA256SUMS real, servido por um stub de curl que mapeia a URL
# para o arquivo — a extracao e a verificacao usam tar e sha de verdade.

af_release_local() { # <versao> — monta uma release local em $SANDBOX/releases
  local v="$1" R="${SANDBOX}/releases" raiz="${SANDBOX}/bundle_src/atlasfile-${1}"
  mkdir -p "$R" "${raiz}/config"
  printf 'services: {}\n# bundle v%s\n' "$v" > "${raiz}/docker-compose.yml"
  printf 'PROJECTS_HOST_ROOT=/path/to/Projects\nOPENSEARCH_PASSWORD=Troque-Esta!Senha123\nOPENSEARCH_INITIAL_ADMIN_PASSWORD=Troque-Esta!Senha123\nDASHBOARDS_COOKIE_PASSWORD=x\nATLASFILE_VERSION=%s\n' "$v" > "${raiz}/.env.example"
  printf '# dashboards v%s\n' "$v" > "${raiz}/config/opensearch_dashboards.yml"
  printf '{"keys": []}\n' > "${raiz}/config/api_keys.example.json"
  tar -czf "${R}/atlasfile-${v}-bundle.tar.gz" -C "${SANDBOX}/bundle_src" "atlasfile-${v}"
  ( cd "$R" && { command -v sha256sum >/dev/null 2>&1 \
      && sha256sum atlasfile-*-bundle.tar.gz || shasum -a 256 atlasfile-*-bundle.tar.gz; } > SHA256SUMS )
  printf '{\n  "tag_name": "v%s",\n  "name": "v%s"\n}\n' "$v" "$v" > "${R}/latest"
}

stub_curl_release() { # stub de curl: URL -> arquivo em $AF_FAKE_RELEASES, gravando em $CALLS
  cat > "${SANDBOX}/bin/curl" <<EOF
#!/usr/bin/env bash
echo "curl \$*" >> "${CALLS}"
[ "\${STUB_RC_curl:-0}" != "0" ] && exit "\${STUB_RC_curl}"
out=""; url=""
while [ \$# -gt 0 ]; do
  case "\$1" in
    -o) out="\$2"; shift 2 ;;
    http*) url="\$1"; shift ;;
    *) shift ;;
  esac
done
src="\${AF_FAKE_RELEASES}/\$(basename "\$url")"
[ -f "\$src" ] || exit 22
if [ -n "\$out" ]; then cp "\$src" "\$out"; else cat "\$src"; fi
EOF
  chmod +x "${SANDBOX}/bin/curl"
}

make_sandbox
t "af_validate_version aceita release e prerelease, recusa qualquer outra coisa"
run_case -- 'af_validate_version 1.0.0 && af_validate_version 1.1.0-rc.1' && ok || no "recusou versao legitima"
run_case -- 'af_validate_version "1.0.0|x"' >/dev/null 2>&1 && no "aceitou valor com pipe (quebraria o sed do set_env)" || ok
run_case -- 'af_validate_version latest' >/dev/null 2>&1 && no "aceitou 'latest' como versao" || ok
run_case -- 'af_validate_version ""' >/dev/null 2>&1 && no "aceitou vazio" || ok

t "af_version_lt compara versoes numericamente, nao como texto"
run_case -- 'af_version_lt 1.0.0 1.1.0' && ok || no "1.0.0 < 1.1.0 falhou"
run_case -- 'af_version_lt 1.1.0 1.0.0' && no "1.1.0 < 1.0.0 passou" || ok
run_case -- 'af_version_lt 1.0.0 1.0.0' && no "1.0.0 < 1.0.0 passou" || ok
run_case -- 'af_version_lt 1.9.0 1.10.0' && ok || no "comparou 1.9/1.10 como texto"

make_sandbox
af_release_local 9.9.9
stub_curl_release
t "af_resolve_version resolve a ultima release pelo JSON real da API"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- 'af_resolve_version')"
assert_eq "$out" "9.9.9"

t "resposta sem tag_name (rate limit) devolve erro, nunca lixo"
printf '{"message": "API rate limit exceeded", "documentation_url": "x"}\n' > "${SANDBOX}/releases/latest"
rc=0; out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- 'af_resolve_version')" || rc=$?
[ "$rc" != "0" ] && ok || no "rate limit virou sucesso"
[ -z "$out" ] && ok || no "devolveu lixo no rate limit: [$out]"

# O despacho e a decisao mais importante da fase: um dir com .git e a instancia
# REAL de quem instalou por clone, e o re-run nao pode arrasta-la para o bundle.
make_sandbox
t "af_source_mode: .git presente vai para fonte; sem .git, bundle; --from-source forca"
mkdir -p "${SANDBOX}/comgit/.git" "${SANDBOX}/semgit"
run_case -- 'INSTALL_DIR="$SANDBOX/comgit"; FROM_SOURCE=0; af_source_mode' && ok || no "dir com .git nao foi para o caminho fonte"
run_case -- 'INSTALL_DIR="$SANDBOX/semgit"; FROM_SOURCE=0; af_source_mode' && no "dir sem .git foi para o caminho fonte" || ok
run_case -- 'INSTALL_DIR="$SANDBOX/semgit"; FROM_SOURCE=1; af_source_mode' && ok || no "--from-source nao forcou o caminho fonte"

t "af_fresh_install_dir: manifesto ou .git contam como instalacao existente"
mkdir -p "${SANDBOX}/vazio"
run_case -- 'af_fresh_install_dir "$SANDBOX/vazio"' && ok || no "dir vazio nao e fresh"
run_case -- 'af_fresh_install_dir "$SANDBOX/comgit"' && no "dir com .git passou por fresh" || ok
run_case -- 'mkdir -p "$SANDBOX/commf"; : > "$SANDBOX/commf/.atlasfile-install-manifest"
  af_fresh_install_dir "$SANDBOX/commf"' && no "dir com manifesto passou por fresh (re-run de bundle seria barrado pelo guard de volume)" || ok

make_sandbox
af_release_local 9.9.9
stub_curl_release
t "af_fetch_bundle instala os 4 arquivos num dir novo e registra os hashes"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/instala"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 9.9.9 "$D" || { printf "ERRO:%s" "$AF_FETCH_ERR"; exit 1; }
  test -f "$D/docker-compose.yml" && test -f "$D/.env.example" \
    && test -f "$D/config/opensearch_dashboards.yml" && test -f "$D/config/api_keys.example.json" \
    && printf "ARQUIVOS "
  grep -q "bundle v9.9.9" "$D/docker-compose.yml" && printf "CONTEUDO "
  [ -n "$(manifest_get "$D/.atlasfile-install-manifest" bundle_sha)" ] && printf "SHAS"')"
case "$out" in *"ARQUIVOS CONTEUDO SHAS"*) ok ;; *) no "instalacao do bundle incompleta: [$out]" ;; esac
grep -q 'releases/download/v9.9.9/atlasfile-9.9.9-bundle.tar.gz' "$CALLS" && ok || no "nao baixou pela URL da release: $(cat "$CALLS")"

t "SHA adulterado reprova SEM extrair nada"
make_sandbox
af_release_local 9.9.9
stub_curl_release
# Wrapper de tar que REGISTRA e delega ao tar real: a propriedade nao e so "o
# dir ficou vazio", e "o tar nunca abriu um tarball de origem nao verificada".
# Sem esta prova, inverter a ordem (extrair antes de conferir o SHA) passaria.
cat > "${SANDBOX}/bin/tar" <<EOF
#!/usr/bin/env bash
echo "tar \$*" >> "${CALLS}"
exec /usr/bin/tar "\$@"
EOF
chmod +x "${SANDBOX}/bin/tar"
sed 's/^[0-9a-f]\{8\}/deadbeef/' "${SANDBOX}/releases/SHA256SUMS" > "${SANDBOX}/releases/SHA256SUMS.tmp" \
  && mv "${SANDBOX}/releases/SHA256SUMS.tmp" "${SANDBOX}/releases/SHA256SUMS"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/instala2"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  rc=0; af_fetch_bundle 9.9.9 "$D" || rc=$?
  printf "rc=%s|err=%s|arquivos=%s" "$rc" "$AF_FETCH_ERR" "$(ls -A "$D" | wc -l | tr -d " ")"')"
case "$out" in "rc=1|"*) ok ;; *) no "checksum adulterado passou: [$out]" ;; esac
case "$out" in *"checksum mismatch"*) ok ;; *) no "erro nao explica o checksum: [$out]" ;; esac
case "$out" in *"arquivos=0") ok ;; *) no "extraiu/instalou apesar do checksum ruim: [$out]" ;; esac
grep -q '^tar ' "$CALLS" && no "o tar foi aberto ANTES de o checksum reprovar: $(grep '^tar ' "$CALLS")" || ok

t "bundle com arquivo intruso e recusado sem tocar o dir de instalacao"
make_sandbox
af_release_local 7.7.7
printf 'malicia\n' > "${SANDBOX}/bundle_src/atlasfile-7.7.7/intruso.sh"
tar -czf "${SANDBOX}/releases/atlasfile-7.7.7-bundle.tar.gz" -C "${SANDBOX}/bundle_src" "atlasfile-7.7.7"
( cd "${SANDBOX}/releases" && { command -v sha256sum >/dev/null 2>&1 \
    && sha256sum atlasfile-*-bundle.tar.gz || shasum -a 256 atlasfile-*-bundle.tar.gz; } > SHA256SUMS )
stub_curl_release
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/instala3"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  rc=0; af_fetch_bundle 7.7.7 "$D" || rc=$?
  printf "rc=%s|err=%s|arquivos=%s" "$rc" "$AF_FETCH_ERR" "$(ls -A "$D" | wc -l | tr -d " ")"')"
case "$out" in "rc=1|"*"arquivos=0") ok ;; *) no "bundle com intruso foi aceito: [$out]" ;; esac
case "$out" in *"unexpected"*) ok ;; *) no "erro nao nomeia o conteudo inesperado: [$out]" ;; esac

t "bundle com symlink e recusado"
make_sandbox
af_release_local 6.6.6
ln -s /etc/passwd "${SANDBOX}/bundle_src/atlasfile-6.6.6/config/link_malicioso"
tar -czf "${SANDBOX}/releases/atlasfile-6.6.6-bundle.tar.gz" -C "${SANDBOX}/bundle_src" "atlasfile-6.6.6"
( cd "${SANDBOX}/releases" && { command -v sha256sum >/dev/null 2>&1 \
    && sha256sum atlasfile-*-bundle.tar.gz || shasum -a 256 atlasfile-*-bundle.tar.gz; } > SHA256SUMS )
stub_curl_release
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/instala4"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  rc=0; af_fetch_bundle 6.6.6 "$D" || rc=$?
  printf "rc=%s|arquivos=%s" "$rc" "$(ls -A "$D" | wc -l | tr -d " ")"')"
case "$out" in "rc=1|arquivos=0") ok ;; *) no "bundle com symlink foi aceito: [$out]" ;; esac

t "release inexistente (404) explica e aponta a lista de releases"
make_sandbox
mkdir -p "${SANDBOX}/releases"
stub_curl_release
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/instala5"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  rc=0; af_fetch_bundle 4.4.4 "$D" || rc=$?
  printf "rc=%s|%s" "$rc" "$AF_FETCH_ERR"')"
case "$out" in "rc=1|"*) ok ;; *) no "404 virou sucesso: [$out]" ;; esac
case "$out" in *"releases"*) ok ;; *) no "erro de 404 nao aponta onde achar versoes: [$out]" ;; esac

# O contrato do update, re-expresso para o mundo bundle: re-run idempotente,
# trabalho do usuario intocado, e arquivo NOSSO editado ganha backup nomeado
# antes de ser substituido (paridade com o clone, que recusa e nomeia).
make_sandbox
af_release_local 1.0.0
af_release_local 1.1.0
stub_curl_release
t "re-run com a mesma versao e idempotente e nao inventa backup"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/up"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 1.0.0 "$D" >/dev/null 2>&1 && af_fetch_bundle 1.0.0 "$D" >/dev/null 2>&1
  printf "backups=%s" "$(ls -A "$D" | grep -c ".backup." || true)"')"
assert_eq "$out" "backups=0"

t "update substitui os arquivos do bundle e preserva .env e arquivo do usuario"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/up2"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 1.0.0 "$D" >/dev/null 2>&1
  printf "MEU_ENV=1\n" > "$D/.env"; printf "rascunho\n" > "$D/minhas_notas.md"
  af_fetch_bundle 1.1.0 "$D" >/dev/null 2>&1
  grep -q "bundle v1.1.0" "$D/docker-compose.yml" && printf "NOVO "
  grep -q "MEU_ENV=1" "$D/.env" && printf "ENV_INTACTO "
  test -f "$D/minhas_notas.md" && printf "USUARIO_INTACTO"')"
case "$out" in *"NOVO ENV_INTACTO USUARIO_INTACTO"*) ok ;; *) no "o update clobberou o que nao e dele: [$out]" ;; esac

t "docker-compose.yml editado pelo usuario ganha backup nomeado antes do update"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/up3"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 1.0.0 "$D" >/dev/null 2>&1
  printf "services: {}\n# minha porta customizada\n" > "$D/docker-compose.yml"
  saida="$(af_fetch_bundle 1.1.0 "$D" 2>&1)"
  printf "backup=%s|" "$(ls -A "$D" | grep -c "docker-compose.yml.backup." || true)"
  printf "%s" "$saida" | grep -q "docker-compose.yml" && printf "AVISADO|"
  printf "%s" "$(manifest_get "$D/.atlasfile-install-manifest" bundle_backups)"')"
case "$out" in "backup=1|AVISADO|"*docker-compose.yml.backup.*) ok ;; *) no "edicao do usuario foi clobberada sem backup/aviso: [$out]" ;; esac

t "e update de arquivo NAO editado segue silencioso, sem backup"
out="$(run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/up4"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 1.0.0 "$D" >/dev/null 2>&1
  af_fetch_bundle 1.1.0 "$D" >/dev/null 2>&1
  printf "backups=%s" "$(ls -A "$D" | grep -c ".backup." || true)"')"
assert_eq "$out" "backups=0"

# A fase 4 nao pode compilar no caminho bundle nem puxar no caminho fonte.
make_sandbox
t "af_stack_up no caminho bundle faz pull e nunca build; no fonte, o contrario"
run_case -- 'AF_SOURCE_PATH=0; IS_TTY=0; LOG_FILE="$SANDBOX/log"; af_stack_up' >/dev/null 2>&1
grep -q 'compose -f docker-compose.yml pull' "$CALLS" && ok || no "bundle path nao fez pull: $(cat "$CALLS")"
grep -q 'build' "$CALLS" && no "bundle path compilou: $(cat "$CALLS")" || ok
: > "$CALLS"
run_case -- 'AF_SOURCE_PATH=1; IS_TTY=0; LOG_FILE="$SANDBOX/log"; af_stack_up' >/dev/null 2>&1
grep -q 'docker-compose.build.yml build' "$CALLS" && ok || no "caminho fonte nao compilou: $(cat "$CALLS")"
grep -q ' pull' "$CALLS" && no "caminho fonte fez pull: $(cat "$CALLS")" || ok

t "caminho bundle nunca chama git"
: > "$CALLS"
make_sandbox
af_release_local 9.9.9
stub_curl_release
run_case AF_FAKE_RELEASES="${SANDBOX}/releases" -- '
  D="$SANDBOX/semgit2"; mkdir -p "$D"; LOG_FILE="$SANDBOX/log"
  af_fetch_bundle 9.9.9 "$D"' >/dev/null 2>&1
grep -q '^git ' "$CALLS" && no "o bundle path tocou o git: $(cat "$CALLS")" || ok

# Downgrade e decisao do usuario, nunca um default: headless recusa.
make_sandbox
t "af_downgrade_gate: headless recusa; interativo respeita a resposta"
rc=0; run_case -- 'ASSUME_YES=1; TTY_DEV=/dev/null; af_downgrade_gate 1.0.0 1.1.0' >/dev/null 2>&1 || rc=$?
[ "$rc" != "0" ] && ok || no "downgrade passou sem confirmacao headless"
printf 'y\n' > "${SANDBOX}/tty_in"
rc=0; run_case -- 'ASSUME_YES=0; TTY_DEV="$SANDBOX/tty_in"; af_downgrade_gate 1.0.0 1.1.0' >/dev/null 2>&1 || rc=$?
[ "$rc" = "0" ] && ok || no "downgrade confirmado com y foi recusado"
printf 'n\n' > "${SANDBOX}/tty_in"
rc=0; run_case -- 'ASSUME_YES=0; TTY_DEV="$SANDBOX/tty_in"; af_downgrade_gate 1.0.0 1.1.0' >/dev/null 2>&1 || rc=$?
[ "$rc" != "0" ] && ok || no "downgrade recusado com n seguiu adiante"

t "e um update normal nao pergunta nada"
rc=0; run_case -- 'ASSUME_YES=1; TTY_DEV=/dev/null; af_downgrade_gate 1.1.0 1.0.0' >/dev/null 2>&1 || rc=$?
[ "$rc" = "0" ] && ok || no "update normal caiu na guarda de downgrade"

# ── Uninstall no mundo bundle ───────────────────────────────────────────────
make_sandbox
t "repo_clone=bundle com manifesto batendo e dir limpo entra no plano de remocao"
out="$(run_case -- "${PLAN_FACTS}
  UN_CLONE_STATE=bundle; UN_DIR_RECORDED=\"\$UN_DIR\"
  un_build_plan 0 0 0; printf '%s' \"\$UN_ACTIONS\"")"
case "$out" in *rm-clone*) ok ;; *) no "instalacao bundle legitima nao e removivel: [$out]" ;; esac

t "bundle com install_dir divergente NAO e removido (mesma guarda do clone)"
out="$(run_case -- "${PLAN_FACTS}
  UN_CLONE_STATE=bundle; UN_DIR_RECORDED=/outro/lugar
  un_build_plan 0 0 0; printf 'A:%s|K:%s' \"\$UN_ACTIONS\" \"\$UN_PLAN_KEEP\"")"
case "$out" in *rm-clone*) no "removeu com manifesto apontando outro lugar" ;; *) ok ;; esac
case "$(achata "$out")" in *"records the install at /outro/lugar"*) ok ;; *) no "nao explicou a preservacao: [$out]" ;; esac

t "arquivo estranho num dir bundle preserva a pasta e nomeia o intruso"
make_sandbox
mkdir -p "${SANDBOX}/binst/config"
printf 'services: {}\n' > "${SANDBOX}/binst/docker-compose.yml"
printf 'x\n' > "${SANDBOX}/binst/.env.example"
printf 'x\n' > "${SANDBOX}/binst/config/opensearch_dashboards.yml"
printf '{}\n' > "${SANDBOX}/binst/config/api_keys.example.json"
printf 'X=1\n' > "${SANDBOX}/binst/.env"
printf 'meu\n' > "${SANDBOX}/binst/meu_tcc.docx"
out="$(run_case -- '
  mf="$SANDBOX/binst/.atlasfile-install-manifest"
  manifest_set "$mf" repo_clone bundle
  manifest_set "$mf" install_dir "$SANDBOX/binst"
  manifest_set "$mf" bundle_files "docker-compose.yml,.env.example,config/opensearch_dashboards.yml,config/api_keys.example.json"
  un_collect "$SANDBOX/binst"
  un_build_plan 0 0 0
  printf "sujo=%s|A:%s|K:%s" "$UN_DIR_DIRTY" "$UN_ACTIONS" "$UN_PLAN_KEEP"')"
case "$out" in "sujo=1|"*) ok ;; *) no "o intruso nao sujou o dir bundle: [$out]" ;; esac
case "$out" in *rm-clone*) no "removeu a pasta com arquivo do usuario dentro" ;; *) ok ;; esac
printf '%s' "$out" | grep -q 'meu_tcc.docx' && ok || no "nao nomeou o intruso: [$out]"

t "e um dir bundle so com artefatos nossos segue removivel"
rm -f "${SANDBOX}/binst/meu_tcc.docx"
out="$(run_case -- '
  un_collect "$SANDBOX/binst"
  un_build_plan 0 0 0; printf "sujo=%s|%s" "$UN_DIR_DIRTY" "$UN_ACTIONS"')"
case "$out" in "sujo=0|"*rm-clone*) ok ;; *) no "artefato nosso travou a remocao do dir bundle: [$out]" ;; esac

t "backup de compose feito pelo update nao conta como intruso"
out="$(run_case -- '
  mf="$SANDBOX/binst/.atlasfile-install-manifest"
  touch "$SANDBOX/binst/docker-compose.yml.backup.20260101000000"
  manifest_set "$mf" bundle_backups docker-compose.yml.backup.20260101000000
  un_collect "$SANDBOX/binst"
  printf "sujo=%s" "$UN_DIR_DIRTY"')"
assert_eq "$out" "sujo=0"

t "sem manifesto, dir bundle e preservado com explicacao (stack ainda sai)"
make_sandbox
mkdir -p "${SANDBOX}/orfao"
printf 'services: {}\n' > "${SANDBOX}/orfao/docker-compose.yml"
out="$(run_case -- '
  un_collect "$SANDBOX/orfao"
  UN_COMPOSE_FILE=1; UN_CONTAINERS=1
  un_build_plan 0 0 0; printf "A:%s|K:%s" "$UN_ACTIONS" "$UN_PLAN_KEEP"')"
case "$out" in *compose-down*) ok ;; *) no "sem manifesto nem a stack saiu: [$out]" ;; esac
case "$out" in *rm-clone*) no "sem manifesto removeu a pasta assim mesmo" ;; *) ok ;; esac
case "$out" in *"not created by this installer"*) ok ;; *) no "nao explicou a preservacao: [$out]" ;; esac

# Pos-4a a instalacao padrao tem UMA imagem, a do GHCR. Se o un_collect so a
# enxergar na companhia das legadas, o uninstall novo vaza ~290 MB em silencio.
t "uninstall enxerga a imagem GHCR quando ela e a UNICA imagem da instalacao"
make_sandbox
mkdir -p "${SANDBOX}/inst"
printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
cat > "${SANDBOX}/bin/docker" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
  "image inspect") exit 1 ;;
  "images --format") printf 'ghcr.io/aleonnet/atlasfile:1.1.0\nopensearchproject/opensearch:2.17.1\n' ;;
esac
exit 0
EOF
chmod +x "${SANDBOX}/bin/docker"
out="$(run_case -- 'un_collect "$SANDBOX/inst"; printf "%s" "$UN_IMAGES"')"
case "$out" in *"ghcr.io/aleonnet/atlasfile:1.1.0"*) ok ;; *) no "imagem GHCR unica fora do plano — uninstall vazaria a imagem: [$out]" ;; esac
case "$out" in *opensearchproject*) no "imagem upstream entrou no plano: [$out]" ;; *) ok ;; esac

t "un_dir_is_safe aceita instalacao bundle (compose file, sem .git)"
make_sandbox
mkdir -p "${SANDBOX}/binst2"
printf 'services: {}\n' > "${SANDBOX}/binst2/docker-compose.yml"
run_case -- 'un_dir_is_safe "$SANDBOX/binst2"' && ok || no "recusou uma instalacao bundle legitima"

t "--doctor reconhece uma instalacao bundle como criada por este instalador"
make_sandbox
mkdir -p "${SANDBOX}/binst3"
printf 'services: {}\n' > "${SANDBOX}/binst3/docker-compose.yml"
printf 'X=1\n' > "${SANDBOX}/binst3/.env"
out="$(run_case -- '
  mf="$SANDBOX/binst3/.atlasfile-install-manifest"
  manifest_set "$mf" repo_clone bundle
  manifest_set "$mf" bundle_files "docker-compose.yml"' >/dev/null 2>&1
  env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --doctor --dir "${SANDBOX}/binst3" 2>&1 || true)"
case "$out" in *"release bundle"*"--uninstall"*) ok ;; *) no "--doctor nao reconhece instalacao bundle (diria que preserva o que ele remove): [$out]" ;; esac
case "$out" in *"NOT created by this installer"*) no "--doctor mente sobre a proveniencia do dir bundle" ;; *) ok ;; esac

# ── Flags novas ─────────────────────────────────────────────────────────────
t "--version exige valor e explica quando ele falta"
out="$(bash "$REPO_ROOT/install.sh" --version 2>&1)" && no "--version sem valor passou" || ok
case "$out" in *"--version"*) ok ;; *) no "erro sem mensagem acionavel: [$out]" ;; esac
out="$(bash "$REPO_ROOT/install.sh" --version --help 2>&1)" && no "--version comendo a flag seguinte passou" || ok

t "--from-source e --version passam pelo parser"
bash "$REPO_ROOT/install.sh" --from-source --help >/dev/null 2>&1 && ok || no "--from-source recusado"
bash "$REPO_ROOT/install.sh" --version 1.0.0 --help >/dev/null 2>&1 && ok || no "--version 1.0.0 recusado"

t "--branch e --repo-url continuam aceitos (o install.ps1 os encaminha)"
bash "$REPO_ROOT/install.sh" --branch x --repo-url y --help >/dev/null 2>&1 && ok || no "flags de fonte recusadas"

t "--doctor nao resolve release nem baixa bundle"
make_sandbox
stub_curl_release
env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null AF_FAKE_RELEASES="${SANDBOX}/releases" \
  bash "$REPO_ROOT/install.sh" --doctor --dir "${SANDBOX}/nada" >/dev/null 2>&1 || true
grep -q 'releases' "$CALLS" && no "o --doctor tocou a rede de releases: $(cat "$CALLS")" || ok

# ── Porta configuravel (ATLASFILE_PORT e familia) ───────────────────────────
# O binding era literal no compose e nao havia mecanismo nenhum de override:
# conflito de porta = beco sem saida. A porta efetiva resolve por precedencia
# flag > env > .env > default, e TODA URL impressa deriva dela.
t "--port passa pelo parser e exige valor valido"
bash "$REPO_ROOT/install.sh" --port 8090 --help >/dev/null 2>&1 && ok || no "--port 8090 recusado pelo parser"
out="$(bash "$REPO_ROOT/install.sh" --port 2>&1)" && no "--port sem valor passou" || ok
case "$out" in *"--port"*) ok ;; *) no "erro de --port sem mensagem acionavel: [$out]" ;; esac
out="$(bash "$REPO_ROOT/install.sh" --port abc --help 2>&1)" && no "--port abc passou" || ok
out="$(bash "$REPO_ROOT/install.sh" --port 0 --help 2>&1)" && no "--port 0 passou (fora de 1-65535)" || ok
out="$(bash "$REPO_ROOT/install.sh" --port 70000 --help 2>&1)" && no "--port 70000 passou (fora de 1-65535)" || ok

t "af_resolve_app_port: precedencia flag > env > .env > default"
make_sandbox
mkdir -p "${SANDBOX}/inst"
printf 'ATLASFILE_PORT=7777\n' > "${SANDBOX}/inst/.env"
out="$(run_case -- 'INSTALL_DIR="$SANDBOX/inst"; AF_PORT_FLAG=8090; ATLASFILE_PORT=9999 af_resolve_app_port; printf "%s" "$AF_PORT"')"
assert_eq "$out" "8090"
out="$(run_case ATLASFILE_PORT=9999 -- 'INSTALL_DIR="$SANDBOX/inst"; AF_PORT_FLAG=""; af_resolve_app_port; printf "%s" "$AF_PORT"')"
assert_eq "$out" "9999"
out="$(run_case -- 'INSTALL_DIR="$SANDBOX/inst"; AF_PORT_FLAG=""; af_resolve_app_port; printf "%s" "$AF_PORT"')"
assert_eq "$out" "7777"
out="$(run_case -- 'INSTALL_DIR="$SANDBOX/vazio"; AF_PORT_FLAG=""; af_resolve_app_port; printf "%s" "$AF_PORT"')"
assert_eq "$out" "8000"

t "e um .env corrompido nao propaga lixo para a porta"
printf 'ATLASFILE_PORT=abc;rm\n' > "${SANDBOX}/inst/.env"
out="$(run_case -- 'INSTALL_DIR="$SANDBOX/inst"; AF_PORT_FLAG=""; af_resolve_app_port; printf "%s" "$AF_PORT"')"
assert_eq "$out" "8000"

# Fiacao REAL da guarda: o script inteiro roda, o lsof do sandbox declara a
# porta ocupada, e a falha tem de citar a porta EFETIVA (do .env) e ensinar a
# saida (--port). Antes desta fase a mensagem era so "free it before
# installing" — beco sem saida.
t "conflito na porta do .env falha citando a porta efetiva e ensinando --port"
make_sandbox
mkdir -p "${SANDBOX}/inst"
printf 'services: {}\n' > "${SANDBOX}/inst/docker-compose.yml"
printf 'ATLASFILE_PORT=8090\n' > "${SANDBOX}/inst/.env"
cat > "${SANDBOX}/bin/lsof" <<EOF
#!/usr/bin/env bash
echo "lsof \$*" >> "${CALLS}"
exit 0
EOF
# ss tambem: a guarda prefere ss (Linux; o lsof sem root nao enxerga socket de
# outro usuario — achado do E2E na lima). No macOS nao ha ss e o lsof responde.
cat > "${SANDBOX}/bin/ss" <<EOF
#!/usr/bin/env bash
echo "ss \$*" >> "${CALLS}"
printf 'LISTEN 0 4096 0.0.0.0:8000 0.0.0.0:*\nLISTEN 0 4096 0.0.0.0:8090 0.0.0.0:*\nLISTEN 0 4096 0.0.0.0:8123 0.0.0.0:*\nLISTEN 0 4096 127.0.0.1:9200 0.0.0.0:*\n'
EOF
chmod +x "${SANDBOX}/bin/lsof" "${SANDBOX}/bin/ss"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --yes --no-open --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in *"port 8090 is already in use"*) ok ;; *) no "nao citou a porta efetiva do .env: [$out]" ;; esac
case "$out" in *"--port"*) ok ;; *) no "a falha nao ensina a saida (--port): [$out]" ;; esac
grep -qE 'ss -ltn|lsof -iTCP:8090' "$CALLS" && ok || no "a guarda nao consultou ss/lsof: $(grep -E 'ss |lsof ' "$CALLS")"

t "e a porta do flag vence a do .env na guarda"
: > "$CALLS"
out="$(env -i HOME="$SANDBOX" PATH="${SANDBOX}/bin:/usr/bin:/bin" TTY_DEV=/dev/null \
  bash "$REPO_ROOT/install.sh" --yes --no-open --port 8123 --dir "${SANDBOX}/inst" 2>&1 || true)"
case "$out" in *"port 8123 is already in use"*) ok ;; *) no "o flag nao venceu o .env: [$out]" ;; esac

t "af_persist_port grava a porta explicita no .env e nao pina o default"
make_sandbox
mkdir -p "${SANDBOX}/inst"; printf 'X=1\n' > "${SANDBOX}/inst/.env"
out="$(run_case -- 'cd "$SANDBOX/inst"; AF_MANIFEST="$SANDBOX/inst/mf"; ENV_STATE=preexisting
  AF_PORT=8090; AF_PORT_EXPLICIT=1; af_persist_port >/dev/null
  grep "^ATLASFILE_PORT=" .env')"
assert_eq "$out" "ATLASFILE_PORT=8090"
out="$(run_case -- 'cd "$SANDBOX/inst"; AF_MANIFEST="$SANDBOX/inst/mf"; ENV_STATE=preexisting
  AF_PORT=8000; AF_PORT_EXPLICIT=0; af_persist_port >/dev/null
  grep -c "^ATLASFILE_PORT=8000" .env || true')"
case "$out" in *0*) ok ;; *) no "pinou o default 8000 sem o usuario pedir" ;; esac

# Guarda de FONTE (precedente do /dev/urandom acima): as URLs de painel,
# espera e browser tem de DERIVAR da porta efetiva. A tela nao alcanca o
# painel na bancada (exigiria a stack no ar), entao a propriedade e provada
# na fonte: nenhum http://localhost:8000 literal em codigo executavel.
t "nenhuma URL literal de localhost:8000 sobrevive em codigo do install.sh"
hardcoded="$(grep -n 'http://localhost:8000' "$REPO_ROOT/install.sh" | grep -v '^[0-9]*:[[:space:]]*#' || true)"
[ -z "$hardcoded" ] && ok || no "URL com porta literal em codigo: $hardcoded"
t "e o mesmo para a porta 9200 do OpenSearch na guarda e no doctor"
hardcoded="$(grep -nE 'in 8000 9200|iTCP:"?9200' "$REPO_ROOT/install.sh" | grep -v '^[0-9]*:[[:space:]]*#' || true)"
[ -z "$hardcoded" ] && ok || no "porta 9200 literal na guarda/doctor: $hardcoded"

# Achado do E2E da 4a numa VM real: um uninstall parcial anterior (pasta suja
# preservada) remove o .env; a re-execucao com --force morria na interpolacao
# de QUALQUER variavel `:?` do compose — a v1.0.0 so cobria ATLASFILE_VERSION.
# O stub grava o AMBIENTE que enxerga: e a unica forma de provar o placeholder
# sem rodar o docker compose real (a interpolacao acontece dentro dele).
# A entrega tem de ser por --env-file, nunca por export: na VM real o docker
# roda atras do shim de sudo (grupo docker ainda nao vale na sessao) e o sudo
# LIMPA o ambiente — o placeholder exportado nunca chegava ao compose. O
# arquivo viaja com o comando e sobrevive ao sudo; o stub le o env-file que
# recebeu, exatamente como o compose faria.
t "un_compose_down sem .env supre TODAS as variaveis :? via --env-file"
make_sandbox
mkdir -p "${SANDBOX}/semenv"
printf 'services: {}\n' > "${SANDBOX}/semenv/docker-compose.yml"
cat > "${SANDBOX}/bin/docker" <<EOF
#!/usr/bin/env bash
tudo="\$*"; envfile=""
while [ \$# -gt 0 ]; do case "\$1" in --env-file) envfile="\$2"; shift 2 ;; *) shift ;; esac; done
AV=vazio; OP=vazio; DC=vazio; PH=vazio
if [ -n "\$envfile" ] && [ -f "\$envfile" ]; then
  AV="\$(grep '^ATLASFILE_VERSION=' "\$envfile" | cut -d= -f2-)"; AV="\${AV:-vazio}"
  OP="\$(grep '^OPENSEARCH_INITIAL_ADMIN_PASSWORD=' "\$envfile" | cut -d= -f2-)"; OP="\${OP:-vazio}"
  DC="\$(grep '^DASHBOARDS_COOKIE_PASSWORD=' "\$envfile" | cut -d= -f2-)"; DC="\${DC:-vazio}"
  PH="\$(grep '^PROJECTS_HOST_ROOT=' "\$envfile" | cut -d= -f2-)"; PH="\${PH:-vazio}"
fi
echo "docker \$tudo [AV=\$AV|OP=\$OP|DC=\$DC|PH=\$PH]" >> "${CALLS}"
exit 0
EOF
chmod +x "${SANDBOX}/bin/docker"
rc=0; run_case -- 'UN_DIR="$SANDBOX/semenv"; UN_ACTIONS=""; un_compose_down' >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0"
if grep -q 'compose --env-file.*down' "$CALLS" && ! grep -q 'vazio' "$CALLS"; then ok
else no "variavel :? nao chegou pelo env-file ao compose down: $(cat "$CALLS")"; fi

t "e com .env completo, os valores do usuario viajam no env-file, sem placeholder"
printf 'ATLASFILE_VERSION=1.0.0\nOPENSEARCH_INITIAL_ADMIN_PASSWORD=MinhaSenha\nDASHBOARDS_COOKIE_PASSWORD=MeuCookie\n' > "${SANDBOX}/semenv/.env"
: > "$CALLS"
run_case -- 'UN_DIR="$SANDBOX/semenv"; UN_ACTIONS=""; un_compose_down' >/dev/null 2>&1
if grep -q 'OP=MinhaSenha' "$CALLS" && ! grep -q '0\.0\.0' "$CALLS"; then ok
else no "placeholder atropelou (ou perdeu) o valor do usuario: $(cat "$CALLS")"; fi

# Update cross-branch do caminho fonte — achado 1 da fase 3: o clone raso nasce
# com refspec so de main, e `--branch outra` morria em "unknown revision".
make_sandbox
t "update cross-branch: --branch diferente do clone passa a funcionar"
( cd "$SANDBOX" && git init -q --bare rb.git && git -C rb.git symbolic-ref HEAD refs/heads/main
  git clone -q rb.git rb_src 2>/dev/null
  cd rb_src && git config user.email t@t && git config user.name t
  printf 'm1\n' > f.txt && git add -A && git commit -qm m1 && git branch -M main && git push -q origin main
  git checkout -qb feature && printf 'vf\n' > f.txt && git add -A && git commit -qm vf \
  && git push -q origin feature ) >/dev/null 2>&1
git clone -q --depth 1 --branch main "file://${SANDBOX}/rb.git" "${SANDBOX}/rb_clone" >/dev/null 2>&1
out="$(run_case PATH=/usr/bin:/bin -- '
  af_update_clone "$SANDBOX/rb_clone" feature >/dev/null 2>&1
  cat "$SANDBOX/rb_clone/f.txt"')"
assert_eq "$out" "vf"

printf '\n%d passed, %d failed\n' "$PASS" "$FAILED"
[ "$FAILED" = "0" ]
