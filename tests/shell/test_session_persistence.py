"""
Tests for CLI interactive-session persistence and resume (-C/--continue).

The interactive shell mirrors its conversation to ``./.janito/session.json``
(a new module :mod:`janito.shell.persistence`), and ``InteractiveShell`` can
snapshot / restore that state so ``janito -C`` resumes the previous
conversation in a working directory.  These tests cover the store's
save/load/clear behaviour and the shell's per-API-mode snapshot/restore
round trip (Completions-style ``messages_history``, stateless Responses
``conversation_items`` and server-side Responses ``mirrored_history`` +
server chain), plus the ``persist_history`` gate that keeps bare/test shells
from writing to disk.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from janito.shell import InteractiveShell
from janito.shell.conversation import effective_rows, recent_conversation_rows
from janito.shell.persistence import (
    STATE_VERSION,
    clear_conversation_state,
    get_state_path,
    load_conversation_state,
    make_state,
    save_conversation_state,
)


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    """Run every test from an empty temp dir so no test touches the repo."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _shell(**kwargs):
    """Build a fresh bare shell for testing (never persists to disk)."""
    kwargs.setdefault("model", "gpt-5.6-luna")
    kwargs.setdefault("no_history", True)
    return InteractiveShell(**kwargs)


def _write_state(**overrides):
    """Persist a minimal valid snapshot and return it."""
    state = make_state(
        provider="openai",
        model="gpt-5.6-luna",
        model_override=None,
        api_type="Completions",
        thinking=False,
        effort=None,
        system_prompt="sys",
        messages_history=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        history_turns=[1],
        previous_response_id=None,
        conversation_items=None,
        conversation_turn=0,
        response_chain=[],
        response_turn=0,
        mirrored_history=[],
        mirrored_turn=0,
    )
    state.update(overrides)
    save_conversation_state(state)
    return state


# ---------------------------------------------------------------------------
# janito.shell.persistence: file store
# ---------------------------------------------------------------------------


def test_state_path_is_cwd_scoped(tmp_path):
    assert get_state_path() == tmp_path / ".janito" / "session.json"


def test_save_load_roundtrip():
    state = _write_state()
    loaded = load_conversation_state()
    assert loaded is not None
    assert loaded["version"] == STATE_VERSION
    assert loaded["messages_history"] == state["messages_history"]
    assert loaded["history_turns"] == [1]
    assert loaded["provider"] == "openai"
    assert loaded["api_type"] == "Completions"
    assert loaded["cwd"]  # records the working directory


def test_load_missing_returns_none():
    assert load_conversation_state() is None


def test_load_corrupt_returns_none():
    get_state_path().parent.mkdir(parents=True, exist_ok=True)
    get_state_path().write_text("{not json")
    assert load_conversation_state() is None


def test_load_without_messages_returns_none():
    get_state_path().parent.mkdir(parents=True, exist_ok=True)
    get_state_path().write_text(json.dumps({"version": 1, "foo": "bar"}))
    assert load_conversation_state() is None


def test_clear_removes_file():
    _write_state()
    assert get_state_path().exists()
    assert clear_conversation_state() is True
    assert not get_state_path().exists()
    assert clear_conversation_state() is False


def test_save_never_raises_when_path_blocked(tmp_path, monkeypatch):
    # Point the store at a path whose parent cannot be created (a file sits in
    # the way); persistence must degrade to a logged no-op instead of raising.
    blocker = tmp_path / ".janito"
    blocker.write_text("a file, so .janito cannot be a directory")
    monkeypatch.setattr("janito.shell.persistence.get_state_path", lambda: blocker / "session.json")
    # No exception raised is the assertion.
    save_conversation_state(
        make_state(
            provider="openai",
            model="m",
            model_override=None,
            api_type="Completions",
            thinking=False,
            effort=None,
            system_prompt=None,
            messages_history=[],
            history_turns=[],
            previous_response_id=None,
            conversation_items=None,
            conversation_turn=0,
            response_chain=[],
            response_turn=0,
            mirrored_history=[],
            mirrored_turn=0,
        )
    )


# ---------------------------------------------------------------------------
# InteractiveShell.conversation_snapshot / restore_conversation
# ---------------------------------------------------------------------------


def test_snapshot_restore_completions_roundtrip():
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    shell.messages_history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "ok"},
    ]
    shell.history_turns = [1, 3]

    snapshot = shell.conversation_snapshot()
    restored = _shell()
    assert restored.restore_conversation(snapshot) is True
    assert restored.messages_history == shell.messages_history
    assert restored.history_turns == [1, 3]
    assert restored.get_system_prompt() == "sys"
    assert effective_rows(restored) == effective_rows(shell)


def test_snapshot_restore_stateless_responses_roundtrip():
    shell = _shell(api_type="Responses")
    shell.initialize_history(system_prompt="sys")
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.conversation_items = [
        {
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": "sys"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "list files"}],
        },
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "ListFiles",
            "arguments": '{"directory": "."}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"files": ["a.py"]}',
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Here are the files."}],
        },
    ]
    shell.history_turns = [5]

    restored = _shell(api_type="Responses")
    assert restored.restore_conversation(shell.conversation_snapshot()) is True
    assert restored.messages_history == shell.messages_history
    assert restored.conversation_items == shell.conversation_items
    assert effective_rows(restored) == effective_rows(shell)


def test_snapshot_restore_server_side_responses_roundtrip():
    shell = _shell(api_type="Responses")
    shell.initialize_history(system_prompt="sys")
    shell.messages_history = [{"role": "system", "content": "sys"}]
    shell.previous_response_id = "resp_2"
    shell.response_chain = ["resp_1", "resp_2"]
    shell.response_turn = 1
    shell.mirrored_history = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "q"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "a"}],
        },
    ]
    shell.mirrored_turn = 1
    shell.history_turns = [1]

    restored = _shell(api_type="Responses")
    assert restored.restore_conversation(shell.conversation_snapshot()) is True
    assert restored.previous_response_id == "resp_2"
    assert restored.response_chain == ["resp_1", "resp_2"]
    assert restored.response_turn == 1
    assert restored.mirrored_history == shell.mirrored_history
    assert restored.mirrored_turn == 1
    assert effective_rows(restored) == effective_rows(shell)


def test_snapshot_restore_is_decoupled_from_live_state():
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    shell.messages_history = [{"role": "user", "content": "hello"}]
    snapshot = shell.conversation_snapshot()
    # Mutating the live shell afterwards must not affect the restored copy.
    shell.messages_history.append({"role": "assistant", "content": "hi"})
    restored = _shell()
    restored.restore_conversation(snapshot)
    assert restored.messages_history == [{"role": "user", "content": "hello"}]


def test_snapshot_records_identity_and_toggles():
    shell = _shell(
        provider="openai",
        api_type="Responses",
        effort="high",
        thinking=True,
    )
    shell.initialize_history(system_prompt="sys")
    snapshot = shell.conversation_snapshot()
    assert snapshot["provider"] == "openai"
    assert snapshot["model"] == "gpt-5.6-luna"
    assert snapshot["api_type"] == "Responses"
    assert snapshot["effort"] == "high"
    assert snapshot["thinking"] is True
    assert snapshot["system_prompt"] == "sys"


def test_restore_rejects_invalid_state():
    restored = _shell()
    assert restored.restore_conversation(None) is False
    assert restored.restore_conversation({"foo": 1}) is False
    assert restored.restore_conversation("nope") is False
    # Shell untouched after a failed restore.
    assert restored.messages_history == []
    assert restored.get_system_prompt() is None


def test_snapshot_uses_explicit_api_type_without_resolving_provider():
    # With no --api-type and no provider the snapshot must not blow up trying
    # to resolve the API type from the config store.
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    snapshot = shell.conversation_snapshot()
    assert snapshot["api_type"] is None
    assert snapshot["messages_history"] == [{"role": "system", "content": "sys"}]


# ---------------------------------------------------------------------------
# persist_history gate and run()-loop auto-save
# ---------------------------------------------------------------------------


def test_save_snapshot_noop_when_persistence_disabled():
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    shell._save_snapshot()
    assert not get_state_path().exists()


def test_save_snapshot_writes_when_enabled():
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    shell.persist_history = True
    shell._save_snapshot()
    assert get_state_path().exists()
    data = json.loads(get_state_path().read_text())
    assert data["messages_history"] == [{"role": "system", "content": "sys"}]


def test_run_saves_conversation_after_turn_and_on_exit(monkeypatch):
    shell = _shell()
    shell.initialize_history(system_prompt="sys")
    shell.persist_history = True
    inputs = iter(["hello", None])

    def fake_prompt():
        return next(inputs)

    def fake_turn(user_input):
        shell.messages_history.append({"role": "user", "content": user_input})
        shell.messages_history.append({"role": "assistant", "content": "hi back"})
        shell.history_turns.append(len(shell.messages_history) - 2)

    monkeypatch.setattr(shell, "_get_user_input", fake_prompt)
    monkeypatch.setattr(shell, "_run_turn", fake_turn)
    # run() assigns shell.turn_func itself from its argument; the fake
    # _run_turn never calls it.
    shell.run(
        turn_func=lambda *a, **k: None,
        verbose=False,
        no_tools=False,
        thinking=False,
    )
    data = json.loads(get_state_path().read_text())
    assert data["messages_history"][-2:] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi back"},
    ]
    assert data["history_turns"] == [1]


def test_run_does_not_save_when_persistence_disabled(monkeypatch):
    shell = _shell()  # persist_history defaults to False
    shell.initialize_history(system_prompt="sys")
    monkeypatch.setattr(shell, "_get_user_input", lambda: None)
    shell.run(
        turn_func=lambda *a, **k: None,
        verbose=False,
        no_tools=False,
        thinking=False,
    )
    assert not get_state_path().exists()


# ---------------------------------------------------------------------------
# recent_conversation_rows (resume recap tail)
# ---------------------------------------------------------------------------


def test_recent_rows_returns_last_five_skipping_tool_rows():
    shell = _shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "m1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "m2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "m3"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "m4"},
        {"role": "assistant", "content": "a4"},
    ]
    assert recent_conversation_rows(shell) == [
        ("assistant", "a2"),
        ("user", "m3"),
        ("assistant", "a3"),
        ("user", "m4"),
        ("assistant", "a4"),
    ]


def test_recent_rows_returns_all_when_fewer_than_limit():
    shell = _shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "only"},
    ]
    assert recent_conversation_rows(shell) == [("user", "only")]


def test_recent_rows_empty_with_only_system_prompt():
    shell = _shell()
    shell.messages_history = [{"role": "system", "content": "SYS-PROMPT"}]
    assert recent_conversation_rows(shell) == []


def test_recent_rows_filters_out_tool_and_reasoning_rows():
    shell = _shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "m1"},
        {"role": "function", "content": "tool-result"},
        {"role": "assistant", "content": "done"},
    ]
    # Only user/assistant rows are kept; tool rows are hidden even when they
    # are among the most recent.
    assert recent_conversation_rows(shell, limit=1) == [("assistant", "done")]
    assert recent_conversation_rows(shell) == [
        ("user", "m1"),
        ("assistant", "done"),
    ]


def test_recent_rows_anchors_on_last_user_when_reply_run_exceeds_limit():
    shell = _shell()
    # A single user question answered by a long run of assistant messages
    # (tool rounds): the plain tail would be assistant-only.
    messages = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "q"},
    ]
    for i in range(1, 10):
        messages.append({"role": "assistant", "content": f"a{i}"})
    shell.messages_history = messages
    # The recap is re-anchored on the last user row: the question first,
    # then the most recent replies (capped at `limit` rows total).
    rows = recent_conversation_rows(shell)
    assert rows[0] == ("user", "q")
    assert len(rows) == 5
    assert rows[-1] == ("assistant", "a9")
    assert all(role in ("user", "assistant") for role, _ in rows)


def test_recent_rows_no_user_rows_returns_tail():
    shell = _shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "assistant", "content": "a1"},
        {"role": "assistant", "content": "a2"},
    ]
    assert recent_conversation_rows(shell) == [
        ("assistant", "a1"),
        ("assistant", "a2"),
    ]


def test_recent_rows_reads_mirrored_history_for_server_side_responses():
    shell = _shell(api_type="Responses")
    shell.messages_history = [{"role": "system", "content": "SYS-PROMPT"}]
    shell.mirrored_history = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "q1"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "a1"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "q2"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "a2"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "q3"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "a3"}],
        },
    ]
    assert recent_conversation_rows(shell) == [
        ("assistant", "a1"),
        ("user", "q2"),
        ("assistant", "a2"),
        ("user", "q3"),
        ("assistant", "a3"),
    ]
