"""
/effort command handler - shows or changes the session reasoning effort.

Usage:
    /effort            - Show the current reasoning effort and supported levels
    /effort <level>    - Switch the session's reasoning effort
    /effort clear      - Clear the session override (config/default applies)

The switch is **runtime-only**: it updates the shell's effort state for the
running session and rebuilds the send function through the session's send
factory, but it does **not** change any persisted configuration.
"""

from .base import CmdHandler
from .registry import register_command

CLEAR_KEYWORDS = {"clear", "default", "none", "auto"}


def available_effort_names(provider: str | None, model: str | None, prefix: str = "") -> list[str]:
    """Return supported reasoning efforts for provider/model matching prefix."""
    from janito.providers.registry import get_provider

    found = get_provider(provider) if provider else None
    supported = found.model_config(model).get("supported_reasoning_efforts") if found is not None else None
    names: list[str] = []
    for entry in supported or []:
        if isinstance(entry, dict):
            name = entry.get("effort")
        else:
            name = entry
        if isinstance(name, str) and name:
            names.append(name)
    lowered = prefix.lower()
    return [n for n in names if n.lower().startswith(lowered)]


def _effective_effort(shell) -> tuple[str | None, str]:
    """Return (effort, source) for display."""
    from janito.config_loaders import load_effort
    from janito.providers.registry import get_provider

    provider = getattr(shell, "provider", None)
    model = getattr(shell, "model", None)
    override = getattr(shell, "effort", None)
    if override:
        return override, "session"
    configured = load_effort(provider, model)
    if configured:
        return configured, "config"
    found = get_provider(provider) if provider else None
    default = found.model_config(model).get("default_reasoning_effort") if found is not None else None
    if default:
        return default, "default"
    return None, "unset"


class EffortCmdHandler(CmdHandler):
    """Command handler for /effort command."""

    @property
    def name(self) -> str:
        return "/effort"

    @property
    def description(self) -> str:
        return "Show or change the session's reasoning effort"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /effort command."""
        parts = user_input.strip().split(None, 1)
        if not parts or parts[0].lower() != self.name.lower():
            return False
        if len(parts) == 1:
            self._show_status(shell)
        else:
            self._set_effort(shell, parts[1].strip())
        return True

    @staticmethod
    def _show_status(shell) -> None:
        effort, source = _effective_effort(shell)
        if effort:
            suffix = {
                "session": "",
                "config": " (config)",
                "default": " (default)",
            }.get(source, "")
            print(f"Reasoning effort is currently '{effort}'{suffix} for this session.")
        else:
            print("Reasoning effort is currently not set for this session.")
        supported = available_effort_names(getattr(shell, "provider", None), getattr(shell, "model", None))
        if supported:
            print(f"Supported levels: {', '.join(supported)}")
        print("Usage: /effort <level> | /effort clear")

    @staticmethod
    def _set_effort(shell, level: str) -> None:
        provider = getattr(shell, "provider", None)
        model = getattr(shell, "model", None)
        if level.lower() in CLEAR_KEYWORDS:
            shell.effort = None
            print("[OK] Reasoning effort override cleared (config/default applies).")
            _rebind_send_function(shell)
            return
        supported = available_effort_names(provider, model)
        canonical = level
        if supported:
            matches = [s for s in supported if s.lower() == level.lower()]
            if not matches:
                print(f"Error: Invalid effort '{level}'. Supported: {', '.join(supported)}")
                return
            canonical = matches[0]
        shell.effort = canonical
        print(f"[OK] Reasoning effort set to '{canonical}' for this session (config default unchanged).")
        _rebind_send_function(shell)


def _rebind_send_function(shell) -> None:
    """Rebuild shell.turn_func so the new effort takes effect."""
    factory = getattr(shell, "turn_factory", None)
    if factory is None or not hasattr(shell, "turn_func"):
        return
    shell.turn_func = factory(
        getattr(shell, "provider", None),
        model_override=getattr(shell, "model_override", None),
        thinking_override=getattr(shell, "thinking", None),
        effort_override=getattr(shell, "effort", None),
    )


_handler = EffortCmdHandler()
register_command(_handler)
