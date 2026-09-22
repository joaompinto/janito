"""Cost estimation for the Xiaomi provider.

Rates source
------------
The per-1M-token rates below are the official Xiaomi pricing for the
MiMo-V2.6 series (international, USD, per 1M tokens).  MiMo-V2.6-Flash
keeps the previous V2.5 rates ($0.14 input cache miss, $0.0028 input
cache hit, $0.28 output); MiMo-V2.6-Pro and the UltraSpeed variant bill
at higher flagship rates.  Xiaomi adjusts figures frequently, so
cross-check the official rate card before relying on them.

Prompt caching
--------------
Xiaomi applies automatic prompt caching: repeated input tokens (a stable
system prompt, a long document, few-shot examples) are billed at the much
lower cache-hit rate instead of the cache-miss rate.  There is no
peak-hour surcharge.
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)``.
#:
#: Xiaomi applies automatic prompt caching: cached input tokens are billed
#: at the much lower cache-hit rate instead of the cache-miss rate.
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "mimo-v2.6-flash": (0.14, 0.0028, 0.28),
    "mimo-v2.6-pro": (0.435, 0.0036, 0.87),
    "mimo-v2.6-pro-ultraspeed": (4.35, 0.036, 8.7),
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
        digits (e.g. ``\"0.422800$\"``), or ``\"N/A\"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    input_miss, input_hit, output_rate = rates
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
