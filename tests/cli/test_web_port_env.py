"""JANITO_WEB_PORT provides the default for ``--web-port``.

The Docker image sets ``JANITO_WEB_PORT=9090`` and relies on this fallback
(instead of hard-coding ``--web-port`` in the container command), so users
can change the listening port with ``docker run -e JANITO_WEB_PORT=...``.

Explicit ``--web-port`` must still win over the environment variable.
"""

from janito.cli.parser import create_parser


def test_web_port_defaults_to_8080(monkeypatch):
    monkeypatch.delenv("JANITO_WEB_PORT", raising=False)
    args = create_parser().parse_args(["--web"])
    assert args.web_port == 8080


def test_web_port_defaults_from_env(monkeypatch):
    monkeypatch.setenv("JANITO_WEB_PORT", "9123")
    args = create_parser().parse_args(["--web"])
    assert args.web_port == 9123


def test_cli_web_port_overrides_env(monkeypatch):
    monkeypatch.setenv("JANITO_WEB_PORT", "9123")
    args = create_parser().parse_args(["--web", "--web-port", "7000"])
    assert args.web_port == 7000
