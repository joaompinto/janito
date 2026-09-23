"""
Tests for the provider-token benchmark script (scripts/provider_token_benchmark.py).

Covers the janito output parsing (``----- Model: ...`` banner, the
``--log=info`` "Request completed" lines and the ``=== ... Out: ... ===``
summary), the JSON report builder, provider discovery via
``janito --list-keys``, and the dependency-free PNG bar-chart renderer.
"""

import importlib.util
import json
import struct
import zlib
from pathlib import Path

import pytest

# scripts/ is not a package, so load the script directly from its path.
_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "provider_token_benchmark.py"
_spec = importlib.util.spec_from_file_location("provider_token_benchmark", _SCRIPT)
pbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pbm)


# ----------------------------------------------------------------------
# Token formatting helpers
# ----------------------------------------------------------------------


def test_format_tokens():
    assert pbm.format_tokens(150) == "150"
    assert pbm.format_tokens(2000) == "2k"
    assert pbm.format_tokens(12345) == "12.3k"
    assert pbm.format_tokens(4000000) == "4m"
    assert pbm.format_tokens(1000000) == "1m"
    assert pbm.format_tokens(None) is None


def test_unformat_tokens():
    assert pbm.unformat_tokens("150") == 150
    assert pbm.unformat_tokens("1.5k") == 1500
    assert pbm.unformat_tokens("12.3k") == 12300
    assert pbm.unformat_tokens("4m") == 4000000
    assert pbm.unformat_tokens(None) is None
    assert pbm.unformat_tokens("nope") is None


# ----------------------------------------------------------------------
# janito output parsing
# ----------------------------------------------------------------------


def test_parse_model():
    stdout = "----- Model: gpt-6-luna | Backend: api.openai.com\n"
    assert pbm.parse_model(stdout) == "gpt-6-luna"
    assert pbm.parse_model("no banner here") is None


def test_parse_usage_log_single_round():
    stderr = (
        "INFO: Loaded 0 MCP tools from 0 services\n"
        "INFO: Request completed: total=1234 tokens (in=1000, out=234, "
        "cached=None, max=128000), 1 messages\n"
    )
    rounds = pbm.parse_usage_log(stderr)
    assert rounds == [
        {
            "total": 1234,
            "in": 1000,
            "out": 234,
            "cached": None,
            "max": 128000,
            "count": 1,
            "elapsed": None,
        }
    ]


def test_parse_usage_log_multi_round():
    stderr = (
        "INFO: Request completed: total=500 tokens (in=300, out=200, "
        "cached=0, max=65536), 1 messages\n"
        "INFO: Request completed: total=1800 tokens (in=1200, out=600, "
        "cached=50, max=65536), 2 responses\n"
    )
    rounds = pbm.parse_usage_log(stderr)
    assert len(rounds) == 2
    assert rounds[0]["out"] == 200
    assert rounds[1]["out"] == 600
    assert rounds[1]["count"] == 2


def test_parse_usage_summary():
    stdout = (
        "=== Total: 1.2k | In: 1k | Out: 234 | Cost: N/A ===\n"
        "some answer text\n"
        "=== Total: 2k | In: 1.5k | Out: 1.5k | Cached: 100 | Cost: N/A ===\n"
    )
    assert pbm.parse_usage_summary(stdout) == ["234", "1.5k"]


# ----------------------------------------------------------------------
# Result building
# ----------------------------------------------------------------------


def test_build_result_ok_from_log():
    stdout = (
        "----- Model: gpt-6-luna | Backend: api.openai.com\n"
        "answer\n"
        "=== Total: 1.2k | In: 1k | Out: 234 | Cost: N/A ===\n"
    )
    stderr = "INFO: Request completed: total=1234 tokens (in=1000, out=234, cached=None, max=128000), 1 messages\n"
    result = pbm.build_result("openai", 0, stdout, stderr)
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-6-luna"
    assert result["status"] == "ok"
    assert result["out_tokens"] == 234
    assert result["in_tokens"] == 1000
    assert result["total_tokens"] == 1234
    assert result["out_display"] == "234"
    assert result["out_tokens_source"] == "log"
    assert result["rounds"] == 1


def test_build_result_ok_sums_multi_round():
    stderr = (
        "INFO: Request completed: total=500 tokens (in=300, out=200, "
        "cached=0, max=65536), 1 messages\n"
        "INFO: Request completed: total=1800 tokens (in=1200, out=600, "
        "cached=50, max=65536), 2 messages\n"
    )
    result = pbm.build_result("deepseek", 0, "", stderr)
    assert result["out_tokens"] == 800
    assert result["in_tokens"] == 1500
    assert result["total_tokens"] == 2300
    assert result["rounds"] == 2
    assert result["out_display"] == "800"


def test_build_result_ok_falls_back_to_display():
    stdout = "----- Model: glm-5.3 | Backend: https://api.z.ai\n" "=== Total: 1.5k | Out: 1.5k | Cost: N/A ===\n"
    result = pbm.build_result("zai", 0, stdout, "")
    assert result["status"] == "ok"
    assert result["out_tokens"] == 1500
    assert result["out_display"] == "1.5k"
    assert result["out_tokens_source"] == "display"


def test_build_result_error():
    stderr = "Error: Unknown provider 'alibaba_tp'. Supported providers: alibaba, ..."
    result = pbm.build_result("alibaba_tp", 1, "", stderr)
    assert result["status"] == "error"
    assert result["out_tokens"] is None
    assert result["error"].strip() != ""


def test_first_error_skips_log_noise_and_picks_root_cause():
    stderr = (
        "INFO: Sending prompt to Anthropic API (native SDK)\n"
        "Traceback (most recent call last):\n"
        '  File "/x/anthropic_api.py", line 115, in _create_client\n'
        "    raise RuntimeError(\n"
        "RuntimeError: API type 'Anthropic' requires the optional "
        "'anthropic' package, which is not installed.\n"
    )
    err = pbm._first_error("", stderr)
    assert err is not None
    assert err.startswith("RuntimeError: API type 'Anthropic'")


def test_build_result_no_usage():
    result = pbm.build_result("x", 0, "just some text", "")
    assert result["status"] == "no-usage"
    assert result["out_tokens"] is None
    assert result["error"]


# ----------------------------------------------------------------------
# Provider discovery
# ----------------------------------------------------------------------


def test_parse_list_keys():
    output = "Config file: /home/user/.janito/auth.json\nopenai  ***\ndeepseek  ***\nalibaba_tp  ***\n\n"
    assert pbm.parse_list_keys(output) == ["alibaba_tp", "deepseek", "openai"]


def test_discover_providers(tmp_path):
    fake = tmp_path / "fake-janito"
    fake.write_text(
        '#!/bin/sh\necho "Config file: /tmp/auth.json"\necho "openai  ***"\necho "deepseek  ***"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    assert pbm.discover_providers(str(fake)) == ["deepseek", "openai"]


def test_discover_providers_failure(tmp_path):
    fake = tmp_path / "fake-janito"
    fake.write_text("#!/bin/sh\necho 'boom' >&2\nexit 3\n", encoding="utf-8")
    fake.chmod(0o755)
    with pytest.raises(RuntimeError, match="--list-keys"):
        pbm.discover_providers(str(fake))


# ----------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------


def test_sort_results_and_chart_entries():
    results = [
        {"provider": "zai", "model": "glm-5.3", "out_tokens": 100},
        {"provider": "openai", "model": "gpt-6-luna", "out_tokens": 500},
        {"provider": "deepseek", "model": "gpt-6-luna", "out_tokens": 300},
        {"provider": "broken", "model": None, "out_tokens": None},
        {"provider": "anthropic", "model": "claude-sonnet-5", "out_tokens": 400},
    ]
    sorted_results = pbm.sort_results(results)
    assert [r["out_tokens"] for r in sorted_results[:4]] == [500, 400, 300, 100]
    assert sorted_results[-1]["provider"] == "broken"

    entries = pbm.chart_entries(sorted_results)
    assert entries == [
        ("gpt-6-luna (openai)", 500),
        ("claude-sonnet-5", 400),
        ("gpt-6-luna (deepseek)", 300),
        ("glm-5.3", 100),
    ]


def test_write_json(tmp_path):
    results = [
        {
            "provider": "openai",
            "model": "gpt-6-luna",
            "out_tokens": 500,
            "status": "ok",
        }
    ]
    path = tmp_path / "report.json"
    pbm.write_json(results, path, "What is this project about", "janito")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["prompt"] == "What is this project about"
    assert data["janito_command"] == "janito"
    assert data["results"] == results
    assert "generated_at" in data


# ----------------------------------------------------------------------
# PNG rendering
# ----------------------------------------------------------------------


def _png_chunks(data):
    chunks = []
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        chunks.append((tag, body))
        pos += 12 + length
    return chunks


def test_encode_png_small_canvas():
    canvas = pbm.Canvas(20, 10)
    canvas.fill_rect(2, 2, 9, 5, pbm.PALETTE[0])
    data = pbm.encode_png(canvas)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = dict(_png_chunks(data))
    width, height = struct.unpack(">II", chunks[b"IHDR"][:8])
    assert (width, height) == (20, 10)
    raw = zlib.decompress(chunks[b"IDAT"])
    assert len(raw) == height * (1 + width * 3)


def test_render_chart_writes_valid_png(tmp_path):
    entries = [
        ("gpt-6-luna", 18432),
        ("deepseek-flash", 8932),
        ("glm-5.3", 512),
    ]
    out = tmp_path / "chart.png"
    pbm.render_chart(entries, out, "What is this project about", "2026-08-09T10:00:00+01:00")
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = dict(_png_chunks(data))
    width, height = struct.unpack(">II", chunks[b"IHDR"][:8])
    assert width > 800
    assert height >= pbm.MARGIN_T + len(entries) * pbm.ROW_H + pbm.MARGIN_B

    # The chart must contain more than just the white background.
    raw = zlib.decompress(chunks[b"IDAT"])
    non_white = sum(1 for i in range(0, len(raw), 3) if raw[i : i + 3] != bytes((255, 255, 255)))
    assert non_white > 1000


def test_render_chart_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="at least one entry"):
        pbm.render_chart([], tmp_path / "chart.png", "p", "2026")


def test_text_width_and_truncate():
    assert pbm.text_width("", scale=2) == 0
    assert pbm.text_width("AB", scale=2, spacing=1) == 2 * (8 * 2 + 1) - 1
    # A string that already fits is returned unchanged.
    short = "short"
    assert pbm._truncate(short, 200, scale=2) == short
    # A long string is cut down and gets an ellipsis, still within the budget.
    long = "a very long prompt that will not fit"
    truncated = pbm._truncate(long, 200, scale=2)
    assert truncated.endswith("...")
    assert truncated != long
    assert pbm.text_width(truncated, scale=2) <= 200


def test_nice_max():
    assert pbm._nice_max(1) == 1
    assert pbm._nice_max(18432) == 20000
    assert pbm._nice_max(999) == 1000
    assert pbm._nice_max(0) == 1


def test_resolve_artifact_path(tmp_path):
    # Explicit paths always win.
    assert pbm.resolve_artifact_path(str(tmp_path / "a.json"), "provider_tokens.json") == tmp_path / "a.json"
    # Defaults land in the system temp dir, kept across runs.
    import tempfile

    default = pbm.resolve_artifact_path(None, "provider_tokens.png")
    assert default == Path(tempfile.gettempdir()) / "provider_tokens.png"
    default_json = pbm.resolve_artifact_path(None, "provider_tokens.json")
    assert default_json == Path(tempfile.gettempdir()) / "provider_tokens.json"


def test_main_list_providers(tmp_path, capsys):
    fake = tmp_path / "fake-janito"
    fake.write_text(
        '#!/bin/sh\necho "openai  ***"\necho "zai  ***"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    rc = pbm.main(["--list-providers", "--janito", str(fake)])
    assert rc == 0
    assert capsys.readouterr().out.split() == ["openai", "zai"]


def test_render_chart_bars_grow_left_to_right(tmp_path):
    """The zero axis is on the left; values must not be rendered RTL."""
    entries = [("largest", 100), ("smallest", 20)]
    out = tmp_path / "orientation.png"
    pbm.render_chart(entries, out, "prompt", "2026")

    data = out.read_bytes()
    chunks = dict(_png_chunks(data))
    width, height = struct.unpack(">II", chunks[b"IHDR"][:8])
    raw = zlib.decompress(chunks[b"IDAT"])
    stride = 1 + width * 3

    def pixel(x, y):
        row = raw[y * stride + 1 : (y + 1) * stride]
        return tuple(row[x * 3 : x * 3 + 3])

    label_w = max(
        110,
        max(pbm.text_width(label, pbm.CHAR_SCALE, pbm.CHAR_SPACING) for label, _ in entries) + 16,
    )
    chart_x0 = pbm.MARGIN_L + label_w + 16
    y = pbm.MARGIN_T + pbm.BAR_H // 2
    assert pixel(chart_x0 + 1, y) == pbm.PALETTE[0]
    assert pixel(chart_x0 + pbm.CHART_W - 1, y) == pbm.PALETTE[0]
    # A mirrored implementation would leave the zero-axis side white.


def test_font_bits_render_leftmost_bit_on_left():
    """Labels must not be horizontally mirrored by the bitmap font renderer."""
    canvas = pbm.Canvas(8, 8)
    canvas.text(0, 0, "E", pbm.INK, scale=1, spacing=0)
    assert canvas.pixels[0][:7] == [pbm.INK] * 7
    assert canvas.pixels[0][7] == pbm.WHITE
