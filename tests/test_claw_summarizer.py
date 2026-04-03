"""Tests for the claw summarizer."""

from __future__ import annotations

import pytest

from shoal.core.claw_summarizer import LLMSummarizer, StubSummarizer, Summarizer
from shoal.models.claw import SummaryBudget


# ---------------------------------------------------------------------------
# StubSummarizer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_summarizer_short_text():
    s = StubSummarizer()
    result = await s.summarize("Hello world.", SummaryBudget.paragraph)
    assert result == "Hello world."


@pytest.mark.asyncio
async def test_stub_summarizer_truncates_long_text():
    s = StubSummarizer()
    long_text = "word " * 200  # ~1000 chars
    result = await s.summarize(long_text, SummaryBudget.headline)
    assert len(result) <= 125  # 120 + "..."
    assert result.endswith("...")


@pytest.mark.asyncio
async def test_stub_summarizer_paragraph_budget():
    s = StubSummarizer()
    long_text = "word " * 200
    result = await s.summarize(long_text, SummaryBudget.paragraph)
    assert len(result) <= 605


@pytest.mark.asyncio
async def test_stub_summarizer_short_budget():
    s = StubSummarizer()
    long_text = "word " * 200
    result = await s.summarize(long_text, SummaryBudget.short)
    assert len(result) <= 305


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_stub_satisfies_protocol():
    s = StubSummarizer()
    assert isinstance(s, Summarizer)


def test_llm_satisfies_protocol():
    s = LLMSummarizer()
    assert isinstance(s, Summarizer)


# ---------------------------------------------------------------------------
# LLMSummarizer (with mocked call_llm)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_summarizer_calls_call_llm(monkeypatch):
    captured: list[dict] = []

    async def mock_call_llm(model, prompt, max_tokens, temperature):
        captured.append(
            {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        )
        return "Mocked summary."

    monkeypatch.setattr("shoal.core.claw_summarizer.call_llm", mock_call_llm, raising=False)

    # Patch the import inside LLMSummarizer.summarize
    import shoal.services.ai_client

    monkeypatch.setattr(shoal.services.ai_client, "call_llm", mock_call_llm)

    s = LLMSummarizer(model="test-model")
    result = await s.summarize("Some text", SummaryBudget.short, context="session-a")
    assert result == "Mocked summary."
    assert len(captured) == 1
    assert captured[0]["model"] == "test-model"
    assert captured[0]["max_tokens"] == 100  # short budget
    assert "session-a" in captured[0]["prompt"]


@pytest.mark.asyncio
async def test_llm_summarizer_falls_back_on_error(monkeypatch):
    async def failing_call_llm(model, prompt, max_tokens, temperature):
        raise RuntimeError("LLM unavailable")

    import shoal.services.ai_client

    monkeypatch.setattr(shoal.services.ai_client, "call_llm", failing_call_llm)

    s = LLMSummarizer()
    result = await s.summarize("Some text", SummaryBudget.paragraph)
    # Should fall back to truncation, not raise
    assert result == "Some text"
