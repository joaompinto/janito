"""Cost estimation for the OpenCode Go provider.

Rates source
------------
The per-1M-token rates below were taken from the OpenCode Go model list and
pricing tables at https://opencode.ai/docs/console/go and the model metadata
at https://models.dev (provider ``opencode-go``), verified 2026-11-15.
OpenCode adjusts the catalog and its limits frequently, so cross-check that
page before relying on them.

What the estimate covers
------------------------
Go is a subscription plan: the amounts below are the token costs the gateway
uses to count usage toward each model's monthly allowance, not a per-request
bill.  Cache writes are not modelled by janito's token accounting, so they
are ignored (cache reads are billed at the cache-hit rate).

Context tiers
-------------
Some models charge a higher rate for the whole request once the prompt
exceeds a threshold (GPT-6 Luna / GPT-5.6 Luna at 272K, Grok 4.7 at 200K,
Claude Haiku 5.5 at 100K, MiniMax M3 at 512K, Qwen3.7 Plus at 256K).
"""

#: Per-1M-token rates (USD) keyed by model name:
#: ``(input cache miss, input cache hit, output)``.
_MODEL_RATES: dict[str, tuple[float, float, float]] = {
    "beam-free": (0.0, 0.0, 0.0),
    "claude-haiku-5-5": (0.10, 0.01, 0.50),
    "deepseek-v4-pro": (0.66, 0.022, 1.98),
    "deepseek-v4.1-flash": (0.15, 0.003, 0.60),
    "gemini-4-argon": (2.00, 0.10, 10.00),
    "glm-5.2": (1.40, 0.26, 4.40),
    "glm-5.3": (1.40, 0.26, 4.40),
    "glm-5.3-flash": (0.15, 0.03, 0.50),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "grok-4.7": (2.00, 0.50, 6.00),
    "hy3": (0.14, 0.035, 0.58),
    "hy4": (0.834, 0.042, 2.501),
    "hy4-preview": (0.834, 0.042, 2.501),
    "iceman-contributor-free": (0.0, 0.0, 0.0),
    "kimi-k2.7-code": (0.95, 0.19, 4.00),
    "kimi-k3": (3.00, 0.30, 15.00),
    "kimi-k3.1-pro": (2.00, 0.20, 10.00),
    "longcat-2.0": (0.30, 0.006, 1.20),
    "longcat-2.5-free": (0.0, 0.0, 0.0),
    "mimo-v2.5": (0.14, 0.0028, 0.28),
    "mimo-v2.5-pro": (0.435, 0.003625, 0.87),
    "mimo-v2.6-flash": (0.14, 0.0028, 0.28),
    "mimo-v2.6-pro": (0.435, 0.003625, 0.87),
    "minimax-m3": (0.30, 0.06, 1.20),
    "minimax-m3.1-flash": (0.15, 0.015, 0.60),
    "muse-spark-1.2-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "qwen3.7-plus": (0.40, 0.04, 1.60),
    "qwen3.8-flash": (0.15, 0.016, 0.47),
    "qwen3.8-max": (2.00, 0.25, 6.00),
    "step-5-preview": (1.00, 0.10, 2.70),
}

#: Context-tier overrides keyed by model name:
#: ``(threshold_tokens, (input miss, input hit, output))``.
#:
#: The higher rates apply to the whole request once the prompt exceeds the
#: threshold (not only to the tokens over it).
_CONTEXT_TIERS: dict[str, tuple[int, tuple[float, float, float]]] = {
    "claude-haiku-5-5": (100_000, (0.50, 0.05, 2.50)),
    "gpt-5.6-luna": (272_000, (0.40, 0.04, 1.80)),
    "gpt-6-luna": (272_000, (0.20, 0.02, 0.75)),
    "grok-4.7": (200_000, (4.00, 1.00, 12.00)),
    "minimax-m3": (512_000, (0.60, 0.12, 2.40)),
    "qwen3.7-plus": (256_000, (1.20, 0.12, 4.80)),
}


def get_cost(
    model: str,
    input: int,
    output: int,
    cached: int,
    is_reference: bool = False,
) -> str:
    """Estimate the token cost of a request in dollars.

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
        digits (e.g. ``"0.040000$"``), or ``"N/A"`` for an unknown model.
    """
    rates = _MODEL_RATES.get(model)
    if rates is None:
        return "N/A"
    tier = _CONTEXT_TIERS.get(model)
    if tier is not None and input > tier[0]:
        rates = tier[1]
    input_miss, input_hit, output_rate = rates
    cost = ((input - cached) * input_miss + cached * input_hit + output * output_rate) / 1_000_000
    return f"{cost:.6f}$"
