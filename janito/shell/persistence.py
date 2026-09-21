"""Filesystem persistence for CLI interactive-session resumes (-C/--continue).

Each interactive shell session in a working directory is mirrored to
``./.janito/session.json`` (relative to the current working directory, next to
the shell's ``history.log`` and the ``changes.jsonl`` tool log) so ``janito
-C`` can restore the previous conversation in that directory.

File format (single JSON object)::

    {"version": 1, "cwd", "saved_at", "provider", "model", "model_override",
     "api_type", "thinking", "effort", "system_prompt",
     "messages_history", "history_turns", "previous_response_id",
     "conversation_items", "conversation_turn", "response_chain",
     "response_turn", "mirrored_history", "mirrored_turn"}

``messages_history``, ``conversation_items`` and ``mirrored_history`` are the
shell's native per-API conversation structures (Completions-style role/content
dicts for the client-side-history modes, Responses input items for the
Responses modes), so restoring the file reproduces the exact in-memory state
the shell had when it was saved.

Like the other best-effort tracking modules (:mod:`janito.tooling.changes`,
:mod:`janito.web.backend.session_store`), persistence never raises: an I/O or
JSON error is logged and the caller is left untouched, so an unwritable
directory or a broken file can never break the shell.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The per-working-directory workspace directory that also holds the shell
#: ``history.log`` and the ``changes.jsonl`` log.
STATE_DIR = Path(".janito")

#: Snapshot file name (relative to ``STATE_DIR``).
STATE_FILE = "session.json"

#: Current on-disk format version; bumped when the snapshot schema changes.
STATE_VERSION = 1


def get_state_path() -> Path:
    """Return the absolute path of the conversation snapshot for this cwd."""
    return Path.cwd() / STATE_DIR / STATE_FILE


def save_conversation_state(state: dict[str, Any]) -> None:
    """Write the conversation snapshot to ``./.janito/session.json``.

    The file is rewritten in full on every save, so rollbacks, restarts and
    mid-session truncations are reflected on disk.  Best-effort: never raises.

    Args:
        state: The snapshot dict to persist (see module docstring).
    """
    try:
        path = get_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except Exception as e:  # noqa: BLE001 - persistence must never break the shell
        logger.debug(f"Failed to save conversation state to {get_state_path()}: {e}")


def load_conversation_state() -> dict[str, Any] | None:
    """Read the conversation snapshot saved by the last session in this cwd.

    Returns:
        dict | None: The saved snapshot, or ``None`` when the file is missing,
        malformed or unreadable.  Never raises.
    """
    path = get_state_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            parsed = json.load(f)
        if not isinstance(parsed, dict) or "messages_history" not in parsed:
            logger.debug(f"Skipping conversation state without messages: {path}")
            return None
        return parsed
    except Exception:  # noqa: BLE001 - a broken file must not break the shell
        logger.debug("Failed to read conversation state %s", path, exc_info=True)
        return None


def clear_conversation_state() -> bool:
    """Remove the conversation snapshot for this cwd, if present.

    Returns:
        bool: ``True`` if the file existed and was removed, ``False`` otherwise.
        Never raises.
    """
    path = get_state_path()
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception as e:  # noqa: BLE001 - best effort, never raises
        logger.debug(f"Failed to delete conversation state {path}: {e}")
    return False


def make_state(
    *,
    provider: str | None,
    model: str | None,
    model_override: str | None,
    api_type: str | None,
    thinking: bool,
    effort: str | None,
    system_prompt: str | None,
    messages_history: list[Any],
    history_turns: list[int],
    previous_response_id: str | None,
    conversation_items: list[Any] | None,
    conversation_turn: int,
    response_chain: list[str],
    response_turn: int,
    mirrored_history: list[Any],
    mirrored_turn: int,
) -> dict[str, Any]:
    """Assemble a versioned, serializable snapshot dict from shell state.

    Kept as a pure helper so tests can build snapshots without a shell and so
    :meth:`janito.shell.interactive.InteractiveShell.conversation_snapshot`
    stays a thin wrapper.
    """
    return {
        "version": STATE_VERSION,
        "cwd": str(Path.cwd()),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "model_override": model_override,
        "api_type": api_type,
        "thinking": bool(thinking),
        "effort": effort,
        "system_prompt": system_prompt,
        "messages_history": messages_history,
        "history_turns": history_turns,
        "previous_response_id": previous_response_id,
        "conversation_items": conversation_items,
        "conversation_turn": conversation_turn,
        "response_chain": response_chain,
        "response_turn": response_turn,
        "mirrored_history": mirrored_history,
        "mirrored_turn": mirrored_turn,
    }


__all__ = [
    "STATE_DIR",
    "STATE_FILE",
    "STATE_VERSION",
    "get_state_path",
    "save_conversation_state",
    "load_conversation_state",
    "clear_conversation_state",
    "make_state",
]
