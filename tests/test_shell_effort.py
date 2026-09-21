from janito.shell.cmds.effort import EffortCmdHandler


class FakeShell:
    def __init__(self):
        self.provider = "openai"
        self.model = "gpt-5"
        self.model_override = None
        self.thinking = False
        self.effort = None
        self.calls = []

        def factory(
            provider,
            model_override=None,
            thinking_override=None,
            effort_override=None,
            silent=False,
        ):
            self.calls.append(effort_override)
            return lambda *a, **k: None

        self.turn_factory = factory
        self.turn_func = lambda *a, **k: None


def test_show_does_not_raise(capsys):
    s = FakeShell()
    assert EffortCmdHandler().handle(s, "/effort") is True
    out = capsys.readouterr().out
    assert out.strip() != ""


def test_set_and_clear():
    s = FakeShell()
    assert EffortCmdHandler().handle(s, "/effort high") is True
    assert s.effort == "high"
    assert EffortCmdHandler().handle(s, "/effort clear") is True
    assert s.effort is None
