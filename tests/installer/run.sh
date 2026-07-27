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
}
ok() { PASS=$((PASS+1)); }
no() { FAILED=$((FAILED+1)); printf 'FAIL: %s — %s\n' "$CURRENT" "$1"; }
assert_eq() { if [ "$1" = "$2" ]; then ok; else no "expected [$2] got [$1]"; fi; }
assert_contains() { if grep -q "$2" "$1" 2>/dev/null; then ok; else no "calls log missing [$2]"; fi; }
assert_not_contains() { if grep -q "$2" "$1" 2>/dev/null; then no "calls log has forbidden [$2]"; else ok; fi; }

make_sandbox() {
  SANDBOX="$(mktemp -d)"
  CALLS="${SANDBOX}/calls.log"; : > "$CALLS"
  mkdir -p "${SANDBOX}/bin"
  # stub factory: records invocation, exits per STUB_RC_<name>
  for name in brew docker git sudo apt-get dnf systemctl open ollama; do
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
    assert_eq "$out" "mac:none:${exp_prefix}" ;;
  *)
    printf '%s' "$out" | grep -q '^linux:' && ok || no "expected linux:* got [$out]" ;;
esac

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
case "$out" in *"NEVER removed automatically"*) ok ;; *) no "no note about Homebrew" ;; esac

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

# Varredura mecanica: NENHUMA linha de mensagem pode escapar da calha. Tres
# vezes seguidas um ponto esquecido apareceu na tela do usuario — a pergunta da
# pasta, e depois as cinco linhas da fase 3.
t "nenhum printf de mensagem usa o prefixo antigo de dois espacos"
fora="$(grep -n "printf '  %s" "$REPO_ROOT/install.sh" | grep -v 'GUT' || true)"
[ -z "$fora" ] && ok || no "linha(s) fora da calha: $fora"

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
assert_not_contains "$CALLS" "compose down"

make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "--plan-only imprime o plano, não pergunta nada e não executa nada"
out="$(run_uninstaller --plan-only || true)"
case "$out" in *"Removal plan"*) ok ;; *) no "não imprimiu o plano: [$out]" ;; esac
case "$out" in *"ATLASFILE_UNINSTALL: plan-only"*) ok ;; *) no "sem a sentinela de plan-only" ;; esac
case "$out" in *"Execute the plan above?"*) no "perguntou no modo que existe para não perguntar" ;; *) ok ;; esac
case "$out" in *"still your call"*) ok ;; *) no "escondeu que a decisão do volume segue aberta" ;; esac
assert_not_contains "$CALLS" "compose down"

# O defeito que motivou tudo: responder "n" devolvia 0, e o install.ps1 leu isso
# como sucesso e apagou o Docker Desktop de uma máquina cujo dono tinha dito não.
make_uninstall_sandbox
printf 'n\n' > "${SANDBOX}/tty_in"
t "cancelar devolve código próprio (10) e a sentinela de cancelado"
rc=0; out="$(run_uninstaller --delegated)" || rc=$?
assert_eq "$rc" "10"
case "$out" in *"ATLASFILE_UNINSTALL: cancelled"*) ok ;; *) no "sem a sentinela de cancelamento: [$out]" ;; esac
case "$out" in *"nothing was touched"*) ok ;; *) no "não disse que nada foi tocado" ;; esac
assert_not_contains "$CALLS" "compose down"

make_uninstall_sandbox
: > "${SANDBOX}/tty_in"
t "execução confirmada emite a sentinela que o orquestrador exige"
rc=0; out="$(run_uninstaller --yes --keep-data --delegated)" || rc=$?
assert_eq "$rc" "0"
case "$out" in *"ATLASFILE_UNINSTALL: confirmed"*) ok ;; *) no "sem a sentinela de confirmação: [$out]" ;; esac
assert_contains "$CALLS" "compose down"

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
case "$out" in *"records the install at /outro/lugar"*) ok ;; *) no "nao explicou por que preservou: [$out]" ;; esac

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
assert_not_contains "$CALLS" "compose down"
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

printf '\n%d passed, %d failed\n' "$PASS" "$FAILED"
[ "$FAILED" = "0" ]
