"""
Tests for shell command autocompletion.

The interactive shell wires a :class:`janito.shell.completer.CommandCompleter`
into its ``prompt_toolkit`` session so that typing a partial slash command
(e.g. ``/t``) suggests the matching registered commands (e.g. ``/tools``).
These tests verify the completer's matching logic, its case-insensitivity,
that plain (non-command) input is left untouched, and that the completer is
correctly attached to the shell's session.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from janito.shell.completer import CommandCompleter


class _FakeCmd:
    """Minimal command handler exposing only a ``name`` (what the completer uses)."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name


def _completer(names):
    """Build a CommandCompleter backed by fake commands with the given names."""
    commands = [_FakeCmd(n) for n in names]
    return CommandCompleter(lambda: commands)


def _completions_for(completer, text):
    """Return the completion texts suggested for the given input."""
    doc = Document(text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, CompleteEvent())]


if pytest is not None:

    def test_completes_matching_prefix():
        completer = _completer(["/tools", "/help", "/history"])
        assert _completions_for(completer, "/t") == ["/tools"]

    def test_multiple_matches_sorted_alphabetically():
        completer = _completer(["/history", "/help"])
        assert _completions_for(completer, "/h") == ["/help", "/history"]

    def test_slash_alone_lists_every_command():
        completer = _completer(["/tools", "/ask", "/status"])
        assert _completions_for(completer, "/") == ["/ask", "/status", "/tools"]

    def test_exact_match_is_offered():
        completer = _completer(["/exit"])
        assert _completions_for(completer, "/exit") == ["/exit"]

    def test_no_match_yields_nothing():
        completer = _completer(["/tools", "/help"])
        assert _completions_for(completer, "/zzz") == []

    def test_non_command_input_is_untouched():
        completer = _completer(["/tools"])
        assert _completions_for(completer, "hello") == []

    def test_slash_in_middle_of_line_is_untouched():
        # A ``/`` that is not at the start of the line is chat text, not a
        # command, so it must not trigger command autocompletion.
        completer = _completer(["/tools", "/help"])
        assert _completions_for(completer, "hello /t") == []
        assert _completions_for(completer, "say /help") == []
        assert _completions_for(completer, "say /help please") == []
        assert _completions_for(completer, "path /t") == []

    def test_leading_whitespace_still_completes():
        # The command only needs to be the first token of the line, so
        # leading indentation/whitespace is allowed.
        completer = _completer(["/tools"])
        assert _completions_for(completer, "  /t") == ["/tools"]

    def test_empty_input_yields_nothing():
        completer = _completer(["/tools"])
        assert _completions_for(completer, "") == []

    def test_case_insensitive_matching():
        completer = _completer(["/tools"])
        assert _completions_for(completer, "/T") == ["/tools"]
        assert _completions_for(completer, "/TOOL") == ["/tools"]

    def test_completion_replaces_only_command_token():
        completer = _completer(["/tools"])
        doc = Document("/t", cursor_position=2)
        completions = list(completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 1
        # start_position is the number of chars to remove before inserting.
        assert completions[0].start_position == -len("/t")
        # display_meta is stored as formatted text; its content is "command".
        meta = completions[0].display_meta
        assert "command" in "".join(part[1] for part in meta)

    def test_completer_uses_registered_commands():
        # The real registered command set should include the well-known commands.
        from janito.shell.cmds import get_registered_commands

        completer = CommandCompleter(get_registered_commands)
        names = _completions_for(completer, "/")
        assert "/help" in names
        assert "/tools" in names
        assert "/exit" in names
        assert "/provider" in names
        assert "/thinking" in names

    def test_session_has_completer_and_complete_while_typing():
        # Building an InteractiveShell wires the completer into its session.
        from janito.shell import InteractiveShell

        shell = InteractiveShell(model="test-model", no_history=True)
        assert isinstance(shell.session.completer, CommandCompleter)
        assert shell.session.complete_while_typing is True

    # ------------------------------------------------------------------
    # Argument autocompletion (/provider <name>)
    # ------------------------------------------------------------------

    def _use_temp_config(monkeypatch, tmp_path):
        """Point the config directory at a temporary directory."""
        import janito.config_dir as config_dir_mod

        config_path = tmp_path / ".janito" / "config.json"
        monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
        return config_path

    def _set_api_key(provider: str):
        """Store an API key for ``provider`` in the (temp) auth store."""
        from janito.auth_config import set_api_key

        set_api_key(provider, f"sk-{provider}")  # pragma: allowlist secret

    def _arg_completer_completions_for(text, provider=None):
        """Completions offered by the real shell completer for the given input."""
        from janito.shell import InteractiveShell

        shell = InteractiveShell(model="test-model", no_history=True, provider=provider)
        return _completions_for(shell.session.completer, text)

    def test_provider_argument_completes_all(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        for name in ("openai", "deepseek", "custom"):
            _set_api_key(name)

        text = "/provider "
        names = _arg_completer_completions_for(text)
        assert "openai" in names
        assert "deepseek" in names
        assert "custom" in names

    def test_provider_argument_completes_prefix(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("openai")

        names = _arg_completer_completions_for("/provider op")
        assert names == ["openai"]

    def test_provider_argument_complete_prefix_case_insensitive(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("deepseek")

        names = _arg_completer_completions_for("/provider DEEP")
        assert names == ["deepseek"]

    def test_provider_argument_command_case_insensitive(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("alibaba")

        names = _arg_completer_completions_for("/PROVIDER ali")
        assert "alibaba" in names

    def test_provider_argument_excludes_providers_without_key(monkeypatch, tmp_path):
        # Only providers with an API key set are offered for autocompletion.
        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("deepseek")

        names = _arg_completer_completions_for("/provider ")
        assert "deepseek" in names
        assert "openai" not in names
        assert "custom" not in names

    def test_provider_argument_no_completion_after_second_space():
        # Only the first argument is completed; a second space means the user
        # has moved past it.
        assert _arg_completer_completions_for("/provider openai ") == []

    def test_provider_argument_no_completion_without_command_prefix():
        # A plain chat line mentioning the word must not offer providers.
        assert _arg_completer_completions_for("op") == []
        assert _arg_completer_completions_for("hello /provider op") == []

    def test_provider_argument_leading_whitespace_still_completes(monkeypatch, tmp_path):
        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("openai")

        names = _arg_completer_completions_for("  /provider op")
        assert names == ["openai"]

    def test_provider_argument_includes_registered_variants(monkeypatch, tmp_path):
        import janito.config_dir as config_dir_mod
        import janito.config_variants as cv

        config_path = tmp_path / ".janito" / "config.json"
        monkeypatch.setattr(config_dir_mod, "_config_dir", config_path.parent)
        cv.create_variant("custom-local")
        _set_api_key("custom-local")

        names = _arg_completer_completions_for("/provider custom-")
        assert "custom-local" in names

    def test_provider_argument_completion_meta(monkeypatch, tmp_path):
        from janito.shell import InteractiveShell

        _use_temp_config(monkeypatch, tmp_path)
        _set_api_key("openai")

        shell = InteractiveShell(model="test-model", no_history=True)
        doc = Document("/provider op", cursor_position=len("/provider op"))
        completions = list(shell.session.completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 1
        assert completions[0].start_position == -len("op")
        meta = completions[0].display_meta
        assert "argument" in "".join(part[1] for part in meta)

    def test_provider_command_still_completes_as_command():
        # Typing just "/provider" (no trailing space) still offers the command.
        names = _arg_completer_completions_for("/provider")
        assert "/provider" in names

    # ------------------------------------------------------------------
    # Argument autocompletion (/model <name> from the current provider)
    # ------------------------------------------------------------------

    def test_model_argument_completes_from_current_provider():
        # The models suggested come from the session's provider (openai here).
        names = _arg_completer_completions_for("/model ", provider="openai")
        assert "gpt-6-luna" in names

    def test_model_argument_completes_deepseek_models():
        names = _arg_completer_completions_for("/model ", provider="deepseek")
        assert "deepseek-flash" in names
        assert "gpt-6-luna" not in names

    def test_model_argument_completes_prefix():
        names = _arg_completer_completions_for("/model gpt", provider="openai")
        assert names == ["gpt-6-astra", "gpt-6-luna", "gpt-6-sol"]

    def test_model_argument_complete_prefix_case_insensitive():
        names = _arg_completer_completions_for("/model GPT", provider="openai")
        assert names == ["gpt-6-astra", "gpt-6-luna", "gpt-6-sol"]

    def test_model_argument_command_case_insensitive():
        names = _arg_completer_completions_for("/MODEL deep", provider="deepseek")
        assert "deepseek-flash" in names

    def test_model_argument_includes_configured_models(monkeypatch, tmp_path):
        from janito.config_store import set_config_value

        _use_temp_config(monkeypatch, tmp_path)
        set_config_value("openai.models.gpt-future.max-output-tokens", 1000)

        names = _arg_completer_completions_for("/model gpt-f", provider="openai")
        assert names == ["gpt-future"]

    def test_model_argument_no_completion_after_second_space():
        # Only the first argument is completed; a second space means the user
        # has moved past it.
        assert _arg_completer_completions_for("/model gpt-6-luna ", provider="openai") == []

    def test_model_argument_no_completion_without_command_prefix():
        # A plain chat line mentioning the word must not offer models.
        assert _arg_completer_completions_for("gpt", provider="openai") == []
        assert _arg_completer_completions_for("hello /model gpt", provider="openai") == []

    def test_model_argument_leading_whitespace_still_completes():
        names = _arg_completer_completions_for("  /model gpt", provider="openai")
        assert names == ["gpt-6-astra", "gpt-6-luna", "gpt-6-sol"]

    def test_model_argument_completion_meta():
        from janito.shell import InteractiveShell

        shell = InteractiveShell(model="test-model", no_history=True, provider="openai")
        doc = Document("/model gpt", cursor_position=len("/model gpt"))
        completions = list(shell.session.completer.get_completions(doc, CompleteEvent()))
        assert len(completions) == 3
        assert completions[0].start_position == -len("gpt")
        meta = completions[0].display_meta
        assert "argument" in "".join(part[1] for part in meta)

    def test_model_command_still_completes_as_command():
        # Typing just "/model" (no trailing space) still offers the command.
        names = _arg_completer_completions_for("/model")
        assert "/model" in names

else:  # pragma: no cover - fallback runner without pytest

    def _main():
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"OK {name}")

    if __name__ == "__main__":
        _main()
