// Per-session store lifecycle + status broadcasting + turn rollback.
//
// The persistent sockets themselves live OUTSIDE the Alpine component (see
// chat.js `_sessionSockets`) so they are never made reactive. This mixin
// only manages the reactive `_sessions` stores and the UI projection
// bookkeeping. Folded into the Alpine component via Object.assign.

window.ChatStoreMixin = {
    // Update a session's status and notify the sidebar so it can show
    // a spinner (processing) or dot (finished) on inactive sessions.
    _setStatus(store, status) {
        if (store.status === status) return;
        store.status = status;
        window.dispatchEvent(new CustomEvent('janito-session-status', {
            detail: { id: store.id, status },
        }));
    },

    // Broadcast the current status of ALL sessions. Called on tab switch
    // so that a session already processing in the background gets its
    // indicator without waiting for the next status change.
    _broadcastAllStatuses() {
        for (const id in this._sessions) {
            const store = this._sessions[id];
            window.dispatchEvent(new CustomEvent('janito-session-status', {
                detail: { id, status: store.status },
            }));
        }
    },

    // If the given session is the active one, mirror its connection state
    // into the top-level `connection` property (and notify the status bar).
    _reflectConnection(id) {
        if (this.sessionId === id) {
            this.connection = this._store(id).connection;
            this._broadcastConn();
        }
    },

    _broadcastConn() {
        window.dispatchEvent(new CustomEvent('janito-connection', { detail: this.connection }));
    },

    // Roll back all rows in the active turn, including applied steering.
    // Clearing the boundary makes repeated acknowledgements harmless.
    _rollbackTurn(store) {
        if (store.turnStartIndex === null) return;
        store.messages.splice(store.turnStartIndex);
        store.turnStartIndex = null;
        store.current = null;
    },

    // Release a session's persistent socket and store. Safe to call for a
    // session that is active, background, or unknown.
    _releaseSession(id) {
        const socket = this._socket(id);
        if (socket) {
            socket.close();
            window.__janitoSessionSockets.delete(id);
        }
        delete this._sessions[id];
    },

    // The active session was deleted: free its resources and clear the view.
    clearActive() {
        if (this.sessionId) this._releaseSession(this.sessionId);
        this.sessionId = null;
        this.messages = [];
        this.status = 'idle';
        this.connection = 'disconnected';
        this.error = null;
        this._current = null;
        this.toolsSummary = null;
        // The draft belonged to the closed conversation; clear it so a stale
        // message doesn't resurface when a new session is opened.
        this.input = '';
        this._autoResize();
        this._broadcastConn();
    },
};
