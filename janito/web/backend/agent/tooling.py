"""Tool discovery (built-in + MCP) and execution for the web agent.

The tools registry, MCP manager and usage-tracking helpers are always
present within the package, so they are imported directly (no defensive
fallbacks).

Tool *execution* is shared with the CLI loop: the synchronous core
(:func:`janito.tooling.executor.run_tool`) does the routing, usage/used-
files/changes tracking and failure shaping, and captures ``report_*``
output through a progress callback.  This module wraps it in a thread and
converts the captured output into ``ToolProgressEvent``s for the browser.
"""

import logging

from janito.mcp_manager import get_mcp_manager

from janito.tooling.executor import (
    is_mcp_tool as is_mcp_tool,  # re-exported for turn.py
)
from janito.tooling.executor import run_tool
from janito.tooling.tools_registry import get_session_tool_schemas
from janito.tooling.tools_registry import (
    get_tool_permissions as get_tool_permissions,  # re-exported for turn.py
)
from janito.tooling.tools_registry import tools_loading_enabled
from janito.tooling.used_files import (
    reset_used_files as reset_used_files,  # re-exported for loop.py
)

from ..events import ToolProgressEvent
from .workers import run_in_worker

logger = logging.getLogger(__name__)


async def resolve_tools(config, tools: list[dict] | None, use_mcp: bool) -> list[dict]:
    """Resolve the tool schemas to hand to the model for this session.

    - ``config.no_tools`` -> empty list.
    - ``tools`` explicitly provided -> use as-is.
    - Otherwise auto-discover built-in tools plus (optionally) MCP tools.
      With ``--no-tools`` the registry holds only the skill tools and MCP
      tools are not loaded.
    """
    if config.no_tools:
        return []

    if tools is not None:
        return tools

    mcp_tools: list[dict] = []
    if use_mcp and tools_loading_enabled():
        mcp_manager = get_mcp_manager()
        try:
            await run_in_worker(mcp_manager.load_services)
            mcp_tools = await run_in_worker(mcp_manager.get_all_tools)
            logger.info(f"Loaded {len(mcp_tools)} MCP tools from {len(mcp_manager.connected_services)} services")
        except Exception as e:  # noqa: BLE001 - intentional boundary, log/convert and continue
            logger.warning(f"Failed to load MCP tools: {e}")

    built_in_tools = get_session_tool_schemas()
    return built_in_tools + mcp_tools


async def execute_tool(
    tool_call_id: str,
    tool_name: str,
    tool_args: dict,
    use_mcp: bool,
    allowed_tools: set[str] | None = None,
):
    """Execute a single tool call, capturing report_* output as progress events.

    ``allowed_tools`` is the execution-time privilege gate (issue #87): when
    given, a call to a tool that was not offered in the current turn is
    rejected by the shared :func:`run_tool` core with a structured error
    instead of executing.

    Returns a tuple ``(result_dict, progress_events, error, exec_time_ms)``.
    The tool runs in a thread via the shared :func:`run_tool` core; the
    progress callback receives every ``report_*`` line (tools are
    synchronous, so the handler sees them in the same thread) and converts
    it into a ``ToolProgressEvent``.
    """
    progress_events: list[ToolProgressEvent] = []

    def handler(level: str, message: str, end: str):
        progress_events.append(
            ToolProgressEvent(
                tool_call_id=tool_call_id,
                level=level,
                message=message,
            )
        )

    result, error, exec_time_ms = await run_in_worker(
        run_tool,
        tool_name,
        tool_args,
        use_mcp,
        progress=handler,
        allowed_tools=allowed_tools,
    )
    return result, progress_events, error, exec_time_ms
