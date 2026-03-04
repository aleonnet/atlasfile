"""
Orchestrator: format MCP tools for OpenAI/Anthropic, chat loop with tool_calls, classify_with_llm.
Uses app.mcp_client for list_tools and call_tool.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.config import settings
from app.llm_catalog import get_max_tool_result_chars
from app.mcp_client import call_tool as mcp_call_tool
from app.mcp_client import list_tools as mcp_list_tools
from app.prompts import get_system_prompt_chat, get_system_prompt_classify

MAX_TOOL_LOOPS = 10
# Fallback quando o modelo não está no catálogo (get_max_tool_result_chars).
MAX_TOOL_RESULT_CHARS_FALLBACK = 120_000


def _truncate_tool_result(result: str, max_chars: int = MAX_TOOL_RESULT_CHARS_FALLBACK) -> str:
    """Se o resultado da ferramenta exceder max_chars, trunca e adiciona mensagem para o modelo e o usuário."""
    if len(result) <= max_chars:
        return result
    return (
        result[: max_chars - 200]
        + "\n\n[Resposta da ferramenta truncada por limite de contexto (máx. "
        + f"{max_chars} caracteres). Total recebido: {len(result)} caracteres. "
        + "O documento pode ser muito longo; use search_documents com termos específicos para trechos.]"
    )


def get_llm_config(use: str) -> tuple[str, str]:
    """Return (provider, model) for chat or classification. use in ('chat', 'classification')."""
    if use == "classification" and settings.classification_llm_provider and settings.classification_llm_model:
        return (settings.classification_llm_provider, settings.classification_llm_model)
    if use == "chat" and settings.chat_llm_provider and settings.chat_llm_model:
        return (settings.chat_llm_provider, settings.chat_llm_model)
    return (settings.default_llm_provider, settings.default_llm_model)


def mcp_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool list (name, description, inputSchema) to OpenAI tools format."""
    out = []
    for t in tools:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description") or "",
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            },
        })
    return out


def mcp_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert MCP tool list to Anthropic tools format (name, description, input_schema)."""
    out = []
    for t in tools:
        schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        if "type" not in schema:
            schema = {**schema, "type": "object"}
        out.append({
            "name": t["name"],
            "description": t.get("description") or "",
            "input_schema": schema,
        })
    return out


def _content_parts_to_anthropic(content_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte content no formato OpenAI (text + image_url com data URL) para blocos Anthropic (text + image base64)."""
    import re
    out: list[dict[str, Any]] = []
    for part in content_list:
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text":
            out.append({"type": "text", "text": part.get("text", "") or ""})
        elif kind == "image_url":
            url = (part.get("image_url") or {}).get("url") or ""
            # data URL: data:image/png;base64,<payload>
            m = re.match(r"^data:([^;]+);base64,(.+)$", url.strip())
            if m:
                media_type = m.group(1).strip()
                data = m.group(2).strip()
                out.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
            # se não for data URL, ignorar (Anthropic não aceita URL externa aqui)
    return out


async def run_chat_loop(
    messages: list[dict[str, Any]],
    provider: str,
    model: str,
    api_key: str | None = None,
    enable_thinking: bool = False,
) -> dict[str, Any]:
    """
    Run chat with tool calls: get MCP tools, send to LLM, on tool_calls execute via MCP and re-send.
    messages: list of {role, content} or {role, content, tool_calls}; content can be string or list (Anthropic).
    enable_thinking: OpenAI -> reasoning_effort; Anthropic -> thinking.enabled.
    Returns { "content": str, "tool_calls_used": list of {name, result_preview} }.
    """
    tools_mcp = await mcp_list_tools()
    tool_calls_used: list[dict[str, Any]] = []

    max_tool_result_chars = get_max_tool_result_chars(provider, model)
    if provider == "openai":
        tools_api = mcp_tools_to_openai(tools_mcp)
        return await _run_chat_openai(messages, model, tools_api, api_key, tool_calls_used, enable_thinking, max_tool_result_chars)
    if provider == "anthropic":
        tools_api = mcp_tools_to_anthropic(tools_mcp)
        return await _run_chat_anthropic(messages, model, tools_api, api_key, tool_calls_used, enable_thinking, max_tool_result_chars)
    raise ValueError(f"Unknown provider: {provider}")


async def _run_chat_openai(
    messages: list[dict[str, Any]],
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    tool_calls_used: list[dict[str, Any]],
    enable_thinking: bool = False,
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS_FALLBACK,
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or None)  # None => env OPENAI_API_KEY
    system_content = get_system_prompt_chat()
    # Mensagens sem role system do cliente; system único no backend
    loop_messages = [{"role": "system", "content": system_content}] + [m for m in messages if m.get("role") != "system"]
    create_kw: dict[str, Any] = {
        "model": model,
        "messages": loop_messages,
        "tools": tools_api,
    }
    if enable_thinking:
        # reasoning_effort: supported by o1, o1-mini, gpt-4.1 and other reasoning models
        create_kw["reasoning_effort"] = "medium"
    for _ in range(MAX_TOOL_LOOPS):
        create_kw["messages"] = loop_messages
        resp = await client.chat.completions.create(**create_kw)
        choice = resp.choices[0] if resp.choices else None
        if not choice:
            return {"content": "", "tool_calls_used": tool_calls_used}
        msg = choice.message
        if not getattr(msg, "tool_calls", None) or len(msg.tool_calls) == 0:
            return {"content": (msg.content or ""), "tool_calls_used": tool_calls_used}

        loop_messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else (tc.function.arguments or {})
            except json.JSONDecodeError:
                args = {}
            result = await mcp_call_tool(name, args)
            result = _truncate_tool_result(result, max_tool_result_chars)
            preview = result[:200] + "..." if len(result) > 200 else result
            tool_calls_used.append({"name": name, "result_preview": preview})
            loop_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    return {"content": "(max tool loops reached)", "tool_calls_used": tool_calls_used}


async def _run_chat_anthropic(
    messages: list[dict[str, Any]],
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    tool_calls_used: list[dict[str, Any]],
    enable_thinking: bool = False,
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS_FALLBACK,
) -> dict[str, Any]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key or None)
    # Convert to Anthropic format: system + messages with content as list of blocks
    system = ""
    anthropic_messages: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content") or ""
            continue
        role = m["role"]
        content = m.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if role == "assistant" and m.get("tool_calls"):
            blocks = list(content) if isinstance(content, list) else [{"type": "text", "text": str(content)}]
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": json.loads(fn["arguments"]) if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {}),
                })
            anthropic_messages.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": m.get("content", "")}],
            })
        else:
            if isinstance(content, list):
                body = _content_parts_to_anthropic(content)
            else:
                body = [{"type": "text", "text": str(content)}]
            anthropic_messages.append({"role": role, "content": body})

    base_system = system or get_system_prompt_chat()
    create_kw: dict[str, Any] = {
        "model": model,
        "max_tokens": 16000 if enable_thinking else 4096,
        "system": base_system,
        "messages": anthropic_messages,
        "tools": tools_api,
    }
    if enable_thinking:
        # Extended thinking: https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
        create_kw["thinking"] = {"type": "enabled", "budget_tokens": 10000}
    for _ in range(MAX_TOOL_LOOPS):
        create_kw["messages"] = anthropic_messages
        resp = await client.messages.create(**create_kw)
        content_blocks = getattr(resp, "content", []) or []
        tool_uses = [b for b in content_blocks if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            parts: list[str] = []
            for b in content_blocks:
                if getattr(b, "type", None) == "thinking":
                    parts.append(getattr(b, "thinking", "") or "")
                elif getattr(b, "text", None) is not None:
                    parts.append(b.text)
            return {"content": "\n\n".join(p for p in parts if p), "tool_calls_used": tool_calls_used}

        anthropic_messages.append({"role": "assistant", "content": content_blocks})
        tool_results = []
        for tu in tool_uses:
            name = getattr(tu, "name", "") or getattr(tu, "input", {}).get("name", "")
            tid = getattr(tu, "id", "")
            inp = getattr(tu, "input", None) or {}
            if isinstance(inp, dict):
                pass
            else:
                inp = {}
            result = await mcp_call_tool(name, inp)
            result = _truncate_tool_result(result, max_tool_result_chars)
            preview = result[:200] + "..." if len(result) > 200 else result
            tool_calls_used.append({"name": name, "result_preview": preview})
            tool_results.append({"type": "tool_result", "tool_use_id": tid, "content": result})
        anthropic_messages.append({"role": "user", "content": tool_results})
    return {"content": "(max tool loops reached)", "tool_calls_used": tool_calls_used}


async def classify_with_llm(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    api_key: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """
    Classify document excerpt via LLM; LLM must call submit_classification.
    Returns { document_type?: str, tags: list[str], confidence: float }.
    """
    if provider_override and model_override:
        provider, model = provider_override, model_override
    else:
        provider, model = get_llm_config("classification")
    tools_mcp = await mcp_list_tools()
    submit_only = [t for t in tools_mcp if t["name"] == "submit_classification"]
    if not submit_only:
        return {"document_type": None, "tags": [], "confidence": 0.0}

    if provider == "openai":
        tools_api = mcp_tools_to_openai(submit_only)
        content = await _classify_openai(doc_id, text_excerpt, filename, model, tools_api, api_key)
    elif provider == "anthropic":
        tools_api = mcp_tools_to_anthropic(submit_only)
        content = await _classify_anthropic(doc_id, text_excerpt, filename, model, tools_api, api_key)
    else:
        return {"document_type": None, "tags": [], "confidence": 0.0}

    if isinstance(content, dict):
        return {
            "document_type": content.get("document_type"),
            "tags": content.get("tags") or [],
            "confidence": float(content.get("confidence", 0.0)),
        }
    return {"document_type": None, "tags": [], "confidence": 0.0}


async def _classify_openai(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    model: str,
    tools_api: list[dict],
    api_key: str | None,
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or None)
    user_content = f"Documento: {filename}\nDoc ID: {doc_id}\n\nTrecho:\n{text_excerpt[:8000]}"
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": get_system_prompt_classify()},
            {"role": "user", "content": user_content},
        ],
        tools=tools_api,
        tool_choice={"type": "function", "function": {"name": "submit_classification"}},
    )
    choice = resp.choices[0] if resp.choices else None
    if not choice or not getattr(choice.message, "tool_calls", None):
        return {}
    for tc in choice.message.tool_calls:
        if tc.function.name == "submit_classification":
            try:
                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else {}
            except json.JSONDecodeError:
                args = {}
            return args
    return {}


async def _classify_anthropic(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    model: str,
    tools_api: list[dict],
    api_key: str | None,
) -> dict[str, Any]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key or None)
    user_content = f"Documento: {filename}\nDoc ID: {doc_id}\n\nTrecho:\n{text_excerpt[:8000]}"
    resp = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=get_system_prompt_classify(),
        messages=[{"role": "user", "content": user_content}],
        tools=tools_api,
        tool_choice={"type": "tool", "name": "submit_classification"},  # force this tool
    )
    content = getattr(resp, "content", []) or []
    for b in content:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == "submit_classification":
            inp = getattr(b, "input", None) or {}
            return inp if isinstance(inp, dict) else {}
    return {}
