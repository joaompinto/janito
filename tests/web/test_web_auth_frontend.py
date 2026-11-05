"""Run auth-related browser helpers with small DOM/network fakes, no bundler."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is needed for browser-helper behavior tests")
SCRIPTS = Path(__file__).resolve().parents[2] / "janito/web/frontend/js"


def run_script(name, before, after):
    source = SCRIPTS.joinpath(name).read_text(encoding="utf-8")
    code = "const assert = require('node:assert/strict');\n" + before + "\n" + source + "\n" + after
    result = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_api_uses_cookie_credentials_and_redirects_on_expiry():
    run_script("api.js", """
        let calls = [], redirects = [], status = 200;
        const window = { __JANITO_TOKEN__: 'must-not-be-used', location: { replace: p => redirects.push(p) } };
        const fetch = async (url, options) => {
            calls.push({ url, options });
            return { ok: status === 200, status, headers: { get: () => 'application/json' },
                     json: async () => ({ detail: 'Unauthorized' }) };
        };
    """, """
        (async () => {
            await Api.get('/api/health');
            assert.equal(calls[0].options.credentials, 'same-origin');
            assert.equal(calls[0].options.headers.Authorization, undefined);
            status = 401;
            await assert.rejects(Api.get('/api/health'));
            assert.deepEqual(redirects, ['/login']);
        })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


@pytest.mark.parametrize("outcome", ["success", "rejected", "network"])
def test_login_clears_input_and_only_redirects_on_success(outcome):
    run_script("login.js", """
        let handler, calls = [], redirects = [];
        const outcome = OUTCOME;
        const input = { value: 'entered-token' }, error = { textContent: '' };
        const document = { getElementById: id => ({
            'login-form': { addEventListener: (event, fn) => { handler = fn; } }, token: input, error
        })[id] };
        const window = { location: { replace: path => redirects.push(path) } };
        const fetch = async (url, options) => {
            calls.push({ url, options });
            if (outcome === 'network') throw new Error('offline');
            return { ok: outcome === 'success' };
        };
    """.replace("OUTCOME", json.dumps(outcome)), """
        (async () => {
            let prevented = false;
            await handler({ preventDefault: () => { prevented = true; } });
            assert.equal(prevented, true);
            assert.equal(calls[0].url, '/auth/login');
            assert.equal(calls[0].options.credentials, 'same-origin');
            assert.deepEqual(JSON.parse(calls[0].options.body), { token: 'entered-token' });
            assert.equal(input.value, '');
            assert.deepEqual(redirects, outcome === 'success' ? ['/'] : []);
            assert.equal(Boolean(error.textContent), outcome !== 'success');
        })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


def test_websocket_omits_tokens_and_stops_retrying_expired_sessions():
    run_script("websocket.js", """
        let redirects = [];
        const window = { __JANITO_TOKEN__: 'must-not-be-used', location: {
            protocol: 'https:', host: 'testserver', replace: path => redirects.push(path)
        } };
        class WebSocket { constructor(url) { this.url = url; } }
    """, """
        const socket = new ChatSocket('session id');
        socket.connect();
        assert.equal(socket.ws.url, 'wss://testserver/api/chat/ws/session%20id');
        socket.ws.onclose({ code: 1008 });
        assert.equal(socket.manualClose, true);
        assert.deepEqual(redirects, ['/login']);
    """)
