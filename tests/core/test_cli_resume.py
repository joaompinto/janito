"""Tests for the CLI resume feature plumbing (-C/--continue)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import janito.__main__ as _main
import janito.shell.persistence as persistence
from janito.cli.chat import (
    _normalize_identity,
    _print_resume_recap,
    _resolve_resume,
    _resume_identity_matches,
)


def _args(**kw):
    ns = argparse.Namespace()
    defaults = dict(
        continue_session=True,
        web=False,
        no_history=False,
        provider=None,
        model=None,
        api_type=None,
        effort=None,
        thinking=False,
    )
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(ns, k, v)
    return ns


def _snapshot(**kw):
    state = {
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "api_type": "Responses",
        "thinking": True,
        "effort": "high",
    }
    state.update(kw)
    return state


def test_normalize_identity():
    assert _normalize_identity(None) is None
    assert _normalize_identity("") is None
    assert _normalize_identity("OpenAI") == "openai"


def test_resume_identity_matches_case_insensitively():
    assert _resume_identity_matches(_snapshot(), "OpenAI", "GPT-5.6-LUNA", "responses") is True


def test_resume_identity_matches_requires_api_type():
    state = _snapshot()
    assert _resume_identity_matches(state, "openai", "gpt-5.6-luna", None) is False
    assert _resume_identity_matches(state, "openai", "gpt-5.6-luna", "Completions") is False


def test_resume_identity_matches_false_on_provider_or_model_mismatch():
    state = _snapshot()
    assert _resume_identity_matches(state, "anthropic", "gpt-5.6-luna", "Responses") is False
    assert _resume_identity_matches(state, "openai", "gpt-4o", "Responses") is False


def test_resume_identity_matches_when_both_none_api_types():
    assert _resume_identity_matches({"provider": "openai", "model": "m", "api_type": None}, "openai", "m", None)


def test_apply_resume_noop_without_snapshot(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: None)
    args = _args()
    _main._apply_resume_session(args)
    assert args.provider is None
    assert args.model is None
    assert args.api_type is None


def test_apply_resume_backfills_identity(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: _snapshot())
    args = _args()
    _main._apply_resume_session(args)
    assert args.provider == "openai"
    assert args.model == "gpt-5.6-luna"
    assert args.api_type == "Responses"
    assert args.thinking is True
    assert args.effort == "high"


def test_apply_resume_explicit_flags_win(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: _snapshot())
    args = _args(
        provider="anthropic",
        model="claude-sonnet",
        api_type="Anthropic",
        effort="low",
        thinking=True,
    )
    _main._apply_resume_session(args)
    assert args.provider == "anthropic"
    assert args.model == "claude-sonnet"
    assert args.api_type == "Anthropic"
    assert args.effort == "low"
    assert args.thinking is True


def test_apply_resume_noop_under_no_history(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: _snapshot())
    args = _args(no_history=True)
    _main._apply_resume_session(args)
    assert args.provider is None


def test_apply_resume_noop_in_web_mode(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: _snapshot())
    args = _args(web=True)
    _main._apply_resume_session(args)
    assert args.provider is None


def test_apply_resume_noop_without_continue_flag(monkeypatch):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: _snapshot())
    args = _args(continue_session=False)
    _main._apply_resume_session(args)
    assert args.provider is None


def test_resolve_resume_ignored_without_continue_flag():
    args = _args(continue_session=False, no_history=False)
    state, persist = _resolve_resume(args, "openai", "gpt-5.6-luna", "Responses")
    assert state is None
    assert persist is True


def test_resolve_resume_disabled_under_no_history(capsys):
    args = _args(continue_session=True, no_history=True)
    state, persist = _resolve_resume(args, "openai", "gpt-5.6-luna", "Responses")
    assert state is None
    assert persist is False
    assert capsys.readouterr().out.strip() != ""  # smoke only


def test_resolve_resume_no_snapshot_starts_fresh(monkeypatch, capsys):
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: None)
    args = _args(continue_session=True, no_history=False)
    state, persist = _resolve_resume(args, "openai", "gpt-5.6-luna", "Responses")
    assert state is None
    assert persist is True
    assert capsys.readouterr().out.strip() != ""  # smoke only


def test_resolve_resume_restores_on_identity_match(monkeypatch):
    snapshot = _snapshot(api_type="Responses")
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: snapshot)
    args = _args(continue_session=True, no_history=False)
    state, persist = _resolve_resume(args, "openai", "gpt-5.6-luna", "Responses")
    assert state is snapshot
    assert persist is True


def test_resolve_resume_mismatch_starts_fresh_without_persisting(monkeypatch, capsys):
    snapshot = _snapshot(api_type="Responses")
    monkeypatch.setattr(persistence, "load_conversation_state", lambda: snapshot)
    args = _args(continue_session=True, no_history=False)
    state, persist = _resolve_resume(args, "openai", "gpt-5.6-luna", "Completions")
    assert state is None
    assert persist is False
    assert capsys.readouterr().out.strip() != ""  # smoke only


def _chat_shell(**kwargs):
    from janito.shell import InteractiveShell

    kwargs.setdefault("model", "gpt-5.6-luna")
    kwargs.setdefault("no_history", True)
    return InteractiveShell(**kwargs)


def test_print_resume_recap_shows_last_messages(capsys):
    shell = _chat_shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "m1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "m2"},
        {"role": "assistant", "content": "a2"},
    ]
    _print_resume_recap(shell)
    out = capsys.readouterr().out
    assert out.strip() != ""
    # Fixture content + numeric bound: tail shown, system prompt excluded.
    assert "a2" in out
    assert "SYS-PROMPT" not in out
    assert len([m for m in shell.messages_history if m["role"] in ("user", "assistant")]) == 4


def test_print_resume_recap_limits_to_five(capsys):
    shell = _chat_shell()
    messages = [{"role": "system", "content": "SYS-PROMPT"}]
    for i in range(1, 6):
        messages.append({"role": "user", "content": f"m{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    shell.messages_history = messages
    _print_resume_recap(shell)
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "a5" in out
    assert "m1" not in out
    assert "a2" not in out


def test_print_resume_recap_noop_without_dialogue(capsys):
    shell = _chat_shell()
    shell.messages_history = [{"role": "system", "content": "SYS-PROMPT"}]
    _print_resume_recap(shell)
    assert capsys.readouterr().out == ""


def test_print_resume_recap_hides_tool_noise(capsys):
    shell = _chat_shell()
    shell.messages_history = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "what is the weather?"},
        {"role": "function", "content": '{"tool": "GetWeather"}'},
        {"role": "function", "content": '{"temp": 22}'},
        {"role": "assistant", "content": "It is 22C."},
    ]
    _print_resume_recap(shell)
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "what is the weather?" in out
    assert "It is 22C." in out
    assert "GetWeather" not in out


def test_print_resume_recap_anchors_on_last_user_prompt(capsys):
    shell = _chat_shell()
    messages = [
        {"role": "system", "content": "SYS-PROMPT"},
        {"role": "user", "content": "last question"},
    ]
    for i in range(1, 10):
        messages.append({"role": "assistant", "content": f"reply {i}"})
    shell.messages_history = messages
    _print_resume_recap(shell)
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "last question" in out
    assert "reply 9" in out
    assert "reply 1" not in out
    assert out.count("Assistant:") <= 4  # numeric bound (Rule 6)
