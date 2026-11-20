"""Tests for web session persistence (issue #36).

The web backend mirrors every conversation to
``./.janito/sessions/<id>/metadata.json`` (relative to the CWD) and restores
those files when the server starts, so conversations survive a restart. The
frontend prefetches every session's history on page load to restore the UI
state ("events sent by the backend, replayed in the frontend").

These tests pin down:

1. creating a session writes its metadata file (metadata + system prompt);
2. messages appended by the agent loop are persisted on demand;
3. a fresh SessionManager restores the persisted sessions from disk;
4. deleting a session removes its file;
5. a restart (F2) rewrites the file with the cleared history;
6. ``--no-history`` disables persistence entirely.
"""

import json
import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

# The web routes need the optional `web` extra (fastapi). Skip gracefully
# when fastapi is not installed (e.g. minimal tox envs).
try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ModuleNotFoundError:
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi (web extra) is not installed")


def _patch_config_start(monkeypatch, start=None):
    """Pin load_system_prompt_start so tests never touch the real config.

    The web backend resolves the effective system prompt through the
    config-aware ``default_system_prompt_manager()`` (system-prompt /
    system-prompt-file keys), so without this the tests would read the
    developer's real config (e.g. a ``system-prompt-file`` pointing at a
    relative path that does not exist in the temp CWD).
    """
    import janito.config_loaders as config_loaders_mod

    monkeypatch.setattr(config_loaders_mod, "load_system_prompt_start", lambda: (start, None))


@pytest.fixture()
def isolated_cwd(tmp_path, monkeypatch):
    """Run the server in a temp CWD so ``.janito/sessions/`` lands there."""
    _patch_config_start(monkeypatch)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def client(isolated_cwd):
    """A TestClient wired to a fresh Janito web app (temp CWD)."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    config = WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True)
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def _session_path(isolated_cwd, session_id):
    return isolated_cwd / ".janito" / "sessions" / session_id / "metadata.json"


def _read_doc(path):
    return json.loads(path.read_text(encoding="utf-8"))


@requires_fastapi
def test_create_session_writes_metadata(client, isolated_cwd):
    """POST /api/chat/sessions writes the session's metadata file."""
    resp = client.post("/api/chat/sessions")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    path = _session_path(isolated_cwd, session_id)
    assert path.exists()

    doc = _read_doc(path)
    assert doc["session_id"] == session_id
    assert doc["title"] == "New conversation"

    # The first message (if a system prompt is configured) is the system role.
    if doc["system_prompt"]:
        assert doc["messages"]
        assert doc["messages"][0]["role"] == "system"
        assert doc["messages"][0]["content"] == doc["system_prompt"]


@requires_fastapi
def test_sessions_dir_env_override(client, isolated_cwd, monkeypatch):
    """JANITO_SESSIONS_DIR redirects persistence (e.g. to a mounted volume)."""
    target = isolated_cwd / "mounted" / "sessions"
    monkeypatch.setenv("JANITO_SESSIONS_DIR", str(target))

    resp = client.post("/api/chat/sessions")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    assert (target / session_id / "metadata.json").exists()
    assert not (isolated_cwd / ".janito" / "sessions").exists()


@requires_fastapi
def test_turn_messages_are_persisted(client, isolated_cwd):
    """Messages appended to a session (as the agent loop does) hit the file."""
    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    sessions = client.app.state.sessions
    session = sessions.get(session_id)

    # Simulate what stream_prompt does to session.messages during a turn.
    session.messages.append({"role": "user", "content": "hello"})
    session.messages.append({"role": "assistant", "content": "hi there"})
    sessions.persist(session)

    doc = _read_doc(_session_path(isolated_cwd, session_id))
    roles = [m["role"] for m in doc["messages"]]
    assert roles[-2:] == ["user", "assistant"]
    assert doc["messages"][-1]["content"] == "hi there"


@requires_fastapi
def test_sessions_restored_from_disk_on_fresh_manager(client, isolated_cwd):
    """A new SessionManager (fresh server start) restores persisted sessions."""
    from janito.web.backend.config import WebServerConfig
    from janito.web.backend.session import SessionManager

    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    sessions = client.app.state.sessions
    session = sessions.get(session_id)
    session.messages.append({"role": "user", "content": "hello"})
    session.messages.append({"role": "assistant", "content": "world"})
    session.title = "restored title"
    sessions.persist(session)

    fresh = SessionManager(WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True))
    assert fresh.load_from_disk() == 1

    restored = fresh.get(session_id)
    assert restored is not None
    assert restored.title == "restored title"
    assert [m["role"] for m in restored.messages][-2:] == ["user", "assistant"]
    assert restored.messages[-1]["content"] == "world"


@requires_fastapi
def test_create_app_restores_sessions(client, isolated_cwd):
    """create_app() itself reloads persisted sessions at startup."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    sessions = client.app.state.sessions
    session = sessions.get(session_id)
    session.messages.append({"role": "user", "content": "survives restart"})
    sessions.persist(session)

    # A brand-new app instance is what a server restart produces.
    app2 = create_app(WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True))
    with TestClient(app2) as c2:
        listed = c2.get("/api/chat/sessions").json()["sessions"]
        assert [s["session_id"] for s in listed] == [session_id]

        history = c2.get(f"/api/chat/sessions/{session_id}").json()
        assert history["messages"][-1]["content"] == "survives restart"


@requires_fastapi
def test_delete_session_removes_file(client, isolated_cwd):
    """DELETE /api/chat/sessions/{id} removes the session's directory."""
    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    path = _session_path(isolated_cwd, session_id)
    assert path.exists()

    resp = client.delete(f"/api/chat/sessions/{session_id}")
    assert resp.status_code == 200
    assert not path.exists()
    assert not path.parent.exists()


@requires_fastapi
def test_restart_rewrites_history(client, isolated_cwd):
    """A restart (F2) rewrites the file with only the system prompt left."""
    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    sessions = client.app.state.sessions
    session = sessions.get(session_id)
    session.messages.append({"role": "user", "content": "hello"})
    sessions.persist(session)

    # Mirror the WebSocket restart path (session.restart + persist).
    session.restart()
    sessions.persist(session)

    doc = _read_doc(_session_path(isolated_cwd, session_id))
    assert all(m["role"] == "system" for m in doc["messages"])


@requires_fastapi
def test_no_history_disables_persistence(isolated_cwd):
    """--no-history skips writing AND restoring session files."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    config = WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True, no_history=True)
    app = create_app(config)
    with TestClient(app) as c:
        resp = c.post("/api/chat/sessions")
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # No file is written for the new session...
        assert not _session_path(isolated_cwd, session_id).exists()

    # ...so a fresh app (server restart) has nothing to restore.
    app2 = create_app(WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True, no_history=True))
    with TestClient(app2) as c2:
        assert c2.get("/api/chat/sessions").json()["sessions"] == []


@requires_fastapi
def test_rollback_is_persisted(client, isolated_cwd):
    """A rollback (Ctrl+C / error) rewrites the file with the truncation."""
    resp = client.post("/api/chat/sessions")
    session_id = resp.json()["session_id"]
    sessions = client.app.state.sessions
    session = sessions.get(session_id)

    start = len(session.messages)
    session.history_turns = [start]
    # A turn starts: user message + partial assistant content appended.
    session.messages.append({"role": "user", "content": "hello"})
    session.messages.append({"role": "assistant", "content": "partial"})
    sessions.persist(session)

    # Server-side rollback mirrors _rollback() in routers/chat.py.
    del session.messages[session.history_turns[-1] :]
    session.history_turns.pop()
    sessions.persist(session)

    doc = _read_doc(_session_path(isolated_cwd, session_id))
    assert all(m["role"] == "system" for m in doc["messages"])


@requires_fastapi
def test_malformed_session_file_is_skipped(isolated_cwd):
    """Unreadable/malformed files do not crash the restore."""
    from janito.web.backend.config import WebServerConfig
    from janito.web.backend.session import SessionManager

    sessions_dir = isolated_cwd / ".janito" / "sessions"
    bad_dir = sessions_dir / "bad"
    bad_dir.mkdir(parents=True)
    (bad_dir / "metadata.json").write_text("not json\n{broken\n", encoding="utf-8")
    # Legacy jsonl files are ignored.
    (sessions_dir / "legacy.jsonl").write_text("not json\n", encoding="utf-8")

    manager = SessionManager(WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True))
    assert manager.load_from_disk() == 0
