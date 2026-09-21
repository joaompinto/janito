"""
Prompt-toolkit session setup for the interactive shell.

Extracted from :mod:`janito.shell.interactive` so the shell module stays
focused on the conversation loop, input dispatch and command handling.
"""

import logging
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.styles import Style

from .completer import CommandCompleter

logger = logging.getLogger(__name__)

# History file path
HISTORY_FILE = Path.cwd() / ".janito" / "history.log"


def _provider_arg_completer(prefix: str) -> list[str]:
    """Return the provider names matching ``prefix`` for ``/provider`` autocompletion.

    Delegates to the ``/provider`` command's helper so the completions always
    match the providers the command accepts (built-in + registered variants).
    Only providers with an API key set are suggested: switching to a provider
    without a key would only make the next prompt fail with an authentication
    error.
    """
    from .cmds.provider import available_provider_names

    return list(available_provider_names(prefix, only_with_api_key=True))


def _thinking_arg_completer(prefix: str) -> list[str]:
    """Return 'on'/'off' options matching prefix for /thinking autocompletion."""
    options = ["on", "off"]
    lowered = prefix.lower()
    return [opt for opt in options if opt.lower().startswith(lowered)]


def _effort_arg_completer(prefix: str) -> list[str]:
    """Return supported reasoning efforts matching prefix for /effort."""
    from janito.general_config import get_active_provider

    from .cmds.effort import available_effort_names

    # No shell instance here; use active provider with no model filter.
    return list(available_effort_names(get_active_provider(), None, prefix))


class _SessionMixin:
    """Mixin providing prompt_toolkit session and history management."""

    def _model_arg_completer(self, prefix: str) -> list[str]:
        """Return the model names matching ``prefix`` for ``/model`` autocompletion.

        Delegates to the ``/model`` command's helper so the completions always
        match the models the command accepts for the **current provider** (its
        built-in models plus configured per-model entries).  The current
        provider is the session's displayed provider (``--provider`` at
        startup or an earlier ``/provider`` switch), else the configured
        default -- the same provider ``/model`` itself switches within.
        """
        from janito.general_config import get_active_provider

        from .cmds.model import available_model_names

        provider = getattr(self, "provider", None) or get_active_provider()
        return available_model_names(provider, prefix)

    def _get_bottom_toolbar(self) -> list:
        """Get the bottom toolbar content."""
        tokens = []

        # Model info
        model = getattr(self, "model", None)
        tokens.append(("class:model", f" model: {model} "))

        # Provider info (if available)
        provider = None
        try:
            from janito.general_config import get_active_provider

            provider = getattr(self, "provider", None) or get_active_provider()
            if provider:
                tokens.append(("", " \u2502 "))
                tokens.append(("class:provider", f" provider: {provider} "))
        except Exception:  # noqa: BLE001 - toolbar is cosmetic; never break the shell
            logger.debug("Could not resolve provider for the toolbar", exc_info=True)

        # Effort info (same style as provider)
        try:
            effort = getattr(self, "effort", None)
            if not effort:
                from janito.config_loaders import load_effort

                effort = load_effort(provider, model)
            if not effort:
                from janito.providers.registry import get_provider

                found = get_provider(provider) if provider else None
                effort = found.model_config(model).get("default_reasoning_effort") if found is not None else None
            tokens.append(("", " \u2502 "))
            tokens.append(("class:provider", f" effort: {effort if effort else '(not set)'} "))
        except Exception:  # noqa: BLE001 - toolbar is cosmetic; never break the shell
            logger.debug("Could not resolve effort for the toolbar", exc_info=True)

        # Multiline mode indicator
        if getattr(self, "multiline_mode", False):
            tokens.append(("class:key-toggle-on", "[multi] "))

        return tokens

    def _create_session(self, multiline: bool = False) -> PromptSession:
        """Create and configure the prompt_toolkit session."""
        kb = KeyBindings()

        @kb.add("f2")
        def restart_chat(event: KeyPressEvent) -> None:
            """Handle F2 key to clear the conversation."""
            self.restart_requested = True
            event.app.exit(result=None)

        @kb.add("f12")
        def do_it_action(event: KeyPressEvent) -> None:
            """Handle F12 key to trigger 'Do It' auto-execution."""
            self.do_it_requested = True
            event.app.exit(result="Do It")

        # Style for the chat shell
        chat_shell_style = Style.from_dict(
            {
                "prompt": "bg:#2323af #ffffff bold",
                "": "#ffffff",
                "bottom-toolbar": "fg:#232323 bg:#f0f0f0",
                "key-label": "bg:#ff9500 fg:#232323 bold",
                "provider": "fg:#117fbf",
                "model": "fg:#1f5fa9",
                "role": "fg:#e87c32 bold",
                "msg_count": "fg:#5454dd",
                "session_id": "fg:#704ab9",
                "tokens_total": "fg:#a022c7",
                "tokens_in": "fg:#00af5f",
                "tokens_out": "fg:#01814a",
                "max-tokens": "fg:#888888",
                "key-toggle-on": "bg:#ffd700 fg:#232323 bold",
                "key-toggle-off": "bg:#444444 fg:#ffffff bold",
                "cmd-label": "bg:#ff9500 fg:#232323 bold",
            }
        )

        # Set up history based on no_history flag
        if self.no_history:
            # In-memory only - don't persist to file
            history = InMemoryHistory()
        else:
            # Persist to file in current directory
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            history = FileHistory(str(HISTORY_FILE))

        return PromptSession(
            history=history,
            key_bindings=kb,
            style=chat_shell_style,
            bottom_toolbar=lambda: self._get_bottom_toolbar(),
            multiline=multiline,
            completer=CommandCompleter(
                lambda: self.commands,
                # Argument completion: ``/provider <name>`` suggests the
                # available provider names (built-in + registered variants)
                # and ``/model <name>`` suggests the models available from the
                # current provider (built-in + configured per-model entries).
                arg_completers={
                    "/provider": _provider_arg_completer,
                    "/model": self._model_arg_completer,
                    "/thinking": _thinking_arg_completer,
                    "/effort": _effort_arg_completer,
                },
            ),
            complete_while_typing=True,
        )
