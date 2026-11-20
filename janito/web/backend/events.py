"""Agent event dataclasses emitted by the web agentic loop.

Each event maps to one WebSocket message sent to the browser.  Every event
carries its own ``to_dict()`` so the wire format lives right next to the
data it serializes (adding a field is a one-file change).
:func:`event_to_dict` is a thin dispatcher kept for existing callers.

The CLI loop does not use these wire events: it prints through the
``TurnObserver`` protocol (``janito.llm_adapters.observer``) instead.
``UsageEvent`` + :func:`usage_event_from_usage` live here too -- the web
backend is their only consumer; the shared adapter layer
(``janito.llm_adapters``) exposes only the normalized ``TurnInfo``.
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from janito.llm_adapters.usage import normalize_usage


def usage_event_from_usage(usage: Any, max_tokens: int | None = None):
    """Build a :class:`UsageEvent` from a usage object.

    Handles every usage shape the supported API types report (see
    :func:`janito.llm_adapters.usage.normalize_usage`).  Returns ``None``
    when no usage was reported by the stream, or when the object carries no
    usable counters (the former per-accumulator ``usage_event()`` guards).
    """
    if usage is None:
        return None
    stats = normalize_usage(usage)
    if not any((stats["total"], stats["input"], stats["output"], stats["cached"])):
        return None
    return UsageEvent(
        total=stats["total"] or 0,
        last_input=stats["input"] or 0,
        last_output=stats["output"] or 0,
        last_cached=stats["cached"] or 0,
        max_tokens=max_tokens,
    )


def _safe_result(result: Any) -> Any:
    """Ensure a tool result is JSON-serializable (for the browser)."""
    if result is None or isinstance(result, (str, int, float, bool)):
        return result
    if isinstance(result, dict):
        try:
            import json

            json.dumps(result)
            return result
        except (TypeError, ValueError):
            return str(result)
    return str(result)


@dataclass
class TokenEvent:
    """Streamed text delta."""

    content: str

    type: ClassVar[str] = "token"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "content": self.content}


@dataclass
class ReasoningEvent:
    """Thinking / reasoning delta."""

    content: str

    type: ClassVar[str] = "reasoning"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "content": self.content}


@dataclass
class ToolCallEvent:
    """The model wants to call a tool."""

    tool_call_id: str
    tool_name: str
    arguments: dict
    permissions: str = ""  # e.g. "r", "w", "x", "rwx"

    type: ClassVar[str] = "tool_call"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.tool_call_id,
            "name": self.tool_name,
            "args": self.arguments,
            "permissions": self.permissions,
        }


@dataclass
class ToolResultEvent:
    """A tool finished executing."""

    tool_call_id: str
    tool_name: str
    result: Any
    error: str | None = None
    execution_time_ms: int | None = None

    type: ClassVar[str] = "tool_result"

    def to_dict(self) -> dict[str, Any]:
        result = self.result
        if isinstance(result, dict) and result.get("success") is False:
            result = _safe_result(result)
        return {
            "type": self.type,
            "id": self.tool_call_id,
            "name": self.tool_name,
            "result": _safe_result(result),
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class ToolProgressEvent:
    """Intermediate tool output (report_* calls inside tool execution)."""

    tool_call_id: str
    level: str  # "start"|"progress"|"output"|"diff"|"result"|"error"|"warning"|"info"
    message: str  # "output" = raw subprocess stdout/stderr (monospace in UI)

    type: ClassVar[str] = "tool_progress"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.tool_call_id,
            "level": self.level,
            "message": self.message,
        }


@dataclass
class PromptStartedEvent:
    """A queued follow-up or steering instruction is entering the history."""

    content: str
    mode: str

    type: ClassVar[str] = "prompt_started"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "content": self.content, "mode": self.mode}


@dataclass
class WaitingEvent:
    """The API is processing, no tokens yet."""

    phase: str  # "initial" | "after_tools"

    type: ClassVar[str] = "waiting"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "phase": self.phase}


@dataclass
class UsageEvent:
    """Token usage (final chunk) plus cumulative turn totals.

    ``total`` / ``last_input`` / ``last_output`` / ``last_cached`` are the
    **final** API round's counters (the historical web display);
    ``turn_input`` / ``turn_cached`` / ``turn_output`` sum every round of the
    turn (tool-call rounds included) and are only set when the backend reports
    them.
    """

    total: int = 0
    last_input: int = 0
    last_output: int = 0
    last_cached: int = 0
    max_tokens: int | None = None
    turn_input: int | None = None
    turn_cached: int | None = None
    turn_output: int | None = None

    type: ClassVar[str] = "usage"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "type": self.type,
            "total": self.total,
            "last_input": self.last_input,
            "last_output": self.last_output,
            "last_cached": self.last_cached,
        }
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        if self.turn_input is not None:
            d["turn_input"] = self.turn_input
        if self.turn_cached is not None:
            d["turn_cached"] = self.turn_cached
        if self.turn_output is not None:
            d["turn_output"] = self.turn_output
        return d


@dataclass
class ImageEvent:
    """A native Responses API image_generation_call result.

    The built-in ``image_generation`` tool returns base64-encoded images
    directly in the response stream (no function call round-trip).  The
    backend decodes them into temp PNG files (served by ``/api/images/``)
    and emits one ``ImageEvent`` per image so the frontend can render it
    as a content card.
    """

    path: str
    revised_prompt: str = ""

    type: ClassVar[str] = "image"

    def to_dict(self) -> dict[str, Any]:
        d = {"type": self.type, "path": self.path}
        if self.revised_prompt:
            d["revised_prompt"] = self.revised_prompt
        return d


@dataclass
class WebSearchEvent:
    """A web search was performed (issue #131)."""

    status: str = "completed"

    type: ClassVar[str] = "web_search"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "status": self.status}


@dataclass
class SourcesEvent:
    """Cited web sources for a search-grounded answer (issue #131)."""

    sources: list = None  # [{url, title, start_index, end_index}]

    type: ClassVar[str] = "sources"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "sources": list(self.sources or [])}


@dataclass
class DoneEvent:
    """Conversation turn complete."""

    full_content: str
    message_count: int

    type: ClassVar[str] = "done"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "content": self.full_content,
            "message_count": self.message_count,
        }


@dataclass
class ErrorEvent:
    """An error occurred during the turn."""

    message: str

    type: ClassVar[str] = "error"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "message": self.message}


AgentEvent = (
    TokenEvent
    | ReasoningEvent
    | ToolCallEvent
    | ToolResultEvent
    | WaitingEvent
    | PromptStartedEvent
    | ToolProgressEvent
    | ImageEvent
    | WebSearchEvent
    | SourcesEvent
    | UsageEvent
    | DoneEvent
    | ErrorEvent
)


def event_to_dict(event: AgentEvent) -> dict[str, Any]:
    """Convert an agent event to a JSON-serializable dict for WebSocket send.

    Each event dataclass knows how to serialize itself via ``to_dict()``;
    unknown event types degrade gracefully instead of raising.
    """
    to_dict = getattr(event, "to_dict", None)
    if to_dict is not None:
        return to_dict()
    # Unknown event type — ignore gracefully
    return {"type": "unknown"}
