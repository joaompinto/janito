"""Shared native DashScope SDK adapter: kwargs + accumulation.

The DashScope generation-API turn pipeline used to live in the web runner
(``janito.web.backend.agent.dashscope``); the pure parts -- call-kwargs
building, stream accumulation and the endpoint-routing helpers
(:func:`_is_multimodal_model` / :func:`_to_multimodal_messages` /
:class:`_ModelEndpointMismatch`) -- live here so both agent loops share
them (the web loop must not import from ``llm_clients``, issue #90).  The
web shim keeps the async glue (:func:`create_client`,
:func:`_dashscope_chunks` and :func:`stream_turn_events`), which consumes
the **sync** DashScope SDK stream chunk-by-chunk through
``asyncio.to_thread``.

The ``dashscope`` package is **optional** (see
``janito.providers.REQUIRES_BY_API_TYPE``); importing it happens lazily
inside :func:`create_client` (kept in the web shim), so importing this
module never requires it.

**Conversation model.** The DashScope generation API is stateless and accepts
the OpenAI chat message shape natively (``system``/``user``/``assistant``/
``tool`` with ``tool_calls``), so the session history is sent as-is; the
multimodal endpoint's content-list conversion is applied per round by the
stream opener (mirroring ``janito.llm_clients.dashscope.dashscope_stream``).
"""

import logging
import re
from types import SimpleNamespace
from typing import Any

from janito.providers.payloads import builtin_tools_enable_flags

logger = logging.getLogger(__name__)


class _ModelEndpointMismatch(RuntimeError):
    """Raised when the DashScope API rejects a model for the chosen endpoint.

    The native DashScope API serves models from two generation endpoints:
    ``text-generation`` (``Generation.call``) for plain-text models and
    ``multimodal-generation`` (``MultiModalConversation.call``) for multimodal
    models.  Sending a model to the wrong endpoint fails with
    ``InvalidParameter: url error, please check url``.  The stream opener
    catches this to retry once on the other endpoint.

    Lives in the shared adapter layer (not ``llm_clients``) so both agent
    loops signal endpoint mismatches with the same exception (issue #90).
    """


def _is_multimodal_model(model: str) -> bool:
    """Return True when a DashScope model is served by the multimodal endpoint.

    The DashScope native API serves plain-text models (``qwen-plus``,
    ``qwen-flash``, ``qwen3-max``, ``qwen3.7-max``, ...) from the
    ``text-generation`` endpoint (``Generation.call``) and multimodal models
    (Qwen-VL / Qwen-Omni, the ``qwen3.x-plus`` generation, and the
    ``qwen3.8-max`` / ``qwen4-max`` flagships) from the ``multimodal-generation`` endpoint
    (``MultiModalConversation.call``).  Calling a model on the wrong endpoint
    fails with ``InvalidParameter: url error, please check url``.

    This is a best-effort heuristic: when it misclassifies a model, both
    stream openers (the CLI's ``dashscope_stream._stream_response`` and the
    web runner's ``_dashscope_chunks``) retry once on the other endpoint.

    Lives in the shared adapter layer (not ``llm_clients``) so the web loop
    does not need to import from the CLI client packages (issue #90).
    """
    name = (model or "").strip().lower()
    if not name:
        return False
    # Vision / omni model families are multimodal by naming convention.
    if "-vl" in name or "omni" in name:
        return True
    # The qwen3.x-plus generation and the qwen3.8-max / qwen4-max flagships
    # are served by
    # the multimodal-generation endpoint, while the qwen3.x-max text models
    # (e.g. qwen3.7-max) are not.
    if re.match(r"^qwen3\.\d+-plus$", name) or name in (
        "qwen3.8-max",
        "qwen3.8-max-0902",
        "qwen4-max",
    ):
        return True
    return False


def _to_multimodal_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert plain-string message content to DashScope multimodal form.

    The multimodal-generation API expects every message ``content`` to be a
    list of modality items (``[{"text": "..."}]``) instead of a plain string.
    Returns a shallow copy with string contents wrapped; other fields
    (``tool_calls``, ``tool_call_id``, ``reasoning_content``) are kept as-is.

    Lives in the shared adapter layer (not ``llm_clients``) so the web loop
    does not need to import from the CLI client packages (issue #90).
    """
    converted = []
    for message in messages:
        message = dict(message)
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = [{"text": content}]
        converted.append(message)
    return converted


def build_call_kwargs(
    model: str,
    messages: list[dict],
    tools_schemas: list[dict] | None,
    config,
    max_output_tokens: int | None,
    preserve_thinking,
    reasoning_effort: str | None,
) -> dict:
    """Build the DashScope generation kwargs for one turn.

    Mirrors ``janito.llm_clients.dashscope.dashscope_api._build_call_kwargs`` (``result_format``,
    streaming, incremental output, ``enable_thinking``).  The OpenAI-format
    ``messages`` history is sent as-is -- the native API accepts that shape.
    ``preserve_thinking`` / ``reasoning_effort`` are accepted for signature
    parity but are not used by the native SDK (like the CLI client).
    """
    if max_output_tokens is None:
        max_output_tokens = 100000  # default to 100k tokens if not set in config

    call_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_output_tokens,
        "result_format": "message",
        "stream": True,
        "incremental_output": True,
    }
    # Enable thinking mode for Qwen models that support it (Alibaba/Qwen
    # reason by default).  Only set when True so models that always reason
    # keep their own default.
    if config.effective_thinking:
        call_kwargs["enable_thinking"] = True
    # The effective model's built-in tools (e.g. code_interpreter /
    # web_search / web_extractor) are native capabilities enabled through
    # request-body kwargs on the DashScope generation API (e.g.
    # enable_code_interpreter / enable_search).  They are set whenever the
    # model declares them for this API type; models without built-in tools
    # send nothing.
    flags = builtin_tools_enable_flags(config.effective_tools_for("DashScope"))
    if flags:
        call_kwargs.update(flags)
    if tools_schemas:
        call_kwargs["tools"] = tools_schemas
    return call_kwargs


def _get(obj, key: str, default=None):
    """Read a key from a DashScope SDK object (DictMixin: dict- or attr-style)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class DashScopeTurnAccumulator:
    """Fold DashScope generation stream chunks into one turn's collected state.

    Implements the same interface as
    :class:`~janito.llm_adapters.completions.CompletionsTurnAccumulator` (``handle`` ->
    ``(reasoning_delta, content_delta)`` plus the end-of-turn accessors).
    With ``incremental_output=True`` each chunk carries only the newly
    generated text, so deltas are forwarded to the browser as they arrive;
    tool-call arguments (a JSON string split across chunks) are accumulated
    by index and exposed in the OpenAI wire format.
    """

    def __init__(self) -> None:
        self.content: list[str] = []
        self.reasoning: list[str] = []
        self.tool_calls: dict[int, dict[str, str]] = {}
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.total_tokens: int | None = None
        self.done: bool = False

    # ------------------------------------------------------------------
    # Stream driving
    # ------------------------------------------------------------------

    def handle(self, chunk) -> tuple[str | None, str | None]:
        """Process one chunk; returns ``(reasoning_delta, content_delta)``."""
        status_code = _get(chunk, "status_code")
        if status_code is not None and status_code != 200:
            self._raise_error(chunk, status_code)

        output = _get(chunk, "output") or {}
        choices = _get(output, "choices") or []
        if not choices:
            # Keep consuming: the terminal chunk may still carry usage.
            self._consume_usage(chunk)
            return None, None

        choice = choices[0]
        message = _get(choice, "message") or {}

        content = _get(message, "content") or ""
        if isinstance(content, list):
            # Multimodal responses carry content as a list of modality items
            # (e.g. [{"text": "..."}]); join the text parts.
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        reasoning = _get(message, "reasoning_content") or ""

        for tc in _get(message, "tool_calls") or []:
            self._handle_tool_call(tc)
        self._consume_usage(chunk)

        if _get(choice, "finish_reason") == "stop":
            self.done = True

        if content:
            self.content.append(content)
        if reasoning:
            self.reasoning.append(reasoning)
        return (reasoning or None), (content or None)

    def _handle_tool_call(self, tc) -> None:
        """Merge one DashScope tool-call chunk into the per-index map."""
        idx = _get(tc, "index", 0) or 0
        entry = self.tool_calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if _get(tc, "id"):
            entry["id"] = _get(tc, "id")
        function = _get(tc, "function") or {}
        if _get(function, "name"):
            entry["name"] = _get(function, "name")
        arguments = _get(function, "arguments")
        if arguments:
            entry["arguments"] += arguments

    def _consume_usage(self, chunk) -> None:
        """Keep the most recent usage reported by the API."""
        usage = _get(chunk, "usage")
        if usage is not None:
            self.input_tokens = _get(usage, "input_tokens", self.input_tokens)
            self.output_tokens = _get(usage, "output_tokens", self.output_tokens)
            self.total_tokens = _get(usage, "total_tokens", self.total_tokens)

    def _raise_error(self, chunk, status_code: int) -> None:
        """Raise a DashScope API error, signalling endpoint mismatches."""
        code = _get(chunk, "code") or ""
        message = _get(chunk, "message") or "DashScope API error"
        request_id = _get(chunk, "request_id") or ""
        detail = f" (request_id={request_id})" if request_id else ""
        if code == "InvalidParameter" and "url error" in message:
            # The model was sent to the wrong generation endpoint
            # (multimodal vs text): signal the stream opener to retry once on
            # the other endpoint.
            raise _ModelEndpointMismatch(f"DashScope API error (code={code}): {message}{detail}")
        raise RuntimeError(f"DashScope API error (code={code}): {message}{detail}")

    # ------------------------------------------------------------------
    # End-of-turn assembly
    # ------------------------------------------------------------------

    def full_content(self) -> str:
        return "".join(self.content)

    def reasoning_content(self) -> str | None:
        return "".join(self.reasoning) if self.reasoning else None

    def tool_calls_list(self) -> list[dict]:
        """Assembled tool calls in OpenAI wire format (for ``run_tool_turn``)."""
        return [
            {
                "id": self.tool_calls[idx]["id"],
                "type": "function",
                "function": {
                    "name": self.tool_calls[idx]["name"],
                    "arguments": self.tool_calls[idx]["arguments"] or "{}",
                },
            }
            for idx in sorted(self.tool_calls)
        ]

    def usage_object(self):
        """The raw usage object of this round, or ``None`` when unreported.

        Uniform accessor used by the web loop to fold each round's usage into
        the turn-level cumulative totals (:class:`TurnInfo`).
        """
        if self.input_tokens is None and self.output_tokens is None and self.total_tokens is None:
            return None
        return SimpleNamespace(
            total_tokens=self.total_tokens,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


# Uniform runner interface (used by loop.py): the accumulator class is
# exposed as ``accumulator`` so every API-type runner has the same shape.
accumulator = DashScopeTurnAccumulator


__all__ = [
    "DashScopeTurnAccumulator",
    "accumulator",
    "build_call_kwargs",
    "_is_multimodal_model",
    "_ModelEndpointMismatch",
    "_to_multimodal_messages",
    "_get",
]
