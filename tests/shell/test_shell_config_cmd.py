"""Tests for the shell /status command handler (behavior over rendering)."""

from unittest.mock import patch

from janito.providers.registry import get_provider as _real_get_provider
from tests.conftest import assert_command_registered

_MISSING = object()


def _fake_provider(
    name,
    *,
    default_model=_MISSING,
    default_max_tokens=_MISSING,
    stateless_mode=_MISSING,
):
    real = _real_get_provider(name)

    def _pick(override, fallback):
        return override if override is not _MISSING else fallback

    class _P:
        def default_model(self):
            return _pick(default_model, real.default_model() if real is not None else None)

        def model_config(self, model=None):
            from janito.providers.models import ModelConfig

            base = real.model_config(model).data if real is not None else {}
            data = dict(base)
            if default_max_tokens is not _MISSING:
                data["max_output_tokens"] = default_max_tokens
            if stateless_mode is not _MISSING:
                data["stateless_mode"] = stateless_mode
            return ModelConfig(data)

        def endpoint_for(self, api_type=None):
            return real.endpoint_for(api_type) if real is not None else None

        def gemini_flavor(self):
            return real.gemini_flavor() if real is not None else False

    return _P()


def _run(
    capsys,
    last,
    provider=None,
    configured_max_tokens=None,
    default_max_tokens=128000,
    thinking=False,
    api_type="Responses",
    stateless_mode=False,
    cli_api_type=None,
    model=None,
    configured_model=None,
    default_model="gpt-6-luna",
):
    from janito.shell.cmds.status import _print_config_info

    def _fake_resolve(resolved_cli_api_type, resolved_provider, resolve_model):
        last["cli_api_type"] = resolved_cli_api_type
        last["provider"] = resolved_provider
        last["model"] = resolve_model
        return api_type

    with (
        patch("janito.shell.cmds.status.get_active_provider", return_value="openai"),
        patch(
            "janito.shell.cmds.status.get_api_key",
            return_value="sk-test-key-1234567890",
        ),
        patch("janito.shell.cmds.status.get_masked_api_key", return_value="sk-***7890"),
        patch(
            "janito.shell.cmds.status.load_model_from_config",
            return_value=configured_model,
        ),
        patch(
            "janito.shell.cmds.status.get_provider",
            return_value=_fake_provider(
                provider,
                default_model=default_model,
                default_max_tokens=default_max_tokens,
                stateless_mode=stateless_mode,
            ),
        ),
        patch(
            "janito.shell.cmds.status.load_max_output_tokens",
            return_value=configured_max_tokens,
        ),
        patch("janito.shell.cmds.status.load_endpoint_from_config", return_value=None),
        patch("janito.shell.cmds.status.resolve_api_type", side_effect=_fake_resolve),
    ):
        _print_config_info(provider, thinking, cli_api_type, model)
    return capsys.readouterr().out


def test_status_registered():
    assert_command_registered("/status")


def test_status_matching(capsys):
    from janito.shell.cmds.status import StatusCmdHandler

    handler = StatusCmdHandler()
    assert handler.name == "/status"
    assert handler.handle(object(), "/status") is True
    assert handler.handle(object(), "/STATUS") is True
    assert handler.handle(object(), "/other") is False
    assert handler.handle(object(), "hello") is False
    capsys.readouterr()


def test_status_smoke(capsys):
    """One smoke assert: handler runs and renders non-empty output."""
    last = {}
    out = _run(capsys, last, provider="openai")
    assert out.strip() != ""
    assert "Provider" in out  # single stable header


def test_cli_api_type_forwarded(capsys):
    last = {}
    _run(capsys, last, provider="google", cli_api_type="Gemini", api_type="Gemini")
    assert last["cli_api_type"] == "Gemini"
    assert last["provider"] == "google"


def test_no_cli_api_type_forwards_none(capsys):
    last = {}
    _run(capsys, last, provider="google")
    assert last["cli_api_type"] is None


def test_session_model_forwarded(capsys):
    last = {}
    _run(capsys, last, provider="alibaba", model="qwen3.8-max")
    assert last["model"] == "qwen3.8-max"


def test_status_handler_forwards_shell_api_type(capsys):
    from janito.shell.cmds.status import StatusCmdHandler

    calls = {}

    def fake_resolve(cli_api_type, provider, model):
        calls["cli_api_type"] = cli_api_type
        calls["provider"] = provider
        return "Gemini"

    class FakeShell:
        provider = "google"
        model = "qwen3.8-flash"
        thinking = False
        api_type = "Gemini"

    with (
        patch("janito.shell.cmds.status.get_active_provider", return_value="openai"),
        patch("janito.shell.cmds.status.get_api_key", return_value=""),
        patch("janito.shell.cmds.status.get_masked_api_key", return_value="(not set)"),
        patch("janito.shell.cmds.status.load_max_output_tokens", return_value=None),
        patch("janito.shell.cmds.status.load_endpoint_from_config", return_value=None),
        patch(
            "janito.shell.cmds.status.get_provider",
            return_value=_fake_provider("google", default_max_tokens=None, stateless_mode=False),
        ),
        patch("janito.shell.cmds.status.resolve_api_type", side_effect=fake_resolve),
    ):
        assert StatusCmdHandler().handle(FakeShell(), "/status") is True
    assert calls["cli_api_type"] == "Gemini"
    assert calls["provider"] == "google"
    assert capsys.readouterr().out.strip() != ""
