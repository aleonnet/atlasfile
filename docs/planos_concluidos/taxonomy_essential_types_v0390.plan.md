# taxonomy_essential_types_v0390 — Taxonomia essencial de document_types

> **CONCLUÍDO em 2026-07-23.** Decisões do usuário: manter `aditivo`; `fato_relevante`
> sai do default (criação governada onde o projeto pedir); zero-sinal → triagem.
> Emenda aprovada durante a execução: `head_chars` no motor de regras + teto do
> caminho de alias abaixo do auto-route.

## Problema

`document_type` misturava GÊNERO (contrato, ata…) com FORMATO (apresentacao,
planilha, email) — e o formato engolia o gênero: `extension_confidence 0.98`
(.pptx→apresentacao etc.) curto-circuitava o detector antes do conteúdo competir.
`plano.pptx` nunca era avaliado como plano. O formato já era faceta própria
(`doc_kind`, derivada da extensão, filtrável na busca e stats).

## Entregas

1. Templates default/default-en: 14 → **10 tipos** (contrato, aditivo, ata,
   parecer, procuracao, relatorio, especificacao, plano, edital, nota_fiscal).
   Atalhos 0.98 de .pptx/.xls*/.csv/.msg/.eml removidos; `.xml→nota_fiscal` fica.
   O topic `fato_relevante` (tema) permanece — camadas ortogonais.
2. **Emenda 1 — `head_chars`** (schema + motor): regra de cabeçalho só enxerga os
   primeiros N chars. Evidência: sem o atalho de extensão, regras "structural_header"
   casavam menção profunda (offsets 1.571–3.074 nos 12 arquivos reais) com conf
   0.96-0.97 → auto-route errado. 15 regras any_of → head_chars: 600; 3 all_of de
   evidência distribuída mantêm corpo inteiro. Retrocompatível (ausente = inteiro).
3. **Emenda 2 — teto de alias 0.96 → 0.84**: frequência de alias no corpo nunca
   auto-roteia sozinha (final = min(tipo, domínio) < 0.85 → triagem).
4. Ground truth do validation set re-rotulado (gênero: decks→plano/especificacao;
   ex-fato_relevante e .msg→relatorio) e teste de piso com contrato novo:
   **zero auto-route com tipo errado** + hits ≥8/12 + domínio ≥7/12.
5. Afinidades da augmentation mantêm os tipos antigos (instâncias existentes).

## Resultado empírico (12 arquivos reais)

Antes: 4 falsos positivos 0.96-0.97 (2 auto-routes errados). Depois: **zero
auto-route errado**; cabeçalhos reais exatos (contrato×4, aditivo×2 AUTO);
`Milestones.pdf` → plano; ambíguos em triagem; `.msg` → 0.25 (triagem baixa).

## Pendência descoberta (fora de escopo, reportada)

Enum backend `LLMProvider` do profile ainda é openai/anthropic — triage com
moonshot/ollama falharia a validação do profile (gap do v0.36 a corrigir).

## Migração de instâncias existentes

Opt-in via Configuração → Templates → "Migrar / remover" (move docs, reescreve
datasets, origem vira alias). Nada muda automaticamente em projetos existentes.
