"""Cost estimation for the Anthropic (Claude) provider.

Rates source
------------
The per-1M-token rates below were taken from the official Claude Platform
pricing page (https://platform.claude.com/docs/en/about-claude/pricing)
and apply as of the verification date.  Anthropic adjusts figures
frequently, so cross-check that page before relying on them.

Claude 4.6 and later models include the full 1M-token context window at
standard pricing, so there is no high-context surcharge.

Prompt caching
--------------
Anthropic applies prompt caching: cached input tokens (cache reads / hits)
are billed at 10% of the base input rate (0.1x), e.g. $0.20/1M for
claude-sonnet-5.  There is no peak-hour surcharge.
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)``.
#:
#: Anthropic applies prompt caching: cached input tokens (cache reads) are
#: billed at the cache-hit rate ($0.20/1M for claude-sonnet-5, 10% of the
#: base input rate).
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.00, 1.00, 50.00),
    "claude-opus-5-5": (4.00, 0.40, 20.00),
    "claude-sonnet-5": (2.00, 0.20, 10.00),
}


def get_cost(
    model: str,
    input: int,
    output: int,
    cached: int,
    is_reference: bool = False,
) -> str:
    """Estimate the monetary cost of a request in dollars.

    Args:
        model: The model name used for the request.
        input: The number of input tokens.
        output: The number of output tokens.
        cached: The number of cached input tokens (cache reads).
        is_reference: Marks the request as a reference request (e.g. tokens
            from attached reference documents).  Passed through for future
            reference-token billing; currently the estimate is unchanged.

    Returns:
        The estimated cost formatted as a dollar string with six decimal
        digits (e.g. ``\"12.000000$\"``), or ``\"N/A\"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    input_miss, input_hit, output_rate = rates
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
