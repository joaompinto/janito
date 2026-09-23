"""
/model command handler - switches the active model for the shell session.

Usage:
    /model            - Show the current model and the models available from
                        the current provider
    /model <name>     - Switch the session's model

The switch is **runtime-only**: it updates the shell's displayed model
(prompt and bottom toolbar) and rebinds the turn function so subsequent
turns use the new model, but it does **not** change the configured default
``model`` in config.json -- use ``janito --set model=<name>`` to persist a
new default.  The switch takes effect immediately for the running session,
whether or not the session was started with ``--model``.

Like the CLI's ``--model`` flag, the model name is validated against the
models available from the current provider (its built-in models); when it
matches, the canonical casing is used.  Only the ``openrouter`` and
``custom`` providers accept any model name.  The shell's argument
autocompletion suggests the available models.

Switching the model clears the LLM conversation history (system prompt
preserved) so the previous model's context does not leak into the new one.
"""

from collections.abc import Iterable

from .base import CmdHandler
from .registry import register_command


def available_model_names(provider: str | None, prefix: str = "") -> Iterable[str]:
    """Return model names available from ``provider`` matching ``prefix``.

    The available set is the provider's built-in ``models`` registry (e.g.
    OpenAI's ``gpt-6-luna``) plus any per-model config entries stored
    under ``providers.<provider>.models`` in config.json, so a custom model
    with model-scoped settings is suggested too.  Matching is
    case-insensitive and the result is sorted case-insensitively; with an
    empty prefix every available model is returned.  Used both by the
    ``/model`` display and by the shell's argument autocompletion.

    Args:
        provider: The provider to list models for (case-insensitive).
        prefix: The partial model name typed so far.

    Returns:
        The matching model names in their canonical casing.
    """
    from janito.config_keys import normalize_provider
    from janito.config_store import get_config_value
    from janito.providers.registry import get_provider

    names: set[str] = set()
    found = get_provider(provider)
    if found is not None:
        names.update(found.model_names())

    # Configured per-model entries (custom models with model-scoped settings
    # such as ``--set max-output-tokens=...``).
    providers = get_config_value("providers")
    if isinstance(providers, dict):
        provider_config = providers.get(normalize_provider(provider))
        if isinstance(provider_config, dict):
            models = provider_config.get("models")
            if isinstance(models, dict):
                names.update(models.keys())

    lowered = prefix.lower()
    return sorted(
        (name for name in names if name.lower().startswith(lowered)),
        key=str.lower,
    )


class ModelCmdHandler(CmdHandler):
    """Command handler for /model command."""

    @property
    def name(self) -> str:
        return "/model"

    @property
    def description(self) -> str:
        return "Show or switch the active model for the session"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /model command."""
        parts = user_input.strip().split(None, 1)
        if not parts or parts[0].lower() != self.name.lower():
            return False

        if len(parts) == 1:
            self._show_current(shell)
        else:
            self._switch_model(shell, parts[1].strip())
        return True

    @staticmethod
    def _show_current(shell) -> None:
        """Print the current model and the models available from the current provider."""
        from janito.general_config import get_active_provider

        provider = getattr(shell, "provider", None) or get_active_provider()
        current = getattr(shell, "model", None)
        print(f"Current provider: {provider}")
        print(f"Current model: {current}")
        print("Available models:")
        for name in available_model_names(provider):
            marker = " (current)" if current and name.lower() == current.lower() else ""
            print(f"  {name}{marker}")
        print("Switch with: /model <name>")

    @staticmethod
    def _switch_model(shell, model_name: str) -> None:
        """Apply the new model for this shell session only."""
        from janito.general_config import get_active_provider
        from janito.providers.validation import validate_model_name

        # The provider in effect: the session's displayed provider (set from
        # --provider at startup, or updated by an earlier /provider switch),
        # else the configured default.
        provider = getattr(shell, "provider", None) or get_active_provider()

        # Like the CLI's --model, the name is validated against the models
        # available from the current provider (its built-in models; only
        # openrouter and custom accept any name).  When it matches, the
        # canonical casing is used.
        try:
            canonical = validate_model_name(provider, model_name)
        except ValueError as e:
            print(f"[ERROR] {e}")
            return

        previous = getattr(shell, "model", None)

        # Runtime-only switch: the shell's model changes for this session,
        # but the configured default in config.json is left untouched (use
        # ``janito --set model=<name>`` to persist a new default).
        shell.model = canonical
        # Remember the explicit switch so a later /provider switch knows a
        # session model override is in effect (and clears it).
        shell.model_override = canonical

        print(f"[OK] Model switched to '{canonical}' for this session " "(config default unchanged).")

        # The switch takes effect in real time: rebuild the turn function
        # with the new model so subsequent turns use it (the factory's
        # model_override wins over --model and the provider's resolved
        # model).  The conversation belongs to the model serving it: when
        # the effective model changes, the previous model's context must not
        # leak into the new one, so start a fresh conversation (system
        # prompt preserved).
        if (previous or "").lower() != canonical.lower():
            factory = getattr(shell, "turn_factory", None)
            if factory is not None and hasattr(shell, "turn_func"):
                # thinking_override keeps the session's runtime /thinking
                # toggle across the model switch (the config is rebuilt with
                # the shell's current flag).
                shell.turn_func = factory(
                    provider,
                    model_override=canonical,
                    thinking_override=getattr(shell, "thinking", None),
                    effort_override=getattr(shell, "effort", None),
                )
            shell.initialize_history(system_prompt=getattr(shell, "_system_prompt", None))
            print("Conversation history cleared (model changed).")


# Register this handler
_handler = ModelCmdHandler()
register_command(_handler)
