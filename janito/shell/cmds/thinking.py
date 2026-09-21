"""
/thinking command handler - enables or disables thinking mode for the current session.

Usage:
    /thinking            - Show the current thinking status
    /thinking on|off     - Enable or disable runtime config thinking for the current session

The switch is **runtime-only**: it updates the shell's thinking state for the
running session and rebuilds the send function through the session's send
factory (so the new flag is baked into the APIConfig the next turn uses), but
it does **not** change any persisted configuration.
"""

from .base import CmdHandler
from .registry import register_command


class ThinkingCmdHandler(CmdHandler):
    """Command handler for /thinking command."""

    @property
    def name(self) -> str:
        return "/thinking"

    @property
    def description(self) -> str:
        return "Show or change the session's thinking mode"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /thinking command."""
        parts = user_input.strip().split(None, 1)
        if not parts or parts[0].lower() != self.name.lower():
            return False

        if len(parts) == 1:
            self._show_status(shell)
        else:
            self._set_thinking(shell, parts[1].strip())
        return True

    @staticmethod
    def _show_status(shell) -> None:
        """Print the current thinking status and usage."""
        provider = getattr(shell, "provider", None)
        if provider and _is_gemini_flavor(provider):
            print("Thinking mode is N/A for this session " "(controlled via Reasoning Effort for Gemini models).")
            print("Usage: /thinking on|off")
            return
        current = getattr(shell, "thinking", False)
        status_str = "enabled (on)" if current else "disabled (off)"
        print(f"Thinking mode is currently {status_str} for this session.")
        print("Usage: /thinking on|off")

    @staticmethod
    def _set_thinking(shell, mode: str) -> None:
        """Enable or disable thinking for this shell session.

        Thinking is resolved into the immutable APIConfig at build time, so a
        runtime flip rebuilds the send function through the session's send
        factory (the same cheap rebuild /provider and /model perform).  When
        no factory is available (e.g. tests building a bare shell), only the
        shell flag is updated.
        """
        mode_lower = mode.lower()
        if mode_lower == "on":
            shell.thinking = True
            print("[OK] Thinking mode enabled for this session " "(config default unchanged).")
            provider = getattr(shell, "provider", None)
            if provider and _is_gemini_flavor(provider):
                print(
                    "[WARN] Gemini models reason by default; thinking depth is controlled "
                    "via reasoning level rather than the thinking flag."
                )
        elif mode_lower == "off":
            shell.thinking = False
            print("[OK] Thinking mode disabled for this session " "(config default unchanged).")
            provider = getattr(shell, "provider", None)
            if provider and _is_gemini_flavor(provider):
                print(
                    "[WARN] Gemini models reason by default; thinking depth is controlled "
                    "via reasoning level rather than the thinking flag."
                )
        else:
            print(f"Error: Invalid option '{mode}'. Use '/thinking on' or '/thinking off'.")
            return
        _rebind_send_function(shell)


def _is_gemini_flavor(provider: str | None) -> bool:
    """Return True when the provider is Gemini-flavored (thinking via reasoning level)."""
    from ...providers.registry import get_provider

    found = get_provider(provider) if provider else None
    return found is not None and found.gemini_flavor()


def _rebind_send_function(shell) -> None:
    """Rebuild ``shell.turn_func`` so the new thinking flag takes effect.

    The send function is bound to a resolved APIConfig (thinking baked in at
    build time), so a runtime /thinking flip re-invokes the session's send
    factory with the shell's current flag.  No-op when the factory or the
    current send function is absent (e.g. bare test shells).
    """
    factory = getattr(shell, "turn_factory", None)
    if factory is None or not hasattr(shell, "turn_func"):
        return
    shell.turn_func = factory(
        getattr(shell, "provider", None),
        model_override=getattr(shell, "model_override", None),
        thinking_override=getattr(shell, "thinking", False),
        effort_override=getattr(shell, "effort", None),
    )


# Register this handler
_handler = ThinkingCmdHandler()
register_command(_handler)
