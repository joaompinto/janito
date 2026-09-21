#!/usr/bin/env python3
"""
OpenAI CLI - A simple command-line interface to interact with OpenAI-compatible endpoints.

This CLI resolves its configuration from local files (no environment variables):
- API key:  from ~/.janito/auth.json for the active provider (--set-api-key)
- Endpoint: the provider's built-in default, or an endpoint override in
            ~/.janito/config.json (--set endpoint=...)
- Model:    --model, or the provider's configured model (--set model=...)

API keys are stored securely in ~/.janito/auth.json using the --set-api-key option.

The CLI includes function calling tools that can be used by the AI model.

Usage:
    python -m janito "Your prompt here"                    # Single prompt mode
    echo "Your prompt" | python -m janito                  # Pipe input mode
    python -m janito                                       # Interactive chat session
    python -m janito --set-api-key <key> --provider <name> # Store API key
"""


import importlib.util
import sys

from . import privileges as _privileges_mod
from .cli.chat import print_version_banner, run_interactive_chat, run_single_prompt
from .cli.handlers import (
    handle_config_interactive,
    handle_delete_secret,
    handle_get_config,
    handle_get_secret,
    handle_info,
    handle_install_plugin,
    handle_install_skill,
    handle_list_keys,
    handle_list_mcp,
    handle_list_models,
    handle_list_plugins,
    handle_list_secrets,
    handle_list_skills,
    handle_list_tools,
    handle_set_api_key,
    handle_set_config,
    handle_set_secret,
    handle_show_config,
    handle_show_providers,
    handle_show_system_prompt,
    handle_uninstall_plugin,
    handle_uninstall_skill,
    handle_unset_config,
)
from .cli.handlers.variants import handle_create_variant, handle_delete_variant
from .cli.input import read_stdin_prompt
from .cli.logging_config import setup_logging
from .cli.parser import create_parser
from .cli.setup import validate_runtime_config, validate_system_prompt_file
from .config_dir import set_config_dir, set_local_config_mode
from .privileges import Privileges
from .providers.validation import validate_model_name, validate_provider_name


def _flatten(values):
    """Flatten [['a', 'b'], ['c']] -> ['a', 'b', 'c']"""
    if not values:
        return []
    flat = []
    for item in values:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def _track_rc(exit_code: int, new_rc: int) -> int:
    """Return the first non-zero exit code seen so far."""
    return exit_code if exit_code != 0 else new_rc


def _setup_runtime(args) -> int | None:
    """Apply early CLI overrides (config dir, local mode, logging, provider, privileges)."""
    set_config_dir(getattr(args, "config_dir", None))
    set_local_config_mode(getattr(args, "local", False))
    setup_logging(args.log)

    # --no-tools: disable all tools (autoload toolsets, skill tools,
    # plugin tools, and server-side/builtin provider tools).
    # Applied before any registry access so the lazy discovery in
    # tools_registry.ensure_initialized() never loads anything.
    if getattr(args, "no_tools", False):
        from .tooling.tools_registry import disable_skills, disable_tools_loading

        disable_tools_loading()
        disable_skills()

    # --no-tasks: stop loading the tasks toolset (StartTask/StopTask/
    # WaitForTask/ListTasks).  Everything else -- and the skill tools -- stays
    # enabled.  Applied before any registry access so the lazy discovery
    # filters "tasks" out of the autoload toolsets.
    if getattr(args, "no_tasks", False):
        from .tooling.tools_registry import disable_toolset

        disable_toolset("tasks")

    # Whenever --provider <name> is used, verify it is a supported provider
    # (i.e. one that maps to a built-in provider config). Normalize it to
    # its canonical casing so every downstream consumer (config scoping,
    # runtime resolution, auth store) uses a consistent provider name.
    if getattr(args, "provider", None):
        try:
            args.provider = validate_provider_name(args.provider)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Whenever --model <name> is used, verify it is one of the provider's
    # built-in models (the base provider's models for variants); "custom"
    # and "openrouter" have no usable built-in model list and accept any
    # model name.  The provider is --provider (canonicalized above), else
    # the configured default.  On success the model is normalized to its
    # canonical built-in casing.
    if getattr(args, "model", None):
        from .general_config import load_provider_from_config

        provider = args.provider or load_provider_from_config()
        if provider:
            try:
                args.model = validate_model_name(provider, args.model)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1

    _setup_privileges(args)
    return None


def _setup_privileges(args) -> None:
    """Configure the running privileges.

    Precedence (highest first):
    1. Explicit ``-r``/``-w``/``-x`` CLI flags -- they override the
       configured default, so e.g. ``-w`` alone grants write-only (no
       default read).
    2. The ``privileges`` config key (``--set privileges=rwx``, issue #89):
       the session default when no privilege flag is given.
    3. The built-in default: **full privileges** (READ/WRITE/EXEC granted).
       A warning is printed in this case; no warning is shown when the
       effective privileges come from explicit ``-r``/``-w``/``-x`` flags
       or from the config key (even when those grant full ``rwx``).
    """
    if args.read or args.write or args.exec:
        if _privileges_mod.running_privileges is None:
            _privileges_mod.running_privileges = Privileges()
        if args.read:
            _privileges_mod.running_privileges.READ = True
        if args.write:
            _privileges_mod.running_privileges.WRITE = True
        if args.exec:
            _privileges_mod.running_privileges.EXEC = True
        return

    # No -r/-w/-x flag: use the configured default privileges
    # (--set privileges=...), else fall back to full privileges with a warning.
    if _privileges_mod.running_privileges is None:
        from .config_loaders import load_privileges_from_config

        _privileges_mod.running_privileges = load_privileges_from_config()
        if _privileges_mod.running_privileges is None:
            _privileges_mod.running_privileges = Privileges(READ=True, WRITE=True, EXEC=True)
            # Deferred: printed after the version banner (see
            # cli.chat._print_privileges_notice).
            _privileges_mod.full_privileges_warning_pending = True


def _has_batch_config_ops(args) -> bool:
    """Return True when any batch config operation flag was passed."""
    return any(
        flag is not None
        for flag in (
            args.set,
            args.unset,
            args.get,
            args.set_secret,
            args.delete_secret,
        )
    )


def _handle_batch_config(args) -> int | None:
    """Handle batch config operations (--set, --unset, --get, secrets)."""
    if not _has_batch_config_ops(args):
        return None

    exit_code = 0
    # Provider used for provider-scoped config keys (e.g. model). It is
    # taken from --provider, falling back to the configured provider value.
    cli_provider = getattr(args, "provider", None)

    if args.set is not None:
        exit_code = _track_rc(exit_code, handle_set_config(_flatten(args.set), cli_provider))
    if args.unset is not None:
        exit_code = _track_rc(exit_code, handle_unset_config(_flatten(args.unset), cli_provider))
    if args.get is not None:
        exit_code = _track_rc(exit_code, handle_get_config(_flatten(args.get), cli_provider))
    if args.set_secret is not None:
        exit_code = _track_rc(exit_code, handle_set_secret(_flatten(args.set_secret)))
    if args.delete_secret is not None:
        exit_code = _track_rc(exit_code, handle_delete_secret(_flatten(args.delete_secret)))

    return exit_code


def _dispatch_flag_command(args) -> int | None:
    """Run the single flag-driven command handler, if any was requested."""
    handlers = [
        (args.info, lambda: handle_info(args)),
        (args.show_config, lambda: handle_show_config(args)),
        (args.show_system_prompt, lambda: handle_show_system_prompt(args)),
        (args.config, lambda: handle_config_interactive()),
        (args.list_keys, lambda: handle_list_keys(args)),
        (args.show_providers, lambda: handle_show_providers(args)),
        (args.set_api_key, lambda: handle_set_api_key(args)),
        (args.list_secrets, lambda: handle_list_secrets(args)),
        (args.get_secret is not None, lambda: handle_get_secret(args)),
        (args.install_skill, lambda: handle_install_skill(args.install_skill)),
        (args.list_skills, lambda: handle_list_skills(args)),
        (args.uninstall_skill, lambda: handle_uninstall_skill(args.uninstall_skill)),
        (args.install_plugin, lambda: handle_install_plugin(args.install_plugin)),
        (args.uninstall_plugin, lambda: handle_uninstall_plugin(args.uninstall_plugin)),
        (args.list_tools, lambda: handle_list_tools(args)),
        (args.list_mcp, lambda: handle_list_mcp(args)),
        (args.list_models, lambda: handle_list_models(args)),
        (args.list_plugins, lambda: handle_list_plugins(args)),
        (args.create_variant, lambda: handle_create_variant(args.create_variant)),
        (args.delete_variant, lambda: handle_delete_variant(args.delete_variant)),
    ]
    for enabled, handler in handlers:
        if enabled:
            return handler()
    return None


def _run_web(args) -> int:
    """Run the web UI server, failing with a hint when extras are missing."""
    # The [web] extra (fastapi / uvicorn) is optional, so check its
    # availability explicitly instead of a defensive try/except
    # ImportError fallback, and fail with an actionable message.
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("uvicorn") is None:
        print(
            "Error: the web UI requires optional dependencies that " "are not installed.",
            file=sys.stderr,
        )
        print("Install them with:\n\n    pip install janito[web]\n", file=sys.stderr)
        return 1

    from .web.backend.app import run_web

    run_web(args)
    return 0


def _declare_prompt_surface(args) -> None:
    """Declare the process's mid-turn question surface for AskUser.

    The AskUser tool's ``should_load()`` gate loads only when a surface can
    answer a question raised mid-turn:

    - web mode (``--web``): in-browser question cards, including headless
      deployments with no TTY stdin;
    - the interactive shell: stdin prompting (Rich table + ``input()``),
      where the user is at the keyboard -- detected as *no positional
      prompt* and *stdin is a TTY*, evaluated before
      :func:`read_stdin_prompt` so piped input cannot flip it.

    Single-prompt runs (positional or piped) declare nothing: nobody is
    watching mid-run, so the tool stays skipped and the model is never
    invited to ask questions. Declared before plugin loading -- the earliest
    point that can trigger tool registry access
    (``register_plugin_tools`` -> ``ensure_initialized``) -- and again in
    ``create_app()`` (idempotent), so plugins and the routers both see it.
    """
    if getattr(args, "web", False):
        from .tooling.prompting import enable_browser_prompts

        enable_browser_prompts()
        return

    if getattr(args, "prompt", None) is None:
        import sys

        if sys.stdin.isatty():
            from .tooling.prompting import enable_browser_prompts

            enable_browser_prompts()


def _reject_continue_with_input(args, *, piped: bool) -> int | None:
    """Reject ``-C/--continue`` outside interactive chat (a prompt is present).

    ``-C`` can only resume an interactive session; with a positional prompt or
    piped stdin there is nothing to resume, so fail with an actionable error
    instead of silently ignoring the flag.

    Returns:
        ``1`` when the flag is misused, otherwise ``None``.
    """
    if not getattr(args, "continue_session", False) or getattr(args, "prompt", None) is None:
        return None
    source = "piped input" if piped else "a prompt argument"
    print(
        "Error: -C/--continue applies to interactive chat sessions only " f"(run 'janito -C' without {source}).",
        file=sys.stderr,
    )
    return 1


def _apply_resume_session(args) -> None:
    """Backfill the session identity from the saved conversation for ``-C``.

    ``janito -C`` resumes the last interactive conversation saved in the
    current working directory.  The saved session's provider / model / API
    type / thinking / effort are reused so the restored conversation stays
    API-compatible even when the configured defaults changed since it was
    saved.  Explicit ``--provider`` / ``--model`` / ``--api-type`` /
    ``--thinking`` / ``--effort`` flags always win and are never
    overridden here -- ``run_interactive_chat`` then starts a fresh
    conversation when they do not match the saved session.

    No-op when ``-C`` was not passed, in web mode (the web UI has its own
    session persistence), or under ``--no-history`` (no snapshot is kept).
    """
    if not getattr(args, "continue_session", False):
        return
    if getattr(args, "web", False) or getattr(args, "no_history", False):
        return
    from .shell.persistence import load_conversation_state

    state = load_conversation_state()
    if not state:
        return
    # Backfill only the values the user did not set explicitly.
    if state.get("provider") and not getattr(args, "provider", None):
        args.provider = state["provider"]
    if state.get("model") and not getattr(args, "model", None):
        args.model = state["model"]
    if state.get("api_type") and not getattr(args, "api_type", None):
        args.api_type = state["api_type"]
    if state.get("effort") and not getattr(args, "effort", None):
        args.effort = state["effort"]
    if not getattr(args, "thinking", False):
        args.thinking = bool(state.get("thinking"))


def _dispatch_chat(args, stdin_prompt: str | None) -> int | None:
    """Dispatch to the interactive shell or single-prompt mode.

    Piped stdin (``stdin_prompt``) also selects single-prompt mode.  ``-C`` /
    ``--continue`` is interactive-only: with a positional prompt or piped
    input there is nothing to resume, so it is rejected here (after web mode
    and config validation have already been handled by ``main``).
    """
    if stdin_prompt:
        args.prompt = stdin_prompt
    if args.prompt is None:
        run_interactive_chat(args)
    else:
        exit_code = _reject_continue_with_input(args, piped=bool(stdin_prompt))
        if exit_code is not None:
            return exit_code
        run_single_prompt(args)
    return None


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Apply the -c/--config-dir override, logging, provider normalization and
    # privilege flags as early as possible.
    exit_code = _setup_runtime(args)
    if exit_code is not None:
        return exit_code

    # Prune accounting entries older than 10 days on every startup so
    # <config dir>/accounting.db does not grow unbounded (issue #76). Runs
    # after _setup_runtime because the config dir (which locates the
    # database) is applied there; best-effort and never raises.
    from .tooling.accounting import prune_old_entries

    prune_old_entries()

    # Handle batch config operations (--set, --unset, --get, secrets)
    exit_code = _handle_batch_config(args)
    if exit_code is not None:
        return exit_code

    _declare_prompt_surface(args)

    # Load plugins before any registry/shell access so plugin tools,
    # commands and system-prompt sections are registered for the session.
    # Runs after _setup_runtime so privileges are already applied.
    #
    # - Plugins installed in ~/.janito/plugins are autoloaded unless
    #   --no-plugins is passed (they are independent of --no-tools).
    # - Plugins explicitly requested with --plugin DIR are always loaded.
    if not getattr(args, "no_tools", False) and (
        getattr(args, "plugin", None) or not getattr(args, "no_plugins", False)
    ):
        from .plugin_manager import load_installed_plugins, load_plugins

        # Show the version banner before any plugin loading messages so the
        # session identity is visible first.
        print_version_banner()

        if not getattr(args, "no_plugins", False):
            load_installed_plugins()
        if getattr(args, "plugin", None):
            load_plugins(args.plugin)

    # Handle single flag-driven commands (--info, --config, --list-*, ...)
    exit_code = _dispatch_flag_command(args)
    if exit_code is not None:
        return exit_code

    # -C/--continue: reuse the saved session's identity so the restored
    # conversation stays API-compatible (before runtime validation, which
    # resolves provider/model/api key against the CLI flags).
    _apply_resume_session(args)

    # Validate that the runtime configuration (API key from auth store,
    # endpoint from provider default/config, model from --model or config)
    # can be resolved before starting a session.
    validate_runtime_config(args)

    # Validate that the configured system-prompt-file (--set
    # system-prompt-file=...) exists before a session starts, failing fast
    # with an actionable error instead of surfacing only when the system
    # prompt is rendered.
    validate_system_prompt_file(args)

    # Web mode: skip stdin check — the server doesn't consume stdin.
    # Must come BEFORE read_stdin_prompt() to avoid blocking on non-tty
    # stdin in headless / service contexts.
    if args.web:
        return _run_web(args)

    # Check for stdin input
    stdin_prompt = read_stdin_prompt()

    # Dispatch to the interactive shell or a single prompt (also rejecting
    # -C/--continue, which is interactive-only, when a prompt is present).
    return _dispatch_chat(args, stdin_prompt)


if __name__ == "__main__":
    # Propagate the exit code returned by main() (e.g. 1 for aborted config
    # changes like setting an API type whose required package is missing) so
    # scripts and CI can observe failures.
    sys.exit(main())
