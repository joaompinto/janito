// Scroll management + keyboard/input handling for the chat component.
// Folded into the Alpine component via Object.assign in chat.js.

window.ChatScrollMixin = {
    // Enter sends/steers, Ctrl/Cmd+Enter queues, Shift+Enter adds a newline,
    // F2 clears,
    // Ctrl+C to cancel the current request.
    onKeydown(e) {
        // IME confirmation and held keys must not submit messages.
        if (e.isComposing || e.keyCode === 229 || e.repeat) return;
        if (e.key === 'F2') {
            e.preventDefault();
            this.restartSession();
            return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
            // Only cancel if a request is in flight; otherwise let the
            // browser do its default (copy selected text / clear input).
            if (this.status === 'waiting' ||
                this.status === 'streaming' ||
                this.status === 'tool_running') {
                e.preventDefault();
                this.cancelRequest();
            }
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
            e.preventDefault();
            this.sendPrompt(e.ctrlKey || e.metaKey ? 'queue' : 'steer');
        }
    },

    _autoResize() {
        this.$nextTick(() => {
            const el = this.$refs.input;
            if (el) {
                el.style.height = 'auto';
                el.style.height = Math.min(el.scrollHeight, 200) + 'px';
            }
        });
    },

    _updateFollowBottom() {
        const el = this.$refs.chatArea;
        if (!el) return;
        const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
        this._followBottom = dist <= this._scrollThreshold;
    },

    // Snap to the bottom unconditionally (tab switch, history load, sending
    // a message, "jump to latest"). Also re-arms the auto-follow state so
    // subsequent streaming keeps the view pinned.
    _forceScrollToBottom() {
        this._followBottom = true;
        this.$nextTick(() => {
            const el = this.$refs.chatArea;
            if (el) el.scrollTop = el.scrollHeight;
        });
    },

    // Follow new content ONLY if the user was already at (or near) the
    // bottom. If they scrolled up to read, their position is preserved
    // ("scroll lock").
    _scrollToBottom() {
        if (!this._followBottom) return;
        this.$nextTick(() => {
            const el = this.$refs.chatArea;
            if (el) el.scrollTop = el.scrollHeight;
        });
    },
};
