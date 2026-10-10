"""JSON-RPC 2.0 primitives for the ACP stdio transport.

ACP exchanges newline-delimited JSON-RPC 2.0 messages over stdin/stdout, so
all messages are single-line JSON (``compact_json``).  Error codes follow the
JSON-RPC 2.0 spec.  Note: malformed input lines carry no usable ``id``, so
they are dropped without a response (no parse-error reply is possible).
"""

import json
from typing import Any

INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class RpcError(Exception):
    """A JSON-RPC error that aborts the current request."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def compact_json(payload: Any) -> str:
    """Serialize ``payload`` to a single line (ACP forbids embedded newlines)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
