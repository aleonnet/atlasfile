"""
Carrega prompts a partir de arquivos .md em app/prompts/.
Fallback para strings padrão se o arquivo não existir (ex.: testes ou empacotamento).
"""
from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_prompt(filename: str, fallback: str) -> str:
    try:
        path = _PROMPTS_DIR / filename
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return fallback


# Fallbacks usados se o .md não existir
_DEFAULT_CHAT = """Você é um assistente que opera sobre um repositório de documentos (AtlasFile).
Use as ferramentas disponíveis para buscar documentos, ler conteúdo, aplicar tags e marcar revisões.
Responda com base em evidências (cite trechos e doc_id quando relevante). Seja objetivo."""

_DEFAULT_CLASSIFY = """Analise o trecho de documento fornecido e classifique-o.
Chame a ferramenta submit_classification com: document_type (tipo do documento, ex: contrato, nota_fiscal),
tags (lista de tags relevantes), confidence (0.0 a 1.0). Use apenas a ferramenta para responder."""


def get_system_prompt_chat() -> str:
    return _read_prompt("system_prompt_chat.md", _DEFAULT_CHAT)


def get_system_prompt_classify() -> str:
    return _read_prompt("system_prompt_classify.md", _DEFAULT_CLASSIFY)
