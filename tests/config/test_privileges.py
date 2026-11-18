"""
Tests for the session privilege model (issue #87).

The registry loads **every** tool whose ``should_load()`` gate passes --
privilege restrictions (``-r``/``-w``/``-x``) are applied by the *session
tool selector* (``get_session_tool_schemas`` / ``get_session_tool_names``)
instead of at discovery time.  This lets the session privilege switches
(``/read`` ``/write`` ``/rx`` ``/rw`` ``/rwx``, issue #141) move beyond the
privileges the session started with: under ``janito -r``, ``/write`` still
offers the write-only tools.  The execution-time gate (``allowed_tools`` on
``run_tool`` / ``ToolExecutor``) then ensures the model can only call the
tools that were actually offered in the turn.

These tests monkeypatch the module-level registry state (like
``test_tools_registry.py``) so no real filesystem discovery runs.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.tooling.tools_registry as tools_registry
from janito import privileges as _privileges_mod
from janito.privileges import Privileges
from janito.tooling.executor import ToolExecutor, extract_tool_names, run_tool


def _fake_tool(name, permissions="", hint=""):
    def fake(**kwargs):
        return {"success": True}

    fake.__name__ = name
    fake._tool_permissions = permissions
    fake._tool_system_prompt_hint = hint
    return fake


def _fake_schema(name, permissions=""):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


@pytest.fixture(autouse=True)
def _restore_privileges():
    """Save/restore the module-level running_privileges around each test."""
    saved = _privileges_mod.running_privileges
    yield
    _privileges_mod.running_privileges = saved


def _patch_registry(monkeypatch, tools):
    """Point the registry state at ``tools`` without running discovery."""
    monkeypatch.setattr(tools_registry, "AVAILABLE_TOOLS", dict(tools))
    monkeypatch.setattr(tools_registry, "_tools_initialized", True)


# ---------------------------------------------------------------------------
# Session tool selector
# ---------------------------------------------------------------------------


def test_session_schemas_none_privileges_allows_everything(monkeypatch):
    """running_privileges=None (no restrictions configured) -> everything.

    The CLI default is now read-only (issue #85); None only occurs outside
    the CLI (e.g. direct registry/web use), where it keeps meaning "no
    restriction configured".
    """
    tools = {
        "ReadFile": _fake_tool("ReadFile", "r"),
        "CreateFile": _fake_tool("CreateFile", "w"),
        "RunBashCode": _fake_tool("RunBashCode", "x"),
        "MoveFile": _fake_tool("MoveFile", "rw"),
        "LoadSkill": _fake_tool("LoadSkill", ""),
    }
    _patch_registry(monkeypatch, tools)
    _privileges_mod.running_privileges = None

    names = {s["function"]["name"] for s in tools_registry.get_session_tool_schemas()}
    assert names == set(tools)
    assert tools_registry.get_session_tool_names() == set(tools)


def test_session_schemas_filtered_by_read_only_privileges(monkeypatch):
    """Under -r only read and permission-less tools are offered."""
    tools = {
        "ReadFile": _fake_tool("ReadFile", "r"),
        "CreateFile": _fake_tool("CreateFile", "w"),
        "RunBashCode": _fake_tool("RunBashCode", "x"),
        "MoveFile": _fake_tool("MoveFile", "rw"),
        "LoadSkill": _fake_tool("LoadSkill", ""),
    }
    _patch_registry(monkeypatch, tools)
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)

    names = {s["function"]["name"] for s in tools_registry.get_session_tool_schemas()}
    assert names == {"ReadFile", "LoadSkill"}
    assert tools_registry.get_session_tool_names() == {"ReadFile", "LoadSkill"}


def test_session_schemas_filtered_by_read_write_privileges(monkeypatch):
    """Under -rw, read/write and permission-less tools are offered, exec is not."""
    tools = {
        "ReadFile": _fake_tool("ReadFile", "r"),
        "CreateFile": _fake_tool("CreateFile", "w"),
        "RunBashCode": _fake_tool("RunBashCode", "x"),
        "MoveFile": _fake_tool("MoveFile", "rw"),
        "LoadSkill": _fake_tool("LoadSkill", ""),
    }
    _patch_registry(monkeypatch, tools)
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=True, EXEC=False)

    names = {s["function"]["name"] for s in tools_registry.get_session_tool_schemas()}
    assert names == {"ReadFile", "CreateFile", "MoveFile", "LoadSkill"}


# ---------------------------------------------------------------------------
# Tool system-prompt hints follow the session privileges
# ---------------------------------------------------------------------------


def _hinted_tools():
    return {
        "ReadFile": _fake_tool("ReadFile", "r", "use max_lines"),
        "CreateFile": _fake_tool("CreateFile", "w", "prefer ReplaceTextInFile"),
        "RunBashCode": _fake_tool("RunBashCode", "x", "prefer RunPowerShellCode on Windows"),
        # No hint declared -> never contributes.
        "LoadSkill": _fake_tool("LoadSkill", ""),
    }


def test_system_prompt_hints_unrestricted_session(monkeypatch):
    """With no privilege restriction every hint is collected, sorted by name."""
    _patch_registry(monkeypatch, _hinted_tools())
    _privileges_mod.running_privileges = None

    assert tools_registry.get_system_prompt_hints() == [
        ("CreateFile", "prefer ReplaceTextInFile"),
        ("ReadFile", "use max_lines"),
        ("RunBashCode", "prefer RunPowerShellCode on Windows"),
    ]


def test_system_prompt_hints_filtered_by_privileges(monkeypatch):
    """Hints of tools the session may not use are not advertised."""
    _patch_registry(monkeypatch, _hinted_tools())
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)

    assert tools_registry.get_system_prompt_hints() == [("ReadFile", "use max_lines")]


def test_system_prompt_hints_empty_when_no_tool_declares_one(monkeypatch):
    """Tools without a hint yield an empty list (the section is omitted)."""
    _patch_registry(monkeypatch, {"ReadFile": _fake_tool("ReadFile", "r")})
    _privileges_mod.running_privileges = None

    assert tools_registry.get_system_prompt_hints() == []


def test_system_prompt_hints_strip_whitespace_only_hint(monkeypatch):
    """A blank hint is treated as no hint at all."""
    _patch_registry(monkeypatch, {"ReadFile": _fake_tool("ReadFile", "r", "   \n ")})
    _privileges_mod.running_privileges = None

    assert tools_registry.get_system_prompt_hints() == []


# ---------------------------------------------------------------------------
# Override commands offer the full registry subset (issue #87)
# ---------------------------------------------------------------------------


def test_write_cmd_offers_write_tools_under_read_only_privileges(monkeypatch):
    """Under -r, /write still offers the write-only tools (explicit override)."""
    from janito.shell.cmds.write import get_write_only_tool_schemas

    permissions = {
        "ReadFile": "r",
        "CreateFile": "w",
        "CreateDirectory": "w",
        "RunBashCode": "x",
        "MoveFile": "rw",
        "LoadSkill": "",
    }
    schemas = [_fake_schema(name, perms) for name, perms in sorted(permissions.items())]
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_all_tool_permissions",
        lambda: permissions,
    )
    monkeypatch.setattr("janito.tooling.tools_registry.get_all_tool_schemas", lambda: schemas)
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)

    names = [s["function"]["name"] for s in get_write_only_tool_schemas()]
    assert names == ["CreateDirectory", "CreateFile"]


def test_rwx_cmd_offers_everything_under_read_only_privileges(monkeypatch):
    """Under -r, /rwx still offers every built-in tool (explicit override)."""
    from janito.shell.cmds.rwx import get_read_write_exec_tool_schemas

    permissions = {"ReadFile": "r", "CreateFile": "w", "RunBashCode": "x"}
    schemas = [_fake_schema(name, perms) for name, perms in sorted(permissions.items())]
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_all_tool_permissions",
        lambda: permissions,
    )
    monkeypatch.setattr("janito.tooling.tools_registry.get_all_tool_schemas", lambda: schemas)
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)

    names = {s["function"]["name"] for s in get_read_write_exec_tool_schemas()}
    assert names == {"ReadFile", "CreateFile", "RunBashCode"}


def test_rx_cmd_excludes_write_tools(monkeypatch):
    """/rx offers exactly the read + execute tools, never write."""
    from janito.shell.cmds.rx import get_read_exec_tool_schemas

    permissions = {"ReadFile": "r", "RunBashCode": "x", "CreateFile": "w"}
    schemas = [_fake_schema(name, perms) for name, perms in sorted(permissions.items())]
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_all_tool_permissions",
        lambda: permissions,
    )
    monkeypatch.setattr("janito.tooling.tools_registry.get_all_tool_schemas", lambda: schemas)

    names = {s["function"]["name"] for s in get_read_exec_tool_schemas()}
    assert names == {"ReadFile", "RunBashCode"}


# ---------------------------------------------------------------------------
# Execution-time gate
# ---------------------------------------------------------------------------


def test_run_tool_rejects_tool_not_offered(monkeypatch):
    """A call to an existing tool outside the turn's offered set is rejected."""
    _patch_registry(
        monkeypatch,
        {
            "ReadFile": _fake_tool("ReadFile", "r"),
            "CreateFile": _fake_tool("CreateFile", "w"),
        },
    )
    result, error, exec_ms = run_tool("CreateFile", {"filepath": "/tmp/x"}, allowed_tools={"ReadFile"})
    assert error is not None
    assert "offered" in error.lower()
    assert result["success"] is False
    assert exec_ms == 0


def test_run_tool_allows_offered_tool(monkeypatch):
    """A call to an offered tool executes normally."""
    calls = []

    def fake_tool(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr("janito.tooling.executor.get_tool_by_name", lambda name: fake_tool)
    result, error, _ = run_tool("ReadFile", {"path": "/tmp/x"}, allowed_tools={"ReadFile"})
    assert error is None
    assert result == {"success": True}
    assert calls == [{"path": "/tmp/x"}]


def test_run_tool_no_gate_by_default(monkeypatch):
    """allowed_tools=None keeps the old behaviour (no gating)."""
    calls = []

    def fake_tool(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr("janito.tooling.executor.get_tool_by_name", lambda name: fake_tool)
    result, error, _ = run_tool("Whatever", {"x": 1})
    assert error is None
    assert result == {"success": True}
    assert calls == [{"x": 1}]


def test_tool_executor_gates_calls(monkeypatch):
    """ToolExecutor forwards allowed_tools to the shared core."""
    _patch_registry(
        monkeypatch,
        {
            "ReadFile": _fake_tool("ReadFile", "r"),
            "CreateFile": _fake_tool("CreateFile", "w"),
        },
    )
    ex = ToolExecutor(allowed_tools={"ReadFile"})
    call = {
        "id": "call_1",
        "function": {"name": "CreateFile", "arguments": "{}"},
    }
    msg = ex.execute_tool_call(call)
    assert msg["role"] == "tool"
    result = json.loads(msg["content"])
    assert result["success"] is False
    assert "offered" in result["error"].lower()


def test_run_tool_reports_not_found_with_available_tools(monkeypatch):
    """An unknown tool name yields a minimal 'not found' error and the list
    of available tools on the result, instead of blaming the privileges."""
    _patch_registry(
        monkeypatch,
        {
            "ReadFile": _fake_tool("ReadFile", "r"),
            "CreateFile": _fake_tool("CreateFile", "w"),
        },
    )
    result, error, exec_ms = run_tool("Grep", {"pattern": "x"}, allowed_tools={"ReadFile", "CreateFile"})
    assert "not found" in error.lower()
    assert result["success"] is False
    assert result["available_tools"] == ["CreateFile", "ReadFile"]
    assert exec_ms == 0


def test_run_tool_mcp_tool_not_offered_is_not_not_found(monkeypatch):
    """An MCP tool that exists but was not offered keeps the 'not offered'
    message (it is a real tool, so 'not found' would be wrong)."""
    _patch_registry(monkeypatch, {"ReadFile": _fake_tool("ReadFile", "r")})
    monkeypatch.setattr("janito.tooling.executor.is_mcp_tool", lambda name: name == "svc_read")
    result, error, _ = run_tool("svc_read", {"path": "x"}, allowed_tools={"ReadFile"})
    assert "offered" in error.lower()
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Privilege override warning
# ---------------------------------------------------------------------------


def test_warn_if_privilege_override_prints_warning(monkeypatch, capsys):
    from janito.shell.cmds._tool_filters import warn_if_privilege_override

    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_session_tool_names",
        lambda: {"ReadFile"},
    )

    warn_if_privilege_override([_fake_schema("CreateFile", "w")], "w")
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "privilege" in out.lower()
    # The tool names are intentionally not listed in the note.
    assert "CreateFile" not in out


def test_warn_if_privilege_override_rx_grants_no_write(monkeypatch, capsys):
    """/rx renders (-r/-x), never -w (issue #109)."""
    from janito.shell.cmds._tool_filters import warn_if_privilege_override

    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_session_tool_names",
        lambda: {"ReadFile"},
    )

    warn_if_privilege_override([_fake_schema("RunBashCode", "x")], "rx")
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "privilege" in out.lower()


def test_warn_if_privilege_override_rwx_lists_all(monkeypatch, capsys):
    """/rwx keeps listing all three flags (-r/-w/-x)."""
    from janito.shell.cmds._tool_filters import warn_if_privilege_override

    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_session_tool_names",
        lambda: {"ReadFile"},
    )

    warn_if_privilege_override([_fake_schema("CreateFile", "w")], "rwx")
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "privilege" in out.lower()


def test_warn_if_privilege_override_silent_within_privileges(monkeypatch, capsys):
    from janito.shell.cmds._tool_filters import warn_if_privilege_override

    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    monkeypatch.setattr(
        "janito.tooling.tools_registry.get_session_tool_names",
        lambda: {"ReadFile"},
    )

    warn_if_privilege_override([_fake_schema("ReadFile", "r")], "r")
    assert capsys.readouterr().out == ""


def test_warn_if_privilege_override_silent_with_full_privileges(capsys):
    from janito.shell.cmds._tool_filters import warn_if_privilege_override

    _privileges_mod.running_privileges = None
    warn_if_privilege_override([_fake_schema("CreateFile", "w")], "w")
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# CLI default privileges (issue #85)
# ---------------------------------------------------------------------------


def _privilege_args(read=False, write=False, exec_=False):
    """Build a minimal argparse-like namespace with the privilege flags."""
    args = type("Args", (), {})()
    args.read = read
    args.write = write
    args.exec = exec_
    return args


def test_setup_privileges_default_is_full_privileges():
    """No -r/-w/-x flags -> running_privileges is full (rwx) with warning pending."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    _privileges_mod.full_privileges_warning_pending = False
    args = _privilege_args()
    main_mod._setup_privileges(args)

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, True, True)
    assert _privileges_mod.full_privileges_warning_pending is True
    _privileges_mod.full_privileges_warning_pending = False


def test_setup_privileges_read_flag_only():
    """-r alone -> read-only, with no warning pending."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    _privileges_mod.full_privileges_warning_pending = False
    args = _privilege_args(read=True)
    main_mod._setup_privileges(args)

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, False, False)
    assert _privileges_mod.full_privileges_warning_pending is False


def test_setup_privileges_write_flag_takes_priority():
    """-w alone -> write-only, no default read (flags take priority)."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    args = _privilege_args(write=True)
    main_mod._setup_privileges(args)

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (False, True, False)


def test_setup_privileges_read_write_flags():
    """-r -w -> read + write, no exec."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    args = _privilege_args(read=True, write=True)
    main_mod._setup_privileges(args)

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, True, False)


def test_setup_privileges_full_flags():
    """-r -w -x -> full privileges."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    args = _privilege_args(read=True, write=True, exec_=True)
    main_mod._setup_privileges(args)

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, True, True)


# ---------------------------------------------------------------------------
# Config default privileges (issue #89)
# ---------------------------------------------------------------------------


def test_parse_privileges_normalizes_order_and_case():
    from janito.privileges import parse_privileges

    assert parse_privileges("rwx") == Privileges(True, True, True)
    assert parse_privileges("XWR") == Privileges(True, True, True)
    # Flag-semantics parity: 'w' alone is write-only (no implicit read).
    assert parse_privileges("w") == Privileges(False, True, False)
    assert parse_privileges("r") == Privileges(True, False, False)
    # Duplicates and mixed order are tolerated; whitespace is stripped.
    assert parse_privileges("rrwwxx") == Privileges(True, True, True)
    assert parse_privileges(" rw ") == Privileges(True, True, False)


def test_parse_privileges_rejects_invalid():
    from janito.privileges import parse_privileges

    with pytest.raises(ValueError, match="rxz"):
        parse_privileges("rxz")
    with pytest.raises(ValueError, match="unset"):
        parse_privileges("")
    with pytest.raises(ValueError):
        parse_privileges("rwx!")


def test_format_privileges_canonical_order():
    from janito.privileges import Privileges as P
    from janito.privileges import format_privileges

    assert format_privileges(P(True, True, True)) == "rwx"
    assert format_privileges(P(True, True, False)) == "rw"
    assert format_privileges(P(False, True, False)) == "w"
    assert format_privileges(P()) == ""


def test_setup_privileges_uses_config_default(monkeypatch):
    """No flags + configured privileges -> the config default applies."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    _privileges_mod.full_privileges_warning_pending = False
    monkeypatch.setattr(
        "janito.config_loaders.load_privileges_from_config",
        lambda: Privileges(READ=True, WRITE=True, EXEC=True),
    )
    main_mod._setup_privileges(_privilege_args())

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, True, True)
    assert _privileges_mod.full_privileges_warning_pending is False


def test_setup_privileges_config_default_is_full_privileges_when_unset(monkeypatch):
    """No flags + no configured privileges -> full (rwx) with warning pending."""
    from janito import __main__ as main_mod

    _privileges_mod.running_privileges = None
    _privileges_mod.full_privileges_warning_pending = False
    monkeypatch.setattr("janito.config_loaders.load_privileges_from_config", lambda: None)
    main_mod._setup_privileges(_privilege_args())

    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, True, True)
    assert _privileges_mod.full_privileges_warning_pending is True
    _privileges_mod.full_privileges_warning_pending = False


def test_setup_privileges_flags_override_config_default(monkeypatch):
    """Explicit flags always beat the configured default (issue #89)."""
    from janito import __main__ as main_mod

    def full():
        return Privileges(READ=True, WRITE=True, EXEC=True)

    monkeypatch.setattr("janito.config_loaders.load_privileges_from_config", full)

    # -r alone under a full-privileges config default -> read-only.
    _privileges_mod.running_privileges = None
    main_mod._setup_privileges(_privilege_args(read=True))
    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (True, False, False)

    # -w alone under a full-privileges config default -> write-only.
    _privileges_mod.running_privileges = None
    main_mod._setup_privileges(_privilege_args(write=True))
    priv = _privileges_mod.running_privileges
    assert (priv.READ, priv.WRITE, priv.EXEC) == (False, True, False)


def test_print_privileges_notice_with_no_flags(capsys, monkeypatch):
    """The full-privileges warning is printed after the version banner."""
    from janito.cli import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_banner_printed", False)
    _privileges_mod.full_privileges_warning_pending = True
    chat_mod._print_privileges_notice(_privilege_args())

    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "warning" in out.lower()
    assert _privileges_mod.full_privileges_warning_pending is False


def test_print_privileges_notice_with_read_flag(capsys, monkeypatch):
    """Explicit -r never sets the warning, so no notice is printed."""
    from janito.cli import chat as chat_mod

    monkeypatch.setattr(chat_mod, "_banner_printed", False)
    _privileges_mod.full_privileges_warning_pending = False
    chat_mod._print_privileges_notice(_privilege_args(read=True))

    out = capsys.readouterr().out
    assert out == ""


def test_print_privileges_notice_silent_with_write_exec_flags(capsys):
    """Explicit flags or config never set the warning, so no notice is printed."""
    from janito.cli import chat as chat_mod

    _privileges_mod.full_privileges_warning_pending = False
    chat_mod._print_privileges_notice(_privilege_args(write=True))
    assert capsys.readouterr().out == ""

    chat_mod._print_privileges_notice(_privilege_args(exec_=True))
    assert capsys.readouterr().out == ""

    chat_mod._print_privileges_notice(_privilege_args(read=True, write=True))
    assert capsys.readouterr().out == ""

    chat_mod._print_privileges_notice(_privilege_args(write=True, exec_=True))
    assert capsys.readouterr().out == ""

    chat_mod._print_privileges_notice(_privilege_args(read=True, write=True, exec_=True))
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_extract_tool_names_handles_both_formats():
    assert extract_tool_names([{"type": "function", "function": {"name": "ReadFile"}}]) == {"ReadFile"}
    # Responses / Anthropic top-level shape.
    assert extract_tool_names([{"name": "ReadFile", "input_schema": {}}]) == {"ReadFile"}
    assert extract_tool_names(None) == set()
    assert extract_tool_names([]) == set()


def test_privilege_restriction_reason():
    from janito.tools import privilege_restriction_reason

    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    assert privilege_restriction_reason("r") is None
    assert privilege_restriction_reason("") is None
    assert "requires" in privilege_restriction_reason("w").lower()
    assert "requires" in privilege_restriction_reason("rw").lower()
    assert "requires" in privilege_restriction_reason("rwx").lower()


def test_tool_is_allowed_by_privileges():
    from janito.tools import tool_is_allowed_by_privileges

    _privileges_mod.running_privileges = None
    assert tool_is_allowed_by_privileges("rwx") is True
    _privileges_mod.running_privileges = Privileges(READ=True, WRITE=False, EXEC=False)
    assert tool_is_allowed_by_privileges("r") is True
    assert tool_is_allowed_by_privileges("w") is False
    assert tool_is_allowed_by_privileges("rw") is False
    assert tool_is_allowed_by_privileges("") is True


if __name__ == "__main__":  # pragma: no cover
    if pytest is not None:
        raise SystemExit(pytest.main([__file__, "-v"]))
