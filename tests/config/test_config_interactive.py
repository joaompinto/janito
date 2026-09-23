"""Tests for the interactive ``--config`` provider selection (questionary)."""

from unittest.mock import Mock, patch

import pytest

from janito.cli.handlers.config import _prompt_max_input_tokens, _prompt_provider
from janito.providers.models import ModelConfig


class _FakeQuestionary:
    """A stand-in for ``questionary.select(...).ask()``."""

    def __init__(self, result):
        self._result = result
        self.select_kwargs = None

    def select(self, *args, **kwargs):
        self.select_kwargs = (args, kwargs)
        return self

    def ask(self):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


def _select_kwargs(fake):
    """Return the kwargs passed to questionary.select by _prompt_provider."""
    return fake.select_kwargs[1]


def test_prompt_provider_uses_questionary_select(monkeypatch, capsys):
    fake = _FakeQuestionary("deepseek")
    monkeypatch.setattr("janito.cli.handlers.config.questionary", fake)

    result = _prompt_provider(existing_provider=None)

    assert result == "deepseek"
    args, kwargs = fake.select_kwargs
    assert args[0] == "Select a provider"
    from janito.providers.validation import list_supported_providers

    for name in list_supported_providers():
        assert name in kwargs["choices"]
    assert "custom" in kwargs["choices"]
    # No pre-selection when there is no existing provider.
    assert kwargs["default"] is None
    out = capsys.readouterr().out
    assert out.strip() != ""


def test_prompt_provider_preselects_existing_provider(monkeypatch):
    fake = _FakeQuestionary("openai")
    monkeypatch.setattr("janito.cli.handlers.config.questionary", fake)

    result = _prompt_provider(existing_provider="openai")

    assert result == "openai"
    kwargs = _select_kwargs(fake)
    assert kwargs["default"] == "openai"


def test_prompt_provider_unknown_existing_provider_has_no_default(monkeypatch):
    fake = _FakeQuestionary("openai")
    monkeypatch.setattr("janito.cli.handlers.config.questionary", fake)

    _prompt_provider(existing_provider="not-a-provider")

    kwargs = _select_kwargs(fake)
    assert kwargs["default"] is None


def test_prompt_provider_none_selection_returns_none(monkeypatch, capsys):
    fake = _FakeQuestionary(None)
    monkeypatch.setattr("janito.cli.handlers.config.questionary", fake)

    result = _prompt_provider(existing_provider=None)

    assert result is None
    err = capsys.readouterr().err
    assert "error" in err.lower() or "required" in err.lower()


def test_prompt_provider_keyboard_interrupt_exits(capsys):
    fake = _FakeQuestionary(KeyboardInterrupt())
    with (
        patch("janito.cli.handlers.config.questionary", fake),
        pytest.raises(SystemExit) as exc_info,
    ):
        _prompt_provider(existing_provider=None)

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() != ""


# ---- max input tokens prompt -------------------------------------------


def test_prompt_max_input_tokens_uses_existing_value_as_default(monkeypatch, capsys):
    # Empty input accepts the default (the already-configured value).
    monkeypatch.setattr(
        "janito.cli.handlers.config._prompt_with_default",
        lambda prompt, default=None, is_password=False: default,
    )
    result = _prompt_max_input_tokens("openai", "gpt-6-luna", 256000)
    assert result == 256000
    out = capsys.readouterr().out
    assert out.strip() != ""
    assert "256000" in out


def test_prompt_max_input_tokens_defaults_to_provider_builtin(monkeypatch):
    monkeypatch.setattr(
        "janito.cli.handlers.config._prompt_with_default",
        lambda prompt, default=None, is_password=False: default,
    )
    monkeypatch.setattr(
        "janito.cli.handlers.config.get_provider",
        lambda provider: Mock(model_config=lambda model=None: ModelConfig({"max_input_tokens": 200000})),
    )
    result = _prompt_max_input_tokens("openai", "gpt-6-luna", None)
    assert result == 200000


def test_prompt_max_input_tokens_falls_back_to_128k(monkeypatch):
    monkeypatch.setattr(
        "janito.cli.handlers.config._prompt_with_default",
        lambda prompt, default=None, is_password=False: default,
    )
    # No existing value and no provider built-in (e.g. 'custom').
    monkeypatch.setattr(
        "janito.cli.handlers.config.get_provider",
        lambda provider: Mock(model_config=lambda model=None: ModelConfig({})),
    )
    result = _prompt_max_input_tokens("custom", None, None)
    assert result == 128000


def test_prompt_max_input_tokens_parses_input(monkeypatch, capsys):
    monkeypatch.setattr(
        "janito.cli.handlers.config._prompt_with_default",
        lambda prompt, default=None, is_password=False: "1048576",
    )
    result = _prompt_max_input_tokens("openai", "gpt-6-luna", None)
    assert result == 1048576
    assert "1048576" in capsys.readouterr().out


def test_prompt_max_input_tokens_rejects_non_numeric(monkeypatch, capsys):
    monkeypatch.setattr(
        "janito.cli.handlers.config._prompt_with_default",
        lambda prompt, default=None, is_password=False: "many",
    )
    result = _prompt_max_input_tokens("openai", "gpt-6-luna", None)
    assert result is None
    err = capsys.readouterr().err
    assert err.strip() != ""
