"""Backend + frontend wiring tests for the Settings drawer's Advanced section.

The Settings drawer (``janito/web/backend/templates/partials/settings_drawer.html``
+ ``settings.js``)
gains an "Advanced" section (collapsed by default) with three per-provider
fields:

* ``endpoint`` -- base-URL override (``providers.<name>.endpoint``);
* ``api_type`` -- a combobox with one option per supported API type
  (``providers.<name>.api-type``, "Responses"/"Completions");
* ``stateless_mode`` -- a toggleable switch, only rendered while the
  API type is "Responses" (``providers.<name>.stateless-mode``).

All three are persisted per provider via ``PATCH /api/config`` (like the
model) and exposed per provider via ``GET /api/config/providers``.  The
``stateless_mode`` override is also honoured at runtime by
``get_stateless_mode_from_provider`` (the CLI's Responses-API path),
so the toggle actually changes how the conversation is chained.

These tests pin down:

1. ``PATCH /api/config`` persists ``endpoint`` / ``api_type`` /
   ``stateless_mode`` under the right per-provider config keys and
   rejects invalid values / unknown providers with ``400``;
2. an empty ``endpoint`` / ``api_type`` clears the per-provider override;
3. the providers endpoint exposes the Advanced fields
   (``api_type``, ``supported_api_types``, ``api_types``,
   ``stateless_mode``, ``default_stateless_mode``,
   ``stateless_mode_override``).

The ``api_types`` field also carries per-type *availability*: API types
whose optional Python package is missing (e.g. the native ``Anthropic``
type without the ``anthropic`` package) are flagged ``available: false``
with the required package and an install hint.  The web UI keeps those
types OUT of the combobox and shows the info instead.
"""

import sys
import tempfile
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

import janito.config_dir as config_dir_mod
import janito.config_loaders as cl
import janito.config_store as cs
from janito.providers.validation import is_api_type_available

# The web routes need the optional `web` extra (fastapi). Skip gracefully
# when fastapi is not installed (e.g. minimal tox envs).
try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ModuleNotFoundError:
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi (web extra) is not installed")

try:
    import anthropic  # noqa: F401

    _HAS_ANTHROPIC = True
except ModuleNotFoundError:
    _HAS_ANTHROPIC = False

# The "aborts without the package" guard test only applies when the optional
# `anthropic` package is missing; skip it when it is installed.
requires_no_anthropic = pytest.mark.skipif(
    _HAS_ANTHROPIC, reason="anthropic package is installed (guard not exercised)"
)


@pytest.fixture(scope="module", autouse=True)
def clean_config(request):
    """Isolate the config dir in a temp dir so tests never touch the real one."""
    prev_dir = config_dir_mod.get_config_dir()
    tmp = tempfile.mkdtemp(prefix="janito_settings_advanced_tests_")
    config_dir_mod.set_config_dir(tmp)

    def restore():
        config_dir_mod.set_config_dir(str(prev_dir))

    request.addfinalizer(restore)


@pytest.fixture(scope="module")
def client(clean_config):
    """A TestClient wired to a fresh Janito web app (isolated config dir)."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    config = WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True)
    app = create_app(config)
    with TestClient(app) as c:
        yield c


def _providers_by_name(client):
    data = client.get("/api/config/providers").json()
    return {p["name"]: p for p in data["providers"]}


# ---------------------------------------------------------------------------
# PATCH /api/config — Advanced section persistence
# ---------------------------------------------------------------------------


@requires_fastapi
def test_patch_endpoint_persists_per_provider(client):
    """{endpoint, provider} writes providers.<provider>.endpoint to config.json."""
    cs.unset_config_value("minimax.endpoint")

    resp = client.patch(
        "/api/config",
        json={"endpoint": "https://minimax.example/v1", "provider": "minimax"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"]["endpoint"] == "https://minimax.example/v1"

    assert cs.load_config().get("providers", {}).get("minimax", {}).get("endpoint") == "https://minimax.example/v1"
    # ...and the providers endpoint reflects the override (base_url wins).
    entry = _providers_by_name(client)["minimax"]
    assert entry["endpoint"] == "https://minimax.example/v1"
    assert entry["base_url"] == "https://minimax.example/v1"


@requires_fastapi
def test_patch_empty_endpoint_clears_override(client):
    """An empty endpoint removes the per-provider override (built-in returns)."""
    cs.set_config_value("minimax.endpoint", "https://minimax.example/v1")
    assert cl.load_endpoint_from_config("minimax") == "https://minimax.example/v1"

    resp = client.patch("/api/config", json={"endpoint": "", "provider": "minimax"})
    assert resp.status_code == 200
    assert resp.json()["updated"]["endpoint"] == ""

    assert cs.load_config().get("providers", {}).get("minimax", {}).get("endpoint") is None
    # Falls back to the built-in endpoint.
    assert _providers_by_name(client)["minimax"]["base_url"] == "https://api.minimax.io/v1"


@requires_fastapi
def test_patch_api_type_persists_and_normalizes(client):
    """api_type is canonicalized (Responses/Completions) and stored per provider."""
    cs.unset_config_value("openai.models.gpt-6-luna.api-type")

    resp = client.patch("/api/config", json={"api_type": "completions", "provider": "openai"})
    assert resp.status_code == 200
    assert resp.json()["updated"]["api_type"] == "Completions"

    assert cl.load_api_type("openai") == "Completions"
    entry = _providers_by_name(client)["openai"]
    assert entry["api_type"] == "Completions"
    # The built-in default is still exposed separately.
    assert entry["default_api_type"] == "Responses"


@requires_fastapi
def test_patch_api_type_rejects_unknown_value(client):
    """A bogus API type is rejected with 400 and nothing is written."""
    cs.unset_config_value("openai.models.gpt-6-luna.api-type")
    before = cs.load_config()

    resp = client.patch("/api/config", json={"api_type": "Bogus", "provider": "openai"})
    assert resp.status_code == 400
    assert "Unsupported API type" in resp.json()["detail"]
    assert cs.load_config() == before


@requires_fastapi
@requires_no_anthropic
def test_patch_api_type_anthropic_aborts_without_package(client):
    """The native Anthropic SDK API type is rejected with 400 (nothing is
    written) when the optional `anthropic` package is not installed, with a
    message naming the package."""
    cs.unset_config_value("anthropic.models.claude-sonnet-5.api-type")
    before = cs.load_config()

    resp = client.patch("/api/config", json={"api_type": "Anthropic", "provider": "anthropic"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Anthropic" in detail
    assert "anthropic" in detail
    assert "pip install anthropic" in detail
    assert cs.load_config() == before


@requires_fastapi
def test_patch_api_type_empty_clears_override(client):
    """An empty api_type removes the per-provider override."""
    # api-type is model-scoped: seed the real key (not the flat
    # "openai.api-type" form nothing reads) so this test passes
    # regardless of execution order / xdist grouping.
    cs.set_config_value("openai.models.gpt-6-luna.api-type", "Completions")
    assert cl.load_api_type("openai") == "Completions"

    resp = client.patch("/api/config", json={"api_type": "", "provider": "openai"})
    assert resp.status_code == 200
    assert resp.json()["updated"]["api_type"] == ""

    assert cl.load_api_type("openai") is None
    assert _providers_by_name(client)["openai"]["api_type"] is None


@requires_fastapi
def test_patch_stateless_mode_persists(client):
    """stateless_mode is stored per provider/model and exposed effectively."""
    cs.unset_config_value("openai.models.gpt-6-luna.stateless-mode")

    resp = client.patch(
        "/api/config",
        json={"stateless_mode": False, "provider": "openai"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"]["stateless_mode"] is False

    assert cl.load_stateless_mode_from_config("openai") is False
    entry = _providers_by_name(client)["openai"]
    assert entry["stateless_mode"] is False  # override wins
    assert entry["default_stateless_mode"] is False  # built-in unchanged
    assert entry["stateless_mode_override"] is False


@requires_fastapi
def test_patch_stateless_mode_accepts_string_bool(client):
    """String forms true/false/1/0 are coerced to booleans."""
    resp = client.patch(
        "/api/config",
        json={"stateless_mode": "true", "provider": "deepseek"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"]["stateless_mode"] is True
    assert cl.load_stateless_mode_from_config("deepseek") is True

    resp = client.patch(
        "/api/config",
        json={"stateless_mode": "0", "provider": "deepseek"},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"]["stateless_mode"] is False


@requires_fastapi
def test_patch_stateless_mode_rejects_invalid(client):
    """A non-boolean stateless_mode is rejected with 400."""
    cs.unset_config_value("openai.models.gpt-6-luna.stateless-mode")
    before = cs.load_config()

    resp = client.patch(
        "/api/config",
        json={"stateless_mode": "maybe", "provider": "openai"},
    )
    assert resp.status_code == 400
    assert "must be a boolean" in resp.json()["detail"]
    assert cs.load_config() == before


@requires_fastapi
def test_patch_advanced_unknown_provider_rejected(client):
    """An unknown provider name is rejected with 400 and nothing is written."""
    before = cs.load_config()
    resp = client.patch(
        "/api/config",
        json={"endpoint": "https://x/v1", "provider": "not-a-provider"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]
    assert cs.load_config() == before


# ---------------------------------------------------------------------------
# GET /api/config/providers — the data the Advanced section renders from
# ---------------------------------------------------------------------------


@requires_fastapi
def test_providers_endpoint_exposes_advanced_fields(client):
    """Each provider entry carries the Advanced fields the drawer reads."""
    # Clear any model-scoped stateless-mode override left by earlier
    # tests in this module (they share the module-scoped config dir).
    cs.unset_config_value("openai.models.gpt-6-luna.stateless-mode")
    cs.unset_config_value("deepseek.models.deepseek-flash.stateless-mode")
    entries = _providers_by_name(client)

    openai = entries["openai"]
    # OpenAI supports both API types -> the drawer shows a combobox with both.
    assert openai["supported_api_types"] == ["Responses", "Completions"]
    assert openai["default_api_type"] == "Responses"
    assert "api_type" in openai  # configured override (None until set)
    # OpenAI's /responses endpoint is server-side by default.
    assert openai["stateless_mode"] is False
    assert openai["default_stateless_mode"] is False
    assert openai["stateless_mode_override"] is None
    assert "endpoint" in openai
    assert "base_url" in openai

    deepseek = entries["deepseek"]
    # DeepSeek supports the Responses / Completions API types plus the
    # Anthropic-compatible API (native Anthropic SDK); Responses (the first
    # supported type) is the built-in default.
    assert deepseek["supported_api_types"] == [
        "Responses",
        "Completions",
        "Anthropic",
    ]
    assert deepseek["default_api_type"] == "Responses"
    # The per-API-type endpoint map is exposed: the OpenAI-compatible base
    # URL for the OpenAI-SDK types and the Anthropic-compatible base URL for
    # the native Anthropic SDK API type.
    assert deepseek["endpoint_by_api_type"] == {
        "Completions": "https://api.deepseek.com",
        "Responses": "https://api.deepseek.com",
        "Anthropic": "https://api.deepseek.com/anthropic",
    }
    # base_url reflects the default API type's built-in endpoint.
    assert deepseek["base_url"] == "https://api.deepseek.com"
    # DeepSeek's /responses endpoint is stateless by default.
    assert deepseek["stateless_mode"] is True
    assert deepseek["default_stateless_mode"] is True

    anthropic = entries["anthropic"]
    # Anthropic supports Completions (the built-in default) plus the native
    # Anthropic SDK API type; the per-API-type endpoint map is exposed so the
    # drawer could show per-type URLs.
    assert anthropic["supported_api_types"] == ["Completions", "Anthropic"]
    assert anthropic["default_api_type"] == "Completions"
    assert anthropic["endpoint_by_api_type"] == {
        "Completions": "https://api.anthropic.com/v1/",
        "Anthropic": "https://api.anthropic.com",
    }
    # base_url reflects the default API type's built-in endpoint.
    assert anthropic["base_url"] == "https://api.anthropic.com/v1/"

    # Every provider exposes per-type availability alongside the plain list.
    for entry in entries.values():
        by_type = {t["type"]: t for t in entry["api_types"]}
        # The "custom" provider has no built-in models, so it exposes no
        # supported API types (both lists are empty/None).
        if not entry["supported_api_types"]:
            assert by_type == {}
            continue
        assert list(by_type) == entry["supported_api_types"]
        for api_type, detail in by_type.items():
            assert "available" in detail
            # OpenAI-SDK types always carry no package requirement; the
            # native types name the package and (when missing) an install hint.
            if api_type in ("Responses", "Completions"):
                assert detail["available"] is True
                assert "required_package" not in detail
                assert "reason" not in detail
            else:
                assert detail["required_package"]
                assert detail["available"] == is_api_type_available(api_type)
                if not detail["available"]:
                    assert f"The {api_type} API requires" in detail["reason"]
                    assert "pip install" in detail["reason"]
                    assert detail["required_package"] in detail["reason"]


@requires_fastapi
def test_providers_endpoint_flags_unavailable_api_type(monkeypatch, client):
    """An API type whose optional package is missing is exposed as
    unavailable (with the package name and an install hint) so the web UI can
    show the info WITHOUT adding the type to the combobox.

    The optional `anthropic` package is forced missing regardless of the
    environment, making the native-SDK API type deterministically
    unavailable while the OpenAI-SDK types stay usable.
    """
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    anthropic = _providers_by_name(client)["anthropic"]
    by_type = {t["type"]: t for t in anthropic["api_types"]}

    # The OpenAI-compatible Completions type is always available (no entry
    # in REQUIRES_BY_API_TYPE), so it stays selectable in the combobox.
    assert by_type["Completions"]["available"] is True
    assert "required_package" not in by_type["Completions"]
    assert "reason" not in by_type["Completions"]

    # The native Anthropic type needs the optional `anthropic` package: it
    # is flagged unavailable with a self-contained reason naming the type,
    # the package and an install hint.
    native = by_type["Anthropic"]
    assert native["available"] is False
    assert native["required_package"] == "anthropic"
    assert native["reason"] == (
        "The Anthropic API requires the optional 'anthropic' package, "
        "which is not installed. Install it with: pip install anthropic"
    )
    assert native["type"] == "Anthropic"
