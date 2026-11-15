"""
Provider cost estimation.

Computes the estimated monetary cost of a request from the provider's
``cost.py`` module (``janito.providers.<name>.cost``) and renders it with an
adaptive, magnitude-aware format (issue #67): :func:`get_provider_cost`
returns the display string, :func:`get_provider_cost_value` the numeric
dollar amount for aggregation (issue #72).

Part of the split provider-config module family (see
:mod:`janito.providers.registry`).
"""

from datetime import datetime
from functools import cache

from .registry import get_provider


def format_cost(cost: float) -> str:
    """Render a dollar amount with an adaptive, magnitude-aware format.

    The number of significant digits grows as the value shrinks, so both
    tiny and large estimates stay readable (issue #67):

    * value < 1 cent        -> ``0.abc\u00a2`` (3 decimal digits, ``c`` rounded)
    * 1 cent <= value < 1$  -> ``X.a\u00a2``   (1 decimal digit, ``a`` rounded)
    * 1$ <= value < 100$    -> ``X.a$``     (1 decimal digit, ``a`` rounded)
    * value >= 100$         -> ``X$``       (integer, rounded)

    A value that rounds up across a unit boundary is promoted to the next
    unit (e.g. ``99.96$`` -> ``100$``, ``0.009999$`` -> ``1.0\u00a2``) so the
    output never shows ``100.0\u00a2`` / ``100.0$``.
    """
    cents = cost * 100
    if cost < 0.01:
        if round(cents, 3) >= 1.0:  # 0.abc\u00a2 rounded up to a full cent
            return f"{cents:.1f}\u00a2"
        return f"{cents:.3f}\u00a2"
    if cost < 1.0:
        if round(cents, 1) >= 100.0:  # X.a\u00a2 rounded up to a full dollar
            return f"{cost:.1f}$"
        return f"{cents:.1f}\u00a2"
    if cost < 100.0:
        if round(cost, 1) >= 100.0:  # X.a$ rounded up to 100
            return f"{cost:.0f}$"
        return f"{cost:.1f}$"
    return f"{cost:.0f}$"


def _adapt_cost_string(raw: str) -> str:
    """Re-render a provider cost string with the adaptive format.

    Provider cost modules return ``NN.DDDDDD$``, optionally followed by a
    rate-band annotation such as `` (off-peak)``.  The numeric part is
    re-rendered with :func:`format_cost` and the annotation is preserved.
    ``N/A`` and unparseable strings pass through unchanged.
    """
    value, sep, annotation = raw.partition("$")
    if not sep:
        return raw
    try:
        return format_cost(float(value)) + annotation
    except ValueError:
        return raw


@cache
def _cost_module(base: str):
    """Import and cache a provider's ``cost`` module by base provider name.

    Hyphens in the provider name map to underscores in the package name
    (``opencode-go`` -> :mod:`janito.providers.opencode_go`).  The module
    object is cached (the ``get_cost`` attribute is still read per call, so
    runtime monkeypatches of the module's ``get_cost`` keep working).
    Raises ``ImportError`` for providers without a cost module.
    """
    from importlib import import_module

    # Provider names may contain hyphens (``opencode-go``); their package
    # directory uses underscores (``opencode_go``).
    module_base = base.replace("-", "_")
    return import_module(f"janito.providers.{module_base}.cost")


def _provider_cost_raw(
    provider: str,
    model: str,
    input: int,
    output: int,
    cached: int,
    now: datetime | None = None,
    is_reference: bool = False,
) -> str | None:
    """Return the raw dollar-formatted cost string from the provider's cost module.

    Resolves the provider (variants resolve to their base provider's cost
    module) and calls its ``get_cost(model, input, output, cached, ...)``,
    returning the raw string (e.g. ``"0.880000$ (off-peak)"``) exactly as the
    module produced it.  ``None`` is returned when the provider is unknown,
    has no cost module, or the module raised -- the callers decide how to
    render that (``"N/A"`` / ``None``).

    Args:
        provider: The provider name (case-insensitive).  Registered provider
            variants (``<provider>-<word>``) resolve to their base
            provider's cost module.
        model: The model name.
        input: The number of input tokens.
        output: The number of output tokens.
        cached: The number of cached input tokens.
        now: Optional request time forwarded to the provider's ``get_cost``
            (when it accepts it) to pick peak/off-peak rates (e.g. DeepSeek).
        is_reference: Marks the request as a reference request (e.g. tokens
            from attached reference documents); forwarded to the provider's
            ``get_cost``.

    Returns:
        The raw cost string, or ``None`` when the provider is unknown or has
        no cost module.
    """
    found = get_provider(provider)
    if found is None:
        return None
    base = found.base_name or found.name
    try:
        get_cost = getattr(_cost_module(base), "get_cost")
        if now is None:
            return get_cost(model, input, output, cached, is_reference=is_reference)
        return get_cost(model, input, output, cached, now=now, is_reference=is_reference)
    except (ImportError, AttributeError, TypeError):
        return None


def get_provider_cost(
    provider: str,
    model: str,
    input: int,
    output: int,
    cached: int,
    now: datetime | None = None,
    is_reference: bool = False,
) -> str:
    """
    Get the estimated monetary cost of a request for a provider's model.

    The cost is computed by the provider's ``cost.py`` module
    (``janito.providers.<name>.cost``), which exports a
    ``get_cost(model, input, output, cached, is_reference=False)`` function
    returning a dollar-formatted string with six decimal digits (e.g.
    ``"0.880000$ (off-peak)"`` when the provider annotates the applied rate
    band).  The numeric part is re-rendered with the adaptive format of
    :func:`format_cost` (e.g. ``"88.0\u00a2 (off-peak)"``) before being
    returned.  Providers without a cost module fall back to ``"N/A"``.

    Args:
        provider: The provider name (case-insensitive).  Registered provider
            variants (``<provider>-<word>``) resolve to their base
            provider's cost module.
        model: The model name.
        input: The number of input tokens.
        output: The number of output tokens.
        cached: The number of cached input tokens.
        now: Optional request time forwarded to the provider's ``get_cost``
            (when it accepts it) to pick peak/off-peak rates (e.g. DeepSeek);
            when omitted the provider applies its default (current time).
        is_reference: Marks the request as a reference request (e.g. tokens
            from attached reference documents); forwarded to the provider's
            ``get_cost``.  DeepSeek bills reference requests at the peak
            rates regardless of the request time and omits the rate-band
            suffix from the returned string; other providers ignore it.

    Returns:
        The estimated cost rendered with the adaptive format (e.g.
        ``"88.0\u00a2 (off-peak)"`` / ``"1.2$"``), preserving the provider's
        rate-band annotation, or ``"N/A"`` when the provider is unknown or
        has no cost module.
    """
    raw = _provider_cost_raw(provider, model, input, output, cached, now=now, is_reference=is_reference)
    if raw is None:
        return "N/A"
    return _adapt_cost_string(raw)


def get_provider_cost_value(
    provider: str,
    model: str,
    input: int,
    output: int,
    cached: int,
    now: datetime | None = None,
    is_reference: bool = False,
) -> float | None:
    """Return the estimated cost of a request as a plain dollar amount.

    Same computation as :func:`get_provider_cost` (the provider's ``cost.py``
    module), but returns the numeric dollar value instead of the adaptive
    display string -- suitable for aggregation (e.g. the accounting database,
    issue #72) where a formatted ``"88.0\u00a2 (off-peak)"`` string would not
    be summable.

    Args:
        provider: The provider name (case-insensitive).
        model: The model name.
        input: The number of input tokens.
        output: The number of output tokens.
        cached: The number of cached input tokens.
        now: Optional request time forwarded to the provider's ``get_cost``.
        is_reference: Marks the request as a reference request; forwarded to
            the provider's ``get_cost``.

    Returns:
        The estimated cost in dollars (e.g. ``0.88``), or ``None`` when the
        provider is unknown, has no cost module, or the cost could not be
        parsed as a number.
    """
    raw = _provider_cost_raw(provider, model, input, output, cached, now=now, is_reference=is_reference)
    if raw is None:
        return None
    value, sep, _ = raw.partition("$")
    if not sep:
        return None
    try:
        return float(value)
    except ValueError:
        return None
