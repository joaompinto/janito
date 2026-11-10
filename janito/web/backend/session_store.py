"""Filesystem persistence for web chat sessions (issue #36).

Each conversation is stored as ``./.janito/sessions/<session_id>/metadata.json``
(relative to the current working directory, mirroring ``./.janito/changes.jsonl``
from :mod:`janito.tooling.changes`).

File format (single JSON object)::

    {"session_id", "title", "created_at", "last_active", "system_prompt",
     "provider", "model", "messages": [...]}

where ``messages`` is the OpenAI-format conversation history in order.

The whole file is rewritten whenever the in-memory conversation changes, so
the on-disk state always matches the session exactly — including rollbacks
(Ctrl+C / errors) and restarts (F2), which truncate the history.

Like the other best-effort tracking modules (:mod:`janito.tooling.changes`,
:mod:`janito.tooling.tools_usage`), persistence never raises: an I/O error is
logged and the in-memory session is left untouched, so an unwritable
directory or a broken disk cannot take the web server down.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Directory (relative to the current working directory) where the session
# files live. ``./.janito`` is the per-project workspace directory (it also
# holds the shell ``history.log`` and the ``changes.jsonl`` log).
SESSIONS_DIR = Path(".janito") / "sessions"

# Serialises access from the multiple threads the web backend uses.
_lock = threading.Lock()

_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", re.ASCII)


def get_sessions_dir() -> Path:
    """Return the absolute path to the sessions directory.

    Returns:
        pathlib.Path: ``<cwd>/.janito/sessions``.
    """
    return Path.cwd() / SESSIONS_DIR


def metadata_file_path(session_id: str) -> Path:
    """Return a confined metadata path, rejecting invalid IDs and symlinks."""
    if not isinstance(session_id, str) or _SESSION_ID.fullmatch(session_id) is None:
        raise ValueError("Invalid session ID")
    directory = get_sessions_dir()
    session_dir = directory / session_id
    meta_path = session_dir / "metadata.json"
    if session_dir.is_symlink() or meta_path.is_symlink():
        raise ValueError("Session paths must not be symbolic links")
    if not meta_path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Session path escapes the sessions directory")
    return meta_path


def _session_meta(session) -> dict[str, Any]:
    """Serialize the session's metadata (everything but ``messages``)."""
    return {
        "session_id": session.session_id,
        "title": session.title,
        "created_at": session.created_at,
        "last_active": session.last_active,
        "system_prompt": session.system_prompt,
        "provider": session.provider,
        "model": session.model,
    }


def _write_metadata(meta_path: Path, payload: dict[str, Any]) -> None:
    """Publish complete JSON atomically; failures leave the last save intact."""
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=meta_path.parent,
            prefix=".metadata-", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, meta_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_session(session) -> None:
    """Rewrite ``<session_id>/metadata.json`` with metadata + messages.

    The file is rewritten in full (not appended) so rollbacks, restarts and
    mid-turn truncations are reflected on disk. Best-effort: never raises.
    """
    try:
        meta_path = metadata_file_path(session.session_id)
        with _lock:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                **_session_meta(session),
                "messages": list(session.messages),
            }
            _write_metadata(meta_path, payload)
    except Exception as e:  # noqa: BLE001 - persistence must never break the server
        logger.debug(f"Failed to save session {session.session_id}: {e}")


def delete_session_file(session_id: str) -> bool:
    """Remove the session's persisted directory.

    Also removes a leftover legacy ``<session_id>.jsonl`` file when present.

    Returns:
        bool: ``True`` if anything was removed, ``False`` otherwise. Never raises.
    """
    try:
        with _lock:
            removed = False
            meta_path = metadata_file_path(session_id)
            legacy_path = get_sessions_dir() / f"{session_id}.jsonl"
            if legacy_path.is_symlink():
                raise ValueError("Session paths must not be symbolic links")
            if meta_path.exists():
                removed = True
                meta_path.unlink()
                try:
                    meta_path.parent.rmdir()
                except OSError:
                    pass
            if legacy_path.exists():
                removed = True
                legacy_path.unlink()
            return removed
    except Exception as e:  # noqa: BLE001 - persistence must never break the server
        logger.debug(f"Failed to delete session file {session_id}: {e}")
        return False


def _read_directory_session(meta_path: Path) -> dict[str, Any] | None:
    """Read a session stored in its ``<id>/metadata.json`` file."""
    try:
        meta_path = metadata_file_path(meta_path.parent.name)
        with meta_path.open("r", encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, dict) and parsed.get("session_id") == meta_path.parent.name:
            parsed.setdefault("messages", [])
            return parsed
        logger.debug(f"Skipping session file without metadata: {meta_path}")
        return None
    except Exception:
        logger.debug("Failed to read session metadata %s", meta_path, exc_info=True)
    return None


def load_sessions() -> list[dict[str, Any]]:
    """Read every ``.janito/sessions/*/metadata.json`` file.

    Returns:
        list[dict]: One ``{session_id, title, created_at, last_active,
        system_prompt, messages}`` dict per readable file, sorted by file
        name. Malformed/unreadable files are skipped with a debug log. Never
        raises.
    """
    sessions: list[dict[str, Any]] = []
    try:
        directory = get_sessions_dir()
        if not directory.exists():
            return sessions
        for meta_path in sorted(directory.glob("*/metadata.json")):
            parsed = _read_directory_session(meta_path)
            if parsed is not None:
                sessions.append(parsed)
    except Exception as e:  # noqa: BLE001 - persistence must never break the server
        logger.debug(f"Failed to load sessions from disk: {e}")
    return sessions


def load_session(session_id: str) -> dict[str, Any] | None:
    """Read a single session (``<session_id>/metadata.json``) from disk.

    Used by the TTL lazy-reload path: a session evicted from memory because
    it was idle past the TTL is restored on demand instead of the frontend
    getting a 404.

    Returns:
        dict | None: ``{session_id, title, created_at, last_active,
        system_prompt, messages, ...}`` for the session, or ``None`` when
        the file is missing, malformed or unreadable. Never raises.
    """
    try:
        meta_path = metadata_file_path(session_id)
        if meta_path.exists():
            return _read_directory_session(meta_path)
    except (OSError, ValueError, RuntimeError):
        logger.debug("Failed to load session %r", session_id, exc_info=True)
    return None


__all__ = [
    "SESSIONS_DIR",
    "get_sessions_dir",
    "metadata_file_path",
    "save_session",
    "delete_session_file",
    "load_sessions",
    "load_session",
]
