"""Cost estimation for the Alibaba (DashScope) provider.

Rates source
------------
The per-1M-token rates below were taken from the official QwenCloud model
marketplace pages https://www.qwencloud.com/models/qwen3.8-max (last
verified 2026-08-15), https://www.qwencloud.com/models/qwen3.8-flash
(verified 2026-08-27) and https://www.qwencloud.com/models/qwen4-max
(verified 2026-11-18, Qwen4-Max GA 2026-11-16) and apply as of the
verification dates.  Alibaba
adjusts figures frequently, so cross-check the official rate card at
https://www.qwencloud.com/pricing/token-plan before relying on them.
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)``.
#:
#: Alibaba applies automatic prefix caching: repeated input tokens (a
#: stable system prompt, a long document, few-shot examples) are billed at
#: the much lower implicit cache-hit rate instead of the cache-miss rate.
#: There is no peak-hour surcharge.
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "qwen3.8-max": (2.0, 0.25, 6.0),
    "qwen3.8-max-0902": (2.0, 0.25, 6.0),
    # qwen4-max: $1.50 input / $0.075 implicit cache hit / $4.50 output
    # per 1M tokens (https://www.qwencloud.com/models/qwen4-max).
    "qwen4-max": (1.5, 0.075, 4.5),
    # qwen3.8-flash: $0.15 input / $0.016 implicit cache hit / $0.47 output
    # per 1M tokens (https://www.qwencloud.com/models/qwen3.8-flash).
    "qwen3.8-flash": (0.15, 0.016, 0.47),
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
        cached: The number of cached input tokens.
        is_reference: Marks the request as a reference request (e.g. tokens
            from attached reference documents).  Passed through for future
            reference-token billing; currently the estimate is unchanged.

    Returns:
        The estimated cost formatted as a dollar string with six decimal
        digits (e.g. ``"0.420000$"``), or ``"N/A"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    input_miss, input_hit, output_rate = rates
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
