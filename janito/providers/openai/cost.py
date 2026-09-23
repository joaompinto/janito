"""Cost estimation for the OpenAI provider.

Rates source
------------
The per-1M-token rates below were taken from the official OpenAI API
pricing for the GPT-6 family (Sol, Luna, Astra) and apply as of the
verification date (2026-09-23).  OpenAI adjusts figures frequently, so
cross-check the official rate card before relying on them.

High-context prompts
--------------------
Requests whose input exceeds 272K tokens are billed at 2x the standard
input rate and 1.5x the standard output rate for the **whole** request
-- not just the portion above the threshold.  Cached-input reads scale
with the input rate, so they are also billed at 2x in high-context mode.

Cache writes
------------
OpenAI bills cache writes at 1.25x the uncached input rate.  The usage
payload does not report cache-write token counts, so the estimate below
covers input reads (cache miss + cache hit) and output only.
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)`` for standard requests.
#:
#: OpenAI applies automatic prefix caching: repeated input tokens (a stable
#: system prompt, a long document, few-shot examples) are billed at the much
#: lower cache-read rate (10% of the input rate) instead of the cache-miss
#: rate.  There is no peak-hour surcharge.
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6-astra": (10.00, 1.00, 50.00),
}

#: Input-token count above which the whole request is billed as high-context
#: (2x input / 1.5x output).  Requests at or below this count use the
#: standard rates.
_HIGH_CONTEXT_INPUT_TOKENS = 272_000

#: High-context multipliers applied to the whole request: ``(input, output)``.
#: Cached-input reads scale with the input multiplier.
_HIGH_CONTEXT_MULTIPLIERS = (2.0, 1.5)


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
        digits (e.g. ``"1.400000$"``), or ``"N/A"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    input_miss, input_hit, output_rate = rates
    if input > _HIGH_CONTEXT_INPUT_TOKENS:
        input_multiplier, output_multiplier = _HIGH_CONTEXT_MULTIPLIERS
        input_miss *= input_multiplier
        input_hit *= input_multiplier
        output_rate *= output_multiplier
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
