"""Role configuration and prompt resolution across CLI and web entry points."""

import pytest

from janito.cli.parser import create_parser
from janito.config_cli import set_config_from_cli, unset_config_key_from_cli
from janito.config_loaders import DEFAULT_ROLE, load_role
from janito.config_store import get_config_value
from janito.session_setup import SessionSetup
from janito.system_prompt import SYSTEM_PROMPT_MANAGER, default_system_prompt_manager


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    from janito.config_dir import set_config_dir, set_local_config_mode
    from janito.tooling import tools_registry

    set_config_dir(tmp_path)
    set_local_config_mode(False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tools_registry, "get_skills_section", lambda: "")
    monkeypatch.setattr(tools_registry, "get_system_prompt_hints", lambda: [])


def test_role_default_configuration_and_override():
    assert load_role() == DEFAULT_ROLE
    assert set_config_from_cli("role=systems engineer") == ("role", "systems engineer")
    assert get_config_value("role") == "systems engineer"
    assert load_role() == "systems engineer"
    assert load_role("technical writer") == "technical writer"
    assert get_config_value("role") == "systems engineer"
    assert unset_config_key_from_cli("role") is True
    assert load_role() == DEFAULT_ROLE


@pytest.mark.parametrize("flag", ["-R", "--role"])
def test_role_flag_preserves_read_privilege(flag):
    args = create_parser().parse_args(["-r", flag, "systems engineer"])
    assert args.read is True
    assert args.role == "systems engineer"
    assert create_parser().parse_args([]).role is None


@pytest.mark.parametrize(
    "cli_role,configured,expected",
    [
        (None, None, DEFAULT_ROLE),
        (None, "systems engineer", "systems engineer"),
        ("technical writer", "systems engineer", "technical writer"),
        ("engineer {specialty}", None, "engineer {specialty}"),
    ],
)
def test_role_reaches_seeded_model_context(cli_role, configured, expected):
    from janito.cli.chat import _build_single_prompt_context, _resolve_system_prompt
    from janito.web.backend.config import WebServerConfig

    if configured:
        set_config_from_cli(f"role={configured}")
    args = create_parser().parse_args(["--role", cli_role] if cli_role is not None else [])
    messages, tools = _build_single_prompt_context(args)
    prompt, no_tools = _resolve_system_prompt(args)
    assert messages == [{"role": "system", "content": prompt}]
    # This line is the feature's explicit prompt contract, not incidental rendering.
    assert prompt.splitlines()[0] == f"Your role is {expected}."
    assert tools is None and no_tools is False
    config = WebServerConfig.from_args(args)
    assert config.role == cli_role
    assert config.cli_args["role"] == cli_role
    assert config.get_effective_system_prompt() == prompt


def test_roles_do_not_leak_between_sessions():
    before = list(SYSTEM_PROMPT_MANAGER.get_all_sections())
    first = SessionSetup(role="systems engineer").effective_system_prompt()
    second = SessionSetup(role="technical writer").effective_system_prompt()
    assert first != second
    assert SessionSetup().effective_system_prompt() == default_system_prompt_manager().render()
    assert list(SYSTEM_PROMPT_MANAGER.get_all_sections()) == before


@pytest.mark.parametrize("key", ["system-prompt", "system-prompt-file"])
def test_configured_prompt_is_not_interpolated(key, tmp_path):
    custom = "Custom {role} and {other} placeholders"
    value = custom
    if key == "system-prompt-file":
        file = tmp_path / "prompt.txt"
        file.write_text(custom, encoding="utf-8")
        value = str(file)
    set_config_from_cli(f"{key}={value}")
    assert SessionSetup(role="systems engineer").messages_context() == [{"role": "system", "content": custom + "\n"}]


def test_custom_and_disabled_prompts_ignore_role():
    assert SessionSetup(role="systems engineer", system_prompt="Custom {role}").messages_context() == [
        {"role": "system", "content": "Custom {role}"}
    ]
    assert SessionSetup(role="systems engineer", no_system_prompt=True).messages_context() == []


def test_show_system_prompt_uses_cli_role(monkeypatch):
    from rich.console import Console

    from janito.cli.handlers.info import handle_show_system_prompt

    tables = []
    monkeypatch.setattr(Console, "print", lambda self, table: tables.append(table))
    args = create_parser().parse_args(["-R", "systems engineer", "--show-system-prompt"])
    assert handle_show_system_prompt(args) == 0
    expected = list(default_system_prompt_manager(args.role).get_all_sections())[0]
    assert tables[0].columns[2]._cells[0] == expected.text


def test_shell_prompt_classifies_role_override_as_builtin(monkeypatch):
    from rich.console import Console

    from janito.shell.cmds.prompt import PromptCmdHandler

    tables = []
    monkeypatch.setattr(Console, "print", lambda self, table: tables.append(table))
    prompt = SessionSetup(role="systems engineer").effective_system_prompt()
    shell = type("Shell", (), {"role": "systems engineer", "get_system_prompt": lambda self: prompt})()
    assert PromptCmdHandler().handle(shell, "/prompt") is True
    sections = list(default_system_prompt_manager(shell.role).get_all_sections())
    assert tables[0].columns[0]._cells[0] == sections[0].label
