# Interactive Mode

Interactive mode provides a **terminal shell** for multi-turn conversations with context preservation.

> **This is the terminal (CLI/shell) interface.** janito also ships a
> browser-based **web UI** (`janito --web`) with its own chat surface, session
> sidebar, and dashboards. The two share the same engine and tools — see
> [CLI vs Web UI](cli-vs-web.md) and [Web UI](web-ui.md) for the differences.

## Starting Interactive Mode

```bash
janito
```

Without arguments, janito starts an interactive shell:

```
Starting interactive chat session. Type '/exit' or CTRL-D to end the session
gpt-6-luna #
```

(The prompt shows the active model name; a status toolbar reports the model,
provider and privileges.)

!!! note
    Anything not recognized as a command is sent to the model as a prompt.
    In particular, bare words like `exit`, `quit` or `help` are **not**
    commands — type `/exit`, `/quit` is not implemented, and help is `/help`.
    Unrecognized `/slash` commands are rejected with an `Unknown command:`
    message instead of being sent to the model.

## Resuming a Session (`-C` / `--continue`)

An interactive session **mirrors its conversation** to `./.janito/session.json`
(in the current working directory, next to the input-history `history.log`)
after every interaction, so you can exit and later pick up exactly where you
left off:

```bash
janito          # chat for a while...
/exit           # (or Ctrl+D) leave
janito -C       # reopen with the whole previous context restored
```

`-C` / `--continue` restores the last conversation saved in that working
directory **including** its provider, model and API type, so the restored
context stays valid (a server-side Responses conversation even resumes from
its last response id). Because the snapshot is keyed to the directory, resume
from the same directory you chatted in.

On resume, janito prints the **5 most recent messages** (a `Resumed
conversation` recap: the latest user prompt plus the replies that followed,
shown in full text; tool-call and reasoning rows are hidden) so you can see
where the previous session left off — display-only; the whole restored
context is still what gets sent to the model.

What gets restored:

- the full conversation (user/assistant turns, tool-call rounds, ...),
- the system prompt,
- the `/history` turn markers and `/rewind` capability,
- the session's provider/model/API type, thinking mode and reasoning effort.

Notes:

- Starting a session without `-C` replaces the snapshot once you interact, so
  use `janito -C` to resume and `janito` to start fresh.
- If you pass `--provider` / `--model` / `--api-type` with `-C` that conflict
  with the saved session, janito starts a new conversation (the saved snapshot
  is left intact for a plain `janito -C`).
- `-C` only applies to the interactive shell — it is rejected with a
  positional prompt or piped stdin.
- `--no-history` disables the snapshot entirely (nothing is written, nothing
  is resumed); it still disables the input-history file as before.

## Available Commands

Plain keyboard/input commands in interactive mode:

| Command | Description |
|---------|-------------|
| `/exit` | End the session |
| `clear` | Clear conversation and start a new one |
| `Ctrl+D` / `Ctrl+Z` + `Enter` (Windows) | Exit (EOF) |
| `Ctrl+C` | While idle: asks whether to quit the conversation. While a response is pending: cancels the request and rolls the last prompt/answer back out of the history |
| `Enter` | While a prompt is pending ("Waiting for response from the API server..."), cancels the request and keeps the prompt in the conversation history |
| `F2` | Clear the conversation and start a fresh one (like `clear`) |
| `F12` | "Do It" — auto-sends a `Do It` prompt to continue an existing plan |

## Chat Commands

Additional slash commands available in the terminal shell:

> These commands are implemented by the **terminal shell**. The web chat only
> handles `/tools` on the client (rendered as a card panel); any other slash
> command typed there is sent to the model as ordinary text.

| Command | Description |
|---------|-------------|
| `/help` | Show help: every command with its description, the session privilege switches (read-only / read + write / full access / read + execute / write-only / no tools) and the keyboard shortcuts |
| `/exit` | End the session |
| `/ask <question>` | Send a one-off question to the LLM with a **fresh, isolated** chat history (the main conversation is not affected) |
| `/skills` | List all available skills (home + agents + local) |
| `/tools` | List all available tools |
| `/plugins` | List the installed plugins (from `<config_dir>/plugins`, default `~/.janito/plugins`), their paths and whether they loaded in the current session |
| `/read` | Switch the privileges of the whole session to read-only (`"r"` permission tools) — the model can read/search/fetch but cannot write or execute. Applies to all subsequent prompts; reflected in `/priv`, the bottom toolbar and the Turn-rule privilege badge |
| `/rw` | Switch the privileges of the whole session to read + write (`"r"`/`"w"` permission tools) — the model can read/search/fetch and create, modify or delete files/dirs but cannot execute anything. Applies to all subsequent prompts |
| `/rwx` | Switch the privileges of the whole session to full access (`"r"`/`"w"`/`"x"` permission tools) — the model gets the full toolset (read, write and execute). Applies to all subsequent prompts |
| `/rx` | Switch the privileges of the whole session to read + execute (`"r"`/`"x"` permission tools) — the model can read/search/fetch and run commands but cannot write or modify anything. Applies to all subsequent prompts |
| `/write` | Switch the privileges of the whole session to write-only (`"w"` permission tools) — the model can create, modify or delete files/dirs but cannot read, search or execute. Applies to all subsequent prompts |
| `/notools <message>` | Send the message to the LLM using the **main** conversation history, but without offering any tools (the per-message equivalent of `--no-tools`). Only this message is affected — the next prompt goes back to the session's default tools. The exchange stays in the main history and rolls back like a normal prompt on cancel |
| `/show_tools_stats` | Show tool usage statistics (from the SQLite `tools_use.db`) |
| `/changes` | Show the file-changing tool executions recorded for the current prompt |
| `/status` | Print the resolved runtime configuration (provider, model, API type, endpoint, masked API key, token limits, reasoning level, thinking). The **Model** row shows the session's effective model (`--model`, `/model` or the startup resolution); the provider's built-in default is marked `(default)`. |
| `/history` | Show the conversation history as rendered rows, marking where each turn started |
| `/prompt` | Show the current system prompt |
| `/priv` | Show the current running privileges (READ / WRITE / EXEC) |
| `/price` | Show a per-model pricing table for every built-in model: estimated cost of 1M input (cache miss) + 1M cached input + 1M output tokens, as separate `1M in` / `1M cache` / `1M output` columns plus their `Total` |
| `/multi` | Enable multiline input for the **next prompt only** (submit with `ESC` then `Enter`) |
| `/rewind` | Undo the most recent turn, stepping back one exchange at a time (truncates the history to the last turn) |
| `/push` | Branch the conversation onto a stack and enter a new chat thread (nestable). Prints `Entering new chat thread [n]`, where `n` is the stack depth; the prompt shows `[n]` while branched |
| `/push <msg>` | Same as `/push`, then immediately starts a new turn in the branched thread using `<msg>` as the prompt |
| `/pop` | Return to the previous stack level. Prints `Returned to thread [n]` (or `Returned to main thread`), then prints `Last Message:` and replays the restored thread's last assistant message |
| `/provider` | Show the current provider and the available providers |
| `/provider <name>` | Switch the session's provider (and model) for this shell session only — the configured default in `config.json` is left unchanged (use `janito --set provider=<name>` to persist a new default; autocompleted). The LLM conversation history is cleared so the new provider/model starts fresh |
| `/model` | Show the current model and the models available from the current provider |
| `/model <name>` | Switch the session's model for this shell session only — the configured default in `config.json` is left unchanged (use `janito --set model=<name>` to persist a new default; autocompleted). Like `--model`, the name is validated against the models available from the current provider (its built-in models; `openrouter` and `custom` accept any name) — when it matches, its canonical casing is used. The LLM conversation history is cleared so the new model starts fresh |
| `/api_types` | List the API types supported by each built-in provider/model (e.g. `Responses` / `Completions`, plus native-SDK types such as `Anthropic` / `DashScope` / `Gemini`), marking each model's built-in default API type |
| `/compact` | Compress older conversation history: keeps the last 3 turns verbatim and replaces everything before them with a single `[RECAP OF PRIOR WORK]` assistant message produced by a dedicated LLM call (Context Compression Engine). The compression call runs silently — only the progress bar shows, the model's raw recap output is not echoed (the turn still counts in the usage accounting). Disabled with "Conversation too short to compact effectively." when there is nothing worth compacting (fewer than 3 turns, or under 2,000 estimated tokens to replace) |
| `/thinking` | Show the current session thinking mode status |
| `/thinking on\|off` | Enable or disable runtime config thinking for the current session — the configured default in `config.json` is left unchanged (autocompleted) |
| `/effort` | Show the current session reasoning effort and supported levels |
| `/effort <level>` | Switch the session's reasoning effort (validated against the current model's supported levels; autocompleted) — runtime-only, config default unchanged |
| `/effort clear` | Clear the session effort override (config/default applies) |
| `/mcp add <name> stdio <cmd>` | Add MCP stdio service |
| `/mcp add <name> http <url>` | Add MCP HTTP service |
| `/mcp list` | List MCP services |
| `/mcp remove <name>` | Remove MCP service |

Beyond the slash commands, typing `!<command>` runs a shell command directly
with the real terminal inherited (so interactive programs such as `vim` or
`less` work); janito reports the command's exit code afterwards.

## Command Autocomplete

As you type a slash command, the shell suggests matching commands in a
dropdown menu. Start typing `/` and every registered command is offered;
narrow the list by typing more characters (for example `/t` suggests
`/tools`). Matching is case-insensitive. Use `Tab` to accept a suggestion, or
the arrow keys to browse the list. Regular chat input (anything not starting
with `/`) is never autocompleted.

Commands that take an argument also autocomplete that argument: after
`/provider `, the provider names are suggested as you type them, e.g.
`/provider op` suggests `openai`. Only providers with an API key stored in
`~/.janito/auth.json` are offered (switching to a key-less provider would
only make the next prompt fail with an authentication error); the full list
is still shown by `/provider` with no argument.

After `/model `, the models available from the **current provider** are
suggested as you type them, e.g. `/model gpt` suggests `gpt-6-luna`. The
available set is the provider's built-in models; `/model` with no argument
lists them all.

After `/thinking `, `on` and `off` are suggested.

After `/effort `, the current model's supported reasoning efforts are suggested.

## Examples

### Basic Chat

```bash
$ janito
Janito 0.0.0 - Working at /home/user/project
Using openai, model gpt-6-luna, API: Responses (server-side)
Starting interactive chat session. Type '/exit' or CTRL-D to end the session

gpt-6-luna # What is Python?
Assistant: Python is a high-level programming language...
gpt-6-luna # Tell me more about it
Assistant: Python was created by Guido van Rossum...
gpt-6-luna # /exit
Chat session ended.
```

### Multi-turn with File Operations

```bash
$ janito
gpt-6-luna # Read the README.md file and summarize it
Assistant: [File content summary]
gpt-6-luna # Now create a similar file called backup.md
Assistant: [File created successfully]
```

### Using Plugins

```bash
$ janito --plugin ../plugins/janito-onedrive-plugin
gpt-6-luna # List my files in Documents
Assistant: [Lists OneDrive files]
gpt-6-luna # Upload notes.txt to the Documents folder
Assistant: [File uploaded]
```

## Tips

- **Conversation History**: Messages are kept in context during the session
- **Use `clear`**: Clear the conversation and start a new one
- **Exit gracefully**: Use `/exit` (or `Ctrl+D`) for a clean exit
- **Undo a turn**: `/rewind` steps back one exchange at a time; `/history`
  shows what is kept
- **Branch a thread**: `/push` opens a nested chat thread (stack depth shown
  as `[n]` in the prompt); `/pop` returns to the previous thread. `clear`
  and `F2` always clear the full stack and start a fresh main thread

## Tracking Changes (`/changes`)

Every successful tool call whose first argument is a `filepath` and that has
write permission (for example `CreateFile`, `ReplaceTextInFile`, `MoveFile`,
...) is logged to `./.janito/changes.jsonl` while a prompt is being processed.
Read-only tools that also take a `filepath` first argument (such as
`ReadFile`) are not tracked, so the log only ever describes genuine changes.
Only the tool name and its parameters are recorded — never the tool's result.
The file is removed before each new prompt, so it always describes the changes
made while handling the *current* prompt.

Run `/changes` to replay those executions in a friendly, readable format:

- **`CreateFile`** — the written `content` is shown with syntax highlighting
  (the language is guessed from the file path).
- **`ReplaceTextInFile`** — a unified diff between `old_str` and `new_str` is
  generated and shown, syntax-highlighted.
- **Any other tool** — its parameters are shown as pretty-printed JSON.

When no changes have been recorded for the current prompt, `/changes` prints a
friendly message instead.

## Exiting

To exit interactive mode:

```bash
# Method 1: Type the exit command
You: /exit

# Method 2: Press Ctrl+D (Unix/macOS)

# Method 3: Press Ctrl+Z then Enter (Windows)

# Method 4: Press Ctrl+C and confirm the quit prompt with y
```

The shell then prints `Chat session ended.`
