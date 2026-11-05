"""Session IDs and persisted metadata cannot redirect filesystem operations."""

import json
import os

import pytest

from janito.web.backend import session_store as store
from janito.web.backend.config import WebServerConfig
from janito.web.backend.session import ConversationSession, SessionManager


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("session_id", [
    "", ".", "..", "../outside", "../../outside", "/absolute", r"..\outside",
    "a/b", r"a\b", "a\x00b", "a\nb", "a" * 129, "é", "%2e%2e", None,
])
def test_invalid_ids_are_rejected_without_filesystem_changes(tmp_path, session_id):
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "metadata.json"
    marker.write_text('{"session_id":"outside","messages":[]}', encoding="utf-8")
    before = marker.read_bytes()
    with pytest.raises(ValueError):
        store.metadata_file_path(session_id)
    store.save_session(ConversationSession(session_id))
    assert store.load_session(session_id) is None
    assert store.delete_session_file(session_id) is False
    assert marker.read_bytes() == before
    assert not store.get_sessions_dir().exists()


@pytest.mark.parametrize("session_id", ["abc123def456", "session-1", "Session_2", "a" * 128])
def test_valid_ids_round_trip(session_id):
    session = ConversationSession(session_id, messages=[{"role": "user", "content": "hello"}])
    store.save_session(session)
    assert store.load_session(session_id)["messages"] == session.messages
    assert store.delete_session_file(session_id) is True


@pytest.mark.parametrize("link_kind", ["directory", "metadata", "legacy"])
@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks can require Windows developer privileges")
def test_symlinks_cannot_redirect_storage(tmp_path, link_kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "metadata.json"
    marker.write_text('{"session_id":"linked","messages":[]}', encoding="utf-8")
    before = marker.read_bytes()
    root = store.get_sessions_dir()
    root.mkdir(parents=True)
    session_dir = root / "linked"
    if link_kind == "directory":
        session_dir.symlink_to(outside, target_is_directory=True)
    else:
        session_dir.mkdir()
        link = session_dir / "metadata.json" if link_kind == "metadata" else root / "linked.jsonl"
        link.symlink_to(marker)
    if link_kind != "legacy":
        store.save_session(ConversationSession("linked"))
        assert store.load_session("linked") is None
        assert store.load_sessions() == []
    assert store.delete_session_file("linked") is False
    assert marker.read_bytes() == before


@pytest.mark.parametrize("stored_id", ["other-session", "../../outside", None])
def test_metadata_identity_must_match_its_directory(stored_id):
    path = store.metadata_file_path("expected")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"session_id": stored_id, "messages": []}), encoding="utf-8")
    assert store.load_session("expected") is None
    assert store.load_sessions() == []
    manager = SessionManager(WebServerConfig(session_ttl=1))
    assert manager.load_from_disk() == 0
    assert manager.get("expected") is None


def test_ttl_reload_rejects_traversal():
    manager = SessionManager(WebServerConfig(session_ttl=1))
    assert manager.get("../../outside") is None
