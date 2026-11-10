"""Failed saves must never truncate the last complete conversation."""

import json
import os
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from janito.web.backend import session_store as store
from janito.web.backend.session import ConversationSession


@pytest.fixture()
def saved_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = ConversationSession("atomic-test", messages=[{"role": "user", "content": "original"}])
    store.save_session(session)
    path = store.metadata_file_path(session.session_id)
    assert path.is_file()
    return session, path


@pytest.mark.parametrize("failure", ["serialize", "sync", "replace"])
def test_failed_save_preserves_previous_snapshot(saved_session, monkeypatch, failure):
    session, path = saved_session
    previous = path.read_bytes()
    session.messages.append({"role": "assistant", "content": "updated"})

    def fail(*args, **kwargs):
        raise OSError("simulated storage failure")

    if failure == "serialize":
        session.messages.append({"content": object()})
    elif failure == "sync":
        monkeypatch.setattr(store.os, "fsync", fail)
    else:
        monkeypatch.setattr(store.os, "replace", fail)
    store.save_session(session)
    assert path.read_bytes() == previous
    assert list(path.parent.iterdir()) == [path]
    assert len(session.messages) >= 2  # Persistence failure does not roll back memory.


def test_replace_publishes_only_complete_snapshot(saved_session, monkeypatch):
    session, path = saved_session
    previous = path.read_bytes()
    session.messages.append({"role": "assistant", "content": "héllo 🌍"})
    replace = os.replace
    calls = []

    def inspect_replace(source, destination):
        assert source.parent == destination.parent
        assert destination.read_bytes() == previous
        assert json.loads(source.read_text(encoding="utf-8"))["messages"] == session.messages
        if os.name == "posix":
            assert source.stat().st_mode & 0o777 == 0o600
        calls.append(destination)
        replace(source, destination)

    monkeypatch.setattr(store.os, "replace", inspect_replace)
    store.save_session(session)
    assert calls == [path]
    assert store.load_session(session.session_id)["messages"] == session.messages
    assert list(path.parent.iterdir()) == [path]


def test_failed_first_save_does_not_publish_partial_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = ConversationSession("first-save", messages=[{"content": object()}])
    store.save_session(session)
    assert store.load_session(session.session_id) is None
    assert store.load_sessions() == []


def test_partial_write_preserves_previous_snapshot(saved_session, monkeypatch):
    session, path = saved_session
    previous = path.read_bytes()
    session.messages.append({"role": "assistant", "content": "updated"})
    named_temporary_file = store.tempfile.NamedTemporaryFile

    @contextmanager
    def interrupted_file(*args, **kwargs):
        with named_temporary_file(*args, **kwargs) as temporary_file:
            def partial_write(content):
                temporary_file.write(content[:10])
                temporary_file.flush()
                raise OSError("disk full during write")

            yield SimpleNamespace(name=temporary_file.name, write=partial_write)

    monkeypatch.setattr(store.tempfile, "NamedTemporaryFile", interrupted_file)
    store.save_session(session)
    assert path.read_bytes() == previous
    assert list(path.parent.iterdir()) == [path]
