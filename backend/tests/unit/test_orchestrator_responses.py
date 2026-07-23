"""Unit tests do caminho Responses API do chat loop (modelos OpenAI pós-gpt-5.2)
e regressão do caminho chat.completions para os modelos que funcionam hoje.

Padrão B do projeto: patch("openai.AsyncOpenAI") + AsyncMock com captura de kwargs.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.llm_catalog as llm_catalog
from app.orchestrator import run_chat_loop

SEARCH_TOOL = {
    "name": "search_documents",
    "description": "Busca documentos",
    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
}


@pytest.fixture(autouse=True)
def _builtin_catalog_only(monkeypatch, tmp_path):
    """Isola o catálogo no builtin: sem cache remoto de máquina de dev interferindo."""
    monkeypatch.setattr(llm_catalog.settings, "projects_root", str(tmp_path))
    monkeypatch.setattr(llm_catalog, "_merged_memo", None)
    yield
    monkeypatch.setattr(llm_catalog, "_merged_memo", None)


class _Usage:
    class input_tokens_details:
        cached_tokens = 7

    input_tokens = 100
    output_tokens = 20


class _ReasoningItem:
    type = "reasoning"

    def model_dump(self, exclude_none: bool = False):
        return {"type": "reasoning", "id": "rs_1", "summary": []}


class _FunctionCallItem:
    type = "function_call"
    name = "search_documents"
    arguments = '{"query": "contrato"}'
    call_id = "c1"

    def model_dump(self, exclude_none: bool = False):
        return {
            "type": "function_call",
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
            "id": "fc_1",
        }


class _RespWithToolCall:
    output = [_ReasoningItem(), _FunctionCallItem()]
    output_text = ""
    usage = _Usage()


class _RespFinal:
    class _MsgItem:
        type = "message"

        def model_dump(self, exclude_none: bool = False):
            return {"type": "message"}

    output = [_MsgItem()]
    output_text = "resposta final com citação"
    usage = _Usage()


def test_loop_responses_com_tool_call_reasoning_e_usage():
    captured: list[dict] = []

    responses = [_RespWithToolCall(), _RespFinal()]

    async def fake_responses_create(**kwargs):
        captured.append(kwargs)
        return responses[len(captured) - 1]

    async def _run():
        with (
            patch("app.orchestrator.mcp_list_tools", new_callable=AsyncMock) as mock_list,
            patch("app.orchestrator.mcp_call_tool", new_callable=AsyncMock) as mock_call,
            patch("openai.AsyncOpenAI") as MockOpenAI,
        ):
            mock_list.return_value = [SEARCH_TOOL]
            mock_call.return_value = "3 documentos encontrados"
            mock_client = AsyncMock()
            mock_client.responses.create = fake_responses_create
            MockOpenAI.return_value = mock_client

            result = await run_chat_loop(
                [{"role": "user", "content": "ache o contrato"}],
                provider="openai",
                model="gpt-5.6",
                enable_thinking=True,
                project_id="proj1",
            )

            # duas chamadas: tool call e resposta final
            assert len(captured) == 2

            # tools FLAT: name no topo, sem wrapper "function"
            tool = captured[0]["tools"][0]
            assert tool["name"] == "search_documents"
            assert "function" not in tool
            assert tool["strict"] is False

            # reasoning ligado no formato da Responses API
            assert captured[0]["reasoning"] == {"effort": "medium"}
            assert "reasoning_effort" not in captured[0]

            # system prompt vai em instructions, não em input
            assert "project_id ativo" in captured[0]["instructions"]
            assert all(item.get("role") != "system" for item in captured[0]["input"] if isinstance(item, dict))

            # 2ª chamada: input contém o item reasoning E o function_call_output do c1
            second_input = captured[1]["input"]
            types_in_input = [item.get("type") for item in second_input if isinstance(item, dict)]
            assert "reasoning" in types_in_input
            fco = next(item for item in second_input if item.get("type") == "function_call_output")
            assert fco["call_id"] == "c1"
            assert fco["output"] == "3 documentos encontrados"

            # tool executada com escopo de projeto aplicado
            mock_call.assert_awaited_once_with("search_documents", {"query": "contrato", "project_id": "proj1"})

            # contrato de retorno + usage acumulado das 2 chamadas
            assert result["content"] == "resposta final com citação"
            assert result["tool_calls_used"][0]["name"] == "search_documents"
            usage = result["usage"]
            assert usage["api_call_count"] == 2
            assert usage["input_tokens"] == 200
            assert usage["output_tokens"] == 40
            assert usage["cache_read_input_tokens"] == 14
            assert "context_pressure" in result

    asyncio.run(_run())


@pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4.1", "gpt-5.1"])
def test_regressao_modelos_atuais_continuam_no_chat_completions(model):
    """gpt-4o-mini/4.1/5.1 seguem no caminho atual — responses.create NUNCA é chamado."""
    captured: list[dict] = []

    async def fake_chat_create(**kwargs):
        captured.append(kwargs)

        class FakeMsg:
            tool_calls = None
            content = "ok"

        class FakeChoice:
            message = FakeMsg()

        class FakeResp:
            choices = [FakeChoice()]
            usage = None

        return FakeResp()

    async def _run():
        with (
            patch("app.orchestrator.mcp_list_tools", new_callable=AsyncMock) as mock_list,
            patch("openai.AsyncOpenAI") as MockOpenAI,
        ):
            mock_list.return_value = [SEARCH_TOOL]
            mock_client = AsyncMock()
            mock_client.chat.completions.create = fake_chat_create
            responses_spy = AsyncMock()
            mock_client.responses.create = responses_spy
            MockOpenAI.return_value = mock_client

            result = await run_chat_loop(
                [{"role": "user", "content": "oi"}],
                provider="openai",
                model=model,
                enable_thinking=True,
            )

            assert result["content"] == "ok"
            responses_spy.assert_not_awaited()
            # client sem base_url para openai (kwargs históricos)
            MockOpenAI.assert_called_once_with(api_key=None)
            # tools no formato chat.completions (wrapper "function")
            assert captured[0]["tools"][0]["function"]["name"] == "search_documents"

    asyncio.run(_run())


def test_moonshot_cai_no_caminho_chat_completions_com_base_url():
    """Provider OpenAI-compatível: mesmo loop de chat.completions, client com base_url."""
    async def fake_chat_create(**kwargs):
        class FakeMsg:
            tool_calls = None
            content = "olá do kimi"

        class FakeChoice:
            message = FakeMsg()

        class FakeResp:
            choices = [FakeChoice()]
            usage = None

        return FakeResp()

    async def _run():
        with (
            patch("app.orchestrator.mcp_list_tools", new_callable=AsyncMock) as mock_list,
            patch("openai.AsyncOpenAI") as MockOpenAI,
        ):
            mock_list.return_value = [SEARCH_TOOL]
            mock_client = AsyncMock()
            mock_client.chat.completions.create = fake_chat_create
            MockOpenAI.return_value = mock_client

            result = await run_chat_loop(
                [{"role": "user", "content": "oi"}],
                provider="moonshot",
                model="kimi-k3",
                api_key="sk-moon",
            )

            assert result["content"] == "olá do kimi"
            MockOpenAI.assert_called_once_with(api_key="sk-moon", base_url="https://api.moonshot.ai/v1")

    asyncio.run(_run())
