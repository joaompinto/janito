# ACP (Agent Client Protocol)

> **Alpha** â€” The `--acp` mode is functional and actively developed, but the
> exact set of ACP v1 methods and session updates janito emits may change
> between releases. Pin a specific version if you depend on it.

Janito can run as an [Agent Client Protocol (ACP)](https://agentclientprotocol.com/)
v1 agent: a subprocess that editors and AI-native development tools spawn and
talk to over stdin/stdout using newline-delimited JSON-RPC 2.0. This lets the
editor drive janito â€” sessions rooted in your project directory, prompts that
render into the editor's chat UI, tool calls shown as progress cards, and
cancellation of a running turn â€” instead of you switching to a terminal.

The ACP agent reuses the same headless agentic loop as `--web`
(`janito.web.backend.agent`), so the tools, MCP services, skills, privileges,
and configuration are identical to the other surfaces.

## Running as an ACP agent

Launch janito from the editor's agent configuration:

```bash
janito --acp
```

ACP runs must speak JSON-RPC, so janito does not accept a chat prompt in this
mode. Configure the provider, model, and API key the same way you would for
any other use:

```bash
janito --set provider=openai --set model=gpt-5.6-luna
janito --set-api-key="sk-your-key" --provider openai
```

## Protocol surface

- **Transports** â€” stdio only. Requests arrive line-by-line on stdin; responses
  and `session/update` notifications go to stdout. stdout carries *only* ACP
  messages â€” the version banner, plugin loading output, and all other logs are
  redirected to stderr so the stream stays valid JSON.
- **Methods** â€” `initialize`, `session/new`, `session/prompt`, and the
  `session/cancel` notification. Other v1 methods (`session/load`,
  `session/list`, `session/delete`, `authenticate`, ...) are not implemented
  and answer with `-32601 Method not found`.
- **Initialization** â€” janito negotiates **protocol version 1** and reports
  `promptCapabilities.embeddedContext = true` (resource blocks are accepted),
  no image/audio input, and no client-side MCP servers.
- **Sessions** â€” `session/new` requires an absolute `cwd`; all file-relative
  work happens inside that directory for the lifetime of the session. The
  system prompt (custom `-S`, effective default prompt including the session
  `cwd`'s `AGENTS.md`) is resolved under the requested `cwd` and prepended
  to the conversation. `session/new` waits for any active turn instead of
  racing its `chdir`.
- **Prompt content** â€” `text` blocks are sent verbatim; `resource` blocks (with
  file contents) and `resource_link` blocks are converted into the prompt.
  Image and audio blocks are passed through as a note that they were ignored
  (janito has no vision/audio input).
- **Streaming** â€” token text maps to `agent_message_chunk`, reasoning to
  `agent_thought_chunk`, tool calls to `tool_call` / `tool_call_update`
  (with `kind`, human-readable `title`, and file `locations` resolved against
  the session's `cwd`). A turn ends with either `stopReason: "end_turn"` or
  `stopReason: "cancelled"`.
- **Cancellation** â€” `session/cancel` cancels the running turn; the prompt
  request then resolves with `stopReason: "cancelled"` instead of an error.
  Cancellation stops streaming promptly but waits for the current sync work
  (tool execution, MCP discovery, sync SDK chunks) to finish before
  restoring the session `cwd`; repeated cancels never interrupt that
  cleanup. A cancelled turn, a failed turn, and a turn ending in an error
  event all roll the conversation back to before the turn, preserving the
  system prompt and earlier completed turns.
- **One turn per session** â€” a second `session/prompt` on a session with a
  running turn is rejected (`-32602`) instead of interleaving with it.

## Known limitations

- **Synchronous work cannot be forcibly stopped.** Cancellation and stdin
  shutdown wait for an in-flight tool, MCP discovery, or sync SDK chunk to
  finish. Turns and session creation are serialized while that work owns
  the process cwd; a long-running tool delays other sessions too.

- **Client `mcpServers` are ignored.** Janito uses the MCP servers configured
  in its own `mcp_config` (`/mcp` services) and does not connect to servers the
  client proposes, and `mcpCapabilities` are reported as disabled.
- **`session/load` is not supported**, so sessions are ephemeral in memory and
  do not persist across agent restarts.
- **Token usage is not reported** (`usage` updates are skipped). Janito's
  counters do not match the ACP usage-group semantics, so reporting them would
  mislead clients that render token bars.
- Mid-turn user questions via the `AskUser` tool are not surfaced to the client
  (`session/request_permission` is not emitted), so the tool is skipped.
- **Unix-like platforms.** The stdio transport relies on
  `asyncio.connect_read_pipe`, which the default Windows event loop does not
  implement â€” `--acp` is currently Linux/macOS only.