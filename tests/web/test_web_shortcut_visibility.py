"""Shortcut discovery must not depend on a response already being in flight."""

from html.parser import HTMLParser

import pytest

pytest.importorskip("jinja2")

from janito.web.backend.templating import make_environment


class _ComposerActions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.actions = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        conditions = [node["x-show"] for _, node in self.stack if "x-show" in node]
        if "x-show" in attrs:
            conditions.append(attrs["x-show"])
        if "data-composer-action" in attrs:
            self.actions[attrs["data-composer-action"]] = {"conditions": conditions, "keys": []}
        if tag not in {"input", "br", "hr", "img", "meta", "link"}:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] == "kbd":
            for _, attrs in reversed(self.stack):
                if "data-composer-action" in attrs:
                    self.actions[attrs["data-composer-action"]]["keys"].append(data.strip())
                    break


def test_both_action_buttons_show_their_shortcuts_without_a_busy_response():
    markup = _ComposerActions()
    markup.feed(make_environment().get_template("partials/input_area.html").render())
    assert markup.actions == {
        "steer": {"conditions": ["sessionId"], "keys": ["Enter"]},
        "queue": {"conditions": ["sessionId"], "keys": ["Ctrl+Enter"]},
    }
