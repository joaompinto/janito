// Streamed-event routing for the chat component, as a dispatch table.
//
// `_handleEvent` used to be a giant `switch` (~150 lines). Each case is now a
// handler keyed by `event.type`. Handlers receive a small context object `c`:
//     { comp, event, store, msg, isActive }
// where `msg` is the in-flight assistant message (store.current). Handlers
// may reassign `c.msg`; `_handleEvent` writes it back to `store.current`
// afterwards so 'done'/'cancelled'/'error' can clear it in one place.
//
// `session_start` and `restarted` fire before any assistant message exists,
// so they are handled as early returns (not part of the table).

const CHAT_EVENT_HANDLERS = {
    waiting(c) {
        c.comp._setStatus(c.store, 'waiting');
        if (c.isActive) c.comp.status = 'waiting';
    },

    token(c) {
        c.comp._setStatus(c.store, 'streaming');
        if (c.isActive) c.comp.status = 'streaming';
        c.comp._appendTextPart(c.msg, c.event.content);
        if (c.isActive) c.comp._scrollToBottom();
    },

    reasoning(c) {
        // Reasoning bursts are interleaved with text/tool parts, so each
        // burst separated by other content becomes its own card.
        c.comp._appendReasoningPart(c.msg, c.event.content, true);
        if (c.isActive) c.comp._scrollToBottom();
    },

    tool_call(c) {
        c.comp._setStatus(c.store, 'tool_running');
        if (c.isActive) c.comp.status = 'tool_running';
        const tool = {
            id: c.event.id,
            name: c.event.name,
            args: c.event.args,
            permissions: c.event.permissions || '',
            status: 'running',
            result: null,
            error: null,
            execution_time_ms: null,
            progress: [],
            open: true,
        };
        c.msg.toolCalls.push(tool);            // flat list for id lookup
        c.msg.parts.push({ kind: 'tool', tool });  // same ref, ordered
        if (c.isActive) c.comp._scrollToBottom();
    },

    tool_progress(c) {
        const tc = c.comp._findToolCall(c.msg, c.event.id);
        if (tc) {
            const last = tc.progress[tc.progress.length - 1];
            if (c.event.level === 'output' && last && last.level === 'output') {
                last.message += '\n' + c.event.message;
            } else {
                tc.progress.push({ level: c.event.level, message: c.event.message });
            }
            if (c.isActive) c.comp._scrollToBottom();
        }
    },

    tool_result(c) {
        const tc = c.comp._findToolCall(c.msg, c.event.id);
        if (tc) {
            tc.status = c.event.error ? 'error' : 'done';
            tc.result = c.event.result;
            tc.error = c.event.error;
            tc.execution_time_ms = c.event.execution_time_ms;

            // CreateSVG tool: render the SVG inline as a content card.
            if (!c.event.error && c.event.result
                && c.event.result.content_type === 'svg'
                && c.event.result.svg_text) {
                c.msg.parts.push({
                    kind: 'svg',
                    svg: c.event.result.svg_text,
                    view_width: c.event.result.view_width,
                    view_height: c.event.result.view_height,
                });
            }

            // CreateImage tool: render the generated image inline as a card.
            if (!c.event.error && c.event.result
                && c.event.result.content_type === 'image'
                && c.event.result.image_path) {
                c.msg.parts.push({ kind: 'image', path: c.event.result.image_path });
            }
        }
        if (c.isActive) c.comp._scrollToBottom();
    },

    image(c) {
        // Native Responses-API image generation (image_generation tool):
        // the backend already saved the PNG and emitted this event with its
        // path, so render it inline as a content card.
        c.comp._setStatus(c.store, 'streaming');
        if (c.isActive) c.comp.status = 'streaming';
        c.msg.parts.push({ kind: 'image', path: c.event.path });
        if (c.isActive) c.comp._scrollToBottom();
    },

    usage(c) {
        c.msg.usage = {
            total: c.event.total,
            last_input: c.event.last_input,
            last_output: c.event.last_output,
            last_cached: c.event.last_cached,
            max_tokens: c.event.max_tokens || null,
            turn_input: c.event.turn_input || null,
            turn_cached: c.event.turn_cached || null,
            turn_output: c.event.turn_output || null,
        };
        if (c.isActive) {
            window.dispatchEvent(new CustomEvent('janito-usage', { detail: c.msg.usage }));
        }
    },

    // The assistant raised an in-browser question (AskUser tool): the
    // backend blocked the turn until the user answers. Add a question card
    // to the in-flight assistant message so the answer can be typed inline
    // in the chat stream. For a background session we fire a toast so the
    // question isn't silently waiting in another tab.
    prompt(c) {
        c.msg.parts.push({
            kind: 'prompt',
            prompt_id: c.event.prompt_id,
            question: c.event.question,
            answerDraft: '',
            answer: '',
            state: 'pending',
        });
        if (c.isActive) {
            c.comp._scrollToBottom();
        } else {
            window.dispatchEvent(new CustomEvent('janito-toast', {
                detail: {
                    kind: 'ok',
                    text: `The assistant asked a question in \u201c${c.store.title || 'a conversation'}\u201d.`,
                },
            }));
        }
    },

    web_search(c) {
        // Search grounding (issue #131): the model searched the web.
        c.comp._setStatus(c.store, 'waiting');
        if (c.isActive) c.comp.status = 'waiting';
    },

    sources(c) {
        // Search grounding (issue #131): cited sources for the answer.
        // Stored for future display; the citation markers are already
        // inlined into the message text (see 'done').
        c.msg.sources = c.event.sources || [];
    },

    done(c) {
        c.msg.streaming = false;
        c.msg.done = true;
        c.store.turnStartIndex = null;
        // Stay busy between queued turns so a new submission cannot jump
        // ahead of pending messages in the local transcript.
        const status = c.store.pendingPrompts.length ? 'waiting' : 'idle';
        c.comp._setStatus(c.store, status);
        if (c.isActive) {
            c.comp.status = status;
            c.comp._scrollToBottom();
        }
        c.msg = null;
    },

    cancelled(c) {
        // Server confirmed the abort and rolled the history back to before
        // this turn. Remove all its rows, including steering instructions,
        // to stay in sync with the server.
        c.comp._rollbackTurn(c.store);
        c.store.pendingPrompts.splice(0);
        c.comp._setStatus(c.store, 'idle');
        if (c.isActive) {
            c.comp.status = 'idle';
            c.comp._scrollToBottom();
        }
        c.msg = null;
    },

    error(c) {
        c.store.error = c.event.message;
        // Server rolled the history back to before this turn on error.
        c.comp._rollbackTurn(c.store);
        c.store.pendingPrompts.splice(0);
        c.comp._setStatus(c.store, 'idle');
        if (c.isActive) {
            c.comp.error = c.event.message;
            c.comp.status = 'idle';
            c.comp._scrollToBottom();
        }
        c.msg = null;

        // Session was lost (e.g. server restarted) — clean up the dead socket
        // and let the sidebar create a fresh session.
        if (/session not found/i.test(c.event.message || '')) {
            console.warn('[chat] session lost on server, recovering…');
            c.comp._releaseSession(c.store.id);
            window.dispatchEvent(new CustomEvent('janito-session-lost', { detail: c.store.id }));
        }
    },
};

window.ChatEventsMixin = {
    // Apply a streamed event to a specific session's store. Only mutates
    // the visible projection when that session is the active tab.
    _handleEvent(event, store) {
        const isActive = (store.id === this.sessionId);

        if (event.type === 'prompt_started') {
            const index = store.pendingPrompts.findIndex(
                p => p.content === event.content && p.mode === event.mode
            );
            if (index !== -1) store.pendingPrompts.splice(index, 1);
            this._beginPrompt(store, event.content, event.mode === 'steer');
            return;
        }

        // F2 may already have removed the assistant row locally.
        if (event.type === 'cancelled') store.pendingPrompts.splice(0);

        // Server greets us on connect with a tools summary. This arrives
        // before any assistant message exists, so handle it up front.
        if (event.type === 'session_start') {
            store.toolsSummary = {
                active: event.active_tools || 0,
                skipped: event.skipped_tools || 0,
                skippedList: event.skipped || {},
            };
            if (isActive) this.toolsSummary = store.toolsSummary;
            return;
        }

        // Server confirmed the clear — history cleared, system prompt
        // preserved. Local UI was already reset in restartSession(); this
        // just serves as an acknowledgement.
        if (event.type === 'restarted') {
            store.current = null;
            store.dirty = false;
            store.loaded = true;
            this._setStatus(store, 'idle');
            if (isActive) {
                this._current = null;
                this.status = 'idle';
                this._forceScrollToBottom();
            }
            return;
        }

        // Every other event needs an in-flight assistant message.
        if (!store.current && event.type !== 'error') return;

        const handler = CHAT_EVENT_HANDLERS[event.type];
        if (!handler) return;

        const c = { comp: this, event, store, msg: store.current, isActive };
        handler(c);

        // Write back in case the handler cleared/changed the current message.
        store.current = c.msg;
        if (isActive) this._current = store.current;
    },
};
