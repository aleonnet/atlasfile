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

# ── ensure_ollama: presence first ───────────────────────────────────────────
make_sandbox
t "ensure_ollama returns 100 when ollama is on PATH"
rc=0; run_case -- 'OS_KIND=mac; ensure_ollama' || rc=$?
assert_eq "$rc" "100"
assert_not_contains "$CALLS" "brew install --cask ollama"

# ── ollama_pull_model: skip when already pulled ─────────────────────────────
make_sandbox
cat > "${SANDBOX}/bin/ollama" <<EOF
#!/usr/bin/env bash
echo "ollama \$*" >> "${CALLS}"
if [ "\$1" = "list" ]; then printf 'NAME ID SIZE\ngemma4:12b abc 8GB\n'; fi
exit 0
EOF
chmod +x "${SANDBOX}/bin/ollama"
t "ollama_pull_model skips pull when model already present"
run_case -- 'IS_TTY=0; LOG_FILE="$SANDBOX/log"; ollama_pull_model gemma4:12b' >/dev/null
assert_not_contains "$CALLS" "ollama pull"

# ── flag parser (full script run with --help exits before any action) ───────
t "flag parser accepts the new flags (--help path proves parse phase)"
if bash "$REPO_ROOT/install.sh" --install-deps --with-ollama --ollama-model x --bootstrap-only --help >/dev/null 2>&1; then ok; else no "--help with new flags failed"; fi

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

printf '\n%d passed, %d failed\n' "$PASS" "$FAILED"
[ "$FAILED" = "0" ]
