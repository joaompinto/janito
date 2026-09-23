"""
Config key constants and helpers.

Defines the scoped-config key sets (flat, provider-scoped, model-scoped) and
the helpers that build/parse dotted config keys.  Extracted from
:mod:`janito.general_config` so the core config storage module stays focused
on read/write primitives.
"""

from .providers.variant_names import normalize_provider

# Config keys that are stored per-provider (as ``<provider>.<key>``)
PROVIDER_SCOPED_KEYS = {
    "model",
    "endpoint",
}

# Config keys that are stored per-provider *and* per-model (as
# ``<provider>.models.<model>.<key>``).  These carry model-level settings
# (token limits, reasoning level, API type, Stateless-mode flag), so
# each provider/model pair keeps its own values.
MODEL_SCOPED_KEYS = {
    "max-input-tokens",
    "max-output-tokens",
    "effort",
    "api-type",
    "stateless-mode",
    "disabled-tools",
}

# Config keys whose values are lists of tool names set via CLI.
LIST_VALUED_KEYS = {"disabled-tools"}

# Config keys whose values should be coerced to int when set via CLI.
INT_VALUED_KEYS = {"max-input-tokens", "max-output-tokens"}

# Config keys whose values should be coerced to bool when set via CLI.
BOOL_VALUED_KEYS = {"stateless-mode", "used-files"}


def split_model_scoped_key(key: str) -> tuple[str, str, str] | None:
    """Split a full model-scoped key into ``(provider, model, leaf)``.

    A full model-scoped key has the shape
    ``<provider>.models.<model>.<leaf>`` where ``leaf`` is one of
    :data:`MODEL_SCOPED_KEYS`.  Model names may themselves contain dots
    (e.g. ``gpt-6-luna``), so the provider is split on the ``.models.``
    marker and the leaf on the **last** dot.

    Args:
        key: The dotted key to parse.

    Returns:
        The ``(provider, model, leaf)`` tuple, or ``None`` when the key is
        not in model-scoped form.
    """
    marker = ".models."
    if marker not in key:
        return None
    provider, rest = key.split(marker, 1)
    if "." not in rest:
        return None
    model, leaf = rest.rsplit(".", 1)
    if not provider or not model or leaf not in MODEL_SCOPED_KEYS:
        return None
    return provider, model, leaf


def model_config_key(provider: str) -> str:
    """Return the config key used to store the model for a given provider.

    Models are stored per-provider using the ``<provider>.model`` key so that
    each provider can have its own default model.

    Args:
        provider: The provider name

    Returns:
        The provider-scoped config key, e.g. ``"openai.model"``
    """
    return f"{normalize_provider(provider)}.model"


def endpoint_config_key(provider: str) -> str:
    """Return the config key used to store the endpoint for a given provider.

    Endpoints are stored per-provider using the ``<provider>.endpoint`` key so
    that each provider can have its own endpoint override.

    Args:
        provider: The provider name

    Returns:
        The provider-scoped config key, e.g. ``"custom.endpoint"``
    """
    return f"{normalize_provider(provider)}.endpoint"


def model_scoped_config_key(provider: str, model: str, key: str) -> str:
    """Return the config key for a model-scoped setting.

    Model-level settings (token limits, reasoning level, API type,
    Stateless-mode flag) are stored per provider/model pair under
    ``providers.<provider>.models.<model>.<key>`` so each provider/model
    combination keeps its own values.

    Args:
        provider: The provider name (normalized to lowercase).
        model: The model name.
        key: A model-scoped config key (one of :data:`MODEL_SCOPED_KEYS`).

    Returns:
        The full model-scoped config key, e.g.
        ``"openai.models.gpt-6-luna.max-output-tokens"``.
    """
    return f"{normalize_provider(provider)}.models.{model}.{key}"


def normalize_api_type(value: str, allowed_types: list[str] | None = None) -> str:
    """Normalize an API type value to its canonical form.

    Accepts ``responses``/``completions`` (and any native-SDK API type, e.g.
    ``anthropic``, ``dashscope``, ``gemini``) in any casing -- the values used with
    ``--set api-type=...`` -- and returns the canonical form
    (``"Responses"`` / ``"Completions"`` / ``"Anthropic"`` /
    ``"DashScope"`` / ``"Gemini"``, ...). The accepted set is the OpenAI-SDK types plus the keys of
    ``REQUIRES_BY_API_TYPE`` (see ``providers.validation.get_all_api_types``).

    Args:
        value: The raw API type value
        allowed_types: The accepted canonical API types.  Callers that
            already know the set (e.g. ``general_config.resolve_api_type``)
            pass it explicitly (dependency injection, issue #110); when
            omitted it is read from the provider registry, which is a
            one-way (acyclic) dependency -- the provider layer never imports
            this module.

    Returns:
        The canonical API type (e.g. ``"Responses"``, ``"Completions"``,
        ``"Anthropic"`` or ``"DashScope"``).

    Raises:
        ValueError: If the value is not a known API type
    """
    if allowed_types is None:
        from .providers.validation import get_all_api_types

        allowed_types = get_all_api_types()
    known = allowed_types
    raw = str(value).strip()
    for api_type in known:
        if api_type.lower() == raw.lower():
            return api_type
    raise ValueError(f"Unsupported API type '{value}'. Supported values: " f"{', '.join(known)}")


def get_masked_api_key(api_key: str) -> str:
    """Mask an API key, preserving its length for display.

    The returned string has the same length as ``api_key``: the first few and
    last few characters are shown and the middle is filled with ``.`` so the
    output never reveals the full key.

    Args:
        api_key: The API key to mask

    Returns:
        str: Masked API key with the same length as the input, or
            ``(not set)`` when the key is empty.
    """
    if not api_key:
        return "(not set)"
    prefix_len = 6
    suffix_len = 4
    n = len(api_key)
    middle = n - prefix_len - suffix_len
    if middle <= 0:
        # Key too short to keep both ends while preserving length; mask it all.
        return "." * n
    return f"{api_key[:prefix_len]}{'.' * middle}{api_key[-suffix_len:]}"
