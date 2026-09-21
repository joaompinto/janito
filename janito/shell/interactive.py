"""
Interactive shell implementation using prompt_toolkit.
"""

import contextlib
import copy
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from ..conversation_utils import rollback_to_last_turn
from ..llm_clients import RequestCancelled
from ..llm_clients.openai.responses_items import message_item
from ..tooling.turn_privileges import (
    reset_turn_privileges,
    resolve_turn_privileges,
    set_turn_privileges,
)
from .conversation import effective_rows
from .session import _SessionMixin

_rich_console = Console(markup=False)

if TYPE_CHECKING:
    from .cmds import CmdHandler


class InteractiveShell(_SessionMixin):
    """Interactive shell for chat sessions using prompt_toolkit."""

    def __init__(
        self,
        model: str,
        commands: list["CmdHandler"] | None = None,
        no_history: bool = False,
        provider: str | None = None,
        thinking: bool = False,
        api_type: str | None = None,
        effort: str | None = None,
    ):
        """
        Initialize the interactive shell.

        Args:
            model: The model name to display in the prompt
            commands: List of command handlers (auto-loaded if not provided)
            no_history: If True, use in-memory history only (no file persistence)
            provider: The provider name in effect for this session (e.g. from
                ``--provider``, updated by ``/provider``). When set, the
                status bar reports it; otherwise it falls back to the
                configured default provider.
            thinking: If True, enable thinking mode for the session.
            api_type: The API type passed via ``--api-type`` (e.g. ``Gemini``,
                ``Responses``, ``Completions``). ``None`` when the CLI flag
                was not given, in which case the effective API type resolves
                from the provider/model configuration (see
                :func:`janito.general_config.resolve_api_type`). Surfaced by
                ``/status`` so it reports the API type actually in use.
            effort: Reasoning depth passed via ``--effort``
                (may be None). Surfaced by ``/status`` so it reports the
                reasoning level actually in use (CLI flag first, then the
                model-scoped configured value, then the built-in default).
        """
        self.model = model
        self.provider = provider
        self.thinking = thinking
        self.api_type = api_type
        self.effort = effort
        # Set by /model for the current session: the explicit model override
        # that the turn_factory (re)built by /provider and /model consults
        # so
        # the runtime model matches the displayed one.  Cleared when /provider
        # switches to another provider (the new provider resolves its own
        # model).
        self.model_override = None
        self.no_history = no_history
        # The active system prompt; (re)set by initialize_history() or a
        # conversation restore.  Defaulted here so get_system_prompt() and the
        # snapshot helpers never hit an unset attribute on a bare shell.
        self._system_prompt: str | None = None
        # When True, the shell mirrors its conversation to
        # ``./.janito/session.json`` after every interaction so ``janito -C``
        # can resume it later.  Enabled by the CLI chat entry point only (not
        # for bare/test shells); always off under ``--no-history``.
        self.persist_history = False
        from .stack import ConversationStack

        self.conversation_stack = ConversationStack()
        # Conversation messages (role/content dicts) passed to the AI as
        # context
        self.messages_history: list[dict[str, Any]] = []
        # Rows /history would render, recorded every time a new user prompt
        # is about to be sent (the count before that turn). Error/cancel
        # recovery truncates messages_history back to the most recent one,
        # and /rewind undoes the last exchange by truncating back to it and
        # dropping it, so the list lets /rewind step back one turn at a time
        # and lets /history mark where each turn started.
        self.history_turns: list[int] = []
        # Server-side conversation handle for the Responses API: the id of the
        # last response, passed as `previous_response_id` on the next turn.
        # None in Completions mode (where history lives in messages_history),
        # when no Responses conversation has started yet, and for stateless
        # Responses providers (which never chain with an id).
        self.previous_response_id: str | None = None
        # Client-side Responses input items. For stateless Responses providers
        # (e.g. DeepSeek, whose /responses endpoint keeps no server state):
        # the full conversation, re-sent on every request via `previous_items`.
        # For server-side Responses providers (e.g. OpenAI): the pending user
        # messages of Enter-cancelled turns, re-sent as input items chained
        # from the last completed response id (see previous_response_id) and
        # cleared again once a turn completes. None in Completions mode and
        # for server-side Responses providers with no pending messages.
        self.conversation_items: list[dict[str, Any]] | None = None
        # Index into conversation_items marking the last known-good state;
        # /rewind truncates back to here.
        self.conversation_turn: int = 0
        # Chain of completed server-side Responses response ids, in turn
        # order. Every successful turn of a server-side Responses provider
        # (e.g. OpenAI) appends its final response id; /rewind truncates
        # back to the recorded start and re-points previous_response_id at
        # the response that preceded the rolled-back exchange, so the next turn
        # continues from there instead of resetting the whole server-side
        # conversation. Empty in Completions mode and for stateless
        # Responses providers (which never chain with an id).
        self.response_chain: list[str] = []
        # Index into response_chain marking the last known-good state;
        # /rewind truncates back to here.
        self.response_turn: int = 0
        # Display-only mirror of completed server-side Responses turns (e.g.
        # OpenAI), kept client-side purely so /history can render the
        # conversation: the real history lives on the server (chained via
        # previous_response_id) and is never fetched back. Same Responses
        # input-item format as conversation_items (message / function_call /
        # function_call_output); the system prompt stays in messages_history.
        # Empty in Completions mode and for stateless Responses providers
        # (which mirror through conversation_items instead).
        self.mirrored_history: list[dict[str, Any]] = []
        # Index into mirrored_history marking the last known-good state;
        # /rewind truncates back to here.
        self.mirrored_turn: int = 0
        # Set True by the F2 key binding; signals the run loop to clear
        # history and start a fresh conversation
        self.restart_requested = False
        # Set True by the F12 key binding; signals the run loop to
        # auto-send a "Do It" prompt
        self.do_it_requested = False
        # Set True by the /exit command handler; signals the run loop to
        # break and end the session
        self.exit_requested = False
        # Set by /multi for the next prompt only; automatically resets
        # after a multiline input is submitted
        self.multiline_mode = False

        # Auto-load registered commands if not provided
        if commands is None:
            from .cmds import get_registered_commands

            self.commands = get_registered_commands()
        else:
            self.commands = commands

        # Create session after commands are loaded
        self.session = self._create_session()

    def initialize_history(self, system_prompt: str | None = None) -> None:
        """
        Initialize the messages history.

        Args:
            system_prompt: Optional system prompt to prepend
        """
        # Full-stack clear (issue #124): a fresh conversation drops all pushed levels.
        try:
            self.conversation_stack.clear()
        except AttributeError:
            pass
        self._system_prompt = system_prompt  # stored so it can be restored on F2/clear without re-reading config
        if system_prompt:
            self.messages_history = [{"role": "system", "content": system_prompt}]
        else:
            self.messages_history = []
        # A fresh conversation has no recorded turns yet: they are
        # each time a user prompt is about to be sent (see _run_turn).
        self.history_turns = []
        # A fresh conversation also starts a fresh server-side conversation:
        # the next turn must not chain to the previous response id, and any
        # stateless client-side items history is dropped.
        self.previous_response_id = None
        self.conversation_items = None
        self.conversation_turn = 0
        self.response_chain = []
        self.response_turn = 0
        # A fresh conversation also clears the /history display mirror of
        # completed server-side turns.
        self.mirrored_history = []
        self.mirrored_turn = 0

    def get_system_prompt(self) -> str | None:
        """Get the current system prompt."""
        return self._system_prompt

    def _get_user_input(self) -> str | None:
        """Prompt for the next input line.

        Returns:
            The user's input, ``None`` to end the session (Ctrl+D, or a
            confirmed Ctrl+C quit), or ``""`` to continue without processing
            (Ctrl+C declined, or F2 restart requested).
        """
        # Use HTML formatting for prompt
        prompt_text = HTML(f'<style bg="#00008b">{self.model} # </style>')

        try:
            result = self.session.prompt(prompt_text, multiline=self.multiline_mode)
            if result is None and self.restart_requested:
                # F2 was pressed: the key binding exits the prompt app with a
                # ``None`` result, the same value the run loop uses to signal
                # "quit". Translate it into a "continue without processing"
                # signal here; the run loop handles the restart right after.
                return ""
            return result
        except KeyboardInterrupt:
            # User pressed Ctrl+C - ask to confirm quit.  When parallel tasks
            # are still running (issue #101), surface them first and ask about
            # terminating them, so the user cannot accidentally orphan
            # background children (and so they know the atexit hook will kill
            # them whatever exit path they take).
            running = self._running_tasks()
            if running:
                self._print_running_tasks_notice()
                question = "\nDo you want to exit and terminate all tasks? (y/n): "
            else:
                question = "\nDo you want to quit the conversation? (y/n): "
            try:
                confirm = self.session.prompt(question)
                if confirm and confirm.lower().strip() in ["y", "yes"]:
                    if running:
                        # Immediate SIGKILL of every live child (no grace);
                        # the atexit cleanup stays the safety net for every
                        # other exit path.
                        self._kill_all_tasks()
                    return None  # User wants to quit
                return ""  # User doesn't want to quit, continue to next iteration
            except (KeyboardInterrupt, EOFError):
                # User pressed Ctrl+C or Ctrl+D again during confirmation
                if running:
                    self._kill_all_tasks()
                return None  # Quit
        except EOFError:
            # User pressed Ctrl+D at main prompt
            return None

    def _kill_all_tasks(self) -> None:
        """Terminate all live background tasks immediately (issue #101).

        Delegates to :meth:`TaskManager.kill_all` (SIGKILL, no grace).  Best
        effort: the atexit ``cleanup`` hook is the fallback safety net, so a
        failure here (e.g. the tasks toolset is not loaded) must not block the
        quit.  Prints a short confirmation of what was stopped.
        """
        try:
            from ..taskmanager import task_manager

            killed = task_manager.kill_all()
        except Exception:  # noqa: BLE001 - atexit cleanup is the safety net
            return
        if killed:
            _rich_console.print(f"Terminated {len(killed)} running task(s).")

    def _handle_restart_request(self) -> bool:
        """Handle the F2 restart keybinding; True when the loop continues."""
        if not self.restart_requested:
            return False
        # Clear screen before printing the message
        os.system("cls" if os.name == "nt" else "clear")
        self._reset_conversation("[Keybinding F2] Conversation history cleared. Starting fresh conversation.")
        return True

    def _reset_conversation(self, message: str) -> None:
        """Reset to a fresh conversation while preserving the system prompt."""
        self.initialize_history(system_prompt=self._system_prompt)
        _rich_console.print(message, style="bold black on white")
        from ..taskmanager import task_manager

        running = task_manager.running_tasks()
        if running:
            count = len(running)
            noun = "task" if count == 1 else "tasks"
            _rich_console.print(f"{count} {noun} still running, use /tasks for viewing.")

    def _handle_command(self, user_input: str) -> bool:
        """Dispatch to registered command handlers; True when handled."""
        for cmd_handler in self.commands:
            if cmd_handler.handle(self, user_input):
                return True
        return False

    def _is_unknown_command(self, user_input: str) -> bool:
        """Reject unrecognized slash commands; True when handled."""
        if user_input.strip().startswith("/"):
            cmd_name = user_input.strip().split()[0]
            print(f"Unknown command: {cmd_name}")
            print("Type /help to see available commands.")
            return True
        return False

    @contextlib.contextmanager
    def _cooked_terminal(self) -> Iterator[None]:
        """Temporarily restore the terminal to cooked mode (POSIX only).

        prompt_toolkit drives the terminal in raw mode while the prompt app
        is running; by the time a ``!cmd`` is dispatched the terminal is
        already back to cooked mode, but forcing it here guarantees that
        full-screen programs (vim, less, ...) start from a sane state and
        that a command that crashes mid-way doesn't leave the shell with a
        raw / no-echo terminal. On Windows and when stdin is not a TTY
        (e.g. tests) there is nothing to restore.
        """
        if os.name == "nt" or not sys.stdin.isatty():
            yield
            return

        import termios

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        cooked = termios.tcgetattr(fd)
        cooked[3] |= termios.ICANON | termios.ECHO
        try:
            termios.tcsetattr(fd, termios.TCSANOW, cooked)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, saved)

    def _run_shell_command(self, user_input: str) -> None:
        """Execute a ``!cmd`` shell command.

        The command inherits the real terminal (stdin/stdout/stderr are not
        captured) so interactive, full-screen programs such as vim or less
        work; plain commands print directly to the terminal. While the
        command runs, SIGINT is ignored in the parent (the child keeps the
        default handler unless it installs its own, e.g. vim) so Ctrl+C is
        handled by the running program instead of aborting the wait and
        leaving it orphaned. There is no timeout: interactive commands can
        legitimately run for as long as the user needs, and a command that
        hangs can be interrupted the usual way.
        """
        cmd = user_input[1:].strip()
        if not cmd:
            return
        print(f"[Shell] Executing: {cmd}")
        try:
            with self._cooked_terminal():
                # Mirror os.system()'s SIGINT handling: block it in the
                # parent while the child runs so the child (which inherits
                # the default disposition) can deal with Ctrl+C itself.
                old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
                try:
                    result = subprocess.run(cmd, shell=True)
                finally:
                    signal.signal(signal.SIGINT, old_handler)
            print(f"[Shell] Exit code: {result.returncode}")
        except KeyboardInterrupt:
            print("\n[Shell] Command interrupted", file=sys.stderr)

    def _dispatch_input(self, user_input: str) -> bool:
        """Handle clear/command/unknown/shell input; True when consumed."""
        if user_input.lower() == "clear":
            # Reset to a fresh conversation while preserving the system
            # prompt (matches startup behaviour). A plain .clear() would
            # drop the system prompt and leave an empty history.
            self._reset_conversation("Conversation history cleared. Starting fresh conversation.")
            return True

        # Handle registered commands
        if self._handle_command(user_input):
            return True

        # Reject unrecognized slash commands instead of sending them to the LLM
        if self._is_unknown_command(user_input):
            return True

        # Handle !cmd for direct shell execution
        if user_input.startswith("!"):
            self._run_shell_command(user_input)
            return True

        return False

    def _run_turn(self, user_input: str, tools: list[dict[str, Any]] | None = None) -> None:
        """Send a prompt to the AI and update the conversation state.

        Args:
            user_input: The user's prompt text.
            tools: Optional explicit tool schemas to offer the model. When
                ``None`` (default) the session default applies (all tools, or
                none when ``no_tools`` is set); pass a list to restrict the
                model to a subset of tools (e.g. no tools for ``/notools``).
        """
        if tools is None:
            tools_to_use = [] if self.no_tools else None
        else:
            tools_to_use = tools
        # Record this turn's start (the number of rows /history would
        # currently render) every time a new user prompt is about to be
        # sent, so the recorded value indexes directly into the displayed
        # history: /history marks the row each turn started at, and /rewind
        # / error-cancel recovery know where this turn began.
        self.history_turns.append(self._history_row_count())
        self.conversation_turn = len(self.conversation_items) if self.conversation_items else 0
        self.response_turn = len(self.response_chain)
        self.mirrored_turn = len(self.mirrored_history)
        # Track this turn's effective privileges so tools that spawn child
        # processes (StartTask) mirror the running turn, not just the
        # session's cmdline privileges: a turn with an explicit tool set
        # (e.g. /notools) must propagate that restriction to the children
        # (issue #94).  Reset when the turn ends so a restricted turn never
        # leaks into the next one.
        turn_privileges_token = set_turn_privileges(resolve_turn_privileges(tools_to_use))
        try:
            result = self.turn_func(
                user_input,
                # verbose is a session default captured in the turn closure
                # (an explicit per-call gate on run_turn); thinking is
                # resolved into the config at build time too -- the /thinking
                # command rebuilds the send function through the factory so
                # the flip takes effect.
                previous_messages=self.messages_history,
                previous_response_id=self.previous_response_id,
                previous_items=self.conversation_items,
                instructions=self.get_system_prompt(),
                tools=tools_to_use,
            )
            # Responses API mode keeps the conversation state the provider
            # uses; Completions mode returns plain text and updates
            # previous_messages (self.messages_history) in place, so nothing
            # else is needed there.
            if hasattr(result, "input_items"):
                self._record_responses_result(result)
            # On success, keep the recorded start where it is (before this
            # turn) so /rewind can undo the last exchange. The next turn
            # will update it before its own run_turn call.
        except RequestCancelled as e:
            # Enter was pressed while waiting for the API: interrupt the
            # request but keep the conversation intact so the next turn still
            # knows the user's message (no rollback, unlike Ctrl+C above).
            # The client never chains the next turn from the aborted request:
            # server-side Responses providers (e.g. OpenAI) discard the
            # response of an interrupted stream, so its id cannot be used as
            # previous_response_id. Instead the client hands back the user's
            # messages as input items; the shell keeps the last completed
            # response id (previous_response_id) and re-sends those items
            # chained from it on the next turn.
            items = getattr(e, "conversation_items", None)
            if items is not None:
                # Server-side Responses: the pending cancelled messages.
                # Stateless Responses (e.g. DeepSeek): the full client-side
                # items, which already include the cancelled message (this
                # also covers a fresh conversation, where the shell had no
                # items yet). Either way, store them so the next turn
                # re-sends them.
                self.conversation_items = items
            elif self.conversation_items is not None:
                # Fallback for stateless flows where the exception carries no
                # items (e.g. the abort happened before the client built
                # them): persist the cancelled message so the next turn
                # includes it.
                self.conversation_items.append(message_item("user", user_input))
            print("Request cancelled (Enter). The prompt stays in the conversation history.")
        except KeyboardInterrupt:
            # Rollback any messages appended during this prompt; the
            # recorded turn start is dropped too, so the rolled-back turn no
            # longer counts (the pre-prompt rule derives Turn N from
            # history_turns, issue #78).
            self._rollback_history()
            print("Request interrupted, previous prompt/answer removed from the conversation history.")
        finally:
            reset_turn_privileges(turn_privileges_token)
        # Note: turn_func already appends user and assistant messages
        # to previous_messages (which is self.messages_history), so we don't
        # need to append them here.

        # End-of-turn notice (issue #101): if the turn left any parallel
        # tasks running (started via StartTask), tell the user they are still
        # in flight.  This fires on every path through _run_turn -- success
        # and rollback alike -- because none of the except clauses re-raise.
        self._print_running_tasks_notice()

    def _running_tasks(self) -> list[dict[str, Any]]:
        """Snapshot of tasks still running, best-effort (issue #101).

        Returns ``[]`` when no tasks are known, the manager exposes no such
        view, or the tasks toolset is disabled (``--no-tasks`` imports nothing
        task-related).  Never raises: a notice must not break a turn.
        """
        try:
            from ..taskmanager import task_manager

            return task_manager.running_tasks()
        except Exception:  # noqa: BLE001 - purely advisory
            return []

    def _print_running_tasks_notice(self) -> None:
        """Print 'N tasks are still running' + a Task ID | Summary table.

        Plain text only: ``_rich_console`` is a ``Console(markup=False)``, so
        Rich markup tags would print literally rather than being styled.
        """
        running = self._running_tasks()
        if not running:
            return
        _rich_console.print(f"The following ({len(running)}) tasks are still running:")
        _rich_console.print("  Task ID  Summary")
        for task in running:
            summary = task.get("summary") or task["task_id"]
            _rich_console.print(f"  {task['task_id']}  {summary}")
        _rich_console.print(
            "You can ask about these tasks at any time (e.g list all " "task, wait all tasks, kill all tasks)."
        )

    def _history_row_count(self) -> int:
        """Return how many rows /history would currently render.

        Delegates to :func:`janito.shell.conversation.effective_rows` -- the
        single place that knows where the conversation lives per API mode
        (Completions-style ``messages_history``, stateless Responses
        ``conversation_items``, or the server-side Responses display mirror
        plus any pending items) -- so the recorded value at prompt-send time
        indexes directly into the displayed history.
        """
        return len(effective_rows(self))

    def _rollback_history(self) -> None:
        """Roll the conversation history back to the most recent turn.

        Removes any messages appended since the last turn (the aborted
        turn's user prompt and any partial assistant output) and drops its
        recorded start, since the turn it marked is gone.  In the Responses
        modes the recorded value is a displayed-row count that is >= the
        length of ``messages_history`` (which only ever holds the system
        prompt), so the truncation is a no-op there -- matching the
        pre-list behaviour, where the Responses rollback was handled
        elsewhere.
        """
        rollback_to_last_turn(self.messages_history, self.history_turns)

    def _record_responses_result(self, result: Any) -> None:
        """Record the conversation state a Responses turn returns.

        Server-side providers (e.g. OpenAI) keep the history on the server:
        remember the returned response id to chain the next turn, and mirror
        the completed turn client-side (display-only) so /history can render
        the conversation. Stateless providers (e.g. DeepSeek) return the full
        conversation as input items (re-sent on the next turn); never chain
        with an id for them, and no mirror is kept (conversation_items is the
        mirror).
        """
        self.conversation_items = result.input_items
        if result.input_items is None:
            self.previous_response_id = result.response_id
            # Server-side Responses: remember this turn's final response id
            # in the chain so /rewind can undo the exchange by chaining the
            # next turn (previous_response_id) from the response that
            # preceded it, instead of resetting the whole server conversation.
            if result.response_id:
                self.response_chain.append(result.response_id)
            # Mirror the completed turn client-side (display-only) so
            # /history can render the conversation: the real history lives on
            # the server and is never fetched back. Pending Enter-cancelled
            # messages are not part of a completed turn and keep showing via
            # conversation_items instead.
            turn_items = getattr(result, "turn_items", None)
            if turn_items:
                self.mirrored_history.extend(turn_items)
        else:
            self.previous_response_id = None

    def _effective_api_type(self) -> str | None:
        """Resolve the API type in effect for the current session identity.

        An explicit ``--api-type`` (``self.api_type``) wins; otherwise the API
        type is re-resolved from the current provider/model the same way the
        turn factory resolves it (a mid-session ``/provider`` or ``/model``
        switch updates ``self.provider`` / ``self.model``, so the resolved
        value tracks the session).  Best-effort: never raises, so a snapshot
        can never break the shell.
        """
        if self.api_type:
            return self.api_type
        provider = self.provider
        if not provider:
            return None
        try:
            from ..general_config import resolve_api_type

            return resolve_api_type(None, provider, self.model)
        except Exception:  # noqa: BLE001 - snapshot must never break the shell
            return None

    def conversation_snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of the current conversation state.

        Captures every field ``janito -C`` needs to reproduce this exact
        conversation: the per-API native history (``messages_history`` for the
        client-side-history modes, ``conversation_items`` / ``mirrored_history``
        plus the server-side chain for the Responses modes), the turn markers
        (``history_turns`` and the rewind indices), the system prompt and the
        session identity (provider / model / API type / thinking / effort).

        The lists are deep-copied so the snapshot is decoupled from the live
        shell state.
        """
        from .persistence import make_state

        return make_state(
            provider=self.provider,
            model=self.model,
            model_override=self.model_override,
            api_type=self._effective_api_type(),
            thinking=bool(getattr(self, "thinking", False)),
            effort=self.effort,
            system_prompt=self._system_prompt,
            messages_history=copy.deepcopy(self.messages_history),
            history_turns=list(self.history_turns),
            previous_response_id=self.previous_response_id,
            conversation_items=(
                copy.deepcopy(self.conversation_items) if self.conversation_items is not None else None
            ),
            conversation_turn=self.conversation_turn,
            response_chain=list(self.response_chain),
            response_turn=self.response_turn,
            mirrored_history=copy.deepcopy(self.mirrored_history),
            mirrored_turn=self.mirrored_turn,
        )

    def restore_conversation(self, state: dict[str, Any]) -> bool:
        """Restore a saved conversation snapshot into this shell.

        Replaces the whole conversation state (per-API history, turn markers,
        server-side chain) and the system prompt with the values from
        ``state``.  The session identity (provider / model / API type) is not
        changed here: the caller (``run_interactive_chat``) only restores when
        the identity matches the snapshot, so the native per-API state stays
        valid for the session.

        Returns:
            bool: ``True`` when the state was restored, ``False`` when
            ``state`` is not a usable snapshot (the shell is left untouched).
        """
        if not isinstance(state, dict) or "messages_history" not in state:
            return False
        self._system_prompt = state.get("system_prompt")
        self.messages_history = copy.deepcopy(state.get("messages_history") or [])
        self.history_turns = list(state.get("history_turns") or [])
        self.previous_response_id = state.get("previous_response_id")
        items = state.get("conversation_items")
        self.conversation_items = copy.deepcopy(items) if items is not None else None
        self.conversation_turn = int(state.get("conversation_turn") or 0)
        self.response_chain = list(state.get("response_chain") or [])
        self.response_turn = int(state.get("response_turn") or 0)
        self.mirrored_history = copy.deepcopy(state.get("mirrored_history") or [])
        self.mirrored_turn = int(state.get("mirrored_turn") or 0)
        return True

    def _save_snapshot(self) -> None:
        """Persist the current conversation for ``janito -C``, when enabled.

        No-op unless the CLI chat entry point enabled persistence
        (``persist_history``); also disabled under ``--no-history``.  Best
        effort: a failed write is logged, never raised.
        """
        if not self.persist_history:
            return
        from .persistence import save_conversation_state

        save_conversation_state(self.conversation_snapshot())

    def run(
        self,
        turn_func: Callable,
        verbose: bool = False,
        no_tools: bool = False,
        thinking: bool = False,
    ) -> None:
        """
        Run the interactive chat loop.

        Args:
            turn_func: Function to call to run one LLM turn with the AI
            verbose: Enable verbose output
            no_tools: If True, don't pass any tools to the AI
            thinking: If True, enable thinking mode
        """
        # Store references so command handlers (e.g. /ask) can use them
        self.turn_func = turn_func
        self.verbose = verbose
        self.no_tools = no_tools
        self.thinking = thinking

        while True:
            self.restart_requested = False
            self.do_it_requested = False
            self.exit_requested = False

            # Show the upcoming conversation turn above the prompt (issue
            # #69): a rich horizontal rule labeled with the next turn number.
            # Display-only and derived from the recorded turns
            # (``history_turns``, one entry per submitted turn), so a turn
            # that is rolled back (Ctrl+C / error) or undone (/rewind) no
            # longer counts and the number is shown again for the retry
            # (issue #78); a fresh conversation starts at Turn 1. The
            # title also carries the running privileges badge
            # (``Turn N with full privileges``), built as Text with a
            # styled span because the shell console disables markup.
            from ..privileges import privilege_badge

            _priv_label, _priv_style = privilege_badge()
            _thread_depth = getattr(getattr(self, "conversation_stack", None), "depth", 0) or 0
            if _thread_depth:
                _turn_title = Text.assemble(
                    "Turn ",
                    (f"{len(self.history_turns) + 1}", "bold"),
                    " / Thread ",
                    (f"{_thread_depth}", "bold"),
                    " with ",
                    (_priv_label, _priv_style),
                    " privileges",
                )
            else:
                _turn_title = Text.assemble(
                    "Turn ",
                    (f"{len(self.history_turns) + 1}", "bold"),
                    " with ",
                    (_priv_label, _priv_style),
                    " privileges",
                )
            _rich_console.print(Rule(_turn_title))
            user_input = self._get_user_input()
            if user_input is None:
                # Quit: persist the current state so `janito -C` can resume it.
                self._save_snapshot()
                break  # User quit

            # Reset multiline mode after input is received (single-use)
            if self.multiline_mode:
                self.multiline_mode = False
                self.session = self._create_session(multiline=False)

            # Check if F12 was pressed (Do It requested)
            if self.do_it_requested:
                _rich_console.print("\n[Keybinding F12] 'Do It' to continue existing plan...")
                user_input = "Do It"

            # Check if F2 was pressed (restart requested)
            if self._handle_restart_request():
                self._save_snapshot()
                continue

            # Handle clear text, registered commands, unknown commands and
            # !cmd shell execution.
            if self._dispatch_input(user_input):
                self._save_snapshot()
                # Check if exit was requested via a command
                if self.exit_requested:
                    break
                continue

            if user_input.strip():
                self._run_turn(user_input)
            # Persist after the turn (or its rollback) so the on-disk copy
            # always mirrors the in-memory conversation.
            self._save_snapshot()

        self._save_snapshot()
        print("\nChat session ended.")
