"""``stream_prompt()`` — the orchestration skeleton of the agentic loop.

Everything heavy lives in sibling modules; this generator reads top to
bottom: resolve config -> resolve API type -> resolve tools -> loop { stream a
response; either run tool calls and continue, or finish }.

The loop is API-type agnostic.  The API type for the turn is resolved for the
*effective provider* (the one selected for the session/provider combo) via
``resolve_api_type`` — ``--api-type`` first, then the provider's configured
``api-type`` (written by the web Settings drawer), then the provider's
built-in default.  Each API type contributes a small runner module (client
factory, call-kwargs builder, stream driver) exposing the same interface;
the shared call-kwargs logic and accumulator classes come straight from the
``janito.llm_adapters`` adapters:

- Completions  -> ``janito.web.backend.agent.completions``
- Responses    -> ``janito.web.backend.agent.responses``
- Anthropic    -> ``janito.web.backend.agent.anthropic``
- DashScope    -> ``janito.web.backend.agent.dashscope``
- Gemini       -> ``janito.web.backend.agent.gemini``
"""

import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

from janito.general_config import get_active_provider, resolve_api_type
from janito.model_settings import FALLBACK_MAX_OUTPUT_TOKENS, resolve_model_settings
from janito.llm_adapters.anthropic import accumulator as anthropic_accumulator
from janito.llm_adapters.anthropic import build_call_kwargs as build_anthropic_kwargs
from janito.llm_adapters.completions import accumulator as completions_accumulator
from janito.llm_adapters.dashscope import accumulator as dashscope_accumulator
from janito.llm_adapters.dashscope import build_call_kwargs as build_dashscope_kwargs
from janito.llm_adapters.gemini import accumulator as gemini_accumulator
from janito.llm_adapters.gemini import build_call_kwargs as build_gemini_kwargs
from janito.llm_adapters.responses import accumulator as responses_accumulator
from janito.llm_adapters.responses import build_call_kwargs as build_responses_kwargs
from janito.accounting_policy import record_turn_accounting
from janito.llm_adapters.usage import TurnInfo
from janito.runtime_config import resolve_runtime_config
from janito.tooling.executor import extract_tool_names

from ..config import WebServerConfig
from ..events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    PromptStartedEvent,
    WaitingEvent,
    usage_event_from_usage,
)
from . import anthropic as anthropic_runner
from . import completions as completions_runner
from . import dashscope as dashscope_runner
from . import gemini as gemini_runner
from . import responses as responses_runner
from .tooling import reset_used_files, resolve_tools
from .turn import run_tool_turn

logger = logging.getLogger(__name__)


def _resolve_turn_config(config, effective_provider, model):
    """Resolve max tokens / preserve_thinking / reasoning level for the turn.

    Thin web entry point over the shared
    :func:`janito.model_settings.resolve_model_settings` service: a
    model-scoped config override wins, then the model's built-in default,
    then ``FALLBACK_MAX_OUTPUT_TOKENS``. Web-specific session overrides
    stay with the caller; ``config`` is kept for signature compatibility.
    """
    return resolve_model_settings(
        effective_provider,
        model,
        fallback_max_output_tokens=FALLBACK_MAX_OUTPUT_TOKENS,
    )


@dataclass(frozen=True)
class _Runner:
    """Per-API runner for the web agent loop.

    Bundles the web-only glue (client creation, event streaming) from the
    runner module with the shared call-kwargs builder and accumulator class
    from the ``janito.llm_adapters`` adapters, so the loop keeps a single uniform
    interface per API type.
    """

    create_client: Callable[..., Any]
    build_call_kwargs: Callable[..., dict]
    accumulator: type
    stream_turn_events: Callable[..., Any]


def _runner_for(api_type: str) -> _Runner:
    """Return the runner for an API type.

    Every API type (Completions included) has its own runner module under
    ``janito.web.backend.agent``, so this never falls back to a built-in
    inline path.
    """
    if api_type == "Completions":
        return _Runner(
            completions_runner.create_client,
            completions_runner.build_call_kwargs,
            completions_accumulator,
            completions_runner.stream_turn_events,
        )
    if api_type == "Responses":
        return _Runner(
            responses_runner.create_client,
            build_responses_kwargs,
            responses_accumulator,
            responses_runner.stream_turn_events,
        )
    if api_type == "Anthropic":
        return _Runner(
            anthropic_runner.create_client,
            build_anthropic_kwargs,
            anthropic_accumulator,
            anthropic_runner.stream_turn_events,
        )
    if api_type == "DashScope":
        return _Runner(
            dashscope_runner.create_client,
            build_dashscope_kwargs,
            dashscope_accumulator,
            dashscope_runner.stream_turn_events,
        )
    if api_type == "Gemini":
        return _Runner(
            gemini_runner.create_client,
            build_gemini_kwargs,
            gemini_accumulator,
            gemini_runner.stream_turn_events,
        )
    raise ValueError(f"Unknown API type: {api_type}")


def _build_assistant_message(acc: Any, full_content: str) -> dict:
    """Build the assistant message dict from the accumulated turn."""
    assistant_message = {"role": "assistant", "content": full_content}
    reasoning_content = acc.reasoning_content()
    if reasoning_content:
        assistant_message["reasoning_content"] = reasoning_content
    # Native Gemini turns: keep the model's raw thought blocks (text +
    # signature) so stateless follow-up turns can resend them verbatim
    # (Gemini 3.x requires this for reasoning continuity).  Only the Gemini
    # accumulator exposes ``thought_parts``; other runners never set it.
    thought_parts = getattr(acc, "thought_parts", None) or []
    if thought_parts:
        assistant_message["thought_parts"] = thought_parts
    # Native Responses-API image generation (image_generation tool): attach
    # the saved image paths so the frontend can rebuild the content cards
    # when the session history is reloaded.  Completions runners never set
    # ``image_results``, so getattr keeps this a no-op for them.
    image_results = getattr(acc, "image_results", None) or []
    if image_results:
        assistant_message["images"] = [
            {"path": img["path"], "revised_prompt": img.get("revised_prompt", "")} for img in image_results
        ]
    return assistant_message


def _create_agent_client(runner, base_url, api_key):
    """Create the SDK client for the API type."""
    return runner.create_client(base_url, api_key)


def _log_agent_config(config, base_url, model, api_type):
    """Log the resolved backend only when verbose mode was requested."""
    if config.verbose:
        logger.info("Web agent: model=%s backend=%s api_type=%s", model, base_url or "api.openai.com", api_type)


def _turn_call_kwargs_and_acc(
    runner,
    model,
    config,
    tools_schemas,
    messages,
    max_output_tokens,
    preserve_thinking,
    reasoning_effort,
):
    """Build the per-type call kwargs and a fresh accumulator for one turn."""
    call_kwargs = runner.build_call_kwargs(
        model,
        messages,
        tools_schemas,
        config,
        max_output_tokens,
        preserve_thinking,
        reasoning_effort,
    )
    return call_kwargs, runner.accumulator()


async def _stream_turn(client, runner, call_kwargs, acc):
    """Stream one API turn, yielding reasoning/token events.

    The caller owns ``acc``; on completion it holds the full turn state for
    end-of-turn assembly.
    """
    async for ev in runner.stream_turn_events(client, call_kwargs, acc):
        yield ev


def _fold_turn_usage(turn_stats: TurnInfo | None, acc) -> TurnInfo | None:
    """Fold one round's usage into the turn-level cumulative totals.

    Each round's accumulator is discarded when the loop continues, so the
    usage of tool-call rounds would otherwise be lost; ``TurnInfo`` keeps
    the final round's counters and sums last_input/last_cached/last_output
    across every round of the turn.
    """
    round_usage = acc.usage_object()
    if turn_stats is None:
        return TurnInfo.from_usage(round_usage)
    turn_stats.add_round(round_usage)
    return turn_stats


def _attach_turn_stats(usage_event, turn_stats: TurnInfo | None) -> None:
    """Attach the cumulative turn totals to the final-round usage event."""
    if turn_stats is None:
        return
    usage_event.turn_input = turn_stats.turn_input
    usage_event.turn_cached = turn_stats.turn_cached
    usage_event.turn_output = turn_stats.turn_output


def _record_web_turn(provider: str | None, model: str | None, turn_stats: TurnInfo | None) -> None:
    """Append one overall-use accounting row for a completed web turn.

    Thin web entry point over the shared
    :func:`janito.accounting_policy.record_turn_accounting` service
    (issue #72). Best effort -- never raises.
    """
    record_turn_accounting(turn_stats, provider, model)


def _apply_steering(messages: list[dict], steering_prompts: list[str] | None):
    """Drain the live inbox only at a complete model/tool boundary."""
    while steering_prompts:
        content = steering_prompts.pop(0)
        messages.append({"role": "user", "content": content})
        yield PromptStartedEvent(content=content, mode="steer")


async def _record_round(acc, full_content, messages, mcp_enabled, allowed_tool_names):
    """Commit the model response and all its tool results before steering."""
    if acc.tool_calls_list():
        async for event in run_tool_turn(
            acc.tool_calls_list(),
            full_content,
            messages,
            mcp_enabled,
            thought_parts=getattr(acc, "thought_parts", None) or [],
            allowed_tools=allowed_tool_names,
        ):
            yield event
    else:
        messages.append(_build_assistant_message(acc, full_content))


async def stream_prompt(
    prompt: str,
    messages: list[dict],
    config: WebServerConfig,
    tools: list[dict] | None = None,
    use_mcp: bool = True,
    steering_prompts: list[str] | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Yield structured events instead of printing to terminal.

    Args:
        prompt: The user prompt to send.
        messages: Caller-owned conversation history (mutated in place).
        config: Runtime config from CLI args.
        tools: Optional explicit tool schemas. ``None`` = auto-discover
               (unless ``config.no_tools``).
        use_mcp: If True, load and use MCP tools.
        steering_prompts: Live inbox consumed between model/tool rounds.
    """
    # Clear the in-process used-files tracker so per-prompt tracking only
    # reflects the files touched while handling the *current* prompt (best
    # effort, never raises), mirroring the CLI's ``run_turn`` behaviour.
    reset_used_files()
    # Effective provider for this turn: a session-only override picked from
    # the chat-page combo wins over the CLI --provider, which wins over the
    # persisted default (config.json / auth.json).  The session override is
    # never written to disk -- see WebServerConfig.session_provider.
    effective_provider = config.session_provider or config.provider or get_active_provider()
    # The API type for this turn: --api-type first, then the provider's
    # configured api-type (the web Settings drawer's per-provider combo, the
    # same value the CLI's --set api-type=... writes), then the provider's
    # built-in default (its default_api_type entry).
    api_type = resolve_api_type(config.api_type, effective_provider)
    runner = _runner_for(api_type)

    try:
        # Endpoint resolution honors the API type: providers with an
        # ``endpoint_by_api_type`` map get their per-type base URL (e.g.
        # DeepSeek's Anthropic-compatible URL, Alibaba's native-SDK URL).
        base_url, api_key, model = resolve_runtime_config(
            cli_model=config.model,
            cli_provider=effective_provider,
            cli_api_type=api_type,
        )
    except (ValueError, OSError, RuntimeError) as e:
        yield ErrorEvent(message=str(e))
        return

    try:
        client = _create_agent_client(runner, base_url, api_key)
    except (ValueError, TypeError, RuntimeError, OSError) as e:
        yield ErrorEvent(message=str(e))
        return

    _log_agent_config(config, base_url, model, api_type)

    mcp_enabled = use_mcp
    tools_schemas = await resolve_tools(config, tools, use_mcp)

    # Execution-time privilege gate (issue #87): the model may only call the
    # tools offered in this turn (the session default is privilege-filtered;
    # the web UI has no per-message tool override).
    allowed_tool_names = extract_tool_names(tools_schemas)

    max_output_tokens, preserve_thinking, reasoning_effort = _resolve_turn_config(config, effective_provider, model)

    messages.append({"role": "user", "content": prompt})

    # Cumulative turn totals: the usage of tool-call rounds would otherwise be
    # lost when the accumulator is discarded each round (see _fold_turn_usage).
    turn_stats: TurnInfo | None = None

    first_turn = True
    while True:
        # Never insert a user message between a tool call and its results.
        # The socket reader owns appends; this task drains at safe boundaries.
        for event in _apply_steering(messages, steering_prompts):
            yield event
        call_kwargs, acc = _turn_call_kwargs_and_acc(
            runner,
            model,
            config,
            tools_schemas,
            messages,
            max_output_tokens,
            preserve_thinking,
            reasoning_effort,
        )

        # Signal the browser that we're waiting for the API (replaces CLI spinner)
        yield WaitingEvent(phase="initial" if first_turn else "after_tools")
        first_turn = False

        # --- Stream the completion, yielding tokens as they arrive ---
        try:
            async for ev in _stream_turn(client, runner, call_kwargs, acc):
                yield ev
        except Exception as e:  # noqa: BLE001 - arbitrary SDK errors
            logger.error(f"API streaming error: {e}")
            yield ErrorEvent(message=f"API error: {e!s}")
            return

        full_content = acc.full_content()

        # Fold this round's usage into the turn totals (the accumulator is
        # discarded when the tool round below continues the loop).
        turn_stats = _fold_turn_usage(turn_stats, acc)

        async for ev in _record_round(acc, full_content, messages, mcp_enabled, allowed_tool_names):
            yield ev

        # A steer received during the final text stream still gets a model
        # round before the turn completes (and before queued follow-ups).
        if acc.tool_calls_list() or steering_prompts:
            continue

        usage_event = usage_event_from_usage(acc.usage_object(), max_tokens=max_output_tokens)
        if usage_event:
            # Attach the cumulative turn totals (tool-call rounds included)
            # to the final-round usage event when the turn spanned several
            # API rounds.
            _attach_turn_stats(usage_event, turn_stats)
            yield usage_event
        # Overall-use accounting (best effort, never raises): one row per
        # completed turn that reported token usage, with the turn-wide
        # counters and the numeric cost estimate (issue #72).
        _record_web_turn(effective_provider, model, turn_stats)

        yield DoneEvent(full_content=full_content, message_count=len(messages))
        return
