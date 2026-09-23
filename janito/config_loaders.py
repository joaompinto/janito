"""
Per-provider config loaders.

These helpers read provider-scoped values (``model``, ``endpoint``) and
model-scoped values (``max-output-tokens``, ``max-input-tokens``,
``effort``, ``api-type``, ``stateless-mode``) from
``~/.janito/config.json``.  They were extracted from
:mod:`janito.general_config` so the core config storage module stays focused
on read/write primitives.

Model-scoped settings are stored under
``providers.<provider>.models.<model>.<key>``; the loaders take an optional
``model`` argument (defaulting to the provider's configured model, else its
built-in default model) and read **only** the model-scoped path.

The class :class:`ProviderConfigLoader` centralizes the loaders (each used
to repeat the ``determine_provider`` -> guard -> ``get_config_value``
-> coerce dance); the module-level functions below are the public API and
delegate to a module-level loader instance.

This module also hosts the flat-key resolvers:
:func:`load_system_prompt_start` (the configured ``start`` section of the
system prompt as ``(text, label)``, from the ``system-prompt`` /
``system-prompt-file`` keys),
:func:`load_privileges_from_config` (the session default privileges,
``privileges`` key, issue #89) and :func:`load_used_files_enabled` (the
``used-files`` flag).

``general_config`` imports this module's helpers at its top; this module
resolves the provider inline in :meth:`ProviderConfigLoader._resolve_provider`
instead of importing ``general_config`` (issue #110) -- this keeps the
import graph acyclic regardless of which module is imported first.
"""

import logging
import os
from pathlib import Path

from .privileges import Privileges, parse_privileges

# Configure logger for this module
logger = logging.getLogger(__name__)


class ProviderConfigLoader:
    """Read provider/model-scoped values from ``~/.janito/config.json``.

    Each loader resolves the provider (``--provider`` CLI argument first, then
    the configured ``provider`` value) and reads its config key.  The
    model-scoped loaders additionally resolve the model (explicit ``model``
    argument first, then the provider's configured model, else its built-in
    default model) and read the ``providers.<provider>.models.<model>.<key>``
    path only.
    """

    @staticmethod
    def _resolve_provider(cli_provider: str | None) -> str | None:
        """Resolve the provider used for provider-scoped config lookups."""
        from .config_keys import normalize_provider
        from .config_store import get_config_value

        # Same resolution as general_config.determine_provider, inlined here
        # so this module never imports general_config (issue #110): the
        # config fan-in stays one-way (general_config -> this module).
        return normalize_provider(cli_provider) or normalize_provider(get_config_value("provider"))

    @staticmethod
    def _resolve_model(cli_provider: str | None, model: str | None = None) -> str | None:
        """Resolve the model used for model-scoped config lookups.

        Priority: the explicit ``model`` argument, then the provider's
        configured model (``<provider>.model``), then the provider's
        built-in default model.
        """
        from .providers.registry import get_provider

        if model:
            return model
        provider = ProviderConfigLoader._resolve_provider(cli_provider)
        if not provider:
            return None
        found = get_provider(provider)
        return load_model_from_config(provider) or (found.default_model() if found is not None else None)

    def load_model(self, cli_provider: str | None = None) -> str | None:
        """Load the model name for the active provider from config.json.

        The model is stored under a provider-scoped key (``<provider>.model``)
        so that different providers can each have their own default model.

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.

        Returns:
            str: Model name from config, or None if not found or provider unknown
        """
        from .config_keys import model_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        return get_config_value(model_config_key(provider))

    def load_max_output_tokens(self, cli_provider: str | None = None, model: str | None = None) -> int | None:
        """Load max output tokens from ~/.janito/config.json if it exists.

        This value is used as the maximum output-token limit (``max_tokens`` /
        ``max_completion_tokens``) for API calls. It is stored per
        provider/model under the nested providers structure (e.g.
        providers.openai.models.gpt-6-luna.max-output-tokens).

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.
            model: The model the value belongs to. ``None`` resolves to the
                provider's configured model, else its built-in default model.

        Returns:
            int: Max output tokens from config, or None if not found
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "max-output-tokens"))
        if value is not None:
            return int(value)
        return None

    def load_max_input_tokens(self, cli_provider: str | None = None, model: str | None = None) -> int | None:
        """Load max input tokens from ~/.janito/config.json if it exists.

        This value is the maximum input-token (context window) limit used for
        the usage summary display. It is stored per provider/model under the
        nested providers structure (e.g.
        providers.openai.models.gpt-6-luna.max-input-tokens).

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.
            model: The model the value belongs to. ``None`` resolves to the
                provider's configured model, else its built-in default model.

        Returns:
            int: Max input tokens from config, or None if not found
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "max-input-tokens"))
        if value is not None:
            return int(value)
        return None

    def load_effort(self, cli_provider: str | None = None, model: str | None = None) -> str | None:
        """Load the reasoning level for the active provider/model from config.json.

        The reasoning level is stored under a model-scoped key
        (``providers.<provider>.models.<model>.effort``) so that
        different provider/model pairs can each have their own reasoning
        depth (e.g. ``low``/``medium``/``xhigh`` for Qwen3.8-Max).

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.
            model: The model the value belongs to. ``None`` resolves to the
                provider's configured model, else its built-in default model.

        Returns:
            str: The reasoning level from config, or None if not found
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "effort"))
        if value is not None:
            return str(value)
        return None

    def load_api_type(self, cli_provider: str | None = None, model: str | None = None) -> str | None:
        """Load the API type for the active provider/model from config.json.

        The API type is stored under a model-scoped key
        (``providers.<provider>.models.<model>.api-type``) so that different
        provider/model pairs can each select which API they talk to
        (``"Responses"`` or ``"Completions"``).

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.
            model: The model the value belongs to. ``None`` resolves to the
                provider's configured model, else its built-in default model.

        Returns:
            str: The API type from config, or None if not found
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "api-type"))
        if value is not None:
            return str(value)
        return None

    def load_stateless_mode(self, cli_provider: str | None = None, model: str | None = None) -> bool | None:
        """Load the Stateless-mode override for a provider/model from config.json.

        The override is stored under a model-scoped key
        (``providers.<provider>.models.<model>.stateless-mode``) so that
        different provider/model pairs can each decide whether their
        Responses API keeps conversation state server-side.

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.
            model: The model the value belongs to. ``None`` resolves to the
                provider's configured model, else its built-in default model.

        Returns:
            bool: The configured override (``True``/``False``), or ``None`` when
                no override is stored (the built-in default applies).
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "stateless-mode"))
        if value is None:
            return None
        # Tolerate string forms written by hand/older configs ("true"/"false").
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on")
        return bool(value)

    def load_disabled_tools(self, cli_provider: str | None = None, model: str | None = None) -> list[str] | None:
        """Load the disabled-tools override for a provider/model.

        Stored under ``providers.<provider>.models.<model>.disabled-tools``
        as a list of external tool names (e.g. ``["WebSearch"]``).

        Returns:
            The configured list, or ``None`` when no override is stored
            (the built-in/derived default applies).  A stored empty list
            means explicitly nothing disabled.
        """
        from .config_keys import model_scoped_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        model = self._resolve_model(cli_provider, model)
        if not model:
            return None
        value = get_config_value(model_scoped_config_key(provider, model, "disabled-tools"))
        if value is None:
            return None
        if isinstance(value, str):
            items = [entry.strip() for entry in value.split(",")]
            return [entry for entry in items if entry]
        if isinstance(value, (list, tuple)):
            items = [str(entry).strip() for entry in value]
            return [entry for entry in items if entry]
        return None

    def load_endpoint(self, cli_provider: str | None = None) -> str | None:
        """Load custom endpoint URL from ~/.janito/config.json if it exists.

        This is used for the 'custom' provider or to override provider base URLs.

        The endpoint is stored under a provider-scoped key
        (``<provider>.endpoint``) so that different providers can each have their
        own endpoint. The provider is resolved from ``cli_provider`` first, then
        from the configured ``provider`` value.

        Args:
            cli_provider: Provider passed via ``--provider`` (may be None). If
                not provided, the provider is read from config.json.

        Returns:
            str: Endpoint URL from config, or None if not found or provider unknown
        """
        from .config_keys import endpoint_config_key
        from .config_store import get_config_value

        provider = self._resolve_provider(cli_provider)
        if not provider:
            return None
        return get_config_value(endpoint_config_key(provider))


# Module-level singleton backing the functions below.
_loader = ProviderConfigLoader()


def load_model_from_config(cli_provider: str | None = None) -> str | None:
    """Load the model name for the active provider from ~/.janito/config.json.

    The model is stored under a provider-scoped key (``<provider>.model``) so
    that different providers can each have their own default model.

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.

    Returns:
        str: Model name from config, or None if not found or provider unknown
    """
    return _loader.load_model(cli_provider)


def load_max_output_tokens(cli_provider: str | None = None, model: str | None = None) -> int | None:
    """Load max output tokens from ~/.janito/config.json if it exists.

    This value is used as the maximum output-token limit (``max_tokens`` /
    ``max_completion_tokens``) for API calls. It is stored per provider/model
    under the nested providers structure (e.g.
    providers.openai.models.gpt-6-luna.max-output-tokens).

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.
        model: The model the value belongs to. ``None`` resolves to the
            provider's configured model, else its built-in default model.

    Returns:
        int: Max output tokens from config, or None if not found
    """
    return _loader.load_max_output_tokens(cli_provider, model)


def load_max_input_tokens(cli_provider: str | None = None, model: str | None = None) -> int | None:
    """Load max input tokens from ~/.janito/config.json if it exists.

    This value is the maximum input-token (context window) limit used for
    the usage summary display. It is stored per provider/model under the
    nested providers structure (e.g.
    providers.openai.models.gpt-6-luna.max-input-tokens).

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.
        model: The model the value belongs to. ``None`` resolves to the
            provider's configured model, else its built-in default model.

    Returns:
        int: Max input tokens from config, or None if not found
    """
    return _loader.load_max_input_tokens(cli_provider, model)


def load_effort(cli_provider: str | None = None, model: str | None = None) -> str | None:
    """Load the reasoning level for the active provider/model from config.json.

    The reasoning level is stored under a model-scoped key
    (``providers.<provider>.models.<model>.effort``) so that
    different provider/model pairs can each have their own reasoning depth
    (e.g. ``low``/``medium``/``xhigh`` for Qwen3.8-Max).

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.
        model: The model the value belongs to. ``None`` resolves to the
            provider's configured model, else its built-in default model.

    Returns:
        str: The reasoning level from config, or None if not found
    """
    return _loader.load_effort(cli_provider, model)


def load_api_type(cli_provider: str | None = None, model: str | None = None) -> str | None:
    """Load the API type for the active provider/model from config.json.

    The API type is stored under a model-scoped key
    (``providers.<provider>.models.<model>.api-type``) so that different
    provider/model pairs can each select which API they talk to
    (``"Responses"`` or ``"Completions"``).

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.
        model: The model the value belongs to. ``None`` resolves to the
            provider's configured model, else its built-in default model.

    Returns:
        str: The API type from config, or None if not found
    """
    return _loader.load_api_type(cli_provider, model)


def load_stateless_mode_from_config(
    cli_provider: str | None = None,
    model: str | None = None,
) -> bool | None:
    """Load the Stateless-mode override for a provider/model from config.json.

    The override is stored under a model-scoped key
    (``providers.<provider>.models.<model>.stateless-mode``) so that
    different provider/model pairs can each decide whether their Responses
    API keeps conversation state server-side.

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.
        model: The model the value belongs to. ``None`` resolves to the
            provider's configured model, else its built-in default model.

    Returns:
        bool: The configured override (``True``/``False``), or ``None`` when
            no override is stored (the built-in default applies).
    """
    return _loader.load_stateless_mode(cli_provider, model)


def load_disabled_tools_from_config(
    cli_provider: str | None = None,
    model: str | None = None,
) -> list[str] | None:
    """Load the disabled-tools override for a provider/model.

    Returns the stored list, or ``None`` when no override is stored.
    """
    return _loader.load_disabled_tools(cli_provider, model)


# Native server-side search tool types that make the external WebSearch
# function tool redundant (issue #144).
_NATIVE_SEARCH_TOOL_TYPES = {"web_search", "web_extractor"}


def _has_native_search(entries) -> bool:
    """Whether native tool entries include server-side search."""
    for entry in entries or []:
        if isinstance(entry, dict) and str(entry.get("type", "")).lower() in _NATIVE_SEARCH_TOOL_TYPES:
            return True
    return False


def _derived_search_default(found, resolved_model, api_type: str | None) -> list[str]:
    """Derived default: ``["WebSearch"]`` when native search exists."""
    try:
        native = found.tools(resolved_model, api_type=api_type) if api_type else None
        if not native:
            native = found.tools(resolved_model)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ):  # noqa: BLE001 - best effort default
        native = None
    if _has_native_search(native):
        return ["WebSearch"]
    if api_type:
        return []
    try:
        by_type = found.model_config(resolved_model).data.get("tools_by_api_type")
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ):  # noqa: BLE001 - best effort default
        by_type = None
    if isinstance(by_type, dict):
        for tools in by_type.values():
            if _has_native_search(tools):
                return ["WebSearch"]
    return []


def resolve_disabled_tools(
    cli_provider: str | None = None,
    model: str | None = None,
    api_type: str | None = None,
) -> list[str]:
    """Resolve the effective disabled external tools for a provider/model.

    Priority: user override (``disabled-tools`` key, empty list disables
    nothing) -> built-in ``disabled_tools`` model entry -> derived default
    (``["WebSearch"]`` when the model's native tools for ``api_type``
    include a server-side search type).

    Args:
        cli_provider: Provider name (or ``None`` to use the configured one).
        model: Model name (or ``None`` to use the configured/default one).
        api_type: Canonical API type used for per-API-type native tools
            resolution (``None`` checks every declared list).

    Returns:
        Sorted list of disabled external tool names (possibly empty).
    """
    from .providers.registry import get_provider

    override = load_disabled_tools_from_config(cli_provider, model)
    if override is not None:
        return sorted(set(override))
    provider_name = ProviderConfigLoader._resolve_provider(cli_provider)
    if not provider_name:
        return []
    resolved_model = ProviderConfigLoader._resolve_model(cli_provider, model)
    found = get_provider(provider_name)
    if found is None:
        return []
    builtin = found.model_config(resolved_model).get("disabled_tools")
    if builtin:
        return sorted(set(str(entry) for entry in builtin if str(entry).strip()))
    return _derived_search_default(found, resolved_model, api_type)


def load_endpoint_from_config(cli_provider: str | None = None) -> str | None:
    """Load custom endpoint URL from ~/.janito/config.json if it exists.

    This is used for the 'custom' provider or to override provider base URLs.

    The endpoint is stored under a provider-scoped key
    (``<provider>.endpoint``) so that different providers can each have their
    own endpoint. The provider is resolved from ``cli_provider`` first, then
    from the configured ``provider`` value.

    Args:
        cli_provider: Provider passed via ``--provider`` (may be None). If not
            provided, the provider is read from config.json.

    Returns:
        str: Endpoint URL from config, or None if not found or provider unknown
    """
    return _loader.load_endpoint(cli_provider)


def _display_config_path(path: Path) -> str:
    """Render a config file path for display, shortening home to ``~``.

    ``~/.janito/config.json`` is shown as ``~/.janito/config.json`` (the form
    users write it in) instead of the expanded absolute path.
    """
    try:
        home = Path.home()
        relative = path.relative_to(home)
        if not relative.parts:
            return "~"
        return "~/" + relative.as_posix()
    except (OSError, RuntimeError, ValueError):
        return str(path)


def load_system_prompt_start() -> tuple[str | None, str | None]:
    """Resolve the configured ``start`` section text and its display label.

    Reads the flat ``system-prompt-file`` / ``system-prompt`` config keys and
    returns ``(text, label)`` where the label records where the text came
    from for the ``/prompt`` / ``--show-system-prompt`` display (issue #86):

    - ``system-prompt-file`` -> ``(config) <value>`` (the key's value as
      written, e.g. ``(config) ~/base-prompt.md``);
    - ``system-prompt`` -> ``(config) <config-file>:system-prompt`` (e.g.
      ``(config) ~/.janito/config.json:system-prompt``);
    - neither key set -> ``(None, None)`` (the built-in base prompt applies).

    ``system-prompt-file`` wins when both are set (it is the more specific
    form): the value is a file path (``~`` is expanded; relative paths are
    resolved against the current working directory) whose content becomes
    the ``start`` section.  An empty file falls back to the default
    (``None``), matching how an empty ``AGENTS.md`` is handled.  Otherwise
    ``system-prompt`` is used verbatim as a literal string.

    The read happens at call time, so each session re-reads the file: a
    change on disk is picked up by the next ``effective_system_prompt()``
    call without a restart.

    Returns:
        ``(text, label)``: the configured start-section text (``None`` when
        neither key is set) and its display label (``None`` when no config
        applies, so the caller uses
        :data:`janito.system_prompt.LABEL_BUILTIN`).

    Raises:
        ValueError: If ``system-prompt-file`` is set but the file cannot be
            read, naming the key and path.
    """
    from .config_store import get_config_path, get_config_value
    from .system_labels import LABEL_CONFIG_PREFIX

    file_value = get_config_value("system-prompt-file")
    if file_value:
        file_value_str = str(file_value).strip()
        path = os.path.expanduser(file_value_str)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read().strip()
        except OSError as e:
            raise ValueError(f"Cannot read config key 'system-prompt-file': " f"{file_value!r}: {e}")
        return (content or None), f"{LABEL_CONFIG_PREFIX}{file_value_str}"

    literal = get_config_value("system-prompt")
    if literal is not None:
        label = f"{LABEL_CONFIG_PREFIX}" f"{_display_config_path(get_config_path())}:system-prompt"
        return str(literal), label
    return None, None


def load_used_files_enabled() -> bool:
    """Load the flat ``used-files`` config flag (default ``False``).

    When set to ``True`` (``janito --set used-files=True``) the CLI/shell
    prints the end-of-turn ``Used files`` report; when unset or ``False``
    (the default) the report is suppressed.  String forms written by hand /
    older configs (``"true"``/``"false"``/``"1"``/``"0"``/``"yes"``/``"no"``/
    ``"on"``/``"off"`` in any case) are tolerated, mirroring
    :meth:`ProviderConfigLoader.load_stateless_mode`.

    Returns:
        bool: ``True`` when the flag is set, ``False`` when unset or falsy.
    """
    from .config_store import get_config_value

    value = get_config_value("used-files")
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def load_privileges_from_config() -> Privileges | None:
    """Load the configured default privileges (``--set privileges=rwx``).

    Reads the flat ``privileges`` config key: a combination of the ``r`` /
    ``w`` / ``x`` characters (e.g. ``rwx``), parsed by
    :func:`janito.privileges.parse_privileges`.  Sessions that pass no
    ``-r`` / ``-w`` / ``-x`` flag start with these privileges; when the key
    is unset the built-in default applies (read-only, issue #85).

    A value written by hand that fails to parse is **not** fatal: it is
    logged and ``None`` is returned (the read-only default applies) instead
    of raising at startup.  ``--set privileges=...`` validates strictly, so
    values stored through the CLI are always valid.

    Returns:
        The parsed :class:`~janito.privileges.Privileges`, or ``None`` when
        the key is unset or invalid.
    """
    from .config_store import get_config_value

    value = get_config_value("privileges")
    if value is None:
        return None
    try:
        return parse_privileges(value)
    except ValueError as e:
        logger.warning("Ignoring invalid 'privileges' config value %r: %s", value, e)
        return None


def validate_system_prompt_file_path(file_value: str) -> str:
    """Validate that a ``system-prompt-file`` value points at an existing file.

    Shared by the ``--set system-prompt-file=...`` handler (rejects a missing
    file when the value is set) and the startup check in
    :func:`janito.cli.setup.validate_system_prompt_file` (rejects it before a
    session starts), so both fail with the same message naming the key and
    path.

    ``~`` is expanded and relative paths resolve against the current working
    directory, matching :func:`load_system_prompt_start`.

    Args:
        file_value: The raw ``system-prompt-file`` config value.

    Returns:
        The resolved path (``~`` expanded, relative to the cwd).

    Raises:
        ValueError: If the file does not exist, naming the key and path.
    """
    path = os.path.expanduser(str(file_value).strip())
    if not os.path.isfile(path):
        raise ValueError(f"Cannot read config key 'system-prompt-file': " f"{file_value!r}: file does not exist")
    return path
