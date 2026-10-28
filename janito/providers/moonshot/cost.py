"""Cost estimation for the Moonshot (Kimi) provider.

Rates source
------------
The per-1M-token rates below are taken from the official Moonshot AI
pricing for the Kimi K3 / K3.1 model families and apply as of the
verification date.  ``kimi-k3`` lists prices in CNY (¥20.00 input cache
miss, ¥2.00 input cache hit, ¥100.00 output per 1M tokens), which
correspond to approximately $2.75 / $0.28 / $13.75 per 1M tokens.
``kimi-k3.1-pro`` is priced at $2.00 input / $0.20 cache hit / $10.00
output per 1M tokens, and ``kimi-k3.1-pro-highspeed`` at $4.00 input /
$0.20 cache hit / $20.00 output per 1M tokens.  Moonshot adjusts figures
frequently, so cross-check the official rate card before relying on them.

Prompt caching
--------------
Moonshot applies automatic context caching: cached input tokens are billed
at the much lower cache-hit rate (10% of the cache-miss input rate)
instead of the cache-miss rate.  There is no peak-hour surcharge.
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)``.
#:
#: Moonshot applies automatic context caching: repeated input tokens (a
#: stable system prompt, a long document, few-shot examples) are billed at
#: the much lower cache-hit rate instead of the cache-miss rate.
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "kimi-k3": (2.75, 0.28, 13.75),
    "kimi-k3.1-pro": (2.00, 0.20, 10.00),
    "kimi-k3.1-pro-highspeed": (4.00, 0.20, 20.00),
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
        cached: The number of cached input tokens (cache hits).
        is_reference: Marks the request as a reference request (e.g. tokens
            from attached reference documents).  Passed through for future
            reference-token billing; currently the estimate is unchanged.

    Returns:
        The estimated cost formatted as a dollar string with six decimal
        digits (e.g. ``"16.500000$"``), or ``"N/A"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    input_miss, input_hit, output_rate = rates
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
