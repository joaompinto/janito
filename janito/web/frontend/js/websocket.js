// WebSocket connection + reconnect logic for the Janito web chat.

const WS_STATES = { 0: 'CONNECTING', 1: 'OPEN', 2: 'CLOSING', 3: 'CLOSED' };

class ChatSocket {
    constructor(sessionId, handlers = {}) {
        this.sessionId = sessionId;
        this.handlers = handlers;   // { onEvent, onOpen, onClose, onError }
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.manualClose = false;
        this.pending = [];          // messages queued while CONNECTING
    }

    connect() {
        this.manualClose = false;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/api/chat/ws/${encodeURIComponent(this.sessionId)}`;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            // Flush any messages queued while the socket was CONNECTING.
            const queued = this.pending;
            this.pending = [];
            for (const obj of queued) {
                this._rawSend(obj);
            }
            if (this.handlers.onOpen) this.handlers.onOpen();
        };

        this.ws.onmessage = (msg) => {
            try {
                const event = JSON.parse(msg.data);
                // A "Session not found" error will never resolve by retrying,
                // so mark the socket as manually closed to stop reconnection.
                if (event.type === 'error' && /session not found/i.test(event.message || '')) {
                    console.warn('[WS] session not found on server, will NOT reconnect');
                    this.manualClose = true;
                }
                if (this.handlers.onEvent) this.handlers.onEvent(event);
            } catch (e) {
                console.error('[WS] Failed to parse message:', e, msg.data);
            }
        };

        this.ws.onclose = (e) => {
            console.warn('[WS] CLOSE', {
                session: this.sessionId,
                code: e.code,
                reason: e.reason,
                wasClean: e.wasClean,
                manualClose: this.manualClose,
                attempts: this.reconnectAttempts,
            });
            if (e.code === 1008) {
                this.manualClose = true;
                window.location.replace('/login');
            }
            if (this.handlers.onClose) this.handlers.onClose(e);
            if (!this.manualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                const delay = this.reconnectDelay * this.reconnectAttempts;
                setTimeout(() => this.connect(), delay);
            } else {
                console.error('[WS] giving up reconnecting', {
                    manualClose: this.manualClose,
                    attempts: this.reconnectAttempts,
                    max: this.maxReconnectAttempts,
                });
            }
        };

        this.ws.onerror = (e) => {
            console.error('[WS] ERROR', { session: this.sessionId, event: e });
            if (this.handlers.onError) this.handlers.onError(e);
        };
    }

    _rawSend(obj) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(obj));
            return true;
        }
        console.warn('[WS] _rawSend failed, state =',
            this.ws ? WS_STATES[this.ws.readyState] : 'no-socket');
        return false;
    }

    send(obj) {
        if (!this.ws) {
            console.error('[WS] send() called but no socket exists');
            return false;
        }
        const state = this.ws.readyState;
        if (state === WebSocket.OPEN) {
            return this._rawSend(obj);
        }
        if (state === WebSocket.CONNECTING) {
            // Socket exists but the handshake isn't done yet — queue the
            // message so it's flushed in onopen instead of failing the send.
            this.pending.push(obj);
            return true;
        }
        console.error('[WS] send() failed: socket in state', WS_STATES[state]);
        return false;
    }

    sendPrompt(content) {
        return this.send({ type: 'prompt', content });
    }

    // Answer an in-browser question raised by an interactive tool (the
    // AskUser tool). The backend blocks the agent turn until this arrives.
    sendPromptAnswer(promptId, answer) {
        return this.send({ type: 'prompt_answer', prompt_id: promptId, answer });
    }

    sendCancel() {
        return this.send({ type: 'cancel' });
    }

    sendRestart() {
        return this.send({ type: 'restart' });
    }

    get isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    close() {
        this.manualClose = true;
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
