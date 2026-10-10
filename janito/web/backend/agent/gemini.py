"""Native Gemini SDK runner for the web agentic loop.

The per-API adapter (call-kwargs building, stream accumulation) lives in
:mod:`janito.llm_adapters.gemini` -- the shared adapter layer used by both agent
loops.  This module keeps the web-only glue: :func:`create_client`
(prepares the sync ``google-genai`` client, guarding the optional package)
and :func:`stream_turn_events` (consumes the sync stream chunk-by-chunk
through ``asyncio.to_thread``).  The loop builds call kwargs and
accumulators directly from the shared adapters in :mod:`janito.llm_adapters.gemini`.
"""

import logging

from janito.llm_adapters.gemini import GeminiTurnAccumulator
from janito.optional_packages import require_optional_package

from .stream_utils import _next_or_none, emit_stream_events
from .workers import run_in_worker

logger = logging.getLogger(__name__)


def create_client(base_url, api_key):
    """Create the native Gemini SDK client, guarding the optional package.

    The ``google-genai`` package is optional (see
    ``janito.providers.REQUIRES_BY_API_TYPE``), so its availability is checked
    explicitly and the import happens lazily.  The resolved base URL (the
    provider's native-SDK base URL from ``endpoint_by_api_type``, or a config
    endpoint override) is passed as the SDK's ``http_options.base_url``;
    ``None`` uses the SDK default
    (``https://generativelanguage.googleapis.com``).
    """
    require_optional_package("google.genai", "Gemini", "google-genai")
    from google import genai

    http_options = {"base_url": base_url} if base_url else None
    return genai.Client(api_key=api_key, http_options=http_options)


async def _gemini_chunks(client, call_kwargs: dict):
    """Yield chunks from the sync Gemini stream, off the event loop.

    ``generate_content_stream`` is a sync generator; each chunk is pulled
    through ``asyncio.to_thread`` so the event loop stays responsive while
    the SDK streams the response.
    """
    stream = client.models.generate_content_stream(**call_kwargs)
    while True:
        chunk = await run_in_worker(_next_or_none, stream)
        if chunk is None:
            return
        yield chunk


async def stream_turn_events(client, call_kwargs: dict, acc: GeminiTurnAccumulator):
    """Stream one Gemini generation turn, yielding reasoning/token events.

    The caller owns ``acc``; on completion it holds the full turn state for
    end-of-turn assembly (``run_tool_turn`` / ``DoneEvent``).
    """
    async for ev in emit_stream_events(_gemini_chunks(client, call_kwargs), acc, break_on_done=True):
        yield ev


__all__ = [
    "create_client",
    "stream_turn_events",
    "_gemini_chunks",
]
