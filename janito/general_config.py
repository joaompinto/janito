"""
General configuration module for managing ~/.janito/config.json.

This module provides the config-resolution helpers (``load_provider_from_config``,
``determine_provider``, ``get_active_provider``, ``resolve_api_type``).  The
storage and per-key logic was split into focused modules:

- :mod:`janito.config_keys` -- key constants and helpers (``PROVIDER_SCOPED_KEYS``,
  ``MODEL_SCOPED_KEYS``, ``split_model_scoped_key``, ``model_config_key``, ...);
- :mod:`janito.config_store` -- the :class:`ConfigStore` read/write primitives
  (``load``/``save``/``get``/``set``/``unset``) and the ``load_config`` /
  ``get_config_value`` ... delegators;
- :mod:`janito.config_variants` -- provider variant management (``load_variants``,
  ``create_variant``, ``delete_variant``, ...);
- :mod:`janito.config_loaders` -- per-provider loaders (``load_model_from_config``,
  ``load_max_output_tokens``, ...);
- :mod:`janito.config_cli` -- CLI-facing helpers (``set_config_from_cli``,
  ``get_config_from_cli``, ``unset_config_key_from_cli``, ...).

Config keys come in three scopes:

- **flat** keys (e.g. ``provider``, ``theme``);
- **provider-scoped** keys (``PROVIDER_SCOPED_KEYS``: ``model``,
  ``endpoint``), stored under ``providers.<provider>.<key>``;
- **model-scoped** keys (``MODEL_SCOPED_KEYS``: ``max-input-tokens``,
  ``max-output-tokens``, ``effort``, ``api-type``,
  ``stateless-mode``), stored under
  ``providers.<provider>.models.<model>.<key>`` so each provider/model pair
  keeps its own values.
"""

import logging

from .config_keys import normalize_api_type, normalize_provider
from .config_loaders import load_api_type, load_model_from_config
from .config_store import get_config_value
from .providers.registry import get_provider
from .providers.validation import get_all_api_types

# Configure logger for this module
logger = logging.getLogger(__name__)


def load_provider_from_config() -> str | None:
    """Load provider name from ~/.janito/config.json if it exists.

    Returns:
        str: Provider name from config, or None if not found
    """

    return get_config_value("provider")


def determine_provider(cli_provider: str | None = None) -> str | None:
    """Determine the provider used for provider-scoped config (e.g. model).

    Unlike :func:`get_active_provider`, this does *not* fall back to a default
    provider. It is used for operations (such as ``--set model``) where a
    provider must be explicitly known.

    Priority:
    1. ``--provider`` CLI argument
    2. ``provider`` value from config.json

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None)

    Returns:
        The normalized provider name, or None if it cannot be determined
    """
    provider = normalize_provider(cli_provider)
    if provider:
        return provider
    return normalize_provider(load_provider_from_config())


def get_active_provider() -> str:
    """Determine the active provider based on config.

    Priority:
    1. Provider from config.json
    2. Fallback to 'openai'

    Returns:
        str: The active provider name
    """
    # 1. Check config.json for provider
    config_provider = load_provider_from_config()
    if config_provider:
        logger.debug(f"Active provider from config: {config_provider}")
        return config_provider

    # 2. Fall back to 'openai'
    logger.debug("No provider found, using fallback: openai")
    return "openai"


def resolve_api_type(
    cli_api_type: str | None = None,
    cli_provider: str | None = None,
    cli_model: str | None = None,
) -> str:
    """Resolve the effective API type ("Responses" or "Completions").

    The API type selects which client the CLI talks to: the Responses API
    (``client.responses.create``, server-side conversation state) or the Chat
    Completions API (``client.chat.completions.create``, client-side history).

    Resolution rules:
      - api_type: ``--api-type`` CLI arg, then the model-scoped configured
        value (``--set api-type=...``, stored under
        ``providers.<provider>.models.<model>.api-type``), and finally the
        effective model's built-in default from the provider config (its
        ``default_api_type`` entry, e.g. ``"Responses"`` for OpenAI's
        default model).
      - model: ``--model`` (``cli_model``), then the provider's configured
        model (``<provider>.model``); the built-in default comes from that
        model's entry (falling back to the default model's entry for models
        without a built-in entry).
      - provider: ``--provider`` (``cli_provider``), then the configured
        provider (config.json), then ``"openai"``.

    Args:
        cli_api_type: API type passed via ``--api-type`` (highest priority).
            May be None.
        cli_provider: Provider passed via ``--provider``. May be None.
        cli_model: Model passed via ``--model``. May be None.

    Returns:
        The canonical API type: ``"Responses"`` or ``"Completions"``.

    Raises:
        ValueError: If an explicitly configured API type is not a known
            API type.
    """
    provider = cli_provider or get_active_provider()
    effective_model = cli_model or load_model_from_config(provider)

    raw = cli_api_type or load_api_type(cli_provider, effective_model)
    if raw:
        try:
            return normalize_api_type(raw, get_all_api_types())
        except ValueError:
            logger.error(f"Unsupported API type: {raw}")
            raise

    found = get_provider(provider)
    default = found.model_config(effective_model).get("default_api_type") if found is not None else None
    return default or "Completions"
