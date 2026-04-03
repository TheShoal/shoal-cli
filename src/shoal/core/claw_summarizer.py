"""Claw summarizer — budget-aware text summarization for journals and workflows.

Provides a Summarizer protocol with two implementations:
- LLMSummarizer: routes through ai_client.call_llm (Bedrock or gateway)
- StubSummarizer: truncation fallback for tests and no-LLM environments

Inspired by lobster-party's SummaryBudget pattern but using Shoal's own
Bedrock/gateway backend rather than OpenRouter.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from shoal.models.claw import SummaryBudget

logger = logging.getLogger("shoal.claw_summarizer")

# Budget -> (max_tokens, instruction fragment)
_BUDGET_HINTS: dict[SummaryBudget, tuple[int, str]] = {
    SummaryBudget.paragraph: (200, "Respond with one concise paragraph (3-4 sentences)."),
    SummaryBudget.short: (100, "Respond with 2-3 sentences."),
    SummaryBudget.headline: (40, "Respond with a single sentence."),
}

_SYSTEM_PROMPT = "Return only the summary text. Do not add commentary or markdown."


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Summarizer(Protocol):
    """Protocol for text summarization backends."""

    async def summarize(self, text: str, budget: SummaryBudget, context: str = "") -> str:
        """Summarize *text* within the given *budget*.

        Args:
            text: Source text to summarize.
            budget: Controls output length.
            context: Optional context hint (e.g. session name, correlation_id).

        Returns:
            Summary text.
        """
        ...


# ---------------------------------------------------------------------------
# LLM implementation
# ---------------------------------------------------------------------------


class LLMSummarizer:
    """Routes summarization through ai_client.call_llm (Bedrock or gateway).

    Args:
        model: Model identifier (e.g. ``amazon.nova-lite-v1:0``).
    """

    def __init__(self, model: str = "amazon.nova-lite-v1:0") -> None:
        self._model = model

    async def summarize(self, text: str, budget: SummaryBudget, context: str = "") -> str:
        """Summarize text using the configured LLM.

        Args:
            text: Source text to summarize.
            budget: Controls output length.
            context: Optional context hint.

        Returns:
            Summary text from the LLM.
        """
        max_tokens, hint = _BUDGET_HINTS.get(budget, _BUDGET_HINTS[SummaryBudget.paragraph])

        context_line = f"Context: {context}\n\n" if context else ""
        prompt = f"{_SYSTEM_PROMPT}\n\n{hint}\n\n{context_line}Text to summarize:\n{text}"

        try:
            from shoal.services.ai_client import call_llm

            return await call_llm(
                model=self._model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.3,
            )
        except Exception as exc:
            logger.warning("LLM summarization failed: %s", exc)
            return _truncate(text, budget)


# ---------------------------------------------------------------------------
# Stub implementation
# ---------------------------------------------------------------------------


class StubSummarizer:
    """Truncation fallback for tests and environments without LLM access."""

    async def summarize(self, text: str, budget: SummaryBudget, context: str = "") -> str:
        """Truncate text to approximate the budget.

        Args:
            text: Source text to truncate.
            budget: Controls output length.
            context: Ignored.

        Returns:
            Truncated text.
        """
        return _truncate(text, budget)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, budget: SummaryBudget) -> str:
    """Truncate text to approximate a budget's character limit."""
    char_limits: dict[SummaryBudget, int] = {
        SummaryBudget.paragraph: 600,
        SummaryBudget.short: 300,
        SummaryBudget.headline: 120,
    }
    limit = char_limits.get(budget, 600)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."
