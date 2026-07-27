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


def usage_block_sh(text):
    """Bloco de ajuda do install.sh, delimitado pelo FIM do heredoc.

    Antes isto era uma fatia de 3000 caracteres a partir de `usage()`. Numero
    magico envelhece: bastou a ajuda crescer para a janela invadir o parser e
    cortar `--projects-root` ao meio, acusando uma flag `--pr` inexistente.
    """
    i = text.find("usage()")
    if i < 0:
        return ""
    j = text.find("\nEOF\n", i)
    return text[i:j] if j > 0 else text[i:]


def usage_block_ps(text):
    """Bloco de ajuda do install.ps1, delimitado pelo fim da here-string."""
    i = text.find("function Show-Usage")
    if i < 0:
        return ""
    j = text.find('"@', i)
    return text[i:j] if j > 0 else text[i:]


def header_block_ps(text):
    """Comentario de cabecalho do install.ps1: termina onde comeca o param()."""
    j = text.find("param(")
    return text[:j] if j > 0 else text[:1400]


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
        #
        # O install.ps1 e um ORQUESTRADOR: ele imprime o plano que recebeu do
        # install.sh rodando dentro do WSL. Entao uma assertiva sobre a saida
        # dele pode legitimamente cobrar texto do OUTRO fonte, e as duas fontes
        # entram na checagem. Isentar seria mais simples e deixaria a assertiva
        # sem guarda nenhuma -- que e exatamente o buraco por onde quatro
        # assertivas ficaram para tras numa traducao.
        (PS_BENCH, (PS, SH), r'Assert-Match\s+"[^"]*"\s+(?P<target>\$\w+|\(Calls\))\s+"(?P<needle>[^"]+)"', r'[Cc]alls'),
        # assert_contains "rotulo" "padrao" -- no bash a saida e o unico alvo
        (SH_BENCH, (SH,), r'assert_contains\s+"[^"]*"\s+"(?P<target>)(?P<needle>[^"]+)"', r'^\x00$'),
    )
    for bench_rel, src_rels, pattern, exempt in specs:
        bench = read(bench_rel)
        src = "\n".join(read(r) for r in src_rels)
        src_rel = " ou ".join(src_rels)
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
    documented = option_flags(usage_block_sh(sh))
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
    shown = option_flags(usage_block_ps(ps))
    header = option_flags(header_block_ps(ps))
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


def pares_orbita_sh(texto, nome):
    """AF_ORBIT="3,19 4,18 ..." -> [(3,19), (4,18), ...]"""
    m = re.search(r'^%s="([^"]+)"' % nome, texto, re.M)
    if not m:
        return None
    return [tuple(int(x) for x in par.split(",")) for par in m.group(1).split()]


def pares_orbita_ps(texto, nome):
    """$AF_ORBIT = @(@(3, 19), @(4, 18), ...) -> [(3,19), (4,18), ...]"""
    i = texto.find("$%s = @(" % nome)
    if i < 0:
        return None
    fim = texto.find("\n$", i + 1)
    bloco = texto[i:fim if fim > 0 else i + 900]
    return [(int(a), int(b)) for a, b in re.findall(r'@\(\s*(\d+)\s*,\s*(\d+)\s*\)', bloco)]


def check_art_parity(problems):
    """Arte do banner identica nos dois instaladores.

    Os dois desenham o MESMO produto e o usuario do Windows ve os dois. Ate aqui
    nada verificava esse vinculo, e eles divergiram de tres formas ao mesmo
    tempo: quadro final com cauda de cometa so de um lado, luas trocadas por um
    AF_ORBIT_START diferente e um banner estatico escrito a mao.
    """
    sh, ps = read(SH), read(PS)

    for nome in ("AF_ORBIT", "AF_COMET"):
        a, b = pares_orbita_sh(sh, nome), pares_orbita_ps(ps, nome)
        if not a or not b:
            problems.append("nao consegui ler %s dos dois instaladores" % nome)
        elif a != b:
            problems.append("%s difere: bash tem %d celulas, PowerShell tem %d (primeira divergencia: %s vs %s)"
                            % (nome, len(a), len(b),
                               next((x for x, y in zip(a, b) if x != y), "-"),
                               next((y for x, y in zip(a, b) if x != y), "-")))

    rampa_sh = re.search(r'^AF_RAMP="([^"]+)"', sh, re.M)
    rampa_ps = re.search(r'\$AF_RAMP = @\(([^)]+)\)', ps)
    if rampa_sh and rampa_ps:
        a = rampa_sh.group(1).split()
        b = re.findall(r'"([0-9a-fA-F]{6})"', rampa_ps.group(1))
        if a != b:
            problems.append("a rampa do banner difere: %s vs %s" % (a, b))

    # Hex das luas: no bash sao variaveis, no PowerShell vivem no New-AfFrame.
    for nome, var in (("lua 1 perto", "AF_MOON1"), ("lua 1 longe", "AF_MOON1_FAR"),
                      ("lua 2 perto", "AF_MOON2"), ("lua 2 longe", "AF_MOON2_FAR")):
        m = re.search(r'%s="([0-9a-fA-F]{6})"' % var, sh)
        if m and m.group(1) not in ps:
            problems.append("o hex da %s (%s) nao aparece no install.ps1" % (nome, m.group(1)))

    for var, rotulo in (("AF_WORD", "wordmark"), ("AF_TAG", "frase de chamada")):
        m = re.search(r'^%s="([^"]+)"' % var, sh, re.M)
        if m and m.group(1) not in ps:
            problems.append("o %s (%r) nao aparece no install.ps1" % (rotulo, m.group(1)))

    # Indice de repouso: no bash e derivado das constantes, no PowerShell e
    # literal. Se um dos dois mudar sozinho, as luas param em lugares diferentes.
    def const_sh(nome):
        m = re.search(r'^%s=(\d+)' % nome, sh, re.M)
        return int(m.group(1)) if m else None

    inicio, ignite, quadros = const_sh("AF_ORBIT_START"), const_sh("AF_IGNITE_N"), const_sh("AF_ORBIT_FRAMES")
    n_orbita = const_sh("AF_ORBIT_N")
    comet = pares_orbita_sh(sh, "AF_COMET")
    if None not in (inicio, ignite, quadros, n_orbita) and comet:
        ultimo = ignite + quadros + len(comet)
        repouso = (inicio + ultimo - ignite) % n_orbita
        m = re.search(r'\$AF_ORBIT_REST = (\d+)', ps)
        if m and int(m.group(1)) != repouso:
            problems.append("indice de repouso das luas: bash chega em %d, install.ps1 declara %d"
                            % (repouso, int(m.group(1))))
        m = re.search(r'\$AF_ORBIT_START = (\d+)', ps)
        if m and int(m.group(1)) != inicio:
            problems.append("AF_ORBIT_START difere: bash %d, install.ps1 %d (as luas trocam de lugar)"
                            % (inicio, int(m.group(1))))


def check_ui_parity(problems):
    """Cada primitiva de UI existe nos DOIS instaladores.

    Quem instala no Windows ve os dois na mesma tela. Uma primitiva que nasce so
    de um lado recria a divergencia que este ciclo esta consertando.
    """
    sh, ps = read(SH), read(PS)
    pares = (
        ("calha vertical",                r'\bGUT="',        r'\$script:Gut\s*='),
        ("barra de fase",                 r'\bbar_show\b',   r'\bShow-AfBar\b'),
        ("limpeza da barra na mensagem",  r'\bbar_clear\b',  r'\bClear-AfBar\b'),
        ("regua de fase",                 r'\brule_sweep\b', r'\bWrite-Rule\b'),
        ("relatorio da execucao",         r'last-run\.log',  r'last-run\.log'),
        ("fechamento do trilho",          r'\brule_close\b', r'\bWrite-RuleClose\b'),
        ("mensagem fora do trilho",       r'\bnote\(\)',     r'\bWrite-Note\b'),
        ("quebra de linha com calha",     r'\baf_wrap\b',    r'\bWrite-Wrapped\b'),
        ("fim do trilho",                 r'\brail_end\b',   r'\bClose-AfRail\b'),
    )
    for rotulo, alvo_sh, alvo_ps in pares:
        if not re.search(alvo_sh, sh):
            problems.append("primitiva de UI '%s' nao existe no install.sh" % rotulo)
        if not re.search(alvo_ps, ps):
            problems.append("primitiva de UI '%s' nao existe no install.ps1" % rotulo)


def check_manifest_keys(problems):
    """Chave gravada no manifesto tem de ser LIDA por alguem.

    O manifesto e o unico registro da ida que sustenta a volta: chave escrita e
    nunca consultada e trabalho que nao vira decisao nenhuma. Tres viviam assim:
    `install_dir` (que sustentava uma garantia anunciada no CHANGELOG e ausente
    do codigo), `env_file` e `api_keys_file` -- esta ultima deixando uma chave de
    API viva em disco depois da desinstalacao. Nada verificava esse vinculo.
    """
    sh, ps = read(SH), read(PS)

    escritas = set(re.findall(r'\bhost_set\s+([a-z_]+)\s', sh))
    escritas |= set(re.findall(r'manifest_set\s+"\$\w+"\s+([a-z_]+)\s', sh))
    lidas = set(re.findall(r'\bhost_get\s+([a-z_]+)', sh))
    lidas |= set(re.findall(r'manifest_get\s+"\$\w+"\s+([a-z_]+)', sh))
    for chave in sorted(escritas - lidas):
        problems.append("%s  o manifesto grava '%s' e ninguem le essa chave — registro que nao vira decisao"
                        % (SH, chave))

    escritas_ps = set(re.findall(r'Set-AfState\s+"([A-Za-z_]+)"', ps))
    lidas_ps = set(re.findall(r'Get-AfState\s+"([A-Za-z_]+)"', ps))
    # Get-AfHostExtra le por lista literal, nao uma chave por chamada.
    for bloco in re.findall(r'foreach\s*\(\$chave in @\(([^)]*)\)\)', ps):
        lidas_ps |= set(re.findall(r'"([A-Za-z_]+)"', bloco))
    # o laco de remocao le pela propriedade Key das entradas da tabela
    lidas_ps |= set(re.findall(r'Key\s*=\s*"([A-Za-z_]+)"', ps))
    for chave in sorted(escritas_ps - lidas_ps):
        problems.append("%s  o manifesto grava '%s' e ninguem le essa chave — registro que nao vira decisao"
                        % (PS, chave))


def check_call_before_declaration(problems):
    """Funcao chamada pelo fluxo principal ANTES de ser declarada.

    No PowerShell uma funcao so existe depois que a linha que a declara RODA, e
    o script corre de cima para baixo. Chamar do fluxo principal algo declarado
    mais abaixo nao e erro de sintaxe: o parse passa, o PSScriptAnalyzer passa, e
    o instalador morre calado na maquina do usuario. Aconteceu com Test-DockerInWsl,
    que o -Doctor chamava e que estava declarada 500 linhas depois.

    O corpo das funcoes e ignorado de proposito: la a ordem nao importa, porque a
    chamada so acontece quando alguem invoca a funcao.
    """
    linhas = read(PS).splitlines()
    declarada = {}
    for i, linha in enumerate(linhas):
        m = re.match(r'function\s+([A-Za-z][A-Za-z-]*)', linha)
        if m:
            declarada[m.group(1).lower()] = i

    def locais_em(texto):
        return {n.lower() for n in re.findall(r'\b([A-Za-z][A-Za-z-]*-[A-Za-z][A-Za-z]*)\b', texto)
                if n.lower() in declarada}

    # "Fluxo principal" NAO e profundidade zero: um `if ($Doctor) { ... }` esta em
    # profundidade 1 e roda na hora. O que isenta e estar no CORPO DE UMA FUNCAO.
    # E a checagem tem de ser TRANSITIVA: o defeito real era o -Doctor chamar
    # Test-AfDoctor (declarada antes, tudo certo) que por dentro chamava
    # Test-DockerInWsl, declarada 500 linhas depois. So a cadeia inteira revela.
    corpo = {}
    chamadas_do_fluxo = []
    profundidade = 0
    atual = None
    prof_da_funcao = None
    for i, linha in enumerate(linhas):
        sem_texto = re.sub(r'"[^"]*"|\'[^\']*\'|#.*$', '', linha)
        m = re.match(r'\s*function\s+([A-Za-z][A-Za-z-]*)', linha)
        if prof_da_funcao is None:
            if m:
                atual = m.group(1).lower()
                corpo.setdefault(atual, set())
                prof_da_funcao = profundidade
            else:
                for nome in locais_em(sem_texto):
                    chamadas_do_fluxo.append((i, nome))
        elif atual:
            corpo[atual] |= locais_em(sem_texto)
        profundidade += sem_texto.count("{") - sem_texto.count("}")
        if profundidade < 0:
            profundidade = 0
        if prof_da_funcao is not None and profundidade <= prof_da_funcao:
            prof_da_funcao = None
            atual = None

    for linha_uso, nome in chamadas_do_fluxo:
        vistos, fila = set(), [nome]
        while fila:
            f = fila.pop()
            if f in vistos:
                continue
            vistos.add(f)
            fila.extend(corpo.get(f, ()))
        for f in sorted(vistos):
            onde = declarada.get(f)
            if onde is not None and onde > linha_uso:
                via = "" if f == nome else " (alcancada por %s)" % nome
                problems.append("%s:%d  %s%s so e declarada na linha %d — no PowerShell ela ainda "
                                "nao existe quando o fluxo principal chega aqui"
                                % (PS, linha_uso + 1, f, via, onde + 1))


def check_gutter_holes(problems):
    """Nenhuma linha VAZIA dentro do trilho, dos dois lados.

    Numa desinstalacao real no macOS o usuario viu tres buracos na calha: dois
    depois do `[y/N]` e um antes do fechamento. A causa era `printf '\\n'` puro
    onde deveria sair a calha — no mac_env_install.sh a linha em branco do trilho
    e `echo -e "${GUT}"`, nunca "".

    O lado bash tem a varredura mecanica na propria bancada (que roda o fonte).
    Aqui fica o lado PowerShell, onde `Write-Host ""` e legitimo como terminador
    de linha depois de -NoNewline: a guarda mira o unico ponto onde ele abria
    buraco, o cabecalho de fase.
    """
    ps = read(PS)
    corpo = re.search(r"function Write-Phase\([^)]*\)\s*\{(.*?)\n\}", ps, re.S)
    if not corpo:
        problems.append("Write-Phase nao encontrado no install.ps1")
        return
    # Comentario nao e codigo: a primeira versao desta guarda casou com o
    # proprio comentario que explica o defeito e reprovou o codigo ja corrigido.
    texto = "\n".join(l for l in corpo.group(1).split("\n")
                      if not l.lstrip().startswith("#"))
    antes = texto.split("Write-Gut")[0]
    if 'Write-Host ""' in antes:
        problems.append(
            "Write-Phase emite linha VAZIA antes da calha: abre buraco no trilho "
            "e diverge do install.sh")


def main():
    problems = []
    check_assertions(problems)
    check_flags(problems)
    check_dead_functions(problems)
    check_art_parity(problems)
    check_ui_parity(problems)
    check_gutter_holes(problems)
    check_call_before_declaration(problems)
    check_manifest_keys(problems)
    for p in problems:
        print(p)
    if problems:
        print("\n%d divergencia(s) entre instalador, bancada e ajuda" % len(problems))
        return 1
    print("instaladores consistentes: assertivas casam com o fonte, ajuda casa com o parser, "
          "sem funcao morta, mesma arte e mesmas primitivas de UI nos dois")
    return 0


if __name__ == "__main__":
    sys.exit(main())
