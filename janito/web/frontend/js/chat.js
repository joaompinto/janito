// Chat Alpine.js component — messages, streaming, input, tool monitor.
//
// Multi-session design
// --------------------
// The app supports many open conversations, and a conversation may keep
// receiving data (tokens, tool calls, tool results) even while the user is
// looking at a *different* tab. To support that, this component keeps a
// **persistent store per session**, each with its own live WebSocket:
//
//     _sessions[sessionId] = {
//         id, messages[], status, error, connection,
//         current,      // the in-flight assistant message (or null)
//         loaded, loading, dirty
//     }
//
//   * Sockets are created once per session and are NEVER closed just because
//     the user switched tabs — so a background conversation keeps streaming
//     and its history keeps growing.
//   * Every socket event is routed to *its own* session's store via
//     `_handleEvent(event, store)`, never to shared component state.
//   * The top-level reactive properties (`messages`, `status`, `connection`,
//     `error`, `_current`) are merely a **projection of the active session**.
//     Switching tabs re-points this projection at the chosen session's store.
//
// Because `this.messages` references the active store's array, a background
// session writing to its own store never disturbs the visible tab — and when
// the user returns, the tab already contains the fully up-to-date conversation.
//
// UI state machine (per session):
//   idle -> [send prompt] -> waiting -> [first token] -> streaming
//        -> [tool_call] -> tool_running -> [tool_result] -> waiting -> streaming
//        -> [done] -> idle
//
// Module layout
// -------------
// This file is the orchestration shell. Focused concerns are split into
// sibling mixins (loaded first in index.html) and folded in via Object.assign:
//   chatFormat.js   -> window.ChatFormatMixin    (pure formatting/rendering)
//   chatMessages.js -> window.ChatMessagesMixin  (UI message/part builders)
//   chatStore.js    -> window.ChatStoreMixin     (store lifecycle, rollback)
//   chatEvents.js   -> window.ChatEventsMixin    (event dispatch table)
//   chatHistory.js  -> window.ChatHistoryMixin   (history reconstruction)
//   chatScroll.js   -> window.ChatScrollMixin    (scroll + keyboard)

// Persistent sockets live OUTSIDE the Alpine component so they are never made
// reactive (proxying a live WebSocket is undesirable). Keyed by session id.
// Exposed on window so the store mixin (_releaseSession) can reach them.
window.__janitoSessionSockets = new Map();

function chatComponent() {
    return Object.assign({
        // ---- Projection of the ACTIVE session (drives the template) ----
        messages: [],            // UI message objects for the active session
        input: '',
        status: 'idle',          // idle | waiting | streaming | tool_running
        connection: 'disconnected',  // disconnected | connecting | connected
        error: null,
        sessionId: null,         // active session id
        _current: null,          // active session's in-flight assistant message
        toolsSummary: null,      // active session's { active, skipped, skippedList }
        // Tools info dialog — opened from the session-start banner's
        // "N tool(s) active" link. `toolsDialog` caches the same listing the
        // /tools command fetches (see ChatCommandsMixin.openToolsDialog).
        toolsDialogOpen: false,
        toolsDialog: null,       // { builtin, mcp, skipped, total } or null
        toolsDialogLoading: false,
        toolsDialogError: null,
        _followBottom: true,     // auto-follow the scroll bottom? false = user "locked" the scroll
        _scrollThreshold: 80,    // px tolerance for "at the bottom" (avoids scrollbar jitter)

        // ---- Per-session persistent state (reactive) ----
        _sessions: {},           // id -> store (see header comment)

        init() {
            // Track scroll position so we only auto-follow new content while
            // the user is "at the bottom". Scrolling up locks the view so the
            // user can read without being yanked down mid-stream.
            this.$nextTick(() => {
                const el = this.$refs.chatArea;
                if (el) el.addEventListener('scroll', () => this._updateFollowBottom());
            });

            // Session selected / created in the sidebar.
            window.addEventListener('janito-open-session', (e) => {
                this.openSession(e.detail);
            });
            // Page-load state restore: the sidebar prefetches every session's
            // stored history (issue #36) without switching tabs.
            window.addEventListener('janito-prefetch-session', (e) => {
                this._prefetchSession(e.detail);
            });
            // A session was deleted (release its socket/store unconditionally).
            window.addEventListener('janito-session-deleted', (e) => {
                this._releaseSession(e.detail);
            });
            // The active session was deleted -> also clear the visible view.
            window.addEventListener('janito-clear-session', () => {
                this.clearActive();
            });
        },

        // ---------------------------------------------------------------
        // Store access
        // ---------------------------------------------------------------

        // Get (or lazily create) the persistent store for a session.
        _store(id) {
            if (!this._sessions[id]) {
                this._sessions[id] = {
                    id,
                    messages: [],
                    status: 'idle',
                    error: null,
                    connection: 'disconnected',
                    current: null,
                    toolsSummary: null, // { active, skipped, skippedList } from session_start
                    title: null,         // session title
                    loaded: false,     // history fetched from the server yet?
                    loading: false,    // a history fetch is in flight
                    dirty: false,      // user already sent a message locally
                    titled: false,     // already named from its first message?
                    pendingPrompts: [], // accepted locally, awaiting a safe boundary
                    turnStartIndex: null, // UI rollback boundary (includes steering)
                };
            }
            return this._sessions[id];
        },

        _socket(id) {
            return window.__janitoSessionSockets.get(id) || null;
        },

        // ---------------------------------------------------------------
        // Tab switching
        // ---------------------------------------------------------------

        async openSession(id) {
            this.sessionId = id;
            window.dispatchEvent(new CustomEvent('janito-session-lock', {
                detail: { sessionId: id, locked: false },
            }));
            const store = this._store(id);

            // Project this session's store into the visible state.
            this.messages = store.messages;
            this.status = store.status;
            this.error = store.error;
            this.connection = store.connection;
            this._current = store.current;
            this.toolsSummary = store.toolsSummary;
            const existingUserMessages = store.messages.filter(m => m.role === 'user');
            window.dispatchEvent(new CustomEvent('janito-session-lock', {
                detail: { sessionId: id, locked: existingUserMessages.length > 0 },
            }));
            this._broadcastConn();
            this._forceScrollToBottom();

            // Broadcast all session statuses so background sessions get their
            // indicators updated in the sidebar (e.g. a session that was already
            // streaming when the user switched away from it).
            this._broadcastAllStatuses();

            // Ensure this session has a live socket (created once, reused).
            if (!this._socket(id)) {
                this._createSocket(id);
            }

            // Load history exactly once per session.
            if (!store.loaded && !store.loading) {
                await this._loadHistory(id);
            }
        },

        // Create a persistent socket for a session. Its callbacks always write
        // to that session's own store, regardless of which tab is visible.
        _createSocket(id) {
            const store = this._store(id);
            const socket = new ChatSocket(id, {
                onOpen: () => {
                    store.connection = 'connected';
                    this._reflectConnection(id);
                },
                onClose: () => {
                    store.connection =
                        socket.reconnectAttempts < socket.maxReconnectAttempts
                            ? 'connecting' : 'disconnected';
                    this._reflectConnection(id);
                },
                onEvent: (event) => this._handleEvent(event, store),
            });
            window.__janitoSessionSockets.set(id, socket);
            socket.connect();
        },

        // Prefetch a session's stored history into its store (once). Used on
        // page load to restore the state of every session (issue #36): the
        // store is created and its messages are replayed, but the visible tab
        // is NOT switched. Guarded by store.loaded/loading, so a later
        // openSession() reuses the already-fetched history.
        _prefetchSession(id) {
            const store = this._store(id);
            if (store.loaded || store.loading) return;
            this._loadHistory(id);
        },

        // Load a session's stored history into its store (once).
        async _loadHistory(id) {
            const store = this._store(id);
            store.loading = true;
            try {
                const session = await Api.getSession(id);
                // Remember the title so a background-session question toast
                // can name the conversation that asked.
                store.title = session.title || null;
                // If the user already started chatting in this session while
                // the fetch was in flight, don't clobber their live messages.
                if (!store.dirty) {
                    const loaded = this._historyToUi(session.messages || []);
                    // Mutate in place so any `this.messages` already pointing
                    // at this array picks up the loaded content.
                    store.messages.splice(0, store.messages.length, ...loaded);
                    // An existing conversation keeps its stored title; only a
                    // fresh "New conversation" session gets auto-named from
                    // its first message (see sendPrompt/_autoTitle).
                    store.titled = session.title !== 'New conversation';
                }
                store.loaded = true;
                if (this.sessionId === id) {
                    const userMessages = store.messages.filter(m => m.role === 'user');
                    window.dispatchEvent(new CustomEvent('janito-session-lock', {
                        detail: { sessionId: id, locked: userMessages.length > 0,
                            provider: session.provider, model: session.model },
                    }));
                    this._forceScrollToBottom();
                }
            } catch (e) {
                console.error('Failed to load session history:', e);
            } finally {
                store.loading = false;
            }
        },

        // ---------------------------------------------------------------
        // Sending
        // ---------------------------------------------------------------

        pendingMessages() {
            return this.sessionId ? this._store(this.sessionId).pendingPrompts : [];
        },

        sendPrompt(mode = 'steer') {
            const content = this.input.trim();
            if (!content) return;

            const id = this.sessionId;
            if (!id) {
                // No active conversation yet (e.g. the page is still
                // bootstrapping, or the active session was just deleted).
                // The input box is still usable, so don't silently drop the
                // submission — tell the user what to do instead.
                this._notifySendBlocked(
                    'No active conversation. Select or create one in the sidebar first.'
                );
                return;
            }
            const store = this._store(id);
            const busy = store.status !== 'idle';

            // Intercept slash commands handled entirely on the client.
            if (!busy && content.startsWith('/') && this._handleSlashCommand(content, store)) {
                this.input = '';
                this._autoResize();
                return;
            }

            // Make sure the message can actually reach the server BEFORE
            // committing the UI (pushing the user message / clearing the
            // input). If the socket is missing or closed, keep the typed text
            // so nothing is lost, and surface the failure.
            const socket = this._socket(id);
            if (!socket || !socket.sendPrompt(content, busy ? mode : 'send')) {
                console.error('[chat] sendPrompt FAILED -> "Not connected to server."');
                store.error = 'Not connected to server.';
                this.error = store.error;
                this._notifySendBlocked(
                    'Not connected to the server — your message was kept.'
                );
                return;
            }

            store.error = null;
            this.error = null;
            store.dirty = true;   // protect the pending _loadHistory from clobbering
            if (busy) {
                store.pendingPrompts.push({ content, mode });
                this.input = '';
                this._autoResize();
                return;
            }
            window.dispatchEvent(new CustomEvent('janito-session-lock', {
                detail: { sessionId: id, locked: true },
            }));

            // A new empty conversation gets named from the start of its first
            // message: rename the session and refresh the sidebar so the tab
            // label replaces the default "New conversation" right away (the
            // backend auto-titles too; doing it here makes the UI update
            // immediately instead of on the next sidebar reload).
            if (!store.titled && store.messages.length === 0) {
                store.titled = true;
                this._autoTitle(id, content);
            }

            this.input = '';
            this._autoResize();
            this._beginPrompt(store, content);
        },

        // Server-started follow-ups and local initial submissions share the
        // same row creation. Steering preserves the whole turn's boundary.
        _beginPrompt(store, content, steering = false) {
            if (store.current) {
                store.current.streaming = false;
                store.current.done = true;
                if (store.current.parts.length === 0) {
                    const index = store.messages.indexOf(store.current);
                    if (index !== -1) store.messages.splice(index, 1);
                }
            }
            if (!steering || store.turnStartIndex === null) {
                store.turnStartIndex = store.messages.length;
            }
            store.messages.push(this._newMessage('user', content));
            const assistant = this._newMessage('assistant', '');
            assistant.streaming = true;
            store.messages.push(assistant);
            store.current = assistant;
            this._setStatus(store, 'waiting');
            if (store.id === this.sessionId) {
                this._current = store.current;
                this.status = 'waiting';
                this._forceScrollToBottom();
            }
        },

        // Surface a blocked submission (no session or not connected) so
        // the user never sees a silent no-op with the text stuck in the box.
        // Rendered as a transient toast by the root app component.
        _notifySendBlocked(text) {
            window.dispatchEvent(
                new CustomEvent('janito-toast', { detail: { kind: 'error', text } })
            );
        },

        // Send an answer typed in an in-chat question card (AskUser tool)
        // back to the session that raised the question, then collapse the
        // card's input into a read-only record of the answer. The backend
        // blocked the agent turn on this answer, so sending it lets the tool
        // resume.
        _submitPromptAnswer({ sessionId, prompt_id, answer }) {
            const socket = this._socket(sessionId);
            if (socket && prompt_id) {
                socket.sendPromptAnswer(prompt_id, answer);
            } else {
                console.warn('[chat] prompt answer dropped: no socket or id', { sessionId, prompt_id });
            }
            this._resolvePromptCard(sessionId, prompt_id, answer);
        },

        // Mark an in-chat question card as answered/skipped once its answer
        // has been sent, so its input collapses into a read-only record.
        _resolvePromptCard(sessionId, prompt_id, answer) {
            const store = this._store(sessionId);
            const resolved = (answer || '').trim();
            for (const msg of store.messages) {
                if (!Array.isArray(msg.parts)) continue;
                for (const part of msg.parts) {
                    if (part.kind === 'prompt' && part.prompt_id === prompt_id && part.state === 'pending') {
                        part.answer = resolved;
                        part.answerDraft = resolved;
                        part.state = resolved ? 'answered' : 'dismissed';
                        return;
                    }
                }
            }
        },

        // Submit the answer typed into an in-chat question card.
        submitPromptCard(part) {
            if (!this.sessionId || !part || part.state !== 'pending') return;
            const answer = (part.answerDraft || '').trim();
            if (!answer) return;
            this._submitPromptAnswer({
                sessionId: this.sessionId,
                prompt_id: part.prompt_id,
                answer,
            });
        },

        // Skip an in-chat question card without answering: the tool receives
        // an empty answer (mirrors the old modal's Dismiss button).
        dismissPromptCard(part) {
            if (!this.sessionId || !part || part.state !== 'pending') return;
            this._submitPromptAnswer({
                sessionId: this.sessionId,
                prompt_id: part.prompt_id,
                answer: '',
            });
        },

        // Name a new conversation from the start of its first message (the
        // first 60 chars, mirroring the backend's auto-title in
        // routers/chat.py), then tell the sidebar to swap just this session's
        // label in place (janito-session-title) instead of reloading the whole
        // list - a full reload re-sorts and rebuilds every tab, which looks
        // like a flicker. Best-effort: a failed rename just logs.
        _autoTitle(id, content) {
            const title = content.slice(0, 60);
            this._store(id).title = title;   // keep the store title fresh
            Api.renameSession(id, title)
                .then(() => {
                    window.dispatchEvent(new CustomEvent('janito-session-title', {
                        detail: { id, title },
                    }));
                })
                .catch((e) => console.error('[chat] failed to auto-title session:', e));
        },

        // ---------------------------------------------------------------
        // Cancel (Ctrl+C)
        // ---------------------------------------------------------------

        // Abort the in-flight request for the active session.  Sends a
        // `{"type": "cancel"}` message to the server which stops the
        // agentic loop and rolls back the conversation history to the
        // pre-turn state. The acknowledgement performs the local rollback;
        // don't open a new turn while the old one is still cancelling.
        cancelRequest() {
            const id = this.sessionId;
            if (!id) return;
            const store = this._store(id);

            // Don't cancel if nothing is running.
            if (store.status !== 'waiting' &&
                store.status !== 'streaming' &&
                store.status !== 'tool_running') {
                return;
            }

            // Tell the server to abort the current turn and roll back the
            // history to before this turn's user message.
            const socket = this._socket(id);
            if (socket) socket.sendCancel();
        },

        // ---------------------------------------------------------------
        // Clear conversation (F2)
        // ---------------------------------------------------------------

        // Clear the conversation on both server and client, preserving the
        // system prompt.  Mirrors the shell's F2 key binding.
        restartSession() {
            const id = this.sessionId;
            if (!id) return;

            const store = this._store(id);

            // If a response is in flight, cancel it first (like Ctrl+C) so
            // the server stops the agentic loop before we clear the history.
            if (store.status === 'waiting' ||
                store.status === 'streaming' ||
                store.status === 'tool_running') {
                const cancelSocket = this._socket(id);
                if (cancelSocket) cancelSocket.sendCancel();
                // Finalize the in-flight assistant message locally.
                if (store.current) {
                    store.current.streaming = false;
                    store.current.cancelled = true;
                    store.current = null;
                }
            }

            // Ask the server to clear history (keeps system prompt).
            const socket = this._socket(id);
            if (socket) socket.sendRestart();

            // Reset local UI immediately.
            store.messages.splice(0, store.messages.length);
            store.pendingPrompts.splice(0);
            store.turnStartIndex = null;
            store.current = null;
            store.dirty = false;
            store.loaded = true;   // no need to re-fetch empty history
            store.titled = false;  // a cleared conversation gets re-named from its next message
            this._current = null;
            this.error = null;
            store.error = null;
            this._setStatus(store, 'idle');
            this.status = 'idle';
            this.input = '';
            this._autoResize();
            this._forceScrollToBottom();
        },
    },
    // ---- Focused concerns (loaded as separate files before this one) ----
    window.ChatStoreMixin,
    window.ChatEventsMixin,
    window.ChatHistoryMixin,
    window.ChatMessagesMixin,
    window.ChatScrollMixin,
    window.ChatCommandsMixin,
    window.ChatFormatMixin);
}
