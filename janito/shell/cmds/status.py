"""
/status command handler - displays current configuration.
"""

from janito.auth_config import get_api_key

# Import general configuration handling
from janito.config_keys import get_masked_api_key
from janito.config_loaders import (
    load_effort,
    load_endpoint_from_config,
    load_max_output_tokens,
    load_model_from_config,
)
from janito.general_config import get_active_provider, resolve_api_type
from janito.llm_clients.openai.responses_state import stateless_mode
from janito.providers.payloads import resolve_thinking_display
from janito.providers.registry import get_provider

from .base import CmdHandler
from .registry import register_command


def _resolve_effective_model(provider: str, model: str | None) -> tuple[str | None, bool]:
    """Resolve the effective model for the session and whether it is a default.

    The session's model (``--model``, ``/model`` or the startup resolution)
    wins; otherwise the provider's configured model; otherwise its built-in
    default model (``None`` e.g. for "custom").

    Returns:
        Tuple ``(model, is_default)``. ``is_default`` is True only when the
        built-in default was used (no session model, nothing configured), so
        the Model row can be marked with ``(default)``.
    """
    if model:
        return model, False
    configured = load_model_from_config(provider)
    if configured:
        return configured, False
    found = get_provider(provider)
    default = found.default_model() if found is not None else None
    return default, default is not None


def _print_config_info(
    provider: str | None = None,
    thinking: bool = False,
    api_type: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> None:
    """Print current configuration info (provider, model, base_url, masked API key, max output tokens).

    Model-level settings (API type, max output tokens, reasoning level,
    thinking, Stateless-mode) are resolved for the *effective model*:
    the session's model, else the provider's configured model, else its
    built-in default model.

    Args:
        provider: The provider in effect for the current shell session (e.g.
            from ``--provider``). When None, falls back to the configured
            default provider.
        thinking: The ``--thinking`` CLI flag for the session. The effective
            thinking mode also considers the effective model's built-in
            default (True for DeepSeek and Alibaba/Qwen).
        api_type: The ``--api-type`` CLI flag for the session (e.g. ``Gemini``,
            ``Responses``, ``Completions``), or None when it was not given.
            Forwarded to ``resolve_api_type`` so the display reports the API
            type the session actually uses: the CLI flag first, then the
            model-scoped configured value (``--set api-type=...``), then the
            effective model's built-in default.
        model: The session's effective model (from ``--model``, ``/model`` or
            the startup resolution). When None, the provider's configured
            model, else its built-in default model is used and the Model row
            marks the built-in default with ``(default)``.
        effort: The ``--effort`` CLI flag for the session
            (e.g. ``high``), or None when it was not given. Takes priority
            over the model-scoped configured value, then the effective
            model's built-in default -- mirroring ``build_api_config`` so
            ``/status`` reports the level actually sent to the API.
    """
    if provider is None:
        provider = get_active_provider()
    api_key = get_api_key(provider) or ""
    masked_key = get_masked_api_key(api_key)

    # Effective model for the session: the shell's model when given, else the
    # provider's configured model, else its built-in default model (None e.g.
    # for "custom").  Only the built-in default (no session model, nothing
    # configured) is marked '(default)' in the display.
    model, model_default = _resolve_effective_model(provider, model)

    # The typed provider accessor backing every built-in default lookup below
    # (None for unknown providers -> the accessor-style None defaults).
    found = get_provider(provider)

    max_output_tokens = load_max_output_tokens(provider, model)

    # Resolve the effective API type first (--api-type, otherwise the
    # model-scoped configured value --set api-type=..., otherwise the
    # effective model's built-in default -- its default_api_type entry) so
    # the built-in base URL can be resolved per API type
    # (endpoint_by_api_type, e.g. Anthropic's native-SDK URL).
    api_type = resolve_api_type(api_type, provider, model)

    # Determine the actual base URL that will be used: a configured endpoint
    # override first, otherwise the provider's built-in default for the
    # effective API type.
    base_url = load_endpoint_from_config(provider)
    if not base_url:
        base_url = found.endpoint_for(api_type) if found is not None else None

    if base_url:
        base_url_display = base_url
    else:
        base_url_display = "(default OpenAI URL)"

    # Resolve the effective max output tokens: an explicit configuration
    # value first, otherwise the effective model's built-in default from
    # the provider config.
    if max_output_tokens:
        max_output_tokens_display = str(max_output_tokens)
    else:
        default_max_output_tokens = found.model_config(model).get("max_output_tokens") if found is not None else None
        max_output_tokens_display = (
            f"{default_max_output_tokens} (default)" if default_max_output_tokens else "(not set)"
        )

    # Resolve the effective reasoning level: the --effort CLI flag
    # first, otherwise an explicit configuration value, otherwise the
    # effective model's built-in default from the provider config (mirrors
    # build_api_config so /status reports what is actually sent).
    effort = effort or load_effort(provider, model)
    if effort:
        reasoning_effort_display = effort
    else:
        default_reasoning_effort = (
            found.model_config(model).get("default_reasoning_effort") if found is not None else None
        )
        reasoning_effort_display = f"{default_reasoning_effort} (default)" if default_reasoning_effort else "(not set)"

    # Resolve the effective thinking mode: the --thinking flag first,
    # otherwise the effective model's built-in default from the provider
    # config
    # (True for DeepSeek/Alibaba-Qwen; a pass-through dict such as
    # {'type': 'adaptive'} for MiniMax-M3).
    effective_thinking = thinking or (found.model_config(model).get("thinking", False) if found is not None else False)
    thinking_display = resolve_thinking_display(effective_thinking, explicit_thinking=bool(thinking), provider=provider)

    # When the effective API type is the Responses API, surface whether the
    # model keeps the conversation state server-side (chained with
    # previous_response_id) or serves a stateless /responses endpoint (the
    # client re-sends the full history on every request, e.g. DeepSeek).
    stateless_mode_display = ""
    if api_type == "Responses":
        if stateless_mode(provider, model):
            stateless_mode_display = "stateless (client re-sends history)"
        else:
            stateless_mode_display = "server-side (previous_response_id)"

    from rich.console import Console
    from rich.table import Table

    table = Table(
        title="Configuration Info",
        title_style="bold",
        header_style="bold cyan",
        show_header=False,
        box=None,
        pad_edge=False,
    )
    table.add_column("Key", style="green", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("Provider", provider)
    table.add_row(
        "Model",
        f"{model} (default)" if model_default else (model or "(not set)"),
    )
    table.add_row("API Type", api_type)
    if stateless_mode_display:
        table.add_row("Stateless Mode", stateless_mode_display)
    table.add_row("Base URL", base_url_display)
    table.add_row("API Key", masked_key)
    table.add_row("Max Output Tokens", max_output_tokens_display)
    table.add_row("Reasoning Effort", reasoning_effort_display)
    table.add_row("Thinking", thinking_display)
    Console(markup=False).print(table)


class StatusCmdHandler(CmdHandler):
    """Command handler for /status command."""

    @property
    def name(self) -> str:
        return "/status"

    @property
    def description(self) -> str:
        return "Show the resolved runtime configuration"

    def handle(self, shell, user_input: str) -> bool:
        """Handle the /status command."""
        if user_input.lower() == self.name.lower():
            _print_config_info(
                getattr(shell, "provider", None),
                getattr(shell, "thinking", False),
                getattr(shell, "api_type", None),
                getattr(shell, "model", None),
                getattr(shell, "effort", None),
            )
            return True
        return False


# Register this handler
_handler = StatusCmdHandler()
register_command(_handler)
