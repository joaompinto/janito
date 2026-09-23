"""Shared pytest fixtures and helpers for the test suite."""

from __future__ import annotations

from typing import Any

import pytest

from janito.llm_adapters.observer import NullObserver
from janito.llm_clients.api_config import APIConfig
from janito.ui.config import UIConfig


@pytest.fixture(autouse=True)
def _reset_browser_prompts_flag():
    """Isolate the mid-turn question surface flag between tests (issue #125).

    ``main(--web)`` enables it globally; without a reset later AskUser gate
    tests see a stale True.
    """
    import janito.tooling.prompting as prompting

    prompting._browser_prompts_enabled = False
    yield
    prompting._browser_prompts_enabled = False


@pytest.fixture(autouse=True)
def _isolate_process_global_state():
    """Snapshot/restore process-global mutable state around each test.

    Multiprocess runners (``pytest -n auto``) execute many test files
    sequentially inside each worker process, so a module global mutated
    by one file (session ``running_privileges``, the tools registry,
    the config-dir override) leaks into later files on the same worker
    and makes failures depend on scheduling.  Restoring the pre-test
    values here keeps every test order-independent under both serial
    and parallel runs.  In-place restore (``clear``/``update``) preserves
    object identity so it composes with ``monkeypatch`` teardowns.
    """
    import janito.config_dir as config_dir_mod
    import janito.privileges as privileges_mod
    import janito.tooling.tools_registry as tools_registry

    saved_config_dir = config_dir_mod.get_base_config_dir()
    saved_local_mode = config_dir_mod.is_local_config_mode()
    saved_privileges = privileges_mod.running_privileges
    saved_warning = privileges_mod.full_privileges_warning_pending
    saved_tools = dict(tools_registry.AVAILABLE_TOOLS)
    saved_initialized = tools_registry._tools_initialized
    saved_loaded = set(tools_registry._loaded_toolsets)
    saved_disabled = set(tools_registry._disabled_toolsets)
    saved_skills = tools_registry._skills_enabled
    saved_loading = tools_registry._tools_loading_enabled
    yield
    config_dir_mod.set_config_dir(saved_config_dir)
    config_dir_mod.set_local_config_mode(saved_local_mode)
    privileges_mod.running_privileges = saved_privileges
    privileges_mod.full_privileges_warning_pending = saved_warning
    tools_registry.AVAILABLE_TOOLS.clear()
    tools_registry.AVAILABLE_TOOLS.update(saved_tools)
    tools_registry._tools_initialized = saved_initialized
    tools_registry._loaded_toolsets.clear()
    tools_registry._loaded_toolsets.update(saved_loaded)
    tools_registry._disabled_toolsets.clear()
    tools_registry._disabled_toolsets.update(saved_disabled)
    tools_registry._skills_enabled = saved_skills
    tools_registry._tools_loading_enabled = saved_loading


def make_config(
    *,
    provider: str = "openai",
    api_type: str = "Completions",
    model: str = "gpt-6-luna",
    base_url: str | None = None,
    api_key: str = "sk-test",
    max_output_tokens: int = 100_000,
    max_input_tokens: int | None = None,
    reasoning_effort: str | None = None,
    thinking: bool = False,
    preserve_thinking: Any = None,
    use_mcp: bool = False,
) -> APIConfig:
    """Build a minimal :class:`APIConfig` for tests that construct clients
    directly (issue #70).

    ``run_turn`` / ``Client`` now take a resolved, immutable
    :class:`~janito.llm_clients.api_config.APIConfig` instead of resolving
    the config/auth stores at call time, so tests that previously passed
    ``cli_model``/``cli_provider``/``use_mcp``/``stream_runner``/``observer``
    to the client constructor build a config with this helper instead.  The
    UI-side stream runner / turn observer go in
    :func:`make_ui_config`.
    """
    return APIConfig(
        provider=provider,
        api_type=api_type,
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_output_tokens=max_output_tokens,
        max_input_tokens=max_input_tokens,
        reasoning_effort=reasoning_effort,
        thinking=thinking,
        preserve_thinking=preserve_thinking,
        use_mcp=use_mcp,
    )


def make_ui_config(*, stream_runner=None, observer=None) -> UIConfig:
    """Build a minimal :class:`~janito.ui.config.UIConfig` for tests.

    The per-round stream runner and the turn observer are injected through
    the UI config (no longer constructor params / module globals to
    monkeypatch); ``None`` values fall back to the headless defaults.
    """
    return UIConfig(
        stream_runner=stream_runner,
        observer=observer or NullObserver(),
    )


def assert_command_registered(name: str) -> None:
    """Assert a shell command is registered (see docs/development/testing.md)."""
    from janito.shell.cmds import get_registered_commands

    names = [cmd.name for cmd in get_registered_commands()]
    assert name in names


def assert_command_matching(handler, name: str) -> None:
    """Assert standard command matching: exact, case-insensitive,
    whitespace-tolerant, and non-matching input rejected."""
    assert handler.name == name

    class _Shell:
        pass

    shell = _Shell()
    assert handler.handle(shell, name) is True
    assert handler.handle(shell, name.upper()) is True
    assert handler.handle(shell, f"  {name}  ") is True
    assert handler.handle(shell, "/tools" if name != "/tools" else "/help") is False
    assert handler.handle(shell, "hello") is False
