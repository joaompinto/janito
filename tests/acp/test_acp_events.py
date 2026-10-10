"""Unit tests for the ACP event mapping (janito events -> session/update)."""

from __future__ import annotations

import os

from janito.acp.events import locations_from_args, map_event
from janito.web.backend.events import (
    ErrorEvent,
    ReasoningEvent,
    TokenEvent,
    ToolCallEvent,
    ToolProgressEvent,
    ToolResultEvent,
    UsageEvent,
)

CWD = "/home/user/proj"


def test_map_token_to_message_chunk():
    update = map_event(TokenEvent(content="hello "), message_id="m1", cwd=CWD)
    assert update["sessionUpdate"] == "agent_message_chunk"
    assert update["messageId"] == "m1"
    assert update["content"] == {"type": "text", "text": "hello "}


def test_map_reasoning_to_thought_chunk():
    update = map_event(ReasoningEvent(content="thinking..."), message_id="m1", cwd=CWD)
    assert update["sessionUpdate"] == "agent_thought_chunk"
    assert update["content"] == {"type": "text", "text": "thinking..."}


def test_map_tool_call_pending():
    update = map_event(
        ToolCallEvent(
            tool_call_id="call_1",
            tool_name="ReadFile",
            arguments={"filepath": "src/a.txt"},
        ),
        message_id="m1",
        cwd=CWD,
    )
    assert update["sessionUpdate"] == "tool_call"
    assert update["toolCallId"] == "call_1"
    assert update["name"] == "ReadFile"
    assert update["title"] == "Reading file"
    assert update["kind"] == "read"
    assert update["status"] == "pending"
    assert update["rawInput"] == {"filepath": "src/a.txt"}
    assert update["locations"] == [{"path": os.path.abspath(os.path.join(CWD, "src/a.txt"))}]


def test_map_tool_call_kind_for_mutation_tools():
    cases = {
        "ReplaceTextInFile": "edit",
        "DeleteFile": "delete",
        "MoveFile": "move",
        "RunBashCode": "execute",
        "GetUrl": "fetch",
        "WebSearch": "search",
        "AskUser": "other",
        "SomePluginTool": "other",
    }
    for name, kind in cases.items():
        update = map_event(
            ToolCallEvent(tool_call_id="c", tool_name=name, arguments={}),
            message_id="m1",
            cwd=CWD,
        )
        assert update["kind"] == kind, name


def test_map_tool_progress_to_in_progress():
    update = map_event(
        ToolProgressEvent(tool_call_id="call_1", level="output", message="building..."),
        message_id="m1",
        cwd=CWD,
    )
    assert update["sessionUpdate"] == "tool_call_update"
    assert update["toolCallId"] == "call_1"
    assert update["status"] == "in_progress"
    assert update["content"][0]["type"] == "content"
    assert update["content"][0]["content"]["text"] == "building..."


def test_map_tool_result_completed():
    update = map_event(
        ToolResultEvent(
            tool_call_id="call_1",
            tool_name="ReadFile",
            result={"success": True, "content": "all good"},
            error=None,
        ),
        message_id="m1",
        cwd=CWD,
    )
    assert update["status"] == "completed"
    assert update["rawOutput"] == {"success": True, "content": "all good"}
    text = update["content"][0]["content"]["text"]
    assert '"all good"' in text


def test_map_tool_result_failed_with_error():
    update = map_event(
        ToolResultEvent(
            tool_call_id="call_1",
            tool_name="ReadFile",
            result=None,
            error="boom",
        ),
        message_id="m1",
        cwd=CWD,
    )
    assert update["status"] == "failed"
    assert update["error"] == "boom"
    assert update["content"][0]["content"]["text"] == "boom"


def test_map_tool_result_marks_dict_failure():
    update = map_event(
        ToolResultEvent(
            tool_call_id="call_1",
            tool_name="ReadFile",
            result={"success": False, "error": "missing"},
            error=None,
        ),
        message_id="m1",
        cwd=CWD,
    )
    assert update["status"] == "failed"


def test_map_error_to_message_chunk():
    update = map_event(ErrorEvent(message="API down"), message_id="m1", cwd=CWD)
    assert update["sessionUpdate"] == "agent_message_chunk"
    assert update["content"]["text"] == "Error: API down"


def test_map_unsupported_events_are_skipped():
    assert map_event(UsageEvent(total=10), message_id="m1", cwd=CWD) is None


def test_map_progress_always_in_progress():
    update = map_event(ToolProgressEvent(tool_call_id="c", level="info", message="x"), message_id="m1", cwd=CWD)
    assert update["status"] == "in_progress"


def test_locations_from_args_resolves_against_cwd():
    assert locations_from_args({"directory": "./sub"}, CWD) == [{"path": os.path.abspath(os.path.join(CWD, "sub"))}]
    abs_path = os.path.join(os.path.abspath(os.sep), "abs-path.txt")
    assert locations_from_args({"filepath": abs_path}, CWD) == [{"path": os.path.abspath(abs_path)}]
    assert locations_from_args({"filepaths": ["a.py", "b.py"]}, CWD) == [
        {"path": os.path.abspath(os.path.join(CWD, "a.py"))},
        {"path": os.path.abspath(os.path.join(CWD, "b.py"))},
    ]
    assert locations_from_args({"pattern": "foo"}, CWD) is None
