"""Tests for the shell /model command handler (behavior over rendering).

A successful ``/model <name>`` switch also persists the selected model to the
project-local config (``./.janito/config.json``, ``providers.<provider>.model``);
the global ``~/.janito/config.json`` is never touched from the shell.
"""

import json

import janito.config_dir as config_dir_mod
from janito.config_store import get_config_value
from janito.shell import InteractiveShell
from janito.shell.cmds.model import available_model_names
from janito.shell.cmds.registry import get_registered_commands
from tests.conftest import assert_command_registered


def _use_temp_config(monkeypatch, tmp_path):
    """Point the base config dir at a tmp dir and chdir into a project dir."""
    monkeypatch.setattr(config_dir_mod, "_config_dir", tmp_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(project_dir)
    return tmp_path / ".janito" / "config.json"


def _local_config_path(tmp_path):
    return tmp_path / "project" / ".janito" / "config.json"


def _shell(provider=None):
    return InteractiveShell(model="test-model", no_history=True, provider=provider)


def _model_handler():
    return next(c for c in get_registered_commands() if c.name == "/model")


def test_model_registered():
    assert_command_registered("/model")


def test_model_matching(capsys):
    handler = _model_handler()
    assert handler.name == "/model"
    shell = _shell()
    assert handler.handle(shell, "/model") is True
    assert handler.handle(shell, "/MODEL") is True
    assert handler.handle(shell, "/models") is False
    assert handler.handle(shell, "hello") is False
    capsys.readouterr()


def test_no_argument_smoke(monkeypatch, tmp_path, capsys):
    """One smoke: lists current model, non-empty + one stable header."""
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="openai")
    assert _model_handler().handle(shell, "/model") is True
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "Current provider:" in out


def test_switch_model_updates_state_and_persists_locally(monkeypatch, tmp_path, capsys):
    global_path = _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="deepseek")
    assert _model_handler().handle(shell, "/model deepseek-flash") is True
    capsys.readouterr()
    assert get_config_value("deepseek.model") == "deepseek-flash"
    assert shell.model == "deepseek-flash"
    assert shell.model_override == "deepseek-flash"
    local_config = json.loads(_local_config_path(tmp_path).read_text())
    assert local_config == {"providers": {"deepseek": {"model": "deepseek-flash"}}}
    assert not global_path.exists()


def test_persistence_failure_does_not_break_switch(monkeypatch, tmp_path, capsys):
    """A failed local write keeps the runtime switch working (best-effort)."""
    _use_temp_config(monkeypatch, tmp_path)

    import janito.config_store as cs

    monkeypatch.setattr(cs, "set_local_config_value", lambda key, value: False)
    shell = _shell(provider="deepseek")
    assert _model_handler().handle(shell, "/model deepseek-flash") is True
    capsys.readouterr()
    assert shell.model == "deepseek-flash"
    assert not _local_config_path(tmp_path).exists()


def test_switch_model_canonicalizes(monkeypatch, tmp_path, capsys):
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="deepseek")
    assert _model_handler().handle(shell, "/model DEEPSEEK-FLASH") is True
    capsys.readouterr()
    assert shell.model == "deepseek-flash"


def test_switch_unknown_model_error_kind(monkeypatch, tmp_path, capsys):
    """Error path: kind only + no side effects."""
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="deepseek")
    assert _model_handler().handle(shell, "/model deepseek-v4-ultra") is True
    out = capsys.readouterr().out
    assert "error" in out.lower()
    assert shell.model == "test-model"
    assert get_config_value("deepseek.model") is None
    assert not _local_config_path(tmp_path).exists()


def test_switch_model_clears_history(monkeypatch, tmp_path, capsys):
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="deepseek")
    shell.initialize_history(system_prompt="sys")
    shell.messages_history.append({"role": "user", "content": "hello"})
    shell.messages_history.append({"role": "assistant", "content": "hi"})
    assert _model_handler().handle(shell, "/model deepseek-v4-pro") is True
    capsys.readouterr()
    assert shell.messages_history == [{"role": "system", "content": "sys"}]


def test_switch_same_model_keeps_history(monkeypatch, tmp_path, capsys):
    _use_temp_config(monkeypatch, tmp_path)
    shell = _shell(provider="deepseek")
    shell.initialize_history(system_prompt="sys")
    shell.messages_history.append({"role": "user", "content": "hello"})
    shell.messages_history.append({"role": "assistant", "content": "hi"})
    shell.model = "deepseek-flash"
    assert _model_handler().handle(shell, "/model deepseek-flash") is True
    capsys.readouterr()
    assert len(shell.messages_history) == 3


def test_available_model_names_from_registry(monkeypatch, tmp_path):
    from janito.config_store import set_config_value

    _use_temp_config(monkeypatch, tmp_path)
    set_config_value("openai.models.gpt-future.max-output-tokens", 1000)
    names = list(available_model_names("openai"))
    assert "gpt-6-luna" in names
    assert "gpt-future" in names
