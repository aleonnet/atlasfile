#!/usr/bin/env python3
"""Guarda de consistencia dos instaladores: fonte x bancada x ajuda.

Existe porque "revisei o instalador inteiro" nao e verificavel por leitura. O
defeito nao mora dentro de um arquivo, mora na RELACAO entre eles -- e foi
exatamente ali que ele passou: as primitivas de UI mudaram as mensagens do
install.ps1 de PT-BR para en-US e quatro assertivas da bancada continuaram
procurando o texto antigo, sem que nada verificasse esse vinculo.

Tres checagens, todas mecanicas:

  1. assertiva de bancada x fonte
     Toda assertiva sobre a SAIDA do instalador (o que o usuario le) precisa
     casar, como regex, com o fonte correspondente. Assertiva sobre o log de
     chamadas dos stubs -- (Calls) no PowerShell -- e isenta: ali o texto e a
     linha de comando montada em runtime, e os argumentos vivem em arrays.

  2. ajuda x argumentos aceitos
     Flag prometida na ajuda tem que ser aceita pelo parser, e flag publica
     aceita pelo parser tem que aparecer na ajuda. Flag deliberadamente oculta
     se declara com "# hidden" na propria linha do parser.

  3. funcao declarada e nunca chamada
     Conta os usos no instalador E na bancada dele -- funcao que so a bancada
     chama e seam de teste, nao codigo morto. Sem essa contagem cruzada, a
     checagem acusaria falso positivo (foi o que ocorreu com af_frame_plain).

Uso: python3 tests/installer/check_consistency.py   (sai 1 se houver divergencia)
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SH, SH_BENCH = "install.sh", "tests/installer/run.sh"
PS, PS_BENCH = "install.ps1", "tests/installer/win/run.ps1"


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def option_flags(text):
    """Flags de um bloco de ajuda: so o token que ABRE a linha de opcao.

    Sem essa ancora, o regex varre a prosa e colhe 'curl -fsSL', 'Write-Host',
    'non-interactive' como se fossem flags.
    """
    found = set()
    for line in text.splitlines():
        m = re.match(r'\s{2,}(-{1,2}[A-Za-z][A-Za-z-]*)((?:,\s*-{1,2}[A-Za-z][A-Za-z-]*)*)', line)
        if m:
            found.add(m.group(1))
            found.update(re.findall(r'-{1,2}[A-Za-z][A-Za-z-]*', m.group(2) or ""))
    return found


def check_assertions(problems):
    """1. assertiva de bancada x fonte."""
    specs = (
        # Assert-Match "rotulo" $out "padrao" | Assert-Match "rotulo" (Calls) "padrao"
        (PS_BENCH, PS, r'Assert-Match\s+"[^"]*"\s+(?P<target>\$\w+|\(Calls\))\s+"(?P<needle>[^"]+)"', r'[Cc]alls'),
        # assert_contains "rotulo" "padrao" -- no bash a saida e o unico alvo
        (SH_BENCH, SH, r'assert_contains\s+"[^"]*"\s+"(?P<target>)(?P<needle>[^"]+)"', r'^\x00$'),
    )
    for bench_rel, src_rel, pattern, exempt in specs:
        bench, src = read(bench_rel), read(src_rel)
        for lineno, line in enumerate(bench.splitlines(), 1):
            m = re.search(pattern, line)
            if not m or re.search(exempt, m.group("target")):
                continue
            needle = m.group("needle")
            try:
                if not re.search(needle, src, re.I):
                    problems.append("%s:%d  assertiva /%s/ nao existe no %s"
                                    % (bench_rel, lineno, needle, src_rel))
            except re.error as exc:
                problems.append("%s:%d  assertiva /%s/ e regex invalida: %s"
                                % (bench_rel, lineno, needle, exc))


def check_flags(problems):
    """2. ajuda x argumentos aceitos, nos dois instaladores."""
    sh = read(SH)
    i = sh.find("usage()")
    documented = option_flags(sh[i:i + 3000])
    arms = sh[sh.find('case "$1" in'):]
    arms = arms[:arms.find("esac")]
    parsed = {}
    for line in arms.splitlines():
        m = re.match(r'\s*([-a-z|]+)\)', line)
        if not m:
            continue
        for flag in m.group(1).split("|"):
            if flag.startswith("-"):
                parsed[flag] = "hidden" if "hidden" in line else "public"
    for flag in sorted(documented - set(parsed)):
        problems.append("%s  ajuda promete %s, que o parser nao aceita" % (SH, flag))
    for flag in sorted(f for f, vis in parsed.items() if vis == "public" and f not in documented):
        problems.append("%s  parser aceita %s, ausente da ajuda (marque '# hidden' se for intencional)"
                        % (SH, flag))

    ps = read(PS)
    block = ps[ps.find("param("):]
    block = block[:block.find(")\n")]
    params = set(re.findall(r'\$([A-Za-z]+)', block))
    j = ps.find("function Show-Usage")
    shown = option_flags(ps[j:j + 2500])
    header = option_flags(ps[:1400])
    for flag in sorted(f for f in shown | header if f.lstrip("-") not in params):
        problems.append("%s  ajuda cita %s, que nao existe no param()" % (PS, flag))
    for name in sorted(p for p in params if "-" + p not in shown):
        problems.append("%s  param -%s nao aparece no Show-Usage" % (PS, name))


def check_dead_functions(problems):
    """3. funcao declarada e nunca chamada -- contando a bancada."""
    specs = (
        (SH, SH_BENCH, r'^([a-z_][a-z0-9_]*)\(\)'),
        (PS, PS_BENCH, r'^function\s+([A-Za-z][A-Za-z-]*)'),
    )
    for src_rel, bench_rel, pattern in specs:
        src, bench = read(src_rel), read(bench_rel)
        for name in re.findall(pattern, src, re.M):
            word = r'\b' + re.escape(name) + r'\b'
            if len(re.findall(word, src)) + len(re.findall(word, bench)) < 2:
                problems.append("%s  funcao %s e declarada e nunca chamada (nem pela bancada)"
                                % (src_rel, name))


def main():
    problems = []
    check_assertions(problems)
    check_flags(problems)
    check_dead_functions(problems)
    for p in problems:
        print(p)
    if problems:
        print("\n%d divergencia(s) entre instalador, bancada e ajuda" % len(problems))
        return 1
    print("instaladores consistentes: assertivas casam com o fonte, ajuda casa com o parser, sem funcao morta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
