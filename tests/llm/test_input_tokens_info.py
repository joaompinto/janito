"""
Tests for the input-tokens/max-tokens display (issue #31).

The token-usage summary shown at the end of each prompt should display the
output token count alongside the configured max output tokens using the
``output/max`` format, e.g. ``Out: 123/65.5k``.

These tests verify:
  - ``format_tokens()`` human-readable formatting.
  - The CLI usage summary line (rendered through the real
    ``janito.ui.usage._display_usage``) shows the ``In: x/max`` part when a
    max-input value is configured and the plain ``In: x`` part otherwise.
  - The web ``UsageEvent`` serialization includes ``max_tokens`` only when
    it is set.
  - The web ``usage_event_from_usage()`` passes ``max_tokens`` through
    (``CompletionsTurnAccumulator`` as the usage source).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

if pytest is not None:
    from janito.llm_adapters.usage import format_tokens
    from janito.providers.costing import format_cost

    # ---- format_tokens unit tests ------------------------------------

    def test_format_tokens_plain_integer():
        assert format_tokens(150) == "150"

    def test_format_tokens_thousands():
        assert format_tokens(2000) == "2k"

    def test_format_tokens_thousands_fractional():
        assert format_tokens(12345) == "12.3k"

    def test_format_tokens_millions():
        assert format_tokens(4_000_000) == "4m"

    def test_format_tokens_none():
        assert format_tokens(None) is None

    # ---- CLI usage-line construction ---------------------------------
    #
    # Rule 6 (dev-docs/testing.md): drive the real _display_usage render
    # path and compose expectations from the source-of-truth
    # format_tokens() -- no local replica of the parts-building logic, no
    # hardcoded rendered strings.

    def _usage(input_tokens, output_tokens, cached_tokens):
        from types import SimpleNamespace

        return SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        )

    def _summary_parts(plain):
        """Parse the ``=== ... ===`` line into a ``{label: value}`` dict."""
        assert plain.startswith("=== ") and plain.endswith(" ===")
        body = plain[len("=== ") : -len(" ===")]
        return {part.split(": ", 1)[0]: part.split(": ", 1)[1] for part in body.split(" | ")}

    def _render_usage_line(provider, model, usage, max_input_tokens=None, max_output_tokens=None):
        """Render through the real _display_usage and return the parsed parts."""
        from io import StringIO

        from rich.console import Console

        from janito.ui.usage import _display_usage

        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        _display_usage(
            usage,
            max_input_tokens,
            max_output_tokens,
            console,
            provider=provider,
            model=model,
        )
        return buf.getvalue().strip()

    def _usage_line(input_tokens, max_input_tokens=None):
        """In/Out parts of the usage line for a Completions-shaped usage."""
        usage = _usage(input_tokens, 50, None)
        return _summary_parts(_render_usage_line(None, None, usage, max_input_tokens=max_input_tokens))

    def _cost_usage_line(provider, model, input_tokens, output_tokens, cached_tokens):
        """Parsed parts of the usage line with the Cost part computed."""
        usage = _usage(input_tokens, output_tokens, cached_tokens)
        return _summary_parts(_render_usage_line(provider, model, usage))

    def _turn_usage_parts(provider, model, stats):
        """Parsed parts of the usage line for a TurnInfo (the turn report)."""
        return _summary_parts(_render_usage_line(provider, model, stats))

    def _summary_line_index(text):
        """Line index of the ``=== ... ===`` summary in rendered output."""
        return next(i for i, line in enumerate(text.splitlines()) if line.startswith("=== "))

    # The one stable marker the capacity-warning tests share (Rule 4: pin
    # a marker once, assert kind + ordering, never the full sentence).
    CAPACITY_WARNING_MARKER = "Reached 80% of input capacity"

    def test_usage_line_cost_from_provider_cost_module(monkeypatch):
        """The Cost part is computed via get_provider_cost for the provider."""
        # Pin the request time to a weekday off-peak hour (Monday 12:00 UTC)
        # so the estimate is deterministic: DeepSeek Flash is $0.15 in
        # (miss) + $0.60 out per 1M tokens off-peak.
        monkeypatch.setattr(
            "janito.providers.deepseek.cost._utcnow",
            lambda: datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        )
        parts = _cost_usage_line("deepseek", "deepseek-flash", 1_000_000, 1_000_000, 0)
        # Compose the expectation from the costing source of truth: the
        # numeric cost of the same counters rendered by format_cost, plus
        # the provider's rate-band annotation (Rule 6).
        assert parts["Cost"] == format_cost(0.75) + " (off-peak)"

    def test_usage_line_cost_bills_cached_input_at_cache_hit(monkeypatch):
        """Cached input tokens are billed at the provider's cache-hit rate."""
        # Pin the request time to a weekday off-peak hour (Monday 12:00 UTC);
        # 500k of the 1M input tokens are cache hits ($0.003 vs $0.15/1M).
        monkeypatch.setattr(
            "janito.providers.deepseek.cost._utcnow",
            lambda: datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        )
        parts = _cost_usage_line("deepseek", "deepseek-flash", 1_000_000, 1_000_000, 500_000)
        assert parts["Cost"] == format_cost(0.6765) + " (off-peak)"

    def test_usage_line_cost_google_provider():
        """Google Gemini usage calculates cost using google.cost module."""
        parts = _cost_usage_line("google", "gemini-3.7-flash", 1_000_000, 1_000_000, 0)
        assert parts["Cost"] == format_cost(4.5)

    def test_usage_line_cost_minimax_provider():
        """MiniMax usage calculates cost using minimax.cost module."""
        parts = _cost_usage_line("minimax", "MiniMax-M3", 100_000, 100_000, 0)
        assert parts["Cost"] == format_cost(0.15)

    def test_usage_line_cost_openai_provider():
        """OpenAI GPT-5.6 Luna usage calculates cost using openai.cost module."""
        # 100k input tokens (<= 272K threshold): standard rates
        # (100k * $0.20 + 1M * $1.20) / 1M = 1.22.
        parts = _cost_usage_line("openai", "gpt-5.6-luna", 100_000, 1_000_000, 0)
        assert parts["Cost"] == format_cost(1.22)

    def test_usage_line_cost_openai_high_context():
        """High-context OpenAI requests (> 272K input tokens) bill at 2x/1.5x."""
        # (300k * $0.40 + 1M * $1.80) / 1M = 1.92.
        parts = _cost_usage_line("openai", "gpt-5.6-luna", 300_000, 1_000_000, 0)
        assert parts["Cost"] == format_cost(1.92)

    def test_usage_line_cost_anthropic_provider():
        """Anthropic usage calculates cost using anthropic.cost module."""
        # 1M input (cache miss) at $2 + 1M output at $10 per 1M tokens.
        parts = _cost_usage_line("anthropic", "claude-sonnet-5", 1_000_000, 1_000_000, 0)
        assert parts["Cost"] == format_cost(12.0)

    def test_usage_line_cost_without_provider_model_is_na():
        """No provider/model falls back to Cost: N/A."""
        parts = _cost_usage_line(None, None, 1_000_000, 1_000_000, 0)
        assert parts["Cost"] == "N/A"

    def test_usage_line_cost_uses_turn_specific_counters(monkeypatch):
        """TurnInfo bills the turn-wide cumulative counters for the Cost.

        The displayed In/Out/Cached keep the final round's counters, but the
        cost must be computed from the turn totals (tool-call rounds
        included).  DeepSeek Flash off-peak: $0.15 in (miss) + $0.60 out
        + $0.003 cache-hit per 1M tokens.
        """
        from janito.llm_adapters.usage import TurnInfo

        # Pin the request time to a weekday off-peak hour (Monday 12:00 UTC)
        # so the estimate is deterministic.
        monkeypatch.setattr(
            "janito.providers.deepseek.cost._utcnow",
            lambda: datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        )
        # Final round reports 1M in / 1M out, but the turn accumulated
        # 2M in (500k cached) / 2M out across tool-call rounds.
        stats = TurnInfo(
            total=1_000_000,
            last_input=1_000_000,
            last_output=1_000_000,
            last_cached=0,
            turn_input=2_000_000,
            turn_cached=500_000,
            turn_output=2_000_000,
        )
        parts = _turn_usage_parts("deepseek", "deepseek-flash", stats)
        # Cost from turn totals: 1.5M*$0.15 + 0.5M*$0.003 + 2M*$0.60
        #   = 0.225 + 0.0015 + 1.2 = 1.4265.
        assert parts["Cost"] == format_cost(1.4265) + " (off-peak)"
        # The displayed counters still mirror the final round's request.
        assert parts["In"] == format_tokens(1_000_000)
        assert parts["Out"] == format_tokens(1_000_000)

    # ---- In/Out parts of the CLI usage line --------------------------

    def test_input_with_max_tokens():
        # Slash form when max input is configured.
        parts = _usage_line(1200, max_input_tokens=128000)
        assert parts["In"] == f"{format_tokens(1200)}/{format_tokens(128000)}"
        assert parts["Out"] == format_tokens(50)

    def test_input_without_max_tokens():
        parts = _usage_line(1200)
        assert parts["In"] == format_tokens(1200)
        assert parts["Out"] == format_tokens(50)
        # No slash when max is not configured
        assert "/" not in parts["In"]

    def test_input_with_max_exact_values():
        parts = _usage_line(500, max_input_tokens=1000)
        assert parts["In"] == f"{format_tokens(500)}/{format_tokens(1000)}"
        assert parts["Out"] == format_tokens(50)

    def test_input_zero_with_max():
        parts = _usage_line(0, max_input_tokens=128000)
        assert parts["In"] == f"{format_tokens(0)}/{format_tokens(128000)}"
        assert parts["Out"] == format_tokens(50)

    def test_input_without_input_max_but_with_output_max():
        parts = _usage_line(1200)
        assert parts["In"] == format_tokens(1200)
        assert parts["Out"] == format_tokens(50)

    # ---- Input-capacity warning (80% of max input tokens) ------------

    def test_usage_warning_when_input_over_80_percent():
        """A warning is printed when In tokens exceed 80% of max input."""
        text = _render_usage_line(None, None, _usage(90_000, 10_000, 0), max_input_tokens=100_000)
        assert CAPACITY_WARNING_MARKER in text

    def test_usage_warning_printed_before_usage_line():
        """The capacity warning appears before the usage summary line."""
        text = _render_usage_line(None, None, _usage(90_000, 10_000, 0), max_input_tokens=100_000)
        warning_line = next(line for line in text.splitlines() if CAPACITY_WARNING_MARKER in line)
        assert text.splitlines().index(warning_line) < _summary_line_index(text)

    def test_usage_no_warning_at_exactly_80_percent():
        """Exactly 80% of capacity does not trigger the warning."""
        text = _render_usage_line(None, None, _usage(80_000, 20_000, 0), max_input_tokens=100_000)
        assert CAPACITY_WARNING_MARKER not in text

    def test_usage_no_warning_below_80_percent():
        """Input below 80% of capacity does not trigger the warning."""
        text = _render_usage_line(None, None, _usage(79_999, 20_001, 0), max_input_tokens=100_000)
        assert CAPACITY_WARNING_MARKER not in text

    def test_usage_no_warning_without_max_input_tokens():
        """Without a configured max input, no capacity warning is shown."""
        text = _render_usage_line(None, None, _usage(90_000, 10_000, 0))
        assert CAPACITY_WARNING_MARKER not in text

    # ---- Web UsageEvent serialization --------------------------------

    def test_usage_event_to_dict_without_max():
        from janito.web.backend.events import UsageEvent

        ev = UsageEvent(total=100, last_input=80, last_output=20, last_cached=10)
        d = ev.to_dict()
        assert d == {
            "type": "usage",
            "total": 100,
            "last_input": 80,
            "last_output": 20,
            "last_cached": 10,
        }
        assert "max_tokens" not in d

    def test_usage_event_to_dict_with_max():
        from janito.web.backend.events import UsageEvent

        ev = UsageEvent(total=100, last_input=80, last_output=20, last_cached=0, max_tokens=65536)
        d = ev.to_dict()
        assert d["max_tokens"] == 65536

    # ---- usage_event_from_usage with max_tokens ----------------------

    def test_stream_accumulator_usage_event_passes_max_tokens():
        from janito.llm_adapters.completions import CompletionsTurnAccumulator
        from janito.web.backend.events import usage_event_from_usage

        class FakeUsage:
            total_tokens = 200
            prompt_tokens = 150
            completion_tokens = 50
            prompt_tokens_details = None

        acc = CompletionsTurnAccumulator(usage=FakeUsage())
        ev = usage_event_from_usage(acc.usage_object(), max_tokens=32768)
        assert ev is not None
        assert ev.max_tokens == 32768
        assert ev.to_dict()["max_tokens"] == 32768

    def test_stream_accumulator_usage_event_no_max():
        from janito.llm_adapters.completions import CompletionsTurnAccumulator
        from janito.web.backend.events import usage_event_from_usage

        class FakeUsage:
            total_tokens = 200
            prompt_tokens = 150
            completion_tokens = 50
            prompt_tokens_details = None

        acc = CompletionsTurnAccumulator(usage=FakeUsage())
        ev = usage_event_from_usage(acc.usage_object())
        assert ev is not None
        assert ev.max_tokens is None
        assert "max_tokens" not in ev.to_dict()

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
