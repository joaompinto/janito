"""Native DashScope SDK runner for the web agentic loop.

The per-API adapter (call-kwargs building, stream accumulation) lives in
:mod:`janito.llm_adapters.dashscope` — the shared adapter layer used by both agent
loops.  This module keeps the web-only glue: :func:`create_client`
(prepares the sync DashScope SDK), :func:`_dashscope_chunks` (consumes the
sync stream chunk-by-chunk through ``asyncio.to_thread``, retrying once on
a model/endpoint mismatch) and :func:`stream_turn_events`.  The loop
builds call kwargs and accumulators directly from the shared adapters in
:mod:`janito.llm_adapters.dashscope`.
"""

import logging
from types import SimpleNamespace

from janito.llm_adapters.dashscope import DashScopeTurnAccumulator
from janito.optional_packages import require_optional_package

from .stream_utils import _next_or_none, emit_stream_events
from .workers import run_in_worker

logger = logging.getLogger(__name__)


def create_client(base_url, api_key):
    """Prepare the native DashScope SDK, guarding the optional package.

    The DashScope SDK routes requests through the module-level
    ``base_http_api_url`` global; it is pointed at the resolved endpoint
    (the provider's native-SDK base URL, or a config endpoint override)
    before the first call.  Returns a lightweight handle carrying the
    resolved ``base_url`` / ``api_key`` for the stream runner.
    """
    require_optional_package("dashscope", "DashScope", "dashscope")
    import dashscope

    if base_url:
        dashscope.base_http_api_url = base_url
        logger.debug(f"DashScope base_http_api_url set to {base_url}")

    return SimpleNamespace(base_url=base_url, api_key=api_key)


async def _dashscope_chunks(handle, call_kwargs: dict):
    """Yield chunks from the sync DashScope stream, off the event loop.

    The native API serves multimodal models (e.g. alibaba's ``qwen3.8-max``
    flagship) from the ``multimodal-generation`` endpoint and
    plain-text models from ``text-generation``; the endpoint is inferred from
    the model name and, when the API rejects the model with the "url error"
    (model/endpoint mismatch), the call is retried once on the other endpoint
    so misclassified models still work (mirrors
    ``janito.llm_clients.dashscope.dashscope_stream._stream_response``; the
    endpoint-routing helpers come from the shared adapter layer, so the web
    loop never imports from ``llm_clients`` -- issue #90).
    """
    from dashscope import Generation, MultiModalConversation

    from janito.llm_adapters.dashscope import (
        _is_multimodal_model,
        _ModelEndpointMismatch,
        _to_multimodal_messages,
    )

    kwargs = dict(call_kwargs)
    kwargs["api_key"] = handle.api_key

    multimodal = _is_multimodal_model(kwargs.get("model", ""))
    attempts = (multimodal, not multimodal)

    last_error: Exception | None = None
    for use_multimodal in attempts:
        round_kwargs = dict(kwargs)
        if use_multimodal:
            # The multimodal API expects message content as a list of
            # modality items ([{"text": "..."}]) instead of a plain string.
            round_kwargs["messages"] = _to_multimodal_messages(round_kwargs["messages"])
        cls = MultiModalConversation if use_multimodal else Generation
        try:
            stream = cls.call(**round_kwargs)
            while True:
                chunk = await run_in_worker(_next_or_none, stream)
                if chunk is None:
                    return
                yield chunk
        except _ModelEndpointMismatch as e:
            last_error = e
            if use_multimodal == attempts[-1]:
                raise
            logger.debug("DashScope rejected the model for this endpoint; retrying on the other generation endpoint")
    raise last_error


async def stream_turn_events(client, call_kwargs: dict, acc: DashScopeTurnAccumulator):
    """Stream one DashScope generation turn, yielding reasoning/token events.

    The caller owns ``acc``; on completion it holds the full turn state for
    end-of-turn assembly (``run_tool_turn`` / ``DoneEvent``).
    """
    async for ev in emit_stream_events(_dashscope_chunks(client, call_kwargs), acc, break_on_done=True):
        yield ev


__all__ = [
    "create_client",
    "stream_turn_events",
    "_dashscope_chunks",
]
