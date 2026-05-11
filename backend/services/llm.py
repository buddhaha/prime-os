"""
PRIME OS — LiteLLM wrapper.

Single entry point for all LLM calls. Normalises provider differences so the
rest of the codebase never imports anthropic, openai, or any SDK directly.

Supported providers (set LLM_MODEL + optional LLM_API_BASE in .env):
  Claude   — "claude-haiku-4-5-20251001"          needs ANTHROPIC_API_KEY
  OpenAI   — "gpt-4o-mini"                        needs OPENAI_API_KEY
  Ollama   — "ollama/llama3.2"                    needs LLM_API_BASE=http://localhost:11434
  vLLM     — "openai/mistral-7b"                  needs LLM_API_BASE=http://localhost:8000/v1
  Any other provider supported by LiteLLM.

All responses are returned in OpenAI ModelResponse format regardless of provider.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm

from ..config import settings

log = logging.getLogger("prime.llm")

# Silently drop parameters that a specific provider doesn't support
# (e.g. Ollama ignores 'tool_choice').
litellm.drop_params = True


# ─────────────────────────────────────────────
# Tool schema conversion
# ─────────────────────────────────────────────

def to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """
    Convert Anthropic-style tool schemas to OpenAI function format.
    LiteLLM expects OpenAI format and converts back to Anthropic when needed.

    Anthropic:  {"name": …, "description": …, "input_schema": {…}}
    OpenAI:     {"type": "function", "function": {"name": …, "description": …, "parameters": {…}}}
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in anthropic_tools
    ]


# ─────────────────────────────────────────────
# Core call
# ─────────────────────────────────────────────

async def chat(
    messages: list[dict],
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    tools: list[dict] | None = None,
) -> litellm.ModelResponse:
    """
    Single async LLM call. Returns a LiteLLM ModelResponse (OpenAI format).

    Args:
        messages:   Conversation history in OpenAI role/content format.
        system:     Optional system prompt — prepended as a system message.
        model:      Override LLM_MODEL for this call only.
        max_tokens: Max tokens in the completion.
        tools:      Anthropic-style tool schemas — auto-converted to OpenAI format.

    The caller should use get_text(), get_tool_calls(), and is_done() to
    inspect the response rather than reading response fields directly.
    """
    full_messages: list[dict] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    kwargs: dict[str, Any] = {}
    if settings.llm_api_base:
        kwargs["api_base"] = settings.llm_api_base
    if tools:
        kwargs["tools"] = to_openai_tools(tools)

    chosen_model = model or settings.llm_model
    log.debug(f"LLM call → {chosen_model} ({len(full_messages)} messages)")

    return await litellm.acompletion(
        model=chosen_model,
        messages=full_messages,
        max_tokens=max_tokens,
        **kwargs,
    )


# ─────────────────────────────────────────────
# Response helpers
# ─────────────────────────────────────────────

def get_text(response: litellm.ModelResponse) -> str:
    """Extract text content from the first choice."""
    return response.choices[0].message.content or ""


def get_tool_calls(response: litellm.ModelResponse) -> list:
    """
    Extract tool calls from the first choice.
    Returns an empty list if the model didn't call any tools.
    Each item has: .id, .function.name, .function.arguments (JSON string).
    """
    return response.choices[0].message.tool_calls or []


def is_done(response: litellm.ModelResponse) -> bool:
    """True when the model has finished and issued no tool calls."""
    finish = response.choices[0].finish_reason
    return finish in ("stop", "end_turn", None) and not get_tool_calls(response)


def parse_tool_args(tool_call) -> dict:
    """Parse a tool call's arguments JSON string into a dict."""
    try:
        return json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, AttributeError):
        return {}


def assistant_message(response: litellm.ModelResponse) -> dict:
    """
    Return the assistant turn as a dict suitable for appending to messages[].
    Handles both text-only and tool-call responses.
    """
    msg = response.choices[0].message
    # model_dump() serialises tool_calls properly for the next request
    return msg.model_dump(exclude_none=True)


def tool_result_message(tool_call_id: str, result: Any) -> dict:
    """Build a tool result message for the next LiteLLM request."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result),
    }
