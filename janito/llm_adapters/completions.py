"""Shared Chat Completions adapter: call-kwargs building + stream accumulation.

Used by both agent loops:

- the web ``stream_prompt()`` loop reaches it through the per-API runner
  ``janito.web.backend.agent.completions``, which wraps ``build_call_kwargs``
  (adding ``messages`` + function ``tools``) and drives the stream with
  ``CompletionsTurnAccumulator``;
- the CLI loop subclasses ``CompletionsTurnAccumulator`` in
  ``janito.llm_clients.openai.completions_stream`` (``CompletionsStreamConsumer``)
  to add its synchronous Enter-to-cancel stream driver.

The per-chunk folding is identical in both; only the stream *driver* differs
(web: ``async for`` yielding token events live; CLI: a sync ``consume``
loop under a progress spinner).
"""

from dataclasses import dataclass, field
from typing import Any

from janito.providers.payloads import (
    apply_builtin_tools_to_extra_body,
    apply_thinking_to_extra_body,
)


def build_call_kwargs(
    model: str,
    config,
    max_output_tokens: int | None,
    preserve_thinking,
    reasoning_effort: str | None = None,
) -> dict:
    """Build the base ``chat.completions.create`` parameters for one turn.

    Config-driven behaviour (from CLI args):
      - ``config.effective_thinking`` (runtime toggle, else the ``--thinking``
        flag, else the provider's built-in ``thinking``) -> add
        extra_body enable_thinking, or the raw thinking dict for providers
        with a structured thinking parameter (e.g. MiniMax-M3)
      - max output tokens from ``janito.general_config`` -> max_tokens
        (``max_completion_tokens`` for gpt-5/gpt-6 models)
      - ``preserve_thinking`` (resolved from the provider config's model
        entry, e.g. ``True`` for Alibaba/Qwen) -> extra_body
      - ``reasoning_effort`` -> ``reasoning_effort`` (e.g. low/medium/xhigh)

    Note: the CLI loop keeps its own ``_build_call_kwargs`` (in
    ``janito.llm_clients.openai.completions_api``) because it threads the
    ``messages`` list and a raw ``thinking`` flag through the shared
    ``Client`` template method instead of a ``WebServerConfig``.
    """
    call_kwargs: dict = {
        "model": model,
        "temperature": 1.0,
    }

    if max_output_tokens is not None:
        if model.startswith("gpt-5") or model.startswith("gpt-6"):
            call_kwargs["max_completion_tokens"] = max_output_tokens
        else:
            call_kwargs["max_tokens"] = max_output_tokens

    # Reasoning effort: sent whenever a reasoning level resolves (None means
    # the API's own default applies).
    provider = getattr(config, "effective_provider", None)
    if reasoning_effort:
        call_kwargs["reasoning_effort"] = reasoning_effort

    if preserve_thinking is not None:
        call_kwargs.setdefault("extra_body", {})["preserve_thinking"] = preserve_thinking

    # Pass the thinking mode in extra_body: enable_thinking for flag-style
    # defaults, or the raw dict for providers with a structured thinking
    # parameter (e.g. MiniMax-M3's {"type": "adaptive"}).  Gemini-flavored
    # providers (google) skip enable_thinking -- the field does not exist on
    # their OpenAI-compatibility API.
    apply_thinking_to_extra_body(call_kwargs, config.effective_thinking, provider=provider)

    # Pass the effective model's built-in tools (e.g. Alibaba/Qwen's
    # code_interpreter / web_search / web_extractor) as request-body
    # enable_* flags in extra_body (see apply_builtin_tools_to_extra_body).
    # These are model capabilities, not function tools, so they are enabled
    # whenever the model declares them for this API type -- even with
    # no_tools / an empty function-tools list.  Models without built-in
    # tools send nothing.
    apply_builtin_tools_to_extra_body(call_kwargs, config.effective_tools_for("Completions"))

    call_kwargs["stream"] = True
    call_kwargs["stream_options"] = {"include_usage": True}
    return call_kwargs


def _raise_chunk_error(chunk) -> None:
    """Raise when a stream chunk carries an API error the SDK could not type.

    Some OpenAI-compatible providers reject a request *in-band*: instead of
    an HTTP error status they stream a single ``ChatCompletionChunk`` with no
    ``choices`` that carries the failure as ``code``/``message`` fields (e.g.
    Alibaba DashScope returns ``code='Not Found', message='Not support'``
    when a model is sent to the wrong gateway).  The OpenAI SDK cannot type
    these, so without this guard the turn would silently produce an empty
    response.  Mirrors ``responses_stream._handle_untyped_error``.
    """
    code = getattr(chunk, "code", None)
    message = getattr(chunk, "message", None)
    if code or message:
        raise RuntimeError(f"{code}: {message}" if code else message)


@dataclass
class CompletionsTurnAccumulator:
    """Fold streamed completion chunks into one turn's collected state.

    ``handle(chunk)`` returns the reasoning/text fragment carried by the
    chunk (or ``None``) so the caller can forward it to the client
    immediately, while the accumulator retains the full picture for
    end-of-turn assembly.

    The CLI stream consumer subclasses this class to add its synchronous
    ``consume`` driver and property-style accessors; the web loop uses the
    class directly.
    """

    content: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    tool_calls: dict[int, dict[str, Any]] = field(default_factory=dict)
    usage: object | None = None
    #: Raw top-level response metadata (id, model, created, finish_reason, ...)
    #: captured from the stream chunks.  Populated by the CLI stream consumer
    #: for the verbose response dump; the web loop never reads it.
    raw_attrs: dict[str, Any] = field(default_factory=dict)

    def _handle_reasoning_delta(self, delta) -> str | None:
        """Capture reasoning/thinking content; returns the delta or None."""
        for attr in ("reasoning_content", "reasoning"):
            val = getattr(delta, attr, None)
            if val:
                self.reasoning.append(val)
                return val
        return None

    def _fold_tool_call_delta(self, tc_delta) -> None:
        """Merge one tool-call delta into the per-index tool call map."""
        idx = tc_delta.index
        if idx not in self.tool_calls:
            self.tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
        if tc_delta.id:
            self.tool_calls[idx]["id"] = tc_delta.id
        if tc_delta.function:
            if tc_delta.function.name:
                self.tool_calls[idx]["name"] = tc_delta.function.name
            if tc_delta.function.arguments:
                self.tool_calls[idx]["arguments"] += tc_delta.function.arguments
        # Preserve provider-specific extras (e.g. Gemini's
        # ``extra_content.google.thought_signature``) so they can be echoed
        # back verbatim on the next turn.  The OpenAI SDK surfaces unknown
        # fields via ``getattr`` because its models allow extra keys; dropping
        # them makes Gemini 3.x reject the follow-up request with a 400
        # "Function call is missing a thought_signature" error.
        extra_content = getattr(tc_delta, "extra_content", None)
        if extra_content:
            self.tool_calls[idx]["extra_content"] = extra_content

    def _handle_tool_call_delta(self, delta) -> None:
        """Accumulate tool-call deltas (split across many chunks)."""
        if not hasattr(delta, "tool_calls") or not delta.tool_calls:
            return
        for tc_delta in delta.tool_calls:
            self._fold_tool_call_delta(tc_delta)

    def handle(self, chunk) -> tuple[str | None, str | None]:
        """Process one chunk; returns ``(reasoning_delta, content_delta)``."""
        if hasattr(chunk, "usage") and chunk.usage:
            self.usage = chunk.usage

        if not chunk.choices:
            _raise_chunk_error(chunk)
            return None, None

        delta = chunk.choices[0].delta

        # Reasoning / thinking content
        reasoning_delta = self._handle_reasoning_delta(delta)

        # Main content
        content_delta = delta.content
        if content_delta:
            self.content.append(content_delta)

        # Tool-call deltas (split across many chunks)
        self._handle_tool_call_delta(delta)

        return reasoning_delta, content_delta

    # --- End-of-turn assembly -------------------------------------------

    def full_content(self) -> str:
        return "".join(self.content)

    def reasoning_content(self) -> str | None:
        return "".join(self.reasoning) if self.reasoning else None

    def tool_calls_list(self) -> list[dict]:
        """Assembled tool calls in original index order (OpenAI wire format).

        Provider-specific extras (e.g. Gemini's
        ``extra_content.google.thought_signature``) captured while folding the
        deltas are preserved on each call so they can be echoed back verbatim
        in the assistant message of the next turn.
        """
        calls = []
        for i in sorted(self.tool_calls):
            tc = self.tool_calls[i]
            call = {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            }
            extra_content = tc.get("extra_content")
            if extra_content:
                call["extra_content"] = extra_content
            calls.append(call)
        return calls

    def usage_object(self):
        """The raw usage object of this round, or ``None`` when unreported.

        Uniform accessor used by the web loop to fold each round's usage into
        the turn-level cumulative totals (:class:`TurnInfo`).
        """
        return self.usage

    @property
    def usage_info(self) -> object | None:
        """Alias of ``usage`` (the CLI stream consumer's historical name)."""
        return self.usage


# Uniform runner interface (used by loop.py): the accumulator class is
# exposed as ``accumulator`` so every API-type runner has the same shape.
accumulator = CompletionsTurnAccumulator
