"""
/provider command handler - switches the active provider for the shell session.

Usage:
    /provider            - Show the current provider and the available providers
    /provider <name>     - Switch the session's provider (and model)

The provider name is validated against the built-in providers (the
``janito.providers`` registry) and the registered provider variants
(``janito --create-variant``).  The switch is **runtime-only**: it updates
the shell's displayed provider (bottom toolbar) and model and rebinds the
send function to the new provider (its API type re-resolved), but it does
**not** change the configured default ``provider`` in config.json -- use
``janito --set provider=<name>`` to persist a new default.  The switch takes
effect immediately for the running session, whether or not the session was
started with ``--provider``.

Switching the provider clears the LLM conversation history (system prompt
preserved) so the previous provider's/model's context does not leak into the
new one.
"""

from collections.abc import Iterable

from .base import CmdHandler
from .registry import register_command


def available_provider_names(prefix: str = "", *, only_with_api_key: bool = False) -> Iterable[str]:
    """Return provider names (built-in + registered variants) matching ``prefix``.

    Matching is case-insensitive and the result is sorted
    case-insensitively; with an empty prefix every available provider is
    returned.  Used both by the ``/provider`` display and by the shell's
    argument autocompletion.

    Args:
        prefix: The partial provider name typed so far.
        only_with_api_key: When True, only providers that have an API key
            stored in ``~/.janito/auth.json`` are returned.  The shell's
            ``/provider`` argument autocompletion passes True so that only
            providers the user can actually switch to are suggested; the
            ``/provider`` display (no argument) keeps listing every provider
            regardless of key.

    Returns:
        The matching provider names in their canonical casing.
    """
    from janito.auth_config import get_api_key
    from janito.providers.validation import list_supported_providers, list_variants

    names = list_supported_providers() + list_variants()
    if only_with_api_key:
        names = [name for name in names if get_api_key(name)]
    lowered = prefix.lower()
    return sorted(
        (name for name in names if name.lower().startswith(lowered)),
        key=str.lower,
    )


class ProviderCmdHandler(CmdHandler):
    """Command handler for /provider command."""

    @property
    def name(self) -> str:
        return "/provider"

    @property
    def description(self) -> str:
        return "Show or switch the active provider for the session"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /provider command."""
        parts = user_input.strip().split(None, 1)
        if not parts or parts[0].lower() != self.name.lower():
            return False

        if len(parts) == 1:
            self._show_current(shell)
        else:
            self._switch_provider(shell, parts[1].strip())
        return True

    @staticmethod
    def _show_current(shell) -> None:
        """Print the current provider and every available provider."""
        from janito.general_config import get_active_provider

        current = getattr(shell, "provider", None) or get_active_provider()
        print(f"Current provider: {current}")
        print("Available providers:")
        for name in available_provider_names():
            print(f"  {name}")
        print("Switch with: /provider <name>")

    @staticmethod
    def _switch_provider(shell, provider_name: str) -> None:
        """Validate and apply the new provider for this shell session only."""
        from janito.config_loaders import load_model_from_config
        from janito.general_config import get_active_provider
        from janito.providers.registry import get_provider
        from janito.providers.validation import validate_provider_name

        try:
            canonical = validate_provider_name(provider_name)
        except ValueError as e:
            print(f"Error: {e}")
            return

        # The provider in effect before the switch: the session's displayed
        # provider (set from --provider at startup, or updated by an earlier
        # /provider switch), else the configured default.  Captured before the
        # runtime update below so it reflects the *old* state.
        previous = getattr(shell, "provider", None) or get_active_provider()

        # Runtime-only switch: the shell's provider changes for this session,
        # but the configured default in config.json is left untouched (use
        # ``janito --set provider=<name>`` to persist a new default).
        shell.provider = canonical

        # Keep the toolbar's model display truthful: re-resolve the effective
        # model for the new provider (configured model, else built-in default).
        # A placeholder "custom" default (e.g. openrouter) is not a usable
        # model, so providers without a configured model keep the previous
        # model display (like "custom") -- a later turn reports the missing
        # model via the runtime resolution.
        model = load_model_from_config(canonical)
        if not model:
            found = get_provider(canonical)
            if found is not None:
                default = found.default_model()
                if default != "custom":
                    model = default
        if model:
            shell.model = model

        print(f"[OK] Provider switched to '{canonical}' for this session " "(config default unchanged).")

        # The switch takes effect in real time: rebind the shell's send
        # function to the new provider (its API type re-resolved), so
        # subsequent turns use the new provider even when the session was
        # started with --provider.  The conversation belongs to the provider
        # serving it: when the effective provider changes, the previous
        # model's context must not leak into the new one, so start a fresh
        # conversation (system prompt preserved).
        if (previous or "").lower() != canonical.lower():
            factory = getattr(shell, "turn_factory", None)
            if factory is not None and hasattr(shell, "turn_func"):
                # thinking_override keeps the session's runtime /thinking
                # toggle across the provider switch (the config is rebuilt
                # with the shell's current flag).
                shell.turn_func = factory(
                    canonical,
                    thinking_override=getattr(shell, "thinking", None),
                    effort_override=getattr(shell, "effort", None),
                )
            # A session model switch (/model) was scoped to the previous
            # provider: the new provider resolves its own effective model.
            shell.model_override = None
            shell.initialize_history(system_prompt=getattr(shell, "_system_prompt", None))
            print("Conversation history cleared (provider changed).")


# Register this handler
_handler = ProviderCmdHandler()
register_command(_handler)
