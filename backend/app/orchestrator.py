"""
Orchestrator: format MCP tools for OpenAI/Anthropic, chat loop with tool_calls, classify_with_llm.
Uses app.mcp_client for list_tools and call_tool.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.config import settings
from app.llm_catalog import get_anthropic_thinking_type, get_context_tokens, get_max_tool_result_chars, supports_reasoning_effort
from app.mcp_client import call_tool as mcp_call_tool
from app.mcp_client import list_tools as mcp_list_tools
from app.prompts import get_system_prompt_chat, get_system_prompt_classify
from app.usage_costs import estimate_usage_cost

MAX_TOOL_LOOPS = 10
# Fallback quando o modelo não está no catálogo (get_max_tool_result_chars).
MAX_TOOL_RESULT_CHARS_FALLBACK = 120_000
_CHARS_PER_TOKEN = 4
# Reserva 60% do contexto para histórico; 20% para tool results, 20% para resposta.
_HISTORY_CONTEXT_FRACTION = 0.6


def _accumulate_usage(
    acc: dict[str, int | float],
    raw: dict[str, int] | None,
    provider: str,
    model: str,
) -> None:
    """Merge raw usage (input_tokens, output_tokens, cache_*) into acc; then set estimated_cost_usd."""
    if not raw:
        return
    acc["input_tokens"] = int(acc.get("input_tokens") or 0) + int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0)
    acc["output_tokens"] = int(acc.get("output_tokens") or 0) + int(raw.get("output_tokens") or raw.get("completion_tokens") or 0)
    for key in ("cache_read_input_tokens", "cache_creation_input_tokens", "cache_write_input_tokens"):
        if key in raw and raw[key]:
            acc[key] = int(acc.get(key) or 0) + int(raw[key])
    acc["total_tokens"] = int(acc.get("input_tokens") or 0) + int(acc.get("output_tokens") or 0)
    acc["estimated_cost_usd"] = estimate_usage_cost(acc, provider, model)


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


def _trim_history_to_context(
    messages: list[dict[str, Any]], provider: str, model: str,
) -> list[dict[str, Any]]:
    """Discard oldest messages (FIFO) so the history fits within 60% of the model context window.
    Always keeps the system prompt (first message if role=system) and the most recent user message."""
    context_limit = get_context_tokens(provider, model)
    max_history_tokens = int(context_limit * _HISTORY_CONTEXT_FRACTION)

    def _estimate_tokens(msgs: list[dict[str, Any]]) -> int:
        return sum(len(str(m.get("content", ""))) // _CHARS_PER_TOKEN for m in msgs)

    if _estimate_tokens(messages) <= max_history_tokens:
        return messages

    system = [messages[0]] if messages and messages[0].get("role") == "system" else []
    rest = messages[1:] if system else list(messages)

    while _estimate_tokens(system + rest) > max_history_tokens and len(rest) > 1:
        rest.pop(0)

    return system + rest


def _estimate_context_pressure(
    messages: list[dict[str, Any]], provider: str, model: str,
) -> dict[str, Any]:
    """Estimate context pressure as ratio of message tokens vs model context window."""
    chars_total = sum(len(str(m.get("content", ""))) for m in messages)
    tokens_estimate = chars_total // _CHARS_PER_TOKEN
    context_limit = get_context_tokens(provider, model)
    ratio = tokens_estimate / context_limit if context_limit else 0
    return {
        "context_tokens_estimate": tokens_estimate,
        "context_tokens_limit": context_limit,
        "context_pressure_ratio": round(min(ratio, 1.0), 4),
    }


def get_llm_config(use: str) -> tuple[str, str]:
    """Return (provider, model) for chat or classification. use in ('chat', 'classification')."""
    if use == "classification" and settings.classification_llm_provider and settings.classification_llm_model:
        return (settings.classification_llm_provider, settings.classification_llm_model)
    if use == "chat" and settings.chat_llm_provider and settings.chat_llm_model:
        return (settings.chat_llm_provider, settings.chat_llm_model)
    return (settings.default_llm_provider, settings.default_llm_model)


_PROJECT_SCOPED_TOOL_NAMES = {"search_documents", "list_documents", "get_stats", "list_tags"}


def _chat_system_prompt(project_id: str | None) -> str:
    prompt = get_system_prompt_chat()
    scope = str(project_id or "").strip()
    if not scope:
        return prompt
    return (
        prompt
        + "\n\n## Escopo ativo\n"
        + f"- project_id ativo desta conversa: `{scope}`.\n"
        + "- Para tools que aceitam `project_id`, use esse valor por padrao.\n"
        + "- Nao misture resultados de outros projetos, a menos que o usuario peca isso explicitamente."
    )


def _apply_project_scope_to_tool_args(tool_name: str, args: dict[str, Any] | None, project_id: str | None) -> dict[str, Any]:
    scoped_args = dict(args or {})
    scope = str(project_id or "").strip()
    if scope and tool_name in _PROJECT_SCOPED_TOOL_NAMES and not str(scoped_args.get("project_id") or "").strip():
        scoped_args["project_id"] = scope
    return scoped_args


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
    project_id: str | None = None,
) -> dict[str, Any]:
    """
    Run chat with tool calls: get MCP tools, send to LLM, on tool_calls execute via MCP and re-send.
    messages: list of {role, content} or {role, content, tool_calls}; content can be string or list (Anthropic).
    enable_thinking: OpenAI -> reasoning_effort; Anthropic -> thinking.enabled.
    Returns { "content": str, "tool_calls_used": list of {name, result_preview} }.
    """
    trimmed = _trim_history_to_context(messages, provider, model)
    tools_mcp = await mcp_list_tools()
    tool_calls_used: list[dict[str, Any]] = []

    max_tool_result_chars = get_max_tool_result_chars(provider, model)
    if provider == "openai":
        tools_api = mcp_tools_to_openai(tools_mcp)
        result = await _run_chat_openai(
            trimmed,
            model,
            tools_api,
            api_key,
            tool_calls_used,
            enable_thinking,
            max_tool_result_chars,
            project_id,
        )
    elif provider == "anthropic":
        tools_api = mcp_tools_to_anthropic(tools_mcp)
        result = await _run_chat_anthropic(
            trimmed,
            model,
            tools_api,
            api_key,
            tool_calls_used,
            enable_thinking,
            max_tool_result_chars,
            project_id,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

    result["context_pressure"] = _estimate_context_pressure(trimmed, provider, model)
    return result


async def _run_chat_openai(
    messages: list[dict[str, Any]],
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    tool_calls_used: list[dict[str, Any]],
    enable_thinking: bool = False,
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS_FALLBACK,
    project_id: str | None = None,
) -> dict[str, Any]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or None)  # None => env OPENAI_API_KEY
    system_content = _chat_system_prompt(project_id)
    # Mensagens sem role system do cliente; system único no backend
    loop_messages = [{"role": "system", "content": system_content}] + [m for m in messages if m.get("role") != "system"]
    create_kw: dict[str, Any] = {
        "model": model,
        "messages": loop_messages,
        "tools": tools_api,
    }
    if enable_thinking and supports_reasoning_effort("openai", model):
        create_kw["reasoning_effort"] = "medium"
    usage_accum: dict[str, int | float] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
    for _ in range(MAX_TOOL_LOOPS):
        create_kw["messages"] = loop_messages
        resp = await client.chat.completions.create(**create_kw)
        u = getattr(resp, "usage", None)
        if u is not None:
            raw = {"prompt_tokens": getattr(u, "prompt_tokens", 0) or 0, "completion_tokens": getattr(u, "completion_tokens", 0) or 0}
            _accumulate_usage(usage_accum, raw, "openai", model)
        choice = resp.choices[0] if resp.choices else None
        if not choice:
            return {"content": "", "tool_calls_used": tool_calls_used, "usage": _usage_return(usage_accum)}
        msg = choice.message
        if not getattr(msg, "tool_calls", None) or len(msg.tool_calls) == 0:
            return {"content": (msg.content or ""), "tool_calls_used": tool_calls_used, "usage": _usage_return(usage_accum)}

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
            args = _apply_project_scope_to_tool_args(name, args, project_id)
            result = await mcp_call_tool(name, args)
            result = _truncate_tool_result(result, max_tool_result_chars)
            preview = result[:200] + "..." if len(result) > 200 else result
            tool_calls_used.append({"name": name, "result_preview": preview})
            loop_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
    return {"content": "(max tool loops reached)", "tool_calls_used": tool_calls_used, "usage": _usage_return(usage_accum)}


def _usage_return(acc: dict[str, int | float]) -> dict[str, int | float]:
    """Build API usage dict: input_tokens, output_tokens, total_tokens, estimated_cost_usd, optional cache_*."""
    out: dict[str, int | float] = {
        "input_tokens": int(acc.get("input_tokens") or 0),
        "output_tokens": int(acc.get("output_tokens") or 0),
        "total_tokens": int(acc.get("total_tokens") or 0),
        "estimated_cost_usd": float(acc.get("estimated_cost_usd") or 0),
    }
    for k in ("cache_read_input_tokens", "cache_creation_input_tokens", "cache_write_input_tokens"):
        if acc.get(k):
            out[k] = int(acc[k])
    return out


async def _run_chat_anthropic(
    messages: list[dict[str, Any]],
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    tool_calls_used: list[dict[str, Any]],
    enable_thinking: bool = False,
    max_tool_result_chars: int = MAX_TOOL_RESULT_CHARS_FALLBACK,
    project_id: str | None = None,
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

    base_system = system or _chat_system_prompt(project_id)
    create_kw: dict[str, Any] = {
        "model": model,
        "max_tokens": 16000 if enable_thinking else 4096,
        "system": base_system,
        "messages": anthropic_messages,
        "tools": tools_api,
    }
    if enable_thinking and supports_reasoning_effort("anthropic", model):
        thinking_type = get_anthropic_thinking_type("anthropic", model)
        if thinking_type == "adaptive":
            create_kw["thinking"] = {"type": "adaptive"}
        else:
            create_kw["thinking"] = {"type": "enabled", "budget_tokens": 10000}
    usage_accum_anth: dict[str, int | float] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
    for _ in range(MAX_TOOL_LOOPS):
        create_kw["messages"] = anthropic_messages
        resp = await client.messages.create(**create_kw)
        u = getattr(resp, "usage", None)
        if u is not None:
            raw: dict[str, int] = {
                "input_tokens": getattr(u, "input_tokens", 0) or 0,
                "output_tokens": getattr(u, "output_tokens", 0) or 0,
            }
            for key in ("cache_creation_input_tokens", "cache_read_input_tokens"):
                if hasattr(u, key) and getattr(u, key):
                    raw[key] = getattr(u, key)
            _accumulate_usage(usage_accum_anth, raw, "anthropic", model)
        content_blocks = getattr(resp, "content", []) or []
        tool_uses = [b for b in content_blocks if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            parts: list[str] = []
            for b in content_blocks:
                if getattr(b, "type", None) == "thinking":
                    parts.append(getattr(b, "thinking", "") or "")
                elif getattr(b, "text", None) is not None:
                    parts.append(b.text)
            return {"content": "\n\n".join(p for p in parts if p), "tool_calls_used": tool_calls_used, "usage": _usage_return(usage_accum_anth)}

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
            inp = _apply_project_scope_to_tool_args(name, inp, project_id)
            result = await mcp_call_tool(name, inp)
            result = _truncate_tool_result(result, max_tool_result_chars)
            preview = result[:200] + "..." if len(result) > 200 else result
            tool_calls_used.append({"name": name, "result_preview": preview})
            tool_results.append({"type": "tool_result", "tool_use_id": tid, "content": result})
        anthropic_messages.append({"role": "user", "content": tool_results})
    return {"content": "(max tool loops reached)", "tool_calls_used": tool_calls_used, "usage": _usage_return(usage_accum_anth)}


def _build_project_context(profile: dict[str, Any] | None) -> str:
    """Build a context block describing the project's business domains and valid topics for the LLM."""
    if profile is None:
        return ""
    parts: list[str] = []

    business_domains = (
        profile.get("business_domains")
        or (profile.get("classification") or {}).get("business_domains")
        or []
    )
    if business_domains:
        lines = ["Domínios de negócio disponíveis neste projeto:"]
        for domain in business_domains:
            key = str(domain.get("key", "")).strip()
            if not key:
                continue
            aliases = domain.get("aliases") or []
            alias_str = ", ".join(str(a) for a in aliases if str(a).strip())
            line = f"- {key}"
            if alias_str:
                line += f" (aliases: {alias_str})"
            lines.append(line)
        if len(lines) > 1:
            parts.append("\n".join(lines))

    from app.topics import get_topic_keys
    topic_keys = get_topic_keys(profile)
    if topic_keys:
        parts.append(f"Topics válidos: {', '.join(topic_keys[:40])}")

    parts.append(
        "Escolha sempre um dos business_domains configurados no projeto.\n"
        "Se a classificação for ambígua entre domínios, use confidence < 0.6."
    )
    return "\n\n".join(parts)


async def classify_with_llm(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    api_key: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify document excerpt via LLM; LLM must call submit_classification.
    Returns { document_type?: str, tags: list[str], confidence: float, business_domain?: str, topics?: list[str], explanation?: str }.
    """
    if provider_override and model_override:
        provider, model = provider_override, model_override
    else:
        provider, model = get_llm_config("classification")
    tools_mcp = await mcp_list_tools()
    submit_only = [t for t in tools_mcp if t["name"] == "submit_classification"]
    if not submit_only:
        return {"document_type": None, "tags": [], "confidence": 0.0, "business_domain": None, "topics": [], "explanation": None}

    project_context = _build_project_context(profile)

    if provider == "openai":
        tools_api = mcp_tools_to_openai(submit_only)
        content, usage_raw = await _classify_openai(doc_id, text_excerpt, filename, model, tools_api, api_key, project_context)
    elif provider == "anthropic":
        tools_api = mcp_tools_to_anthropic(submit_only)
        content, usage_raw = await _classify_anthropic(doc_id, text_excerpt, filename, model, tools_api, api_key, project_context)
    else:
        return {"document_type": None, "tags": [], "confidence": 0.0, "business_domain": None, "topics": [], "explanation": None}

    if usage_raw:
        usage_raw["estimated_cost_usd"] = estimate_usage_cost(usage_raw, provider, model)

    base: dict[str, Any]
    if isinstance(content, dict):
        base = {
            "document_type": content.get("document_type"),
            "tags": content.get("tags") or [],
            "confidence": float(content.get("confidence", 0.0)),
            "business_domain": content.get("business_domain"),
            "topics": content.get("topics") or [],
            "explanation": content.get("explanation"),
        }
    else:
        base = {"document_type": None, "tags": [], "confidence": 0.0, "business_domain": None, "topics": [], "explanation": None}
    base["usage"] = usage_raw
    base["provider"] = provider
    base["model"] = model
    return base


async def _classify_openai(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    project_context: str = "",
) -> tuple[dict[str, Any], dict[str, int]]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key or None)
    context_block = f"\n\n{project_context}\n\n" if project_context else "\n\n"
    user_content = f"Documento: {filename}\nDoc ID: {doc_id}{context_block}Trecho:\n{text_excerpt[:8000]}"
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": get_system_prompt_classify()},
            {"role": "user", "content": user_content},
        ],
        tools=tools_api,
        tool_choice={"type": "function", "function": {"name": "submit_classification"}},
    )
    usage_raw: dict[str, int] = {}
    u = getattr(resp, "usage", None)
    if u is not None:
        usage_raw = {
            "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(u, "completion_tokens", 0) or 0,
        }
    choice = resp.choices[0] if resp.choices else None
    if not choice or not getattr(choice.message, "tool_calls", None):
        return {}, usage_raw
    for tc in choice.message.tool_calls:
        if tc.function.name == "submit_classification":
            try:
                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else {}
            except json.JSONDecodeError:
                args = {}
            return args, usage_raw
    return {}, usage_raw


async def _classify_anthropic(
    doc_id: str,
    text_excerpt: str,
    filename: str,
    model: str,
    tools_api: list[dict],
    api_key: str | None,
    project_context: str = "",
) -> tuple[dict[str, Any], dict[str, int]]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key or None)
    context_block = f"\n\n{project_context}\n\n" if project_context else "\n\n"
    user_content = f"Documento: {filename}\nDoc ID: {doc_id}{context_block}Trecho:\n{text_excerpt[:8000]}"
    resp = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=get_system_prompt_classify(),
        messages=[{"role": "user", "content": user_content}],
        tools=tools_api,
        tool_choice={"type": "tool", "name": "submit_classification"},
    )
    usage_raw: dict[str, int] = {}
    u = getattr(resp, "usage", None)
    if u is not None:
        usage_raw = {
            "input_tokens": getattr(u, "input_tokens", 0) or 0,
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
        }
        for key in ("cache_creation_input_tokens", "cache_read_input_tokens"):
            if hasattr(u, key) and getattr(u, key):
                usage_raw[key] = getattr(u, key)
    content = getattr(resp, "content", []) or []
    for b in content:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == "submit_classification":
            inp = getattr(b, "input", None) or {}
            return (inp if isinstance(inp, dict) else {}), usage_raw
    return {}, usage_raw
