# Roadmap — AtlasFile

Evoluções avaliadas com critério e registradas para além das sessões de desenvolvimento.
Cada item traz o **gatilho** que justifica tirá-lo daqui — nada entra em execução sem plano próprio aprovado.

## Internacionalização e classificação multilíngue

_Contexto: v0.33.0 entregou UI PT-BR/EN-US completa e classificação bilíngue no modelo SKOS/EuroVoc (key canônico + sinônimos multilíngues na mesma entrada). Detalhes em `planos_concluidos/frontend_sota_tanstack_query_i18n_ptbr_enus_v0330.plan.md`._

| Item | O que é | Gatilho para executar |
|---|---|---|
| Detecção de idioma por documento (`doc_language`) + analyzers por idioma no OpenSearch | Padrão Elastic multilingual: cada doc detecta o idioma na ingestão; índice usa analyzer específico (stemming EN vs PT); dicionários de topics/aliases separados roteados pela detecção | Dicionários multilíngues combinados começarem a colidir (falsos positivos cross-idioma) ou entrada de um 3º idioma |
| `topics` EN validado por corpus | Os +315 sinônimos EN (v0.33.0) foram derivados por tradução de domínio; validação estatística exige corpus EN rotulado no pipeline do classificador | Volume real de documentos EN decididos na triagem suficiente para compor validação |
| Localização de prompts LLM | **Rejeitada com critério** (v0.33.0): prompt canônico único + regra "responda no idioma do usuário" cobre o caso sem duplicar manutenção/QA | Só reavaliar se um idioma exibir qualidade de resposta comprovadamente inferior |

## Direção de arte / visual

| Item | O que é | Estado |
|---|---|---|
| Shader blackhole (geodésicas de Schwarzschild, MIT — [s13k.dev/blackhole](https://s13k.dev/blackhole/)) como elemento vivo da UI | Candidatos aprovados em conceito pelo usuário (2026-07-19): (a) indicador de contexto do chat — buraco negro cresce com o % de contexto da sessão (análogo do MODE_TOKENS; o dado já existe na UI). **Restrição de design do usuário: não pode ficar muito pequeno** — presença visual desde o início (semente já legível, análogo ao TOKEN_AREA_MIN do shader), não um ícone tímido; (b) fundo do AuthGate/onboarding (backdrop lenteado, não o DOM); (c) estado especial do Orb durante ciclo do classificador. Porte: componente WebGL2 próprio (`BlackholeGL`) adaptando o fragment Shadertoy-style, com gating de `prefers-reduced-motion` e custo de GPU limitado pelo tamanho do canvas | Em avaliação — exige plano próprio com mockups |

## Como usar este arquivo

- Adicione itens SEMPRE com gatilho explícito — roadmap sem critério vira lista de desejos.
- Ao executar um item: plano próprio em `planos_concluidos/` ao concluir, e o item sai daqui com um ponteiro para o plano.
