// Behavioral tests for the plain-JS composer; no browser/build dependencies.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function component() {
    const context = vm.createContext({
        window: { dispatchEvent() {} },
        CustomEvent: class { constructor(type, options) { Object.assign(this, { type, ...options }); } },
        console: { error() {} },
    });
    const root = path.resolve(__dirname, '../../janito/web/frontend/js');
    for (const name of ['chatStore', 'chatEvents', 'chatMessages', 'chatScroll', 'chat']) {
        vm.runInContext(fs.readFileSync(path.join(root, name + '.js'), 'utf8'), context);
    }
    const comp = context.chatComponent();
    Object.assign(comp, {
        _autoResize() {}, _forceScrollToBottom() {}, _scrollToBottom() {},
        _handleSlashCommand() { return false; },
    });
    comp.sessionId = 'active';
    const store = comp._store('active');
    store.titled = true;
    comp.messages = store.messages;
    const sent = [];
    comp._socket = () => ({
        sendPrompt(content, mode) { sent.push({ content, mode }); return true; },
        sendCancel() { sent.push({ cancel: true }); return true; },
    });
    return { comp, store, sent };
}

test('Enter steers; Ctrl/Cmd+Enter queues; multiline and composition do not submit', () => {
    const { comp } = component();
    const sent = [];
    comp.sendPrompt = mode => sent.push(mode);
    for (const [options, expected] of [
        [{}, 'steer'], [{ ctrlKey: true }, 'queue'], [{ metaKey: true }, 'queue'],
        [{ shiftKey: true }, null], [{ ctrlKey: true, shiftKey: true }, null],
        [{ altKey: true }, null], [{ isComposing: true }, null],
        [{ keyCode: 229 }, null], [{ repeat: true }, null],
    ]) {
        let prevented = false;
        const before = sent.length;
        comp.onKeydown({ key: 'Enter', preventDefault() { prevented = true; }, ...options });
        assert.equal(prevented, expected !== null);
        assert.equal(sent.length - before, expected === null ? 0 : 1);
        if (expected) assert.equal(sent.at(-1), expected);
    }
});

for (const state of ['waiting', 'streaming', 'tool_running']) {
    for (const mode of ['steer', 'queue']) {
        test(`${mode} while ${state} preserves the active response and shows the pending message`, () => {
            const { comp, store, sent } = component();
            comp.input = 'original';
            comp.sendPrompt();
            const current = store.current;
            comp._setStatus(store, state);
            comp.status = state;
            comp.input = '  follow-up  ';
            comp.sendPrompt(mode);
            assert.equal(sent.at(-1).mode, mode);
            assert.equal(sent.at(-1).content, 'follow-up');
            assert.equal(comp.input, '');
            assert.equal(store.current, current);
            assert.equal(store.messages.length, 2);
            assert.equal(comp.pendingMessages()[0].mode, mode);
            assert.equal(store.status, state);
        });
    }
}

test('idle Enter and Ctrl+Enter both start a normal turn', () => {
    for (const mode of ['steer', 'queue']) {
        const { comp, store, sent } = component();
        comp.input = 'hello';
        comp.sendPrompt(mode);
        assert.equal(sent[0].mode, 'send');
        assert.equal(store.current.streaming, true);
        assert.equal(store.status, 'waiting');
        assert.equal(store.turnStartIndex, 0);
    }
});

test('failed sends keep the draft and do not enqueue or change history', () => {
    for (const state of ['idle', 'streaming']) {
        const { comp, store } = component();
        comp._socket = () => ({ sendPrompt() { return false; } });
        comp._setStatus(store, state);
        comp.status = state;
        comp.input = 'keep me';
        comp.sendPrompt('queue');
        assert.equal(comp.input, 'keep me');
        assert.equal(store.pendingPrompts.length, 0);
        assert.equal(store.messages.length, 0);
        assert.equal(store.status, state);
        assert.ok(store.error);
    }
});

test('steering splits the transcript at the safe boundary and cancellation rolls back the whole turn once', () => {
    const { comp, store } = component();
    comp._beginPrompt(store, 'earlier');
    comp._handleEvent({ type: 'done' }, store);
    const historySize = store.messages.length;
    comp.input = 'original';
    comp.sendPrompt();
    comp._handleEvent({ type: 'token', content: 'in progress' }, store);
    comp.input = 'change direction';
    comp.sendPrompt('steer');
    comp._handleEvent({ type: 'prompt_started', mode: 'steer', content: 'change direction' }, store);
    assert.equal(store.pendingPrompts.length, 0);
    assert.equal(store.messages.length, historySize + 4);
    assert.equal(store.turnStartIndex, historySize);
    comp.cancelRequest();
    assert.notEqual(store.status, 'idle');
    comp._handleEvent({ type: 'cancelled' }, store);
    comp._handleEvent({ type: 'cancelled' }, store);
    assert.equal(store.messages.length, historySize);
    assert.equal(store.current, null);
    assert.equal(store.status, 'idle');
});

test('queued turns start after done and background sessions never replace the active projection', () => {
    const { comp, store } = component();
    comp.input = 'original';
    comp.sendPrompt();
    comp.input = 'later';
    comp.sendPrompt('queue');
    comp._handleEvent({ type: 'done' }, store);
    assert.equal(store.status, 'waiting');
    assert.equal(store.pendingPrompts.length, 1);
    const background = comp._store('background');
    background.pendingPrompts.push({ content: 'background follow-up', mode: 'queue' });
    const activeMessages = comp.messages;
    comp._handleEvent({ type: 'prompt_started', mode: 'queue', content: 'background follow-up' }, background);
    assert.equal(comp.messages, activeMessages);
    assert.equal(comp.status, 'waiting');
    assert.equal(background.status, 'waiting');
    assert.equal(background.pendingPrompts.length, 0);
    comp._handleEvent({ type: 'prompt_started', mode: 'queue', content: 'later' }, store);
    assert.equal(store.pendingPrompts.length, 0);
    assert.equal(store.messages.at(-2).content, 'later');
    assert.equal(store.status, 'waiting');
});

test('a submission between queued turns cannot jump ahead of the pending history', () => {
    const { comp, store, sent } = component();
    comp.input = 'original';
    comp.sendPrompt();
    comp.input = 'queued first';
    comp.sendPrompt('queue');
    comp._handleEvent({ type: 'done' }, store);
    const historySize = store.messages.length;
    comp.input = 'queued second';
    comp.sendPrompt('queue');
    assert.equal(store.messages.length, historySize);
    assert.equal(sent.at(-1).mode, 'queue');
    assert.equal(store.pendingPrompts.length, 2);
});

test('steering before any output does not leave empty assistant bubbles', () => {
    const { comp, store } = component();
    comp._beginPrompt(store, 'original');
    comp._handleEvent({ type: 'prompt_started', mode: 'steer', content: 'one' }, store);
    comp._handleEvent({ type: 'prompt_started', mode: 'steer', content: 'two' }, store);
    assert.equal(store.messages.length, 4);
    assert.equal(store.messages.filter(m => m.role === 'assistant').length, 1);
});
