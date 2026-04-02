"""AI client — thin async wrapper for LLM calls via AWS Bedrock or AI Gateway.

Reads endpoint/credentials from the ``[dreamer.ai]`` config section.
Falls back to a stub if no configuration is present, preserving the
existing Dreamer fallback behaviour.

Usage::

    from shoal.services.ai_client import call_llm

    summary = await call_llm(
        model="amazon.nova-lite-v1:0",
        prompt="Summarise ...",
        max_tokens=500,
        temperature=0.3,
    )
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("shoal.ai_client")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def call_llm(
    model: str,
    prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
) -> str:
    """Call the configured LLM and return the response text.

    Resolves the backend in priority order:

    1. AWS Bedrock (if ``boto3`` is installed and ``[dreamer.ai]`` configures
       ``provider = "bedrock"`` or provider is unset and boto3 is available).
    2. HTTP AI Gateway (if ``[dreamer.ai]`` configures a non-empty
       ``endpoint``).
    3. Stub / fallback (no external calls — returns a placeholder string).

    Args:
        model: Model identifier (e.g. ``amazon.nova-lite-v1:0``).
        prompt: Full prompt text to send to the model.
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature.

    Returns:
        Response text from the model.

    Raises:
        RuntimeError: If the configured backend returns an unrecoverable error.
    """
    from shoal.core.config import load_config

    cfg = load_config()
    dreamer_ai = cfg.dreamer.ai

    if dreamer_ai.provider == "bedrock":
        return await _call_bedrock(model, prompt, max_tokens, temperature)

    if dreamer_ai.provider == "gateway" and dreamer_ai.endpoint:
        return await _call_gateway(dreamer_ai.endpoint, model, prompt, max_tokens, temperature)

    if dreamer_ai.provider in ("auto", "stub"):
        try:
            return await _call_bedrock(model, prompt, max_tokens, temperature)
        except ImportError:
            pass

    msg = (
        f"No LLM backend configured (provider={dreamer_ai.provider!r}, ",
        f"endpoint={dreamer_ai.endpoint!r}). ",
        "Set [dreamer.ai] in config.toml.",
    )
    raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Bedrock backend
# ---------------------------------------------------------------------------


async def _call_bedrock(
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Invoke AWS Bedrock using the Converse API.

    Args:
        model: Bedrock model ID.
        prompt: Prompt text.
        max_tokens: Max tokens.
        temperature: Sampling temperature.

    Returns:
        Response text.

    Raises:
        ImportError: If boto3 is not installed.
        RuntimeError: If Bedrock returns an error.
    """
    import asyncio

    try:
        import boto3  # optional dep — boto3 stubs not installed
    except ImportError as exc:
        raise ImportError("boto3 is required for Bedrock: pip install boto3") from exc

    def _invoke() -> str:
        client = boto3.client("bedrock-runtime")
        response = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        )
        output = response["output"]["message"]["content"]
        return str(output[0]["text"]) if output else ""

    logger.debug("Calling Bedrock model %s", model)
    return await asyncio.to_thread(_invoke)


# ---------------------------------------------------------------------------
# HTTP AI Gateway backend
# ---------------------------------------------------------------------------


async def _call_gateway(
    endpoint: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call an OpenAI-compatible HTTP AI Gateway.

    Args:
        endpoint: Base URL of the gateway (e.g. ``http://ai-gw:8080/v1``).
        model: Model name as understood by the gateway.
        prompt: Prompt text.
        max_tokens: Max tokens.
        temperature: Sampling temperature.

    Returns:
        Response text.

    Raises:
        RuntimeError: On HTTP or JSON parse failure.
    """
    import asyncio

    url = endpoint.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode()

    def _post() -> str:
        req = urllib.request.Request(  # noqa: S310
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # nosec B310
                body = json.loads(resp.read())
            return str(body["choices"][0]["message"]["content"])
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"AI Gateway HTTP {exc.code}: {exc.reason}") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Unexpected AI Gateway response: {exc}") from exc

    logger.debug("Calling AI Gateway at %s (model=%s)", endpoint, model)
    return await asyncio.to_thread(_post)
