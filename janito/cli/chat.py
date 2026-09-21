"""
CLI chat execution modes: interactive and single prompt.
"""

import os
from collections.abc import Callable

from .. import __version__
from ..general_config import load_provider_from_config, resolve_api_type
from ..llm_clients import APIConfig, RequestCancelled, build_api_config
from ..runtime_config import resolve_runtime_config
from ..shell import InteractiveShell
from ..tooling.path_utils import display_path
from ..ui.config import UIConfig
from ..ui.observer import RichTurnObserver, SilentTurnObserver
from ..ui.stream_runner import _run_with_progress_bar

# Whether the version banner has already been printed for this process, so it
# is shown only once (e.g. before plugin loading in main() and again by the
# full-privileges warning).
_banner_printed = False


def _make_turn_func(
    api_config: APIConfig,
    ui_config: UIConfig | None = None,
    session_verbose: bool = False,
):
    """Return a run-turn callable bound to a resolved APIConfig.

    One closure replaces the previous five per-API-type closures (issue #70):
    the client class is picked by :func:`janito.llm_clients.create_client`
    from ``api_config.api_type`` and the union signature is kept so the
    interactive shell can call it identically in all modes:

      - Completions / Anthropic / DashScope / Gemini modes: the conversation
        history is owned client-side (``previous_messages`` mutated in place,
        ``instructions`` folded in); ``previous_response_id`` /
        ``previous_items`` are ignored.
      - Responses mode: ``previous_response_id`` (server-side providers) or
        ``previous_items`` (stateless providers, e.g. DeepSeek) chain the
        conversation; ``previous_messages`` is ignored.

    Each backend's ``_init_conversation_state`` already picks what it needs
    from the union kwargs, so there is a single body.

    The end-of-turn report (used files + token-usage summary) and the
    overall-use accounting row are delivered by ``Client.run_turn`` itself:
    it builds the ``TurnInfo`` internally (folding every round's usage into
    it, tool-call rounds included) and hands it -- together with the resolved
    ``APIConfig``, whose provider / model / max tokens feed the report -- to
    the injected observer's ``on_turn_complete`` when the turn finishes
    (there is no caller-supplied out-param, issue #82).  The observer itself
    lives on the ``ui_config`` (``ui_config.observer``, injected at the
    composition point), so the client is the only place that delivers turn
    events.

    Args:
        api_config: The resolved, immutable
            :class:`~janito.llm_clients.api_config.APIConfig` for this
            session (provider, model, endpoint, api_key, token limits,
            reasoning level, ``use_mcp``).  Built once per session / provider
            switch by ``build_api_config``; the returned callable performs no
            config-store / auth-store reads.
        ui_config: The injected, immutable
            :class:`~janito.ui.config.UIConfig` (per-round stream runner +
            turn observer) for this session.
        session_verbose: The session's verbose flag, captured as the closure
            default for the per-call ``verbose`` gate (``/ask`` and
            ``/compact`` still override it per call).
    """
    from ..llm_clients import create_client

    client = create_client(api_config, ui_config)

    def run_turn(
        prompt,
        *,
        verbose=session_verbose,
        previous_messages=None,
        previous_response_id=None,
        previous_items=None,
        instructions=None,
        tools=None,
    ):
        # ``verbose`` stays an explicit per-call gate (design doc §7): the
        # closure defaults it to the session flag captured here (not on any
        # config); /ask forwards the shell flag and /compact passes False to
        # suppress the dumps.
        # Thinking mode is resolved into ``api_config.thinking`` at build
        # time (the shell's /thinking toggle rebuilds the config via the
        # factory).
        # The end-of-turn report is delivered by Client.run_turn itself to
        # the injected observer's on_turn_complete (client-owned TurnInfo
        # + the resolved APIConfig, issue #82) -- the closure has no out-param
        # to pass.
        return client.run_turn(
            prompt,
            verbose=verbose,
            previous_messages=previous_messages,
            previous_response_id=previous_response_id,
            previous_items=previous_items,
            instructions=instructions,
            tools=tools,
        )

    return run_turn


def _make_turn_factory(
    cli_api_type: str | None,
    cli_model: str | None,
    cli_provider: str | None,
    cli_effort: str | None,
    verbose: bool = False,
    cli_thinking: bool | None = None,
) -> Callable[[str | None, str | None], Callable]:
    """Return a factory that builds the run-turn function for a provider.

    The interactive shell stores the returned factory as ``turn_factory`` and
    ``/provider`` calls it with the new provider, so a provider switch takes
    effect in real time.  For the target provider the factory re-resolves:

      - **model**: an explicit ``/model`` switch (``model_override``) wins;
        otherwise ``--model`` only applies to the provider it was given for
        (the session's startup provider).  After a switch the new provider's
        configured model, else its built-in default, is used (matching the
        toolbar display updated by ``/provider``).
      - **API type**: ``--api-type``, then the model-scoped configured
        value for that provider/model, then the built-in default.

    The resolved model / provider / API type are then handed to
    ``build_api_config`` -- the single resolution point (issue #70) -- so a
    provider switch rebuilds the immutable :class:`APIConfig`, exactly when a
    new one is needed.  Thinking mode is resolved into the config the same
    way: the shell's runtime ``/thinking`` toggle re-invokes the factory with
    ``thinking_override`` set, so the flip takes effect by rebuilding the
    config.  The CLI's TUI stream runner and Rich turn observer are injected
    here via the ``UIConfig`` (composition point), so every CLI entry point
    keeps the spinner / Enter-to-cancel and rendered output.

    Args:
        cli_api_type: API type passed via ``--api-type`` (may be None).
        cli_model: Model passed via ``--model`` (may be None).
        cli_provider: Provider passed via ``--provider`` (may be None).
        cli_effort: Reasoning depth passed via ``--effort``
            (may be None).
        verbose: Session default for verbose output (captured in the turn
            closure; per-call overrides still possible via
            ``turn_func(verbose=...)``).
        cli_thinking: The ``--thinking`` CLI flag for the session (may be
            None).  ``True`` forces thinking on; ``False``/``None`` leaves it
            to the provider's built-in default.  A ``thinking_override``
            passed to the returned factory wins over this value (the shell's
            runtime ``/thinking`` toggle).

    Returns:
        A callable ``factory(provider, model_override=None, thinking_override=None,
        silent=False) -> turn_func``.  ``silent=True`` swaps the injected
        turn observer for the silent variant (see
        :class:`janito.ui.observer.SilentTurnObserver`) while keeping the
        TUI stream runner -- used by the /compact compression call so its
        raw output is not echoed but the spinner still shows.
    """

    def turn_factory(
        provider: str | None,
        model_override: str | None = None,
        thinking_override: bool | None = None,
        effort_override: str | None = None,
        silent: bool = False,
    ) -> Callable:
        from janito.config_loaders import load_model_from_config
        from janito.providers.registry import get_provider

        # An explicit /model switch (model_override) always wins.  Otherwise
        # --model applies to the startup provider only; a switched-to
        # provider gets its own effective model (configured, else built-in
        # default).
        if model_override:
            model = model_override
        elif (provider or "").lower() == (cli_provider or "").lower():
            model = cli_model
        else:
            found = get_provider(provider)
            model = load_model_from_config(provider) or (found.default_model() if found is not None else None)
        # Thinking is resolved into the config at build time (issue #70): the
        # shell's runtime /thinking toggle passes thinking_override (the
        # shell's current flag) so a mid-session flip takes effect by
        # rebuilding the config; otherwise the session's --thinking flag
        # applies.
        thinking = thinking_override if thinking_override is not None else cli_thinking
        effort = effort_override if effort_override is not None else cli_effort
        # ``silent`` swaps the turn observer for the headless silent variant
        # (used by the /compact compression call, whose raw recap JSON must
        # not be echoed) while keeping the injected TUI stream runner, so
        # the spinner / Enter-to-cancel still work.  The default keeps the
        # Rich observer.
        observer = SilentTurnObserver() if silent else RichTurnObserver()
        return _make_turn_func(
            build_api_config(
                api_type=resolve_api_type(cli_api_type, provider, model),
                cli_model=model,
                cli_provider=provider,
                reasoning_effort=effort,
                thinking=thinking,
            ),
            ui_config=UIConfig(
                stream_runner=_run_with_progress_bar,
                observer=observer,
            ),
            session_verbose=verbose,
        )

    return turn_factory


def print_version_banner(console=None):
    """Print a banner with the version and the current working directory."""
    global _banner_printed

    from rich.console import Console

    if console is None:
        console = Console()
    console.print(f"Janito [cyan]{__version__}[/cyan] - Working at " f"[magenta]{display_path(os.getcwd())}[/magenta]")
    _banner_printed = True


def _print_privileges_notice(args) -> None:
    """Print the full-privileges warning after the version banner.

    The warning is only pending when the session fell back to the implicit
    full-privileges default (no ``-r``/``-w``/``-x`` flags, no ``privileges``
    config key). Explicit flags or config -- even ``rwx`` -- never set it,
    so no warning is shown for those.

    Called for both interactive sessions (``run_interactive_chat``) and
    single-prompt runs (``run_single_prompt``), always after ensuring the
    version banner was printed first.
    """
    from .. import privileges as _privileges_mod

    if not getattr(_privileges_mod, "full_privileges_warning_pending", False):
        return

    from rich.console import Console

    if not _banner_printed:
        print_version_banner()
    Console().print(
        "Warning: running with full privileges (rwx). " "Use -r/-w/-x to restrict.",
        style="yellow",
    )
    _privileges_mod.full_privileges_warning_pending = False


def _enable_requested_toolsets(args) -> None:
    """Enable web-only toolsets when requested via CLI flags."""
    from ..session_setup import SessionSetup

    SessionSetup().enable_toolsets()


def _resolve_system_prompt(args) -> tuple[str | None, bool]:
    """Return ``(effective_system_prompt, no_tools)`` for the enabled modes."""
    from ..session_setup import SessionSetup

    setup = SessionSetup(
        system_prompt=args.system_prompt,
        no_system_prompt=args.no_system_prompt,
    )
    return setup.effective_system_prompt(), setup.no_tools


def _print_tool_summary(args) -> None:
    """Report the total number of active and skipped tools."""
    from .. import privileges as _privileges_mod
    from ..tooling.tools_registry import get_all_tools, get_session_tool_schemas
    from ..tools import get_skipped_tools

    all_tools = get_all_tools()
    active_tools = get_session_tool_schemas()
    skipped_tools = get_skipped_tools()
    parts = [f"\u2713 {len(active_tools)} tool(s) active"]
    if _privileges_mod.running_privileges is not None:
        restricted = len(all_tools) - len(active_tools)
        if restricted:
            parts.append(f"{restricted} restricted")
    parts.append(f"{len(skipped_tools)} skipped")
    print(", ".join(parts))
    if skipped_tools and args.verbose:
        for tool_name, reason in skipped_tools.items():
            print(f"    - {tool_name}: {reason}")


def _normalize_identity(value) -> str | None:
    """Lowercase a session-identity value for comparison (``None``/``""`` -> ``None``)."""
    if value in (None, ""):
        return None
    return str(value).lower()


def _resume_identity_matches(state, provider, model, api_type) -> bool:
    """Whether the current session identity matches a saved snapshot.

    ``-C/--continue`` restores a saved conversation only when the provider,
    model and API type all match: the saved conversation lives in the per-API
    native format (and a server-side Responses conversation is chained from a
    saved response id), so it is only valid for the exact session identity
    that produced it.
    """
    return (
        _normalize_identity(state.get("provider")) == _normalize_identity(provider)
        and _normalize_identity(state.get("model")) == _normalize_identity(model)
        and _normalize_identity(state.get("api_type")) == _normalize_identity(api_type)
    )


def _resolve_resume(args, provider, model, api_type) -> tuple[dict | None, bool]:
    """Decide the resume state and whether this session should be persisted.

    ``-C/--continue`` restores the conversation this shell saved to
    ``./.janito/session.json``. The snapshot is only restored when the session
    identity (provider/model/API type) matches, so the per-API native
    conversation state stays valid. When it does not match (the user passed
    conflicting ``--provider``/``--model``/``--api-type`` flags), the session
    starts fresh **and is not persisted**, so the saved snapshot is not
    overwritten by the throwaway conversation.

    Returns:
        ``(resume_state, persist_session)``: the snapshot to restore (``None``
        for a fresh conversation) and whether this shell should write new
        snapshots on exit / after each interaction.
    """
    from rich.console import Console

    persist_session = not getattr(args, "no_history", False)
    if not getattr(args, "continue_session", False):
        return None, persist_session
    if getattr(args, "no_history", False):
        print("Nothing to resume: --no-history disables the conversation " "snapshot used by -C/--continue.")
        print("Starting a new conversation.")
        return None, persist_session
    from ..shell.persistence import load_conversation_state

    resume_state = load_conversation_state()
    if resume_state is None:
        print("No previous conversation found to resume in this directory " "(./.janito/session.json).")
        print("Starting a new conversation.")
        return None, persist_session
    if not _resume_identity_matches(resume_state, provider, model, api_type):
        saved = (
            f"{resume_state.get('provider') or '?'} / "
            f"{resume_state.get('model') or '?'} "
            f"({resume_state.get('api_type') or '?'})"
        )
        print(
            f"The saved conversation ({saved}) does not match this session's "
            f"provider/model/API type ({provider} / {model} / {api_type})."
        )
        print(
            "Starting a new conversation. To resume the saved one instead, "
            "run 'janito -C' without --provider/--model/--api-type."
        )
        print(
            "This new conversation will not be saved, so the saved " "snapshot above stays available for 'janito -C'."
        )
        return None, False
    Console().print(
        "Resumed previous conversation: "
        f"[cyan]{provider}[/cyan], model [magenta]{model}[/magenta], "
        f"API: [yellow]{api_type}[/yellow]. Type 'clear' to start fresh."
    )
    return resume_state, persist_session


def _print_resume_recap(shell, *, limit: int = 5) -> None:
    """Echo the most recent messages after a ``-C/--continue`` resume.

    Display-only recap so the user can see where the previous session left
    off: the full restored conversation is still what gets sent to the model;
    this prints the last ``limit`` user/assistant messages **in full**
    (tool-call / reasoning rows are hidden and the recap is anchored on the
    most recent user prompt, see
    :func:`janito.shell.conversation.recent_conversation_rows`).  No-op when
    there are no messages to show.
    """
    from rich.console import Console
    from rich.rule import Rule

    from ..shell.conversation import recent_conversation_rows

    rows = recent_conversation_rows(shell, limit=limit)
    if not rows:
        return
    console = Console(markup=False)
    console.print(Rule("Resumed conversation", style="bold cyan"))
    for role, content in rows:
        label = "You:" if role == "user" else "Assistant:"
        style = "bold green" if role == "user" else "bold"
        console.print(label, style=style)
        console.print(content if content else "(no text)")
        console.print()


def run_interactive_chat(args):
    """Run the interactive chat session.

    Args:
        args: Parsed command line arguments
    """
    _print_privileges_notice(args)
    _enable_requested_toolsets(args)

    # Check if any skills are installed
    from ..tooling.skills_provider import get_skills_provider

    skills = get_skills_provider().list_skills()
    if skills:
        print(f"\u2713 {len(skills)} skill(s) available")

    _print_tool_summary(args)

    # Resolve the model for display (and bind CLI model/provider so every
    # prompt uses the same configuration without environment variables).
    cli_model = getattr(args, "model", None)
    cli_provider = getattr(args, "provider", None)
    cli_effort = getattr(args, "effort", None)
    cli_api_type = getattr(args, "api_type", None)
    try:
        _, _, model = resolve_runtime_config(cli_model, cli_provider)
    except ValueError:
        model = cli_model or "(not configured)"
    provider = cli_provider or load_provider_from_config() or "(not configured)"
    try:
        api_type = resolve_api_type(cli_api_type, provider, cli_model)
    except ValueError:
        api_type = cli_api_type or "(not configured)"
    from rich.console import Console

    # Annotate where the conversation state lives: the Responses API keeps
    # it server-side (chained via previous_response_id) unless the
    # stateless-mode ("keep in server") config flips it to stateless,
    # in which case the client re-sends the full history; Completions and
    # other API types always keep history client-side.  The flag is resolved
    # by the single helper the Responses client itself uses.
    if api_type == "Responses" and provider != "(not configured)":
        from ..llm_clients.openai.responses_state import stateless_mode

        state = "client-side" if stateless_mode(provider, model) else "server-side"
    else:
        state = "client-side"
    Console().print(
        f"Using [cyan]{provider}[/cyan], model [magenta]{model}[/magenta], "
        f"API: [yellow]{api_type}[/yellow] [green]({state})[/green]"
    )
    Console().print(
        "Keys: [bold green]F2[/bold green] - Clear conversation, " '[bold green]F12[/bold green] - Send "Do It"'
    )
    print("Starting interactive chat session. Type '/exit' or CTRL-D to end the session")

    # -C/--continue: decide whether to restore the conversation this shell
    # saves to ./.janito/session.json after every interaction.
    resume_state, persist_session = _resolve_resume(args, provider, model, api_type)

    # Choose system prompt based on enabled modes
    effective_system_prompt, no_tools = _resolve_system_prompt(args)

    shell = InteractiveShell(
        model=model,
        no_history=args.no_history,
        provider=None if provider == "(not configured)" else provider,
        api_type=cli_api_type,
        effort=cli_effort,
    )
    # Factory to (re)build the run-turn function per provider: ``/provider``
    # calls
    # it with the new provider so the switch takes effect in real time
    # (provider, model and API type are re-resolved, see _make_turn_factory).
    # The session's verbose flag is baked into the config at build time
    # (issue #70); the shell keeps its own copy for /status display.
    shell.turn_factory = _make_turn_factory(
        cli_api_type,
        cli_model,
        cli_provider,
        cli_effort,
        verbose=args.verbose,
        cli_thinking=getattr(args, "thinking", False),
    )
    if resume_state is not None:
        # Restore the whole conversation (system prompt included) exactly as
        # it was saved; the identity was matched above, so the native state is
        # valid for this session.
        if not shell.restore_conversation(resume_state):
            print("Could not restore the saved conversation; starting a new one.")
            shell.initialize_history(system_prompt=effective_system_prompt)
        else:
            # Echo the last few messages so the user can see where the
            # previous session left off. Display-only: the full restored
            # conversation is still what gets sent to the model.
            _print_resume_recap(shell)
    else:
        shell.initialize_history(system_prompt=effective_system_prompt)
    # Mirror the conversation to ./.janito/session.json after every
    # interaction so `janito -C` can resume it later (--no-history keeps it
    # in memory only, mirroring the web UI's --no-history semantics).  In the
    # -C identity-mismatch case persistence stays off so the saved snapshot
    # is not overwritten by the throwaway fresh session.
    shell.persist_history = persist_session
    shell.run(
        turn_func=shell.turn_factory(cli_provider, effort_override=cli_effort),
        verbose=args.verbose,
        no_tools=no_tools,
        thinking=args.thinking,
    )


def _build_single_prompt_context(args):
    """Build ``(messages_history, tools_to_use)`` for a single prompt run."""
    from ..session_setup import SessionSetup

    setup = SessionSetup(
        system_prompt=args.system_prompt,
        no_system_prompt=args.no_system_prompt,
    )
    return setup.messages_context(), setup.tools_arg()


def run_single_prompt(args):
    """Run a single prompt.

    Args:
        args: Parsed command line arguments
    """
    import sys

    if not _banner_printed:
        print_version_banner()
    _print_privileges_notice(args)
    _enable_requested_toolsets(args)

    prompt = args.prompt

    if not prompt:
        print("Error: Empty prompt provided.", file=sys.stderr)
        sys.exit(1)

    # Initialize messages history (with or without system prompt based on -Z or -S flag)
    messages_history, tools_to_use = _build_single_prompt_context(args)

    try:
        # Select the API type for the provider: --api-type, then the
        # provider's configured api-type, then its built-in default, and
        # build the resolved per-session APIConfig once (issue #70).  The
        # CLI's TUI stream runner and Rich turn observer are injected at this
        # composition point via the UIConfig.
        turn_func = _make_turn_func(
            build_api_config(
                api_type=resolve_api_type(
                    getattr(args, "api_type", None),
                    getattr(args, "provider", None),
                ),
                cli_model=getattr(args, "model", None),
                cli_provider=getattr(args, "provider", None),
                reasoning_effort=getattr(args, "effort", None),
                thinking=getattr(args, "thinking", False),
            ),
            ui_config=UIConfig(
                stream_runner=_run_with_progress_bar,
                observer=RichTurnObserver(),
            ),
            session_verbose=args.verbose,
        )
        # In Responses mode the system prompt is sent as `instructions` on the
        # first turn (extracted from the seeded history); in Completions mode
        # the same value is carried inside `previous_messages`.
        instructions = None
        if messages_history and messages_history[0].get("role") == "system":
            instructions = messages_history[0].get("content")
        turn_func(
            prompt,
            previous_messages=messages_history,
            instructions=instructions,
            tools=tools_to_use,
        )
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(130)
    except RequestCancelled:
        # Enter was pressed while waiting for the API response.
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(130)
