"""Per-provider configuration package.

Each ``janito.providers.<name>.config`` module exports that provider's
``PROVIDER_CONFIG`` entry.  This package assembles the entries into the
internal ``_PROVIDER_CONFIGS`` dict and the optional-package map
``REQUIRES_BY_API_TYPE``; the per-provider ``Provider`` objects are built
from these by :func:`janito.providers.registry.get_provider`.

Configuration is organized at two levels: the *provider level* holds what is
intrinsic to the provider (``default_model``, ``endpoint``,
``endpoint_by_api_type``), while everything that depends on the model lives
under the per-provider ``models`` dict, keyed by model name.  See
:mod:`janito.providers.template.config` for a fully commented reference of
every CONFIG option (with example values).
"""

from .alibaba.config import PROVIDER_CONFIG as _ALIBABA_CONFIG
from .anthropic.config import PROVIDER_CONFIG as _ANTHROPIC_CONFIG
from .apertus.config import PROVIDER_CONFIG as _APERTUS_CONFIG
from .custom.config import CUSTOM_ENDPOINT_MARKER as CUSTOM_ENDPOINT_MARKER
from .custom.config import PROVIDER_CONFIG as _CUSTOM_CONFIG
from .deepseek.config import PROVIDER_CONFIG as _DEEPSEEK_CONFIG
from .google.config import PROVIDER_CONFIG as _GOOGLE_CONFIG
from .meta.config import PROVIDER_CONFIG as _META_CONFIG
from .minimax.config import PROVIDER_CONFIG as _MINIMAX_CONFIG
from .moonshot.config import PROVIDER_CONFIG as _MOONSHOT_CONFIG
from .openai.config import PROVIDER_CONFIG as _OPENAI_CONFIG
from .openrouter.config import PROVIDER_CONFIG as _OPENROUTER_CONFIG
from .xai.config import PROVIDER_CONFIG as _XAI_CONFIG
from .xiaomi.config import PROVIDER_CONFIG as _XIAOMI_CONFIG
from .zai.config import PROVIDER_CONFIG as _ZAI_CONFIG

# Per-provider built-in defaults, assembled from the per-provider ``config.py``
# modules above (each entry is the module's ``PROVIDER_CONFIG``, held by
# reference).  See the module docstring for the entry schema.
_PROVIDER_CONFIGS: dict[str, dict] = {
    # AI Providers with OpenAI-compatible APIs
    "openai": _OPENAI_CONFIG,
    "google": _GOOGLE_CONFIG,
    "minimax": _MINIMAX_CONFIG,
    "xiaomi": _XIAOMI_CONFIG,
    "moonshot": _MOONSHOT_CONFIG,
    "alibaba": _ALIBABA_CONFIG,
    "zai": _ZAI_CONFIG,
    "meta": _META_CONFIG,
    "deepseek": _DEEPSEEK_CONFIG,
    "xai": _XAI_CONFIG,
    "anthropic": _ANTHROPIC_CONFIG,
    "apertus": _APERTUS_CONFIG,
    # Aggregator provider: proxies many models behind a single
    # OpenAI-compatible endpoint.  Its built-in default model is the
    # "custom" placeholder (no usable default) -- the user must supply a
    # model explicitly (--model or <provider>.model in config.json); the
    # placeholder "custom" model entry only carries built-in defaults (the
    # default API type).  See ``janito/providers/openrouter/config.py``.
    "openrouter": _OPENROUTER_CONFIG,
    # Special case: requires an endpoint from config (--set endpoint) and has
    # no built-in default model (and therefore no built-in model entries).
    "custom": _CUSTOM_CONFIG,
}

# Optional Python package required by each non-OpenAI API type.
#
# The two built-in API types (``"Responses"`` and ``"Completions"``) are
# served by the ``openai`` package, which is a hard dependency, so they never
# appear here. Any *other* API type listed in a model's
# ``supported_api_types`` (e.g. ``"Anthropic"`` for the native Anthropic SDK)
# is backed by an optional package declared in this dict, keyed by the
# canonical API type.
#
# When the user attempts to set an API type whose required package is missing,
# the change is aborted with a message naming the package that must be
# installed (see :func:`janito.providers.validation.ensure_api_type_available`).
REQUIRES_BY_API_TYPE: dict[str, str] = {
    "Anthropic": "anthropic",
    "DashScope": "dashscope",
    "Gemini": "google-genai",
}
