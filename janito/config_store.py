"""
Config storage: read/write primitives for ``~/.janito/config.json``.

Provides :class:`ConfigStore` (load/save/get/set/unset with provider- and
model-scoped key handling) plus the module-level delegating functions
(``load_config``, ``get_config_value``, ``set_config_value``,
``unset_config_value``).  Extracted from :mod:`janito.general_config` so the
core config module stays focused on resolution and provider helpers.
"""

import json
import logging
from pathlib import Path
from typing import Any

from .config_dir import get_config_dir, get_config_file_paths
from .config_keys import PROVIDER_SCOPED_KEYS, split_model_scoped_key

# Configure logger for this module
logger = logging.getLogger(__name__)


def get_config_path() -> Path:
    """Get the path to the config.json file (the write target).

    Returns:
        Path: Path to <config-dir>/config.json (defaults to ~/.janito/config.json)
    """
    return get_config_dir() / "config.json"


def get_config_paths() -> list[Path]:
    """Get all config.json paths used for resolution, in priority order.

    With ``-l`` / ``--local`` the project-local path (``./.janito/config.json``)
    comes first, followed by the base path (``~/.janito/config.json`` or the
    ``-c`` / ``--config-dir`` override). Otherwise only the base path is
    returned.

    Returns:
        List of paths, highest priority first.
    """
    return get_config_file_paths("config.json")


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge ``override`` into a copy of ``base`` (override wins).

    Nested dicts are merged recursively so a local ``providers`` structure
    overrides the global one per provider/subkey instead of replacing it
    wholesale.

    Args:
        base: The base mapping (e.g. the global config).
        override: The mapping applied on top (e.g. the local config).

    Returns:
        A new merged dict; neither input is mutated.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_config_file(config_path: Path) -> dict[str, Any]:
    """Load a single config.json file.

    Args:
        config_path: Path to the config file to read.

    Returns:
        The parsed config, or an empty dict when the file is missing or invalid.
    """
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        return {}


class ConfigStore:
    """Read/write primitives for ``~/.janito/config.json``.

    The store centralizes the four config operations (``load``, ``save``,
    ``get``, ``set``/``unset``) plus the provider/model-scoped key handling
    that ``set`` and ``unset`` used to duplicate.  Reads merge the resolution
    chain (project-local over base when ``-l`` / ``--local`` is active);
    writes always target the primary (write) config file only, never the
    merged view.
    """

    def load(self) -> dict[str, Any]:
        """Load the entire config, merged across the resolution chain.

        With ``-l`` / ``--local`` the project-local config.json (``./.janito``)
        is deep-merged over the base one (``~/.janito`` or the ``-c`` override)
        so local values take precedence; otherwise the single base file is read.

        Returns:
            Dict containing the config, or empty dict if no file exists or is invalid
        """
        paths = get_config_paths()
        if not any(path.exists() for path in paths):
            logger.debug("Config file not found")
            return {}

        merged: dict[str, Any] = {}
        # Iterate base -> local so that local entries override global ones.
        for config_path in reversed(paths):
            if not config_path.exists():
                continue
            with open(config_path) as f:
                data = json.load(f)
            logger.debug(f"Loaded config from {config_path}: {list(data.keys())}")
            merged = _deep_merge(merged, data)
        return merged

    def save(self, config: dict[str, Any]) -> None:
        """Save the config dictionary to config.json.

        Args:
            config: Dictionary to save to config.json

        Raises:
            IOError: If unable to write to the config file
        """
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        logger.debug(f"Saved config to {config_path}")

    def get(self, key: str) -> Any | None:
        """Get a config value by key.

        Supports flat keys, provider-scoped keys (``"openai.model"``) and
        model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
        scoped forms read from the nested providers structure.

        Args:
            key: The config key to retrieve

        Returns:
            The config value, or None if not found or config file doesn't exist
        """
        config = self.load()

        # Model-scoped key (<provider>.models.<model>.<key>).
        model_scoped = split_model_scoped_key(key)
        if model_scoped is not None:
            provider, model, leaf = model_scoped
            providers = config.get("providers", {})
            if isinstance(providers, dict):
                provider_config = providers.get(provider)
                if isinstance(provider_config, dict):
                    models = provider_config.get("models")
                    if isinstance(models, dict):
                        model_config = models.get(model)
                        if isinstance(model_config, dict):
                            value = model_config.get(leaf)
                            logger.debug(f"Getting config '{key}': " f"{value if value is None else '(set)'}")
                            return value
            return None

        # Provider-scoped key (e.g., "openai.model").
        if "." in key:
            parts = key.split(".", 1)
            if len(parts) == 2:
                provider, subkey = parts
                providers = config.get("providers", {})
                if isinstance(providers, dict) and provider in providers:
                    provider_config = providers[provider]
                    if isinstance(provider_config, dict):
                        value = provider_config.get(subkey)
                        logger.debug(f"Getting config '{key}': {value if value is None else '(set)'}")
                        return value

        # Fall back to flat key lookup
        value = config.get(key)
        logger.debug(f"Getting config '{key}': {value if value is None else '(set)'}")
        return value

    def _ensure_provider(self, config: dict, provider: str) -> dict:
        """Return (creating if needed) the ``providers.<provider>`` dict."""
        providers = config.get("providers")
        if not isinstance(providers, dict):
            providers = {}
            config["providers"] = providers
        provider_config = providers.get(provider)
        if not isinstance(provider_config, dict):
            provider_config = {}
            providers[provider] = provider_config
        return provider_config

    def _set_model_scoped(self, config: dict, provider: str, model: str, leaf: str, value: Any) -> None:
        """Write a model-scoped value into the nested providers/models map."""
        provider_config = self._ensure_provider(config, provider)
        models = provider_config.get("models")
        if not isinstance(models, dict):
            models = {}
            provider_config["models"] = models
        model_config = models.get(model)
        if not isinstance(model_config, dict):
            model_config = {}
            models[model] = model_config
        model_config[leaf] = value
        self.save(config)

    def set(self, key: str, value: Any) -> None:
        """Set a config value.

        Supports flat keys, provider-scoped keys (``"openai.model"``) and
        model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
        scoped forms write to the nested providers structure.

        Args:
            key: The config key to set
            value: The value to set
        """
        logger.debug(f"Setting config '{key}' = {value}")
        # Writes target the primary config file only (never the merged view),
        # so a --set in -l/--local mode stores the value in ./.janito without
        # copying the global entries into the local file.
        config = _load_config_file(get_config_path())

        # Model-scoped key (<provider>.models.<model>.<key>).
        model_scoped = split_model_scoped_key(key)
        if model_scoped is not None:
            provider, model, leaf = model_scoped
            self._set_model_scoped(config, provider, model, leaf, value)
            return

        # Provider-scoped key (e.g., "openai.model").
        if "." in key:
            parts = key.split(".", 1)
            if len(parts) == 2 and parts[1] in PROVIDER_SCOPED_KEYS:
                provider, subkey = parts
                provider_config = self._ensure_provider(config, provider)
                provider_config[subkey] = value
                self.save(config)
                return

        # Fall back to flat key storage
        config[key] = value
        self.save(config)

    def unset(self, key: str) -> bool:
        """Remove a config value by key.

        Supports flat keys, provider-scoped keys (``"openai.model"``) and
        model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
        scoped forms remove from the nested providers structure.  When a
        model's dict or a non-variant provider dict becomes empty after
        removal it is pruned; an emptied variant entry is kept (``{}``)
        because it is the variant's registration marker.

        Args:
            key: The config key to remove

        Returns:
            bool: True if the key was removed, False if it didn't exist
        """
        # Writes target the primary config file only (see set).
        config = _load_config_file(get_config_path())

        # Model-scoped key (<provider>.models.<model>.<key>).
        model_scoped = split_model_scoped_key(key)
        if model_scoped is not None:
            return self._unset_model_scoped(config, *model_scoped)

        # Provider-scoped keys (e.g., "openai.model") live in the nested
        # providers structure.
        if "." in key:
            parts = key.split(".", 1)
            if len(parts) == 2:
                provider, subkey = parts
                if subkey in PROVIDER_SCOPED_KEYS:
                    return self._unset_provider_scoped(config, provider, subkey)

        # Fall back to flat key removal
        if key in config:
            del config[key]
            self.save(config)
            logger.info(f"Removed config key: {key}")
            return True
        logger.debug(f"Config key not found for removal: {key}")
        return False

    def _prune_provider_entry(self, config: dict[str, Any], providers: dict[str, Any], provider: str) -> None:
        """Prune an emptied provider entry (variant marker rule) and the map.

        A variant's registration marker lives in the providers map itself, so
        an emptied variant entry is kept as ``{}`` (only non-variant
        providers are pruned when empty).  An emptied ``providers`` map is
        always dropped from the config.
        """
        provider_config = providers.get(provider)
        if not provider_config:
            # Variant registration is read through the leaf variant_names
            # module (issue #110): no import of the config-variant layer.
            from .providers.variant_names import is_variant_style_name

            if not is_variant_style_name(provider):
                providers.pop(provider, None)
        if not providers:
            config.pop("providers", None)

    def _unset_provider_scoped(self, config: dict[str, Any], provider: str, subkey: str) -> bool:
        """Remove a provider-scoped key from the nested providers map.

        Args:
            config: The primary config dict (mutated in place).
            provider: The provider (or variant) name.
            subkey: A provider-scoped config key (e.g. ``model``).

        Returns:
            bool: True if the key was removed, False if it didn't exist.
        """
        providers = config.get("providers")
        if not isinstance(providers, dict):
            logger.debug(f"Config key not found for removal: {provider}.{subkey}")
            return False
        provider_config = providers.get(provider)
        if not isinstance(provider_config, dict):
            logger.debug(f"Config key not found for removal: {provider}.{subkey}")
            return False
        if subkey not in provider_config:
            logger.debug(f"Config key not found for removal: {provider}.{subkey}")
            return False
        del provider_config[subkey]
        self._prune_provider_entry(config, providers, provider)
        self.save(config)
        logger.info(f"Removed config key: {provider}.{subkey}")
        return True

    def _unset_model_scoped(self, config: dict[str, Any], provider: str, model: str, leaf: str) -> bool:
        """Remove a model-scoped key from the nested providers/models map.

        When the model's dict becomes empty it is pruned; an emptied
        non-variant provider dict is pruned too (variant entries keep their
        ``{}`` registration marker).

        Args:
            config: The primary config dict (mutated in place).
            provider: The provider (or variant) name.
            model: The model name.
            leaf: A model-scoped config key (e.g. ``max-output-tokens``).

        Returns:
            bool: True if the key was removed, False if it didn't exist.
        """
        providers = config.get("providers")
        provider_config = providers.get(provider) if isinstance(providers, dict) else None
        models = provider_config.get("models") if isinstance(provider_config, dict) else None
        model_config = models.get(model) if isinstance(models, dict) else None
        if not isinstance(model_config, dict) or leaf not in model_config:
            logger.debug(f"Config key not found for removal: " f"{provider}.models.{model}.{leaf}")
            return False
        del model_config[leaf]
        if not model_config:
            del models[model]
        if not models:
            del provider_config["models"]
        self._prune_provider_entry(config, providers, provider)
        self.save(config)
        logger.info(f"Removed config key: {provider}.models.{model}.{leaf}")
        return True


# Module-level singleton store backing the functions below.
_store = ConfigStore()


def load_config() -> dict[str, Any]:
    """Load the entire config.json file (merged across the resolution chain).

    With ``-l`` / ``--local`` the project-local config.json (``./.janito``) is
    deep-merged over the base one (``~/.janito`` or the ``-c`` override) so
    local values take precedence; otherwise the single base file is read.

    Returns:
        Dict containing the config, or empty dict if no file exists or is invalid
    """
    return _store.load()


def get_config_value(key: str) -> Any | None:
    """Get a config value by key.

    Supports flat keys, provider-scoped keys (``"openai.model"``) and
    model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
    scoped forms read from the nested providers structure.

    Args:
        key: The config key to retrieve

    Returns:
        The config value, or None if not found or config file doesn't exist
    """
    return _store.get(key)


def set_config_value(key: str, value: Any) -> None:
    """Set a config value.

    Supports flat keys, provider-scoped keys (``"openai.model"``) and
    model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
    scoped forms write to the nested providers structure.

    Args:
        key: The config key to set
        value: The value to set
    """
    _store.set(key, value)


def unset_config_value(key: str) -> bool:
    """Remove a config value by key.

    Supports flat keys, provider-scoped keys (``"openai.model"``) and
    model-scoped keys (``"openai.models.gpt-6-luna.max-output-tokens"``); the
    scoped forms remove from the nested providers structure.  Emptied model
    dicts and non-variant provider dicts are pruned; variant entries keep
    their ``{}`` registration marker.

    Args:
        key: The config key to remove

    Returns:
        bool: True if the key was removed, False if it didn't exist
    """
    return _store.unset(key)
