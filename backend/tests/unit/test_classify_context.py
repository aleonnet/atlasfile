"""Tests for classify_with_llm receiving project context (business_domains + topics)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.orchestrator import _build_project_context


def _sample_profile() -> dict:
    return {
        "classification": {
            "business_domains": [
                {"key": "societario_fiscal", "aliases": ["societario", "fiscal", "cnpj"]},
                {"key": "juridica", "aliases": ["juridico", "passivo", "contingencia"]},
                {"key": "marketing_produtos", "aliases": ["marketing", "produtos"]},
            ],
        },
        "indexing": {
            "topics_path": "config/topics_v1.yaml",
        },
    }


def test_build_project_context_includes_business_domains():
    ctx = _build_project_context(_sample_profile())
    assert "Domínios de negócio disponíveis neste projeto" in ctx
    assert "societario_fiscal" in ctx
    assert "juridica" in ctx
    assert "marketing_produtos" in ctx
    assert "aliases: societario, fiscal, cnpj" in ctx


def test_build_project_context_includes_topics():
    ctx = _build_project_context(_sample_profile())
    assert "Topics válidos:" in ctx


def test_build_project_context_includes_instructions():
    ctx = _build_project_context(_sample_profile())
    assert "Escolha sempre um dos business_domains" in ctx
    assert "confidence < 0.6" in ctx


def test_build_project_context_none_profile():
    ctx = _build_project_context(None)
    assert ctx == ""


def test_build_project_context_empty_profile():
    ctx = _build_project_context({})
    assert "confidence < 0.6" in ctx


def test_classify_with_llm_passes_profile_context():
    """Verify that classify_with_llm builds user_content including project business domains."""
    import asyncio

    profile = _sample_profile()
    captured_calls: list[dict] = []

    async def mock_openai_create(**kwargs):
        captured_calls.append(kwargs)

        class FakeTC:
            class function:
                name = "submit_classification"
                arguments = '{"document_type": "contrato", "tags": ["juridica"], "confidence": 0.85, "business_domain": "juridica"}'

            id = "tc1"

        class FakeMsg:
            tool_calls = [FakeTC()]
            content = ""

        class FakeChoice:
            message = FakeMsg()

        class FakeResp:
            choices = [FakeChoice()]

        return FakeResp()

    async def _run():
        with (
            patch("app.orchestrator.mcp_list_tools", new_callable=AsyncMock) as mock_list,
            patch("openai.AsyncOpenAI") as MockOpenAI,
        ):
            mock_list.return_value = [
                {"name": "submit_classification", "description": "...", "inputSchema": {"type": "object", "properties": {}}},
            ]
            mock_client = AsyncMock()
            mock_client.chat.completions.create = mock_openai_create
            MockOpenAI.return_value = mock_client

            from app.orchestrator import classify_with_llm

            result = await classify_with_llm(
                doc_id="test-123",
                text_excerpt="Contrato de prestação de serviços jurídicos...",
                filename="contrato_servicos.pdf",
                provider_override="openai",
                model_override="gpt-4o-mini",
                profile=profile,
            )

            assert result["business_domain"] == "juridica"
            assert result["confidence"] == 0.85

            assert len(captured_calls) == 1
            messages = captured_calls[0]["messages"]
            user_msg = next(m for m in messages if m["role"] == "user")
            assert "societario_fiscal" in user_msg["content"]
            assert "juridica" in user_msg["content"]
            assert "aliases: societario, fiscal, cnpj" in user_msg["content"]

    asyncio.run(_run())
