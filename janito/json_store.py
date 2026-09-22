"""
Shared JSON-file store base class for Janito configuration.

``auth_config`` (``~/.janito/auth.json``), ``secrets_config``
(``~/.janito/secrets.json``) and ``mcp_config`` (``~/.janito/mcp_services.json``)
all implement the same pattern: a JSON file in the config directory with
path resolution (project-local ``./.janito`` first, base directory as the
fallback when ``-l`` / ``--local`` is active), a load that deep-merges the
resolution chain (local wins), a save that creates the directory and (for
auth/secrets) restricts permissions to the owner (``0600``), and a small set
of get/set/delete/list operations.

This module extracts that shared machinery into a :class:`JsonFileStore` base
class; each store subclasses it and adds its domain-specific methods.  The
three config modules keep their module-level functions as thin delegators to a
module-level singleton, so existing import sites are unaffected.
"""

import json
import logging
import os
from collections.abc import Set as AbstractSet
from pathlib import Path

from .config_dir import get_config_dir, get_config_file_paths

# Configure logger for this module
logger = logging.getLogger(__name__)


class JsonFileStore:
    """A JSON config file with path resolution, merging and 0600 perms.

    Args:
        filename: The config file name (e.g. ``"auth.json"``).
        chmod_600: Whether to restrict the file to owner read/write (``0600``)
            after saving. Defaults to ``True``.
        merge_local: Whether reads resolve the project-local file first and
            fall back to the base file, merging the chain with local values
            winning (``-l`` / ``--local`` mode). When ``False`` only the base
            file is read. Defaults to ``True``.
        default: The mapping returned when the file does not exist. Defaults
            to ``{}``.
    """

    def __init__(
        self,
        filename: str,
        *,
        chmod_600: bool = True,
        merge_local: bool = True,
        default: dict | None = None,
    ):
        self.filename = filename
        self.chmod_600 = chmod_600
        self.merge_local = merge_local
        self.default: dict = dict(default) if default else {}

    # ------------------------------------------------------------------
    # Path resolution (delegates to janito.config_dir)
    # ------------------------------------------------------------------

    def file_path(self) -> Path:
        """Get the write target path: ``<write dir>/<filename>``."""
        return get_config_dir() / self.filename

    def file_paths(self) -> list[Path]:
        """Get all paths used for resolution, in priority order.

        With ``-l`` / ``--local`` the project-local path comes first, followed
        by the base path; otherwise only the base path is returned.
        """
        return get_config_file_paths(self.filename)

    def ensure_directory(self) -> Path:
        """Ensure the config directory exists and return it."""
        path = self.file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.parent

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load the config, merged across the resolution chain (local wins).

        Returns:
            The parsed config, or a copy of ``default`` when no file exists.
        """
        if self.merge_local:
            paths = self.file_paths()
            if not any(path.exists() for path in paths):
                logger.debug(f"Config file '{self.filename}' not found")
                return dict(self.default)

            merged: dict = {}
            # Iterate base -> local so that local entries override global ones.
            for path in reversed(paths):
                if not path.exists():
                    continue
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    logger.debug(f"Loaded config from {path}")
                    merged.update(json.loads(content))
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse {self.filename}: {e}")
                    continue
            return merged

        # Single-file mode (no local merge): read the base file only.
        path = self.file_path()
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.debug(f"Config file '{self.filename}' not found: {path}")
            return dict(self.default)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.filename}: {e}")
            return dict(self.default)

    def save(self, config: dict) -> bool:
        """Save ``config`` to the file (creating the directory if needed).

        When ``chmod_600`` is set, the file is restricted to owner read/write.
        Best-effort: returns ``False`` (and logs) when the write fails, never
        raises.

        Args:
            config: The dictionary to persist.

        Returns:
            bool: ``True`` on success, ``False`` on failure.
        """
        try:
            self.ensure_directory()
            path = self.file_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            if self.chmod_600:
                os.chmod(path, 0o600)
            logger.debug(f"Saved {self.filename} to {path}")
            return True
        except OSError as e:
            logger.error(f"Failed to save {self.filename}: {e}")
            return False

    # ------------------------------------------------------------------
    # Generic key operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> object:
        """Get a top-level value by key, or ``None`` when absent."""
        return self.load().get(key)

    def set(self, key: str, value: object) -> bool:
        """Set a top-level key and persist; returns success."""
        config = self.load()
        config[key] = value
        return self.save(config)

    def delete(self, key: str) -> bool:
        """Remove a top-level key and persist.

        Returns:
            bool: ``True`` if the key was removed, ``False`` if it did not
                exist (or the save failed).
        """
        config = self.load()
        if key in config:
            del config[key]
            return self.save(config)
        return False

    def list_keys(self, *, exclude: AbstractSet[str] = frozenset()) -> list:
        """List the top-level keys, optionally excluding metadata keys."""
        return [k for k in self.load().keys() if k not in exclude]


class AuthConfigStore(JsonFileStore):
    """Storage for ``~/.janito/auth.json`` (provider -> API key)."""

    def __init__(self):
        super().__init__("auth.json")

    def set_api_key(self, provider: str, api_key: str) -> bool:
        """Store an API key for a provider; returns success.

        The default provider lives in ``config.json`` (the ``provider``
        key), never in ``auth.json``: storing a key does not change which
        provider is the default.
        """
        logger.debug(f"Setting API key for provider: {provider}")
        config = self.load()
        config[provider] = api_key
        result = self.save(config)
        if result:
            logger.info(f"API key saved for provider: {provider}")
        return result

    def get_api_key(self, provider: str) -> str | None:
        """Get the API key for a provider, or ``None`` when absent."""
        config = self.load()
        api_key = config.get(provider)
        if api_key:
            logger.debug(f"API key found for provider: {provider}")
        else:
            logger.debug(f"No API key found for provider: {provider}")
        return api_key

    def list_providers(self) -> list:
        """List all configured providers (auth.json only holds API keys)."""
        return self.list_keys()

    def delete_api_key(self, provider: str) -> bool:
        """Delete the API key for a provider; returns ``True`` if removed."""
        config = self.load()
        if provider in config:
            del config[provider]
            return self.save(config)
        return False


class SecretsConfigStore(JsonFileStore):
    """Storage for ``~/.janito/secrets.json`` (arbitrary key -> secret)."""

    def __init__(self):
        super().__init__("secrets.json")

    def set_secret(self, key: str, value: str) -> bool:
        """Store a secret; returns success."""
        logger.debug(f"Setting secret: {key}")
        config = self.load()
        config[key] = value
        result = self.save(config)
        if result:
            logger.info(f"Secret saved: {key}")
        return result

    def get_secret(self, key: str) -> str | None:
        """Get a secret value, or ``None`` when absent."""
        config = self.load()
        value = config.get(key)
        if value:
            logger.debug(f"Secret found: {key}")
        else:
            logger.debug(f"Secret not found: {key}")
        return value

    def delete_secret(self, key: str) -> bool:
        """Delete a secret; returns ``True`` if removed."""
        config = self.load()
        if key in config:
            del config[key]
            return self.save(config)
        return False

    def list_secrets(self) -> list:
        """List all configured secret keys."""
        return list(self.load().keys())

    def secret_exists(self, key: str) -> bool:
        """Check whether a secret key is present."""
        return key in self.load()


class McpConfigStore(JsonFileStore):
    """Storage for ``~/.janito/mcp_services.json`` (service registry).

    Unlike the auth/secrets stores this file is a single document (no local
    merge) and does not restrict permissions.  ``save`` is strict: an I/O
    error propagates to the caller (matching the historical contract).
    """

    def __init__(self):
        super().__init__(
            "mcp_services.json",
            chmod_600=False,
            merge_local=False,
            default={"services": {}},
        )

    def save(self, config: dict) -> bool:
        """Save ``config``; raises on I/O failure (strict, no chmod)."""
        path = self.file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        logger.debug(f"Saved {self.filename} to {path}")
        return True

    def get_service(self, name: str) -> dict | None:
        """Get a specific MCP service config by name, or ``None``."""
        return self.load().get("services", {}).get(name)

    def add_service(self, name: str, service_config: dict) -> None:
        """Add or update an MCP service."""
        config = self.load()
        if "services" not in config:
            config["services"] = {}
        config["services"][name] = service_config
        self.save(config)

    def remove_service(self, name: str) -> bool:
        """Remove an MCP service; returns ``True`` if it existed."""
        config = self.load()
        services = config.get("services", {})
        if name in services:
            del services[name]
            config["services"] = services
            self.save(config)
            logger.info(f"Removed MCP service: {name}")
            return True
        logger.debug(f"MCP service not found for removal: {name}")
        return False

    def list_services(self) -> dict:
        """Return the mapping of service names to their configurations."""
        return self.load().get("services", {})
