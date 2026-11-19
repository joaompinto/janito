#!/usr/bin/env python3
"""
Base Tool Class - A foundation for AI tools with built-in progress reporting.

This module provides a base class that tools can inherit from to get automatic
progress reporting capabilities and permission awareness.

The report_*() methods delegate to the module-level reporter functions so that
a context-variable-based report handler (set in web mode) can intercept output.
"""

from abc import ABC, abstractmethod
from typing import Any

from .prompting import get_prompt_handler
from .reporter import report_diff as _report_diff
from .reporter import report_error as _report_error
from .reporter import report_output as _report_output
from .reporter import report_progress as _report_progress
from .reporter import report_result as _report_result
from .reporter import report_start as _report_start
from .reporter import report_warning as _report_warning


class BaseTool(ABC):
    """
    Base class for AI tools with built-in progress reporting and permissions.

    Tools should inherit from this class and implement the `run` method.
    The class automatically provides progress reporting methods that are
    aware of the tool's declared permissions.
    """

    # Class-level permissions attribute (set by the @tool decorator)
    _tool_permissions: str = ""

    # Optional human-readable explanation for why the tool was not loaded.
    # Tools may set this inside should_load() before returning False.
    _load_skip_reason: str = ""

    # Optional text this tool contributes to the system prompt (a usage hint
    # for the LLM).  Subclasses set it as a class attribute; the registry
    # collects the hints of the tools a session may actually use into
    # per-tool ``tools:<Toolname>`` sections under the ``tools`` header (see
    # :func:`janito.system_prompt.sync_default_sections`).  Write the hint
    # function-first without a tool-name prefix ("read PDFs with pdfplumber
    # or pypdf"); the tool name lives in the section name.  Empty (the
    # default) means the tool contributes nothing.
    system_prompt_hint: str = ""

    def __init__(self):
        """Initialize the base tool."""

    @classmethod
    def should_load(cls) -> bool:
        """
        Validate whether this tool should be loaded and made available.

        Tools can override this class method to check runtime requirements
        such as external binaries, platform support, environment variables,
        or credentials. Tools returning False are skipped during discovery:
        they are never registered, advertised to the LLM, or callable.

        When returning False, tools may set `cls._load_skip_reason` to a
        human-readable explanation (used for diagnostics, e.g. /tools).

        Returns:
            bool: True if the tool should be loaded (default), False to skip it
        """
        return True

    @abstractmethod
    def run(self, **kwargs) -> dict[str, Any]:
        """
        Execute the tool's main functionality.

        This method must be implemented by subclasses.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Dict[str, Any]: Tool result dictionary
        """

    def _get_start_style(self) -> str:
        """Compute the rich style for start messages based on permissions."""
        permissions = getattr(self, "_tool_permissions", "")
        if not permissions:
            return "cyan"  # Cyan for no permissions (default)
        elif "x" in permissions:
            return "yellow"  # Yellow for execute
        elif "w" in permissions:
            return "yellow"  # Yellow for write (same as execute)
        elif "r" in permissions:
            return "green"  # Green for read-only (safe)
        else:
            return "cyan"  # Cyan as fallback

    def report_start(self, message: str, end: str = "\n") -> None:
        """
        Report that the tool operation is starting.

        Delegates to the module-level reporter so a web-mode handler can
        intercept the message. Uses prefix=" " (space, no emoji) to preserve
        the existing BaseTool output format — this differentiates tool
        messages from LLM messages in the CLI.

        Args:
            message (str): The message to display
            end (str): String appended after the message (default: "\n")
        """
        style = self._get_start_style()
        _report_start(message, end=end, color=style, prefix=" ")

    def report_progress(self, message: str, end: str = "\n") -> None:
        """
        Report ongoing progress of the tool operation.

        Args:
            message (str): The progress message to display
            end (str): String appended after the message (default: "\n")
        """
        _report_progress(message, end=end)

    def report_output(self, message: str, end: str = "\n") -> None:
        """
        Report raw command/subprocess output (stdout/stderr lines).

        In CLI mode this prints the line as-is (no emoji, no colour).
        In web mode it becomes a ToolProgressEvent(level="output") rendered
        in a monospace terminal block.

        Args:
            message (str): The output line to display
            end (str): String appended after the message (default: "\n")
        """
        _report_output(message, end=end)

    def report_result(self, message: str, end: str = "\n") -> None:
        """
        Report intermediate or final results from the tool operation.

        Args:
            message (str): The result message to display
            end (str): String appended after the message (default: "\n")
        """
        _report_result(message, end=end)

    def report_diff(self, old_str: str, new_str: str, end: str = "\n") -> None:
        """
        Report the diff between two strings with rich syntax highlighting.

        Generates a unified diff between ``old_str`` and ``new_str`` and
        prints it on the terminal (syntax-highlighted with the Pygments
        "diff" lexer). In web mode the diff is forwarded to the active
        report handler as a ``"diff"`` level event.

        Args:
            old_str (str): The text that was searched for (the "before" side)
            new_str (str): The replacement text (the "after" side)
            end (str): String appended after the message (default: "\n")
        """
        _report_diff(old_str, new_str, end=end)

    def report_error(self, message: str, end: str = "\n") -> None:
        """
        Report an error during tool execution.

        Args:
            message (str): The error message to display
            end (str): String appended after the message (default: "\n")
        """
        _report_error(message, end=end)

    def report_warning(self, message: str, end: str = "\n") -> None:
        """
        Report a warning during tool execution.

        Args:
            message (str): The warning message to display
            end (str): String appended after the message (default: "\n")
        """
        _report_warning(message, end=end)

    def prompt_user(self, question: str) -> str:
        """
        Prompt the user with a question and return their answer.

        In CLI mode the question is displayed inside a ``rich`` table (the
        question text itself is still rendered as markdown, like LLM
        replies) and the answer is read from stdin. In web mode the web
        backend installs a prompt handler through the ``prompting`` context
        variable: it presents the question as a modal in the browser and
        waits for the answer, so no console is needed. This method is
        intended to be called by tools that need interactive input from the
        user (e.g. the AskUser tool).

        When stdin ends (e.g. piped input / Ctrl+D), an empty answer is
        returned so the tool can report "no answer". Pressing Ctrl+C,
        however, lets the ``KeyboardInterrupt`` propagate: it interrupts the
        in-flight LLM conversation turn (the agent loop rolls the history
        back), instead of silently continuing with an empty answer.

        Args:
            question (str): The question to display to the user.

        Returns:
            str: The user's answer (stripped of leading/trailing whitespace).
        """
        handler = get_prompt_handler()
        if handler is not None:
            # Web mode: the backend installed an in-browser prompt handler.
            return handler(question).strip()

        from rich.console import Console
        from rich.markdown import Markdown
        from rich.table import Table

        console = Console(stderr=True, highlight=False, markup=False)

        table = Table(header_style="bold cyan", show_header=True, expand=False)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", overflow="fold")
        table.add_row("Question", Markdown(question))

        console.print(table)

        try:
            answer = input("Your answer: ").strip()
        except EOFError:
            # Piped input / Ctrl+D: no answer to read, report an empty one.
            answer = ""
        return answer
