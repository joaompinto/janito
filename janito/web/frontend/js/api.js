// REST fetch helpers for the Janito web API.

const Api = {
    baseUrl: '',

    async request(method, path, body = null) {
        const opts = {
            method,
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
        };
        if (body !== null) {
            opts.body = JSON.stringify(body);
        }
        const res = await fetch(this.baseUrl + path, opts);
        if (!res.ok) {
            if (res.status === 401) window.location.replace('/login');
            let detail = res.statusText;
            try {
                const data = await res.json();
                detail = data.detail || JSON.stringify(data);
            } catch (e) { /* ignore */ }
            throw new Error(`HTTP ${res.status}: ${detail}`);
        }
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            return res.json();
        }
        return res.text();
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    patch(path, body) { return this.request('PATCH', path, body); },
    del(path) { return this.request('DELETE', path); },

    // Convenience wrappers
    getConfig() { return this.get('/api/config'); },
    patchConfig(body) { return this.patch('/api/config', body); },
    getStatus(provider) {
        const qs = provider ? `?provider=${encodeURIComponent(provider)}` : '';
        return this.get('/api/config/status' + qs);
    },
    getProviders() { return this.get('/api/config/providers'); },
    setDefaultProvider(name) {
        return this.post('/api/config/default-provider', { provider: name });
    },
    // Session-only switch used by the topbar combo: in-memory on the server,
    // never written to ~/.janito/config.json (unlike setDefaultProvider).
    setSessionProvider(name, sessionId = null) {
        return this.post('/api/config/session-provider', {
            provider: name,
            ...(sessionId ? { session_id: sessionId } : {}),
        });
    },
    // Runtime-only thinking toggle (status bar): in-memory on the server,
    // never written to ~/.janito/config.json (unlike patchConfig).
    setThinking(thinking) {
        return this.post('/api/config/thinking', { thinking });
    },
    setApiKey(provider, apiKey) {
        return this.post('/api/config/api-key', { provider, api_key: apiKey });
    },
    getTools() { return this.get('/api/tools'); },
    getSkippedTools() { return this.get('/api/tools/skipped'); },
    getMcpTools() { return this.get('/api/mcp/tools'); },
    getMcpServices() { return this.get('/api/mcp/services'); },
    connectMcp(name) { return this.post(`/api/mcp/services/${encodeURIComponent(name)}/connect`); },
    disconnectMcp(name) { return this.post(`/api/mcp/services/${encodeURIComponent(name)}/disconnect`); },
    listSessions() { return this.get('/api/chat/sessions'); },
    createSession() { return this.post('/api/chat/sessions'); },
    getSession(id) { return this.get(`/api/chat/sessions/${encodeURIComponent(id)}`); },
    deleteSession(id) { return this.del(`/api/chat/sessions/${encodeURIComponent(id)}`); },
    renameSession(id, title) { return this.patch(`/api/chat/sessions/${encodeURIComponent(id)}`, { title }); },
};
