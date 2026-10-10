"""Mapping from web-loop agent events to ACP ``session/update`` payloads.

The web backend streams turns as :class:`janito.web.backend.events.AgentEvent`
instances; :func:`map_event` translates the ones ACP clients can render into
the ACP v1 ``session/update`` updates.  Events without an ACP equivalent
(usage, image, done, ...) map to ``None`` and are skipped.
"""

import json
import os
import re

from janito.web.backend.events import (
    ErrorEvent,
    ReasoningEvent,
    TokenEvent,
    ToolCallEvent,
    ToolProgressEvent,
    ToolResultEvent,
    UsageEvent,
)

# Cap tool output size sent to the client (full reads inline mode can be huge).
_MAX_TOOL_OUTPUT = 100_000

# Tool class name -> ACP ToolCall kinds (see the ACP v1 schema).
_TOOL_KIND = {
    "ReadFile": "read",
    "ReadMultipleFiles": "read",
    "ListFiles": "read",
    "GetCurrentTime": "read",
    "GetTaskInfo": "read",
    "FindFiles": "search",
    "SearchText": "search",
    "SearchRegex": "search",
    "WebSearch": "search",
    "CreateFile": "edit",
    "ReplaceTextInFile": "edit",
    "CreateDirectory": "edit",
    "CreateSVG": "edit",
    "DeleteFile": "delete",
    "RemoveDirectory": "delete",
    "MoveFile": "move",
    "RunBashCode": "execute",
    "RunPowerShellCode": "execute",
    "RunPythonCode": "execute",
    "RunPythonFile": "execute",
    "RunGitHubCLI": "execute",
    "StartTask": "execute",
    "StopTask": "execute",
    "WaitForTask": "execute",
    "GetUrl": "fetch",
    "HeadlessBrowse": "fetch",
    "AskUser": "other",
}

# Human-readable titles shown in the client's tool-call list.
_TOOL_TITLES = {
    "ReadFile": "Reading file",
    "ReadMultipleFiles": "Reading files",
    "ListFiles": "Listing directory",
    "GetCurrentTime": "Reading current time",
    "GetTaskInfo": "Reading task info",
    "FindFiles": "Finding files",
    "SearchText": "Searching files",
    "SearchRegex": "Searching files",
    "WebSearch": "Searching the web",
    "CreateFile": "Creating file",
    "ReplaceTextInFile": "Editing file",
    "CreateDirectory": "Creating directory",
    "CreateSVG": "Creating SVG",
    "DeleteFile": "Deleting file",
    "RemoveDirectory": "Removing directory",
    "MoveFile": "Moving file",
    "RunBashCode": "Running shell command",
    "RunPowerShellCode": "Running PowerShell command",
    "RunPythonCode": "Running Python code",
    "RunPythonFile": "Running Python script",
    "RunGitHubCLI": "Running GitHub CLI command",
    "StartTask": "Starting task",
    "StopTask": "Stopping task",
    "WaitForTask": "Waiting for task",
    "GetUrl": "Fetching URL",
    "HeadlessBrowse": "Browsing the web",
    "AskUser": "Asking the user",
    "OpenBrowser": "Opening browser",
    "CreateImage": "Creating image",
}

_LOCATION_ARG_KEYS = ("filepath", "directory", "source", "destination")


def _humanize(name: str) -> str:
    """``ReadMultipleFiles`` -> ``Read Multiple Files``."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name)


def _tool_kind(name: str) -> str:
    return _TOOL_KIND.get(name, "other")


def _tool_title(name: str) -> str:
    return _TOOL_TITLES.get(name, _humanize(name))


def _location_from_value(value: str, cwd: str) -> dict:
    path = value if os.path.isabs(value) else os.path.join(cwd, value)
    return {"path": os.path.abspath(path)}


def locations_from_args(args: dict, cwd: str) -> list[dict] | None:
    """Extract file locations from tool arguments, resolved against ``cwd``."""
    locations: list[dict] = []
    for key in _LOCATION_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value:
            locations.append(_location_from_value(value, cwd))
    filepaths = args.get("filepaths")
    if isinstance(filepaths, list):
        for item in filepaths:
            if isinstance(item, str) and item:
                locations.append(_location_from_value(item, cwd))
    return locations or None


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _content_block(text: str) -> dict:
    return {"type": "content", "content": text_block(text)}


def _clip(text: str) -> str:
    if len(text) <= _MAX_TOOL_OUTPUT:
        return text
    return text[:_MAX_TOOL_OUTPUT] + "\n...[output truncated]"


def _result_to_text(result) -> str:
    if result is None:
        return "Tool completed with no output."
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(result)


def map_event(event, *, message_id: str, cwd: str) -> dict | None:
    """Translate one agent event into an ACP session/update payload."""
    if isinstance(event, TokenEvent):
        return {
            "sessionUpdate": "agent_message_chunk",
            "messageId": message_id,
            "content": text_block(event.content),
        }
    if isinstance(event, ReasoningEvent):
        return {
            "sessionUpdate": "agent_thought_chunk",
            "messageId": message_id,
            "content": text_block(event.content),
        }
    if isinstance(event, ToolCallEvent):
        return _tool_call_update(event, cwd)
    if isinstance(event, ToolProgressEvent):
        return _tool_progress_update(event)
    if isinstance(event, ToolResultEvent):
        return _tool_result_update(event)
    if isinstance(event, ErrorEvent):
        return {
            "sessionUpdate": "agent_message_chunk",
            "messageId": message_id,
            "content": text_block(f"Error: {event.message}"),
        }
    if isinstance(event, UsageEvent):
        # Skipped: janito's token counters do not match the ACP usage_group
        # semantics, so reporting them would mislead the client.
        return None
    return None


def _tool_call_update(event: ToolCallEvent, cwd: str) -> dict:
    # Malformed model output can surface non-dict arguments; only dicts
    # carry file locations.
    arguments = event.arguments if isinstance(event.arguments, dict) else {}
    update = {
        "sessionUpdate": "tool_call",
        "toolCallId": event.tool_call_id,
        "name": event.tool_name,
        "title": _tool_title(event.tool_name),
        "kind": _tool_kind(event.tool_name),
        "status": "pending",
        "rawInput": event.arguments,
    }
    locations = locations_from_args(arguments, cwd)
    if locations:
        update["locations"] = locations
    return update


def _tool_progress_update(event: ToolProgressEvent) -> dict:
    return {
        "sessionUpdate": "tool_call_update",
        "toolCallId": event.tool_call_id,
        "status": "in_progress",
        "content": [_content_block(_clip(event.message))],
    }


def _tool_result_update(event: ToolResultEvent) -> dict:
    failed = bool(event.error) or (
        isinstance(event.result, dict) and event.result.get("success") is False
    )
    update = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": event.tool_call_id,
        "status": "failed" if failed else "completed",
        "content": [_content_block(_clip(event.error or _result_to_text(event.result)))],
    }
    if failed and event.error:
        update["error"] = event.error
    if isinstance(event.result, str):
        update["rawOutput"] = _clip(event.result)
    elif event.result is not None and not failed:
        update["rawOutput"] = event.result
    return update
