"""Tool discovery and privilege gating for the tool framework.

Discovery (scanning the ``janito.tools.*`` toolsets for ``@tool``-marked
classes, running their ``should_load()`` gate and wrapping them as callables)
and the privilege predicates used by the session tool selector live here --
in the tooling framework -- so ``tooling`` never imports from
``janito.tools`` (issue #90: the tools package depends one-way on the
framework, not vice versa).  ``janito.tools/__init__.py`` re-exports these
for the plugin manager and the shell/web tool lists.
"""

import importlib
import inspect
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import get_type_hints

from .decorator import is_tool

logger = logging.getLogger(__name__)

# Tools that were skipped during discovery because their should_load()
# validation failed, mapped to a human-readable reason.
_skipped_tools: dict[str, str] = {}


def get_skipped_tools() -> dict[str, str]:
    """
    Get tools that were skipped during discovery.

    Returns:
        Dict[str, str]: Mapping of tool class names to skip reasons
    """
    return _skipped_tools.copy()


def _check_should_load(cls: type) -> bool:
    """
    Run a tool class's should_load() validation.

    Tools that fail validation (or raise during validation) are recorded
    in _skipped_tools and excluded from discovery.

    Args:
        cls: The tool class to validate

    Returns:
        bool: True if the tool should be loaded, False to skip it
    """
    should_load = getattr(cls, "should_load", None)
    if not callable(should_load):
        return True
    try:
        if should_load():
            return True
        reason = getattr(cls, "_load_skip_reason", "") or "should_load() returned False"
        _skipped_tools[cls.__name__] = reason
    except Exception as e:  # noqa: BLE001 - discovery must never break the agent loop
        logger.warning("Tool %s should_load() raised: %s", cls.__name__, e)
        _skipped_tools[cls.__name__] = f"should_load() raised {type(e).__name__}: {e}"
    return False


# Maps permission characters to Privileges dataclass attribute names.
_PERMISSION_TO_PRIVILEGE = {
    "r": "READ",
    "w": "WRITE",
    "x": "EXEC",
}


def missing_privileges(tool_permissions: str) -> list[str]:
    """Return the privilege characters ``tool_permissions`` needs that the
    current ``running_privileges`` do not grant.

    ``running_privileges`` is ``None`` when no restrictions were configured
    (outside the CLI, where ``_setup_privileges`` always sets it -- the
    default is read-only, issue #85), in which case nothing is missing.
    Tools declaring no permissions (``""``) always return an empty list.

    Args:
        tool_permissions: The tool's ``_tool_permissions`` string (e.g.
            ``"rw"``).

    Returns:
        The missing privilege characters (e.g. ``["w"]``), or ``[]`` when
        the tool is allowed.
    """
    from .. import privileges as _privileges_mod

    running = _privileges_mod.running_privileges
    if running is None:
        return []

    missing: list[str] = []
    for char in tool_permissions:
        attr = _PERMISSION_TO_PRIVILEGE.get(char)
        if attr is not None and not getattr(running, attr, False):
            missing.append(char)
    return missing


def tool_is_allowed_by_privileges(tool_permissions: str) -> bool:
    """Whether the current ``running_privileges`` satisfy every privilege
    character declared by ``tool_permissions``.

    Used by the session tool selector (:func:`janito.tooling.tools_registry
    .get_session_tool_schemas`) to decide which tools a normal prompt may
    offer.  The per-command tool modes (``/read`` ``/write`` ``/rx`` ``/rw``
    ``/rwx``) pass their own explicit tool list instead and are therefore
    able to override the session privileges for a single exchange (issue
    #87).

    Args:
        tool_permissions: The tool's ``_tool_permissions`` string.

    Returns:
        ``True`` when the tool is allowed by the current privileges.
    """
    return not missing_privileges(tool_permissions)


def privilege_restriction_reason(tool_permissions: str) -> str | None:
    """Human-readable reason a tool is restricted by the current privileges.

    Returns ``None`` when the tool is allowed (or no ``-r``/``-w``/``-x``
    flags were passed); otherwise a message such as
    ``"insufficient privileges: requires 'w' (WRITE)"`` for display in the
    ``/tools`` command and the web tools panel.

    Args:
        tool_permissions: The tool's ``_tool_permissions`` string.

    Returns:
        The restriction reason, or ``None`` when the tool is allowed.
    """
    missing = missing_privileges(tool_permissions)
    if not missing:
        return None
    missing_descriptions = [f"'{c}' ({_PERMISSION_TO_PRIVILEGE[c]})" for c in missing]
    return "insufficient privileges: requires " + ", ".join(missing_descriptions)


def _check_tool_privileges(cls: type) -> bool:
    """Check whether the current ``running_privileges`` satisfy the tool's
    required permissions.

    Discovery no longer skips tools on privileges: everything is loaded so
    the per-command tool modes (``/read`` ``/write`` ``/rx`` ``/rw``
    ``/rwx``) can expand beyond the session privileges (issue #87).  This
    predicate remains for the session tool selector
    (:func:`tool_is_allowed_by_privileges`) and for introspection.

    Args:
        cls: The tool class to validate.

    Returns:
        ``True`` when the tool is allowed by the current privileges.
    """
    return tool_is_allowed_by_privileges(getattr(cls, "_tool_permissions", "") or "")


def _make_class_tool(cls: type) -> Callable:
    """Create a wrapper function that instantiates and calls run."""
    # Get the run method signature and type hints
    run_method = cls.run
    run_sig = inspect.signature(run_method)
    run_type_hints = get_type_hints(run_method)

    # Create a wrapper with the same signature as the run method
    # but without the 'self' parameter
    params = list(run_sig.parameters.values())[1:]  # Skip 'self'
    new_sig = run_sig.replace(parameters=params)

    def class_tool_wrapper(*args, **kwargs):
        instance = cls()
        return instance.run(*args, **kwargs)

    # Set the correct signature and metadata
    class_tool_wrapper.__signature__ = new_sig
    class_tool_wrapper.__name__ = cls.__name__
    class_tool_wrapper.__doc__ = cls.__doc__
    class_tool_wrapper._is_tool = True
    class_tool_wrapper._tool_permissions = getattr(cls, "_tool_permissions", "")
    # Propagate the system prompt hint (see BaseTool.system_prompt_hint) so
    # the registry can collect it from the wrapped tool.
    class_tool_wrapper._tool_system_prompt_hint = getattr(cls, "system_prompt_hint", "")
    # Propagate the load validation hook for later introspection
    class_tool_wrapper.should_load = getattr(cls, "should_load", None)

    # Preserve type hints (excluding 'self')
    class_tool_wrapper.__annotations__ = {k: v for k, v in run_type_hints.items() if k != "self"}

    return class_tool_wrapper


def _collect_module_tools(module, full_module_name: str, tools: dict) -> None:
    """Discover and register tool classes defined in ``module``."""
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue

        attr = getattr(module, attr_name)
        if not isinstance(attr, type):
            continue

        # Check if the class is actually defined in this module
        # (not imported from elsewhere)
        if hasattr(attr, "__module__") and attr.__module__ == full_module_name:
            # Check if the class is explicitly marked as a tool
            if is_tool(attr):
                # Let tools opt out of loading (missing binaries,
                # unsupported platform, missing credentials, ...).
                # Privilege restrictions no longer skip tools here: everything
                # is loaded so the per-command tool modes (/read /write /rx
                # /rw /rwx) can override the session privileges (issue #87);
                # the session tool selector applies them instead.
                if not _check_should_load(attr):
                    continue

                tools[attr_name] = _make_class_tool(attr)


def wrap_tool_class(cls: type) -> Callable | None:
    """
    Validate and wrap a single tool class into a callable.

    Runs the same ``should_load()`` gate as toolset discovery and returns
    ``None`` (and records the skip reason) when the tool must not be loaded.
    Privilege restrictions are **not** applied here: everything is loaded so
    the per-command tool modes (``/read`` ``/write`` ``/rx`` ``/rw``
    ``/rwx``) can override the session privileges for a single exchange
    (issue #87); the session tool selector applies them instead.  Used by
    the plugin manager to register tool classes contributed by a plugin's
    ``TOOLS`` list.

    Args:
        cls: A ``BaseTool`` subclass decorated with ``@tool``.

    Returns:
        The wrapped callable (its ``__name__`` is the class name), or None
        if the tool failed validation.
    """
    if not is_tool(cls):
        logger.warning("Skipping %s: not a @tool class", getattr(cls, "__name__", cls))
        return None
    if not _check_should_load(cls):
        return None
    return _make_class_tool(cls)


def discover_module_tools(module) -> dict[str, Callable]:
    """
    Discover tool classes defined in an arbitrary module.

    Unlike :func:`discover_toolsets` (which only scans ``janito.tools.*``
    toolset directories), this works on any imported module, so the plugin
    manager can collect tools from a plugin's ``tools`` subpackage.

    Args:
        module: An imported module object.

    Returns:
        Dict mapping tool names (class names) to wrapped callables.
    """
    tools: dict[str, Callable] = {}
    _collect_module_tools(module, module.__name__, tools)
    return tools


def _load_module_tools(toolset_name: str, module_name: str, tools: dict) -> None:
    """Import one toolset module and register its tool classes."""
    full_module_name = f"janito.tools.{toolset_name}.{module_name}"
    try:
        # Import the module
        module = importlib.import_module(full_module_name)
    except Exception as e:  # noqa: BLE001 - discovery must never break the agent loop
        # Skip modules that can't be imported (missing optional dependency,
        # platform-specific tool, broken toolset) but surface the cause so a
        # tool that silently fails to load can be diagnosed.
        logger.warning("Skipping tool module %s: %s", full_module_name, e)
        return

    _collect_module_tools(module, full_module_name, tools)


def discover_toolsets(toolset_names: list[str]) -> dict[str, Callable]:
    """
    Discover and load tools from specified toolsets.

    Args:
        toolset_names: List of toolset names to load (e.g., ["files", "git"])

    Returns:
        Dict[str, Callable]: Dictionary mapping tool names to functions
    """
    tools = {}
    # The toolsets live in ``janito/tools/<toolset>/``; this module lives in
    # ``janito/tooling/``, so resolve the sibling directory by filesystem path
    # (importing ``janito.tools`` here would recreate the tooling -> tools
    # cycle this module exists to break, issue #90).
    tools_dir = str(Path(__file__).resolve().parent.parent / "tools")

    for toolset_name in toolset_names:
        toolset_path = os.path.join(tools_dir, toolset_name)
        if not os.path.exists(toolset_path):
            continue

        # Look for Python files in the toolset directory (excluding __init__.py)
        for filename in os.listdir(toolset_path):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]  # Remove .py extension
                _load_module_tools(toolset_name, module_name, tools)

    return tools


__all__ = [
    "_check_should_load",
    "_check_tool_privileges",
    "_collect_module_tools",
    "_load_module_tools",
    "_make_class_tool",
    "_skipped_tools",
    "discover_module_tools",
    "discover_toolsets",
    "get_skipped_tools",
    "missing_privileges",
    "privilege_restriction_reason",
    "tool_is_allowed_by_privileges",
    "wrap_tool_class",
]
