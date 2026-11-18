"""
Main tools module for AI function calling.

This module provides easy access to all available tools and their schemas.

:class:`ToolsRegistry` groups the registry operations (lazy discovery,
toolset loading, skills enable/disable, lookups) behind a single class API;
the module-level functions below are thin delegators to a module-level
singleton (:data:`_registry`), so existing import sites keep working.

State location note
-------------------
The registry's state intentionally lives at **module level** (``AVAILABLE_TOOLS``,
``_tools_initialized``, ``_loaded_toolsets``, ``_skills_enabled``,
``_tools_loading_enabled``, ``_disabled_toolsets``): tests
(``test_used_files.py``, ``test_tool_executor.py``) monkeypatch
``tools_registry.AVAILABLE_TOOLS`` and ``tools_registry._tools_initialized``
directly to inject stub tools without triggering the slow filesystem
discovery.  ``ToolsRegistry`` methods therefore read the module globals and
declare ``global`` only where they rebind a name (``_tools_initialized``,
``_skills_enabled``, ``_tools_loading_enabled``).
"""

from collections.abc import Callable
from typing import Any

from .discovery import discover_toolsets, tool_is_allowed_by_privileges
from .schema import get_function_schema
from .skills_provider import get_skills_advertisement, get_skills_tools

# Configuration for auto-loading toolsets
AUTOLOAD_TOOLSETS = ["files", "system", "net", "tasks"]

# Track loaded toolsets to avoid duplicates
_loaded_toolsets = set(AUTOLOAD_TOOLSETS.copy())

# Toolsets that are individually disabled (``--no-tasks``).  Disabled
# toolsets are skipped by the autoload discovery in ``ensure_initialized``
# and ``add_toolset`` refuses to load them, so their tools never appear.
# Unlike ``_tools_loading_enabled`` (``--no-tools``) this only affects the
# named toolsets; everything else -- and the skill tools -- stays enabled.
_disabled_toolsets: set[str] = set()

# Flag to enable skills support
_skills_enabled = True

# Whether non-skill tools (the autoload toolsets and any toolset added via
# ``add_toolset``, e.g. janitoweb) are loaded at all.
# ``--no-tools`` sets this to False; skill tools are never affected, so they
# stay available even when every other tool is disabled.
_tools_loading_enabled = True


# Lazily-initialized registry of available tools.
# Discovery is deferred until first access so that CLI flags (e.g. -r, -w, -x)
# can set running_privileges *before* tools are filtered.
AVAILABLE_TOOLS: dict[str, Callable] = {}
_tools_initialized: bool = False


class ToolsRegistry:
    """Grouped API over the module-level tools registry state.

    Encapsulates the registry operations: lazy discovery
    (:meth:`ensure_initialized`), dynamic toolset loading (:meth:`add_toolset`),
    skills enable/disable (:meth:`enable_skills` / :meth:`disable_skills`) and
    the tool lookups (:meth:`all_tools`, :meth:`get`, :meth:`permissions`, ...).

    The underlying state lives at module level (``AVAILABLE_TOOLS``,
    ``_tools_initialized``, ``_loaded_toolsets``, ``_skills_enabled``,
    ``_tools_loading_enabled``, ``_disabled_toolsets``) so the
    test monkeypatches of ``tools_registry.AVAILABLE_TOOLS`` /
    ``_tools_initialized`` keep working; methods read the module globals and
    declare ``global`` only where they rebind a name.
    """

    def ensure_initialized(self) -> None:
        """
        Run tool discovery on first access (lazy initialization).

        Discovery loads **every** tool whose ``should_load()`` gate passes;
        privilege restrictions (``-r``/``-w``/``-x``) are not applied here so
        the per-command tool modes (``/read`` ``/write`` ``/rx`` ``/rw``
        ``/rwx``) can override the session privileges for a single exchange
        (issue #87).  The session tool selector
        (:meth:`session_schemas` / :meth:`session_tool_names`) applies the
        privilege filter to what a normal prompt may offer.

        When tool loading is disabled (``--no-tools``), the autoload
        toolsets are skipped but the skill tools are still registered, so
        ``load_skill`` / ``read_skill_resource`` stay available.
        Individually disabled toolsets (``--no-tasks`` via
        :meth:`disable_toolset`) are filtered out of the autoload list
        before discovery, so their tools never load either.
        """
        global _tools_initialized
        if _tools_initialized:
            return
        _tools_initialized = True

        if _tools_loading_enabled:
            toolset_names = [name for name in AUTOLOAD_TOOLSETS if name not in _disabled_toolsets]
            AVAILABLE_TOOLS.update(discover_toolsets(toolset_names))

        # Add skill tools if enabled. Never gated by _tools_loading_enabled:
        # --no-tools disables the other tools but leaves skills enabled.
        if _skills_enabled:
            AVAILABLE_TOOLS.update(get_skills_tools())

    def add_toolset(self, toolset_name: str) -> bool:
        """
        Dynamically add a toolset to the available tools.

        Args:
            toolset_name: Name of the toolset to add (e.g., "janitoweb", "files", "system")

        Returns:
            bool: True if the toolset was added, False if already loaded or invalid
        """
        # --no-tools: no toolset is loaded (skill tools stay available).
        if not _tools_loading_enabled:
            return False
        # Individually disabled toolsets (--no-tasks) can never be loaded,
        # matching the --no-tools behavior of not being re-enableable.
        if toolset_name in _disabled_toolsets:
            return False

        self.ensure_initialized()

        if toolset_name in _loaded_toolsets:
            return False

        _loaded_toolsets.add(toolset_name)

        # Discover and load tools from the new toolset
        new_tools = discover_toolsets([toolset_name])

        if new_tools:
            AVAILABLE_TOOLS.update(new_tools)
            return True

        return False

    def register_plugin_tools(self, tools: dict[str, Callable]) -> None:
        """
        Register tools contributed by a plugin.

        Plugin tools go through the same ``should_load()`` gate as built-in
        tools (applied by ``wrap_tool_class`` / ``discover_module_tools`` in
        the plugin manager); privileges are applied by the session tool
        selector like every other tool.  Plugin tools are gated by
        ``_tools_loading_enabled`` (``--no-tools`` disables them);
        ``--no-plugins`` disables them independently.

        Args:
            tools: Mapping of tool names to wrapped callables.
        """
        if not tools:
            return
        # --no-tools disables plugin tools as well (not registered).
        if not _tools_loading_enabled:
            return
        self.ensure_initialized()
        AVAILABLE_TOOLS.update(tools)

    def all_tools(self) -> dict[str, Callable]:
        """
        Get all available tools as a dictionary mapping names to functions.

        Returns:
            Dict[str, Callable]: Dictionary of tool names to functions
        """
        self.ensure_initialized()
        return AVAILABLE_TOOLS.copy()

    def all_schemas(self) -> list[dict[str, Any]]:
        """
        Get all tool schemas in the format expected by OpenAI function calling.

        Returns:
            List[Dict[str, Any]]: List of tool schemas
        """
        self.ensure_initialized()
        return [get_function_schema(tool) for tool in AVAILABLE_TOOLS.values()]

    def all_permissions(self) -> dict[str, str]:
        """
        Get permissions for all available tools.

        Returns:
            Dict[str, str]: Dictionary mapping tool names to their permission strings
        """
        self.ensure_initialized()
        return {name: getattr(tool, "_tool_permissions", "") for name, tool in AVAILABLE_TOOLS.items()}

    def _disabled_tool_names(self) -> set[str]:
        """Names of external tools disabled for the active provider/model.

        Resolved via :func:`janito.config_loaders.resolve_disabled_tools`
        (issue #144); empty when no provider/model resolves or nothing is
        disabled.  Imported lazily so the tooling -> root edge stays
        one-way and failure here never breaks tool listing.
        """
        try:
            from janito.config_loaders import resolve_disabled_tools

            return set(resolve_disabled_tools())
        except Exception:  # noqa: BLE001 - tool listing must never break
            return set()

    def disabled_tool_names(self) -> set[str]:
        """Names of external tools disabled for the active provider/model.

        Public accessor for :meth:`_disabled_tool_names` (issue #144).
        """
        return self._disabled_tool_names()

    def session_schemas(self) -> list[dict[str, Any]]:
        """Schemas of the tools the current session may offer by default.

        Applies the ``-r``/``-w``/``-x`` privilege filter on top of the
        complete registry (see :func:`janito.tools.tool_is_allowed_by_privileges`):
        with ``running_privileges`` unset (``None``) everything is allowed,
        otherwise only the tools whose declared permissions are satisfied are
        returned.  The CLI default is read-only (issue #85), so a normal
        janito run offers only the READ tools.  This is the default ``tools=``
        set for a normal prompt; the per-command tool modes (``/read``
        ``/write`` ``/rx`` ``/rw`` ``/rwx``) bypass it by passing their own
        explicit list (issue #87).

        Returns:
            List[Dict[str, Any]]: List of function-calling schemas allowed by
            the current session privileges.
        """
        self.ensure_initialized()
        disabled = self._disabled_tool_names()
        return [
            get_function_schema(tool)
            for name, tool in AVAILABLE_TOOLS.items()
            if name not in disabled and tool_is_allowed_by_privileges(getattr(tool, "_tool_permissions", "") or "")
        ]

    def system_prompt_hints(self) -> list[tuple[str, str]]:
        """System prompt hints contributed by the session's tools.

        Tools may declare a ``system_prompt_hint`` class attribute (see
        :class:`janito.tooling.base_tool.BaseTool`) with usage guidance for
        the LLM.  This collects the non-empty hints of the tools the current
        session may actually use -- the same privilege / model-disabled
        filtering as :meth:`session_tool_names` -- so a restricted session
        never gets advertised hints for tools it cannot call.

        Returns:
            List[Tuple[str, str]]: ``(tool name, hint)`` pairs sorted by tool
            name (empty when no tool contributes a hint).
        """
        self.ensure_initialized()
        allowed = self.session_tool_names()
        hints: list[tuple[str, str]] = []
        for name, tool in AVAILABLE_TOOLS.items():
            hint = (getattr(tool, "_tool_system_prompt_hint", "") or "").strip()
            if hint and name in allowed:
                hints.append((name, hint))
        return sorted(hints)

    def session_tool_names(self) -> set[str]:
        """Names of the tools the current session may offer by default.

        Same privilege filtering as :meth:`session_schemas`, returning just
        the tool names (used by the execution-time gate and the privilege
        override warning).

        Returns:
            Set[str]: Names of the tools allowed by the current session
            privileges.
        """
        self.ensure_initialized()
        disabled = self._disabled_tool_names()
        return {
            name
            for name, tool in AVAILABLE_TOOLS.items()
            if name not in disabled and tool_is_allowed_by_privileges(getattr(tool, "_tool_permissions", "") or "")
        }

    def get(self, name: str) -> Callable:
        """
        Get a specific tool by name.

        Args:
            name (str): Name of the tool

        Returns:
            Callable: The tool function

        Raises:
            KeyError: If tool with given name doesn't exist
        """
        self.ensure_initialized()
        if name not in AVAILABLE_TOOLS:
            raise KeyError(f"Tool '{name}' not found. Available tools: {list(AVAILABLE_TOOLS.keys())}")
        return AVAILABLE_TOOLS[name]

    def schema(self, name: str) -> dict[str, Any]:
        """
        Get a specific tool schema by name.

        Args:
            name (str): Name of the tool

        Returns:
            Dict[str, Any]: The tool schema

        Raises:
            KeyError: If tool with given name doesn't exist
        """
        return get_function_schema(self.get(name))

    def permissions(self, name: str) -> str:
        """
        Get the permissions required by a specific tool.

        Args:
            name (str): Name of the tool

        Returns:
            str: Permission string (e.g., "r", "rw", "rwx") or empty string if no permissions declared

        Raises:
            KeyError: If tool with given name doesn't exist
        """
        self.ensure_initialized()
        if name not in AVAILABLE_TOOLS:
            raise KeyError(f"Tool '{name}' not found. Available tools: {list(AVAILABLE_TOOLS.keys())}")
        return getattr(AVAILABLE_TOOLS[name], "_tool_permissions", "")

    def skills_section(self) -> str:
        """
        Get the skills advertisement section to append to system prompts.

        Returns:
            String with skill names, descriptions, and tool instructions
        """
        if not _skills_enabled:
            return ""

        advertisement = get_skills_advertisement()

        if not advertisement:
            return ""

        # Add tool usage instructions
        tools_section = """
\n## Skill Tools
Use these tools to load skill content when needed:
- **load_skill(skill_name)**: Load the full instructions from a skill's SKILL.md file
- **read_skill_resource(skill_name, resource_name)**: Read a supplementary file from a skill

You should load a skill when the user's request matches its description or you need specialized guidance."""

        return advertisement + tools_section

    def enable_skills(self) -> None:
        """Enable skills support."""
        global _skills_enabled
        self.ensure_initialized()
        _skills_enabled = True
        AVAILABLE_TOOLS.update(get_skills_tools())

    def disable_skills(self) -> None:
        """Disable skills support."""
        global _skills_enabled
        self.ensure_initialized()
        _skills_enabled = False
        for tool_name in ["load_skill", "read_skill_resource"]:
            AVAILABLE_TOOLS.pop(tool_name, None)

    def disable_tools_loading(self) -> None:
        """Disable loading of all tools (``--no-tools``).

        Must be called before the first :meth:`ensure_initialized` to take
        effect: afterwards the autoload toolsets are never discovered,
        :meth:`add_toolset` and :meth:`register_plugin_tools` become
        no-ops.  Skill tools must be disabled separately via
        :meth:`disable_skills` (the CLI does both for ``--no-tools``).
        """
        global _tools_loading_enabled
        _tools_loading_enabled = False

    def tools_loading_enabled(self) -> bool:
        """Whether non-skill tools are loaded (False after ``--no-tools``)."""
        return _tools_loading_enabled

    def disable_toolset(self, toolset_name: str) -> None:
        """Disable a single toolset (``--no-tasks``).

        Must be called before the first :meth:`ensure_initialized` to take
        effect: afterwards the toolset is filtered out of the autoload
        discovery and :meth:`add_toolset` refuses to load it.  Every other
        toolset -- and the skill tools -- stays enabled.

        Args:
            toolset_name: Name of the toolset to disable (e.g. ``"tasks"``).
        """
        global _disabled_toolsets
        _disabled_toolsets = _disabled_toolsets | {toolset_name}

    def disabled_toolsets(self) -> set[str]:
        """Names of the toolsets disabled via :meth:`disable_toolset`."""
        return set(_disabled_toolsets)


# Module-level singleton backing the functions below.
_registry = ToolsRegistry()


def add_toolset(toolset_name: str) -> bool:
    """
    Dynamically add a toolset to the available tools.

    Args:
        toolset_name: Name of the toolset to add (e.g., "janitoweb", "files", "system")

    Returns:
        bool: True if the toolset was added, False if already loaded or invalid
    """
    return _registry.add_toolset(toolset_name)


def get_all_tools() -> dict[str, Callable]:
    """
    Get all available tools as a dictionary mapping names to functions.

    Returns:
        Dict[str, Callable]: Dictionary of tool names to functions
    """
    return _registry.all_tools()


def get_all_tool_schemas() -> list[dict[str, Any]]:
    """
    Get all tool schemas in the format expected by OpenAI function calling.

    Returns:
        List[Dict[str, Any]]: List of tool schemas
    """
    return _registry.all_schemas()


def get_all_tool_permissions() -> dict[str, str]:
    """
    Get permissions for all available tools.

    Returns:
        Dict[str, str]: Dictionary mapping tool names to their permission strings
    """
    return _registry.all_permissions()


def get_session_tool_schemas() -> list[dict[str, Any]]:
    """Schemas of the tools the current session may offer by default.

    The ``-r``/``-w``/``-x`` privilege-filtered view of the registry: with no
    privilege flags this equals :func:`get_all_tool_schemas`; otherwise it
    drops the tools whose declared permissions the session privileges do not
    grant.  This is the default ``tools=`` set for a normal prompt (the CLI
    and web clients resolve it when ``tools is None``); the per-command tool
    modes (``/read`` ``/write`` ``/rx`` ``/rw`` ``/rwx``) bypass it by
    passing their own explicit list (issue #87).

    Returns:
        List[Dict[str, Any]]: List of function-calling schemas allowed by the
        current session privileges.
    """
    return _registry.session_schemas()


def get_session_tool_names() -> set[str]:
    """Names of the tools the current session may offer by default.

    Privilege-filtered tool names (see :func:`get_session_tool_schemas`);
    used by the execution-time gate and the privilege override warning.

    Returns:
        Set[str]: Names of the tools allowed by the current session
        privileges.
    """
    return _registry.session_tool_names()


def get_disabled_tool_names() -> set[str]:
    """Names of external tools disabled for the active provider/model.

    Resolved via :func:`janito.config_loaders.resolve_disabled_tools`
    (issue #144); empty when nothing is disabled.

    Returns:
        Set[str]: Names of the model-disabled tools.
    """
    return _registry.disabled_tool_names()


def get_tool_by_name(name: str) -> Callable:
    """Get a specific tool by name.

    Args:
        name (str): Name of the tool

    Returns:
        Callable: The tool function

    Raises:
        KeyError: If tool with given name doesn't exist
    """
    return _registry.get(name)


def get_tool_permissions(name: str) -> str:
    """
    Get the permissions required by a specific tool.

    Args:
        name (str): Name of the tool

    Returns:
        str: Permission string (e.g., "r", "rw", "rwx") or empty string if no permissions declared

    Raises:
        KeyError: If tool with given name doesn't exist
    """
    return _registry.permissions(name)


def get_skills_section() -> str:
    """
    Get the skills advertisement section to append to system prompts.

    Returns:
        String with skill names, descriptions, and tool instructions
    """
    return _registry.skills_section()


def get_system_prompt_hints() -> list[tuple[str, str]]:
    """
    Get the system prompt hints contributed by the session's tools.

    See :meth:`ToolsRegistry.system_prompt_hints`: only tools the current
    privileges allow are included, and each hint is the tool's stripped
    ``system_prompt_hint`` class attribute.

    Returns:
        List[Tuple[str, str]]: ``(tool name, hint)`` pairs sorted by name.
    """
    return _registry.system_prompt_hints()


def enable_skills() -> None:
    """Enable skills support."""
    _registry.enable_skills()


def disable_skills() -> None:
    """Disable skills support."""
    _registry.disable_skills()


def disable_tools_loading() -> None:
    """Disable loading of all tools (``--no-tools``).

    Skill tools must be disabled separately via :func:`disable_skills`.
    """
    _registry.disable_tools_loading()


def register_plugin_tools(tools: dict[str, Callable]) -> None:
    """
    Register tools contributed by a plugin.

    Args:
        tools: Mapping of tool names to wrapped callables (see
            :meth:`ToolsRegistry.register_plugin_tools`).
    """
    _registry.register_plugin_tools(tools)


def tools_loading_enabled() -> bool:
    """Whether non-skill tools are loaded (False after ``--no-tools``)."""
    return _registry.tools_loading_enabled()


def disable_toolset(toolset_name: str) -> None:
    """Disable a single toolset (``--no-tasks``).

    Skill tools and every other toolset stay enabled.
    """
    _registry.disable_toolset(toolset_name)


def disabled_toolsets() -> set[str]:
    """Names of the toolsets disabled via :func:`disable_toolset`."""
    return _registry.disabled_toolsets()


if __name__ == "__main__":
    # Example usage
    print("Available tools:")
    for name in AVAILABLE_TOOLS:
        print(f"  - {name}")

    print("\nTool schemas:")
    for schema in get_all_tool_schemas():
        print(f"  - {schema['function']['name']}: {schema['function']['description']}")
