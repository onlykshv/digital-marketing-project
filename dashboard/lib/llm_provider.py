"""A small, isolated interface to an external LLM provider (Anthropic).

Nothing outside this file touches the provider SDK directly -- callers use `is_configured()`,
`complete()` (single-shot synthesis, used by `copilot_engine.py`), and `complete_with_tools()`
(multi-turn tool-calling, used by `agent.py`) only. This keeps the provider swappable and keeps
every other module free of API-specific error handling and free of any Anthropic SDK import.

No credentials are ever hard-coded: the API key is read from the `ANTHROPIC_API_KEY` environment
variable only. If it is unset, or the `anthropic` package is not installed, or the call fails for
any reason (network, auth, rate limit, timeout), this module reports "not available" rather than
raising past its boundary -- callers are expected to fall back to a deterministic, grounded answer
path, never to show a broken page or a hallucinated response.

`complete_with_tools()` accepts and returns plain dicts/lists (never `anthropic.types.*` objects),
so `agent.py`'s orchestration loop -- which tool to call, how to validate its arguments, how many
turns to allow -- has zero Anthropic-specific code in it. The `tools` parameter shape (name /
description / input_schema as JSON Schema) is not really Anthropic-specific either; it is the same
shape OpenAI and most other function-calling APIs use, so swapping providers later would not
require reshaping the tool schemas themselves, only this file's request/response translation.
"""
from __future__ import annotations

import os

_MODEL = "claude-sonnet-4-5-20250929"
_MAX_TOKENS = 700
_MAX_TOKENS_TOOL_USE = 1024
# P1-12: an explicit, bounded request timeout -- without one, the SDK's own default (several
# minutes) means a hung network request could leave a Streamlit page rendering its spinner far
# longer than a manager would ever wait, before eventually reaching the existing fallback. A
# timeout here raises inside the `try` block below exactly like any other request failure, and is
# caught by the same broad `except Exception` -> `ProviderUnavailable` translation already in
# place, so no separate handling is needed at the call site.
_REQUEST_TIMEOUT_SECONDS = 20.0


class ProviderUnavailable(Exception):
    """Raised (and always caught by the caller) when the LLM path cannot be used this call --
    missing key, missing package, or a failed request. Never propagates to the page."""


def is_configured() -> bool:
    """True only if an API key is present in the environment. Does not import the SDK or make
    a network call -- cheap enough to check on every page render."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system_prompt: str, user_prompt: str) -> str:
    """Send one request to the configured provider and return its text response.

    Raises ProviderUnavailable (never any other exception type) on any failure, so the caller can
    catch a single, predictable exception and fall back to the deterministic answer path.
    """
    if not is_configured():
        raise ProviderUnavailable("No ANTHROPIC_API_KEY configured in the environment.")

    try:
        import anthropic
    except ImportError as e:
        raise ProviderUnavailable("The 'anthropic' package is not installed.") from e

    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=_REQUEST_TIMEOUT_SECONDS)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if not text.strip():
            raise ProviderUnavailable("Provider returned an empty response.")
        return text
    except ProviderUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any provider failure must degrade gracefully, never crash the page
        raise ProviderUnavailable(f"Provider request failed: {type(e).__name__}") from e


def format_tool_result(tool_use_id: str, result: dict) -> dict:
    """Build the plain-dict `tool_result` content block Anthropic's API expects in a follow-up
    'user' turn. `result` is JSON-serialized as-is -- whatever `agent_tools.py`'s `{"ok", "data",
    "error"}` contract returned, verbatim, so the model sees exactly what the deterministic tool
    actually produced, never a paraphrase of it."""
    import json
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, default=str),
    }


def complete_with_tools(system_prompt: str, messages: list[dict], tools: list[dict]) -> dict:
    """Send one request to the configured provider with a tool-use-capable message, and return a
    plain-dict summary of the response -- never an `anthropic.types.*` object.

    `messages` is a plain list of `{"role": "user" | "assistant", "content": ...}` dicts (content
    is either a string, or a list of content-block dicts such as `{"type": "text", ...}`,
    `{"type": "tool_use", ...}`, or the dict `format_tool_result()` builds) -- the caller
    (`agent.py`) owns building and growing this list turn by turn; this function only sends it.

    `tools` is a list of `{"name", "description", "input_schema"}` dicts (JSON Schema) -- see
    `agent_tool_schemas.py`.

    Returns a dict:
        stop_reason: str            -- "tool_use", "end_turn", "max_tokens", or "stop_sequence"
        text: str                   -- any plain text the model produced this turn (may be "")
        tool_calls: list[dict]      -- [{"id", "name", "input"}, ...] requested this turn
        raw_content: list[dict]     -- the full content block list, as plain dicts, for the
                                        caller to append verbatim as this turn's "assistant"
                                        message when continuing the conversation

    Raises ProviderUnavailable (never any other exception type) on any failure -- same contract
    as `complete()`.
    """
    if not is_configured():
        raise ProviderUnavailable("No ANTHROPIC_API_KEY configured in the environment.")

    try:
        import anthropic
    except ImportError as e:
        raise ProviderUnavailable("The 'anthropic' package is not installed.") from e

    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=_REQUEST_TIMEOUT_SECONDS)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS_TOOL_USE,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        raw_content = []
        tool_calls = []
        text_parts = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                raw_content.append({"type": "text", "text": block.text})
                text_parts.append(block.text)
            elif block_type == "tool_use":
                raw_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        return {
            "stop_reason": response.stop_reason,
            "text": "".join(text_parts),
            "tool_calls": tool_calls,
            "raw_content": raw_content,
        }
    except ProviderUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 -- any provider failure must degrade gracefully, never crash
        raise ProviderUnavailable(f"Provider request failed: {type(e).__name__}") from e
