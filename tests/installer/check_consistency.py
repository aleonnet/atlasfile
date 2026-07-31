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
import shutil
import subprocess
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

    O `#?` existe pelo CABECALHO do install.ps1: as linhas dele comecam com
    `#` e a ancora antiga (`\s{2,}` no inicio) nunca casava nenhuma — medido
    na Fase 4b: header_block_ps devolvia um conjunto VAZIO e a metade "ajuda
    cita flag que nao existe" do check_flags era guarda morta para o header.
    """
    found = set()
    for line in text.splitlines():
        m = re.match(r'\s*#?\s{2,}(-{1,2}[A-Za-z][A-Za-z-]*)((?:,\s*-{1,2}[A-Za-z][A-Za-z-]*)*)', line)
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
                      ("lua 2 perto", "AF_MOON2"), ("lua 2 longe", "AF_MOON2_FAR"),
                      ("cabeca do cometa", "AF_COMET_HEAD_HEX")):
        m = re.search(r'%s="([0-9a-fA-F]{6})"' % var, sh)
        if m and m.group(1) not in ps:
            problems.append("o hex da %s (%s) nao aparece no install.ps1" % (nome, m.group(1)))

    # Cauda do cometa. Os hexes vivem em AF_COL_C1..C3 no bash (dentro do af_fg)
    # e num array no PowerShell. A guarda de quadros compara GLIFOS, nao cor:
    # sem esta checagem uma cauda pintada errada -- que foi o caso, com a cabeca
    # em "ffd0c4" no lugar do branco -- passaria batida por tudo.
    caudas_sh = re.findall(r'AF_COL_C[123]="\$\(af_fg ([0-9a-fA-F]{6})', sh)
    m = re.search(r'\$AF_COMET_TAIL_HEX = @\(([^)]+)\)', ps)
    caudas_ps = re.findall(r'"([0-9a-fA-F]{6})"', m.group(1)) if m else []
    if caudas_sh and [c.lower() for c in caudas_sh] != [c.lower() for c in caudas_ps]:
        problems.append("a cauda do cometa difere: bash %s, install.ps1 %s"
                        % (caudas_sh, caudas_ps))

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


# A UNICA divergencia deliberada entre os dois banners, decidida pelo dono do
# projeto: o lado Windows identifica a plataforma numa terceira linha de texto.
# Ela vive na linha 4, a partir da coluna 23 -- onde o install.sh nunca desenha
# (na linha 4 o conteudo dele para na coluna 18). Esta constante e o unico
# perdao que a guarda de quadros da; qualquer outro pixel diferente reprova.
PS_LINHA_PLATAFORMA = "(Windows / WSL2)"
PS_PLATAFORMA_COL = 23
AF_LINHAS_POR_QUADRO = 7


def _dump_quadros_sh():
    """Os quadros do install.sh, em texto puro, pela funcao real dele."""
    # `set --` ANTES do source: um script sourcado herda os parametros
    # posicionais de quem o chama, entao o caminho passado em $1 chegava ao
    # parser de flags do install.sh e ele morria com "Unknown flag: ./install.sh".
    roteiro = ('export ATLASFILE_INSTALL_LIB=1; caminho="$1"; set --; . "$caminho"; '
               'n=0; while [ $n -lt $AF_FRAMES ]; do af_frame_plain $n; n=$((n+1)); done')
    saida = subprocess.run(["bash", "-c", roteiro, "_", os.path.join(ROOT, SH)],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
    if saida.returncode != 0:
        return None, (saida.stderr.strip() or saida.stdout.strip() or
                      "bash saiu com %d e sem mensagem" % saida.returncode)[:200]
    return saida.stdout.split("\n"), None


def _dump_quadros_ps():
    """Os quadros do install.ps1, pelo seam ATLASFILE_DUMP_FRAMES."""
    amb = dict(os.environ, ATLASFILE_DUMP_FRAMES="1", NO_COLOR="1")
    saida = subprocess.run(["pwsh", "-NoProfile", "-File", os.path.join(ROOT, PS)],
                           capture_output=True, text=True, cwd=ROOT, env=amb, timeout=180)
    if saida.returncode != 0:
        return None, (saida.stderr.strip() or saida.stdout.strip() or
                      "pwsh saiu com %d e sem mensagem" % saida.returncode)[:200]
    return saida.stdout.split("\n"), None


def check_frame_parity(problems):
    """Os dois banners DESENHAM igual, quadro a quadro.

    A check_art_parity compara as TABELAS que alimentam o desenho (orbita,
    cometa, rampa, hexes, indice de repouso). Isso deixa de fora tudo que os
    ALGORITMOS fazem com elas -- e foi exatamente ali que os dois divergiram em
    quatro pontos ao mesmo tempo, com a guarda verde o tempo todo:

      * a cauda do cometa era contigua no bash e amostrada (faiscada) no
        PowerShell -- justamente a forma que o comentario do install.sh registra
        como MEDIDA e rejeitada;
      * as luas seguiam orbitando durante o voo do cometa no bash e congelavam
        no PowerShell (o quadro FINAL coincidia, que e o unico que a guarda de
        repouso olhava);
      * a ignicao revelava uma linha a mais no PowerShell;
      * o brilho especular usava outra formula e outra linha de destaque.

    Comparar desenho e a unica forma de pegar essa classe. O preco e rodar os
    dois interpretadores; sem `pwsh` a checagem se ANUNCIA pulada, nunca some
    calada -- guarda que pula em silencio vira guarda que nao existe.
    """
    if not shutil.which("pwsh"):
        print("PULADO  check_frame_parity: pwsh ausente nesta maquina "
              "(instale com `brew install powershell`) — a paridade de DESENHO "
              "do banner nao foi verificada")
        return

    quadros_sh, erro = _dump_quadros_sh()
    if quadros_sh is None:
        problems.append("%s  nao consegui despejar os quadros: %s" % (SH, erro))
        return
    quadros_ps, erro = _dump_quadros_ps()
    if quadros_ps is None:
        problems.append("%s  nao consegui despejar os quadros: %s" % (PS, erro))
        return

    # A tag de plataforma tem de ESTAR la: sem esta assertiva, apagar a linha do
    # Windows faria a guarda ficar verde e a divergencia deliberada sumiria sem
    # ninguem notar.
    if PS_LINHA_PLATAFORMA not in "\n".join(quadros_ps):
        problems.append("%s  a linha de plataforma %r sumiu do banner — se foi de "
                        "proposito, tire tambem a excecao em PS_LINHA_PLATAFORMA"
                        % (PS, PS_LINHA_PLATAFORMA))
        return

    normalizado = []
    for i, linha in enumerate(quadros_ps):
        if i % AF_LINHAS_POR_QUADRO == 4:
            cauda = linha[PS_PLATAFORMA_COL:]
            # A revelacao e progressiva, entao um quadro do meio traz um PEDACO
            # da tag ("(Win"). Qualquer outra coisa nessa faixa e divergencia de
            # verdade e nao pode ser perdoada.
            if cauda and not PS_LINHA_PLATAFORMA.startswith(cauda):
                problems.append("%s  quadro %d, linha 4: a coluna %d em diante tem %r, "
                                "que nao e a linha de plataforma"
                                % (PS, i // AF_LINHAS_POR_QUADRO, PS_PLATAFORMA_COL, cauda))
                return
            linha = linha[:PS_PLATAFORMA_COL]
        normalizado.append(linha.rstrip())

    esperado = [l.rstrip() for l in quadros_sh]
    while esperado and not esperado[-1]:
        esperado.pop()
    while normalizado and not normalizado[-1]:
        normalizado.pop()

    if len(esperado) != len(normalizado):
        problems.append("o banner tem %d linhas no install.sh e %d no install.ps1 "
                        "(%d e %d quadros) — a coreografia nao tem o mesmo tamanho"
                        % (len(esperado), len(normalizado),
                           len(esperado) // AF_LINHAS_POR_QUADRO,
                           len(normalizado) // AF_LINHAS_POR_QUADRO))
        return

    divergentes = [i for i, (a, b) in enumerate(zip(esperado, normalizado)) if a != b]
    for i in divergentes[:6]:
        problems.append("banner diverge no quadro %d, linha %d:\n      bash: %r\n      ps1 : %r"
                        % (i // AF_LINHAS_POR_QUADRO, i % AF_LINHAS_POR_QUADRO,
                           esperado[i], normalizado[i]))
    if len(divergentes) > 6:
        problems.append("banner: mais %d linha(s) divergentes alem das mostradas"
                        % (len(divergentes) - 6))


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
        # A regua nao pode ser so "existir nos dois": ela tem de VARRER a rampa
        # nos dois. Chapada de um lado e degrade do outro, as duas metades da
        # tela nao parecem o mesmo produto — foi o que o usuario viu no Windows.
        ("rampa na regua",                r'af_rgb_at "\$pos"',
                                          r'Get-AfRampHex[^\n]*Cabecalho\[\$i\]'),
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


"""Funcoes do install.ps1 que desenham FORA do trilho de proposito.

Write-Phase termina uma linha ja aberta com -NoNewline; Close-AfRail e
Write-Panel escrevem DEPOIS do fechamento; Show-BannerStatic emoldura a arte,
que vive antes de o trilho existir. Lista curta e explicita: uma isencao por
descuido e como o buraco volta.
"""
PS_FORA_DO_TRILHO = ("Write-Phase", "Close-AfRail", "Write-Panel", "Show-BannerStatic")


def check_gutter_holes(problems):
    """Nenhuma linha VAZIA dentro do trilho, dos dois lados.

    Numa desinstalacao real no macOS o usuario viu tres buracos na calha: dois
    depois do `[y/N]` e um antes do fechamento. A causa era `printf '\\n'` puro
    onde deveria sair a calha — no mac_env_install.sh a linha em branco do trilho
    e `echo -e "${GUT}"`, nunca "".

    O lado bash tem a varredura mecanica na propria bancada (que roda o fonte).
    Aqui fica o lado PowerShell.

    Antes isto mirava SO o corpo do Write-Phase -- o unico ponto conhecido na
    epoca. Uma auditoria depois achou oito outros: cinco reguas do -Doctor, a
    abertura do -DryRun, o bloco que explica o WSL no meio da fase 1 e o respiro
    do -Verbose. Guarda de um ponto so nao e guarda da propriedade; agora a faixa
    inteira do trilho e varrida, delimitada pelas mesmas marcas que o install.sh
    usa (AF-INICIO-DO-TRILHO / AF-FIM-DO-TRILHO).
    """
    linhas = read(PS).splitlines()

    # A marca tem de ABRIR a linha de comentario. Procurar a string solta casava
    # com o proprio comentario de abertura, que cita "AF-FIM-DO-TRILHO la
    # embaixo" no meio da prosa: a faixa virava (960, 961) e a guarda varria
    # ZERO linha, passando com dois mutantes vivos dentro. Foi assim que ela
    # nasceu inutil, e o piso de sanidade abaixo existe para isso nao se repetir
    # em silencio.
    def marca(nome):
        alvo = re.compile(r'#\s*' + nome + r'\b')
        return next((i for i, l in enumerate(linhas) if alvo.match(l.strip())), None)

    ini, fim = marca("AF-INICIO-DO-TRILHO"), marca("AF-FIM-DO-TRILHO")
    if ini is None or fim is None:
        problems.append("%s  faltam as marcas AF-INICIO-DO-TRILHO / AF-FIM-DO-TRILHO "
                        "que delimitam o trilho" % PS)
        return
    # Faixa vazia ou invertida = guarda cega. Preferir gritar a passar verde.
    if fim - ini < 200:
        problems.append("%s  a faixa do trilho tem so %d linhas (marcas em %d e %d) — "
                        "a guarda de calha estaria varrendo quase nada"
                        % (PS, fim - ini, ini + 1, fim + 1))
        return

    atual = None
    for i in range(ini + 1, fim):
        linha = linhas[i]
        m = re.match(r'function\s+([A-Za-z][A-Za-z-]*)', linha)
        if m:
            atual = m.group(1)
        elif linha.startswith("}"):
            atual = None          # funcoes deste arquivo sao todas de topo
        if atual in PS_FORA_DO_TRILHO:
            continue
        # Comentario nao e codigo: a primeira versao desta guarda casou com o
        # proprio comentario que explica o defeito e reprovou o codigo corrigido.
        if linha.lstrip().startswith("#"):
            continue
        if re.search(r'Write-Host\s+""', linha):
            problems.append(
                "%s:%d  Write-Host \"\" dentro do trilho abre buraco na calha — "
                "use Write-Gut \"\" (linha de calha), como o install.sh" % (PS, i + 1))


def check_glyph_shadowing(problems):
    """Nenhuma variavel local pode sombrear um GLIFO global.

    Nomes de variavel do PowerShell NAO diferenciam maiusculas: um `$ok = $false`
    dentro de uma funcao sombreia o glifo `$OK` e a linha de sucesso sai
    "True waiting for..." em vez de "checkmark waiting for...".

    Mordeu duas vezes em maquina real — primeiro no --doctor (o contador $ok
    sobrescrevendo o glifo, imprimindo "0 Microsoft Windows") e depois no
    Wait-Spinner. Duas ocorrencias da mesma classe sem nenhuma guarda.
    """
    ps = read(PS)
    glifos = set(re.findall(r"^\$(OK|BAD|DOT)\s*=", ps, re.M))
    if not glifos:
        problems.append("%s  nao achei os glifos globais para checar sombreamento" % PS)
        return
    vistos = set()
    for nome in sorted(glifos):
        # atribuicao a uma variavel com o MESMO nome em outra caixa
        for m in re.finditer(r"\$([A-Za-z]+)\s*=", ps):
            achado = m.group(1)
            if achado != nome and achado.upper() == nome.upper():
                linha = ps[:m.start()].count("\n") + 1
                if (linha, achado) in vistos:
                    continue   # duas atribuicoes na MESMA linha (try/catch)
                vistos.add((linha, achado))
                problems.append(
                    "%s:%d  $%s sombreia o glifo global $%s (PowerShell ignora "
                    "maiusculas em nomes de variavel)" % (PS, linha, achado, nome))


def check_singular_nouns(problems):
    """Nome de funcao do PowerShell usa substantivo SINGULAR.

    E regra do PSScriptAnalyzer (PSUseSingularNouns), e ele so roda no job do
    Windows: `Set-AfDockerPrefs` passou pela bancada inteira e derrubou o CI
    depois. Verificar aqui custa nada e a resposta vem em segundos, nao em
    minutos.
    """
    ps = read(PS)
    for nome in re.findall(r"^function ([A-Za-z]+)-([A-Za-z]+)", ps, re.M):
        verbo, substantivo = nome
        if substantivo.endswith("s") and not substantivo.endswith("ss"):
            problems.append(
                "%s  funcao '%s-%s' usa substantivo plural (PSUseSingularNouns "
                "reprova no CI)" % (PS, verbo, substantivo))


def _aspas_abertas(texto):
    """Linhas que abrem aspa e nao fecham, fora de here-string."""
    dentro, achados = False, []
    for n, l in enumerate(texto.split("\n"), 1):
        t = l.strip()
        if dentro:
            # A here-string fecha numa linha que COMECA com '@ - e ela costuma
            # continuar com um pipe. Exigir a linha inteira igual a "'@" fazia o
            # verificador ficar presa dentro dela e nao ver mais nada; foi assim
            # que a primeira versao disto nao achou a aspa que derrubou o CI.
            if t.startswith("'@") or t.startswith('"@'):
                dentro = False
            continue
        if t.endswith("@'") or t.endswith('@"'):
            dentro = True
            continue
        aspa = None
        for c in l:
            if aspa is None and c == "#":
                break
            if aspa is None and c in "'\"":
                aspa = c
            elif aspa == c:
                aspa = None
        if aspa is not None:
            achados.append((n, aspa, t[:70]))
    return achados


def check_ascii_only(problems):
    """O install.ps1 tem de ser ASCII PURO, byte a byte.

    Nao e preciosismo: medido no Windows 11 com Windows PowerShell 5.1, UTF-8
    sem BOM e lido como ANSI e o parser morre no primeiro glifo multibyte, numa
    cascata de "Missing closing ')'" que aponta para linhas erradas. Adicionar
    BOM conserta o `-File` e quebra o `irm | iex`, porque a string passa a
    comecar com U+FEFF. ASCII puro e a unica forma que sobrevive aos DOIS
    caminhos de entrega, e por isso os glifos do arquivo sao declarados por code
    point ([char]0x2588 e afins).

    Isto ja existia no job Windows do CI e em NENHUM lugar local: eu enchi os
    comentarios de travessao, `checkmark` e meio-bloco durante uma auditoria, a
    bancada inteira passou verde na minha maquina E na VM, e o CI reprovou com
    30 bytes nao-ASCII. Guarda que so o CI ve custa uma volta de push a cada
    descuido.
    """
    caminho = os.path.join(ROOT, PS)
    with open(caminho, "rb") as fh:
        octetos = fh.read()
    ruins = {}
    linha = 1
    for byte in octetos:
        if byte == 0x0A:
            linha += 1
        elif byte > 127:
            ruins[linha] = ruins.get(linha, 0) + 1
    if ruins:
        onde = ", ".join("linha %d (%dx)" % (n, q) for n, q in sorted(ruins.items())[:8])
        problems.append("%s  tem %d byte(s) nao-ASCII em %d linha(s) — o PowerShell 5.1 "
                        "le o arquivo como ANSI e o parse quebra em cascata: %s"
                        % (PS, sum(ruins.values()), len(ruins), onde))


def check_quotes(problems):
    """Nenhuma linha abre aspa sem fechar, no instalador e na bancada.

    O parser do PowerShell so roda no job do Windows, e uma aspa faltando la
    produz erro em CASCATA que aponta para uma linha de COMENTARIO dezenas de
    linhas adiante - diagnostico caro e a minutos de distancia. Aconteceu duas
    vezes neste ciclo, as duas por edicao automatizada que comeu a aspa final.
    """
    for rel in (PS, "tests/installer/win/run.ps1"):
        for linha, aspa, trecho in _aspas_abertas(read(rel)):
            problems.append("%s:%d  aspa %s aberta e nao fechada -> %s"
                            % (rel, linha, aspa, trecho))


def main():
    problems = []
    check_assertions(problems)
    check_flags(problems)
    check_dead_functions(problems)
    check_art_parity(problems)
    check_frame_parity(problems)
    check_ui_parity(problems)
    check_gutter_holes(problems)
    check_glyph_shadowing(problems)
    check_singular_nouns(problems)
    check_ascii_only(problems)
    check_quotes(problems)
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
