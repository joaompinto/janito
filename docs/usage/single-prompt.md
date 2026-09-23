# Single Prompt

Run a single prompt and get a response without entering interactive mode.

## Basic Usage

```bash
janito "What is the capital of France?"
```

## Piping Input

You can pipe text into janito:

```bash
echo "Explain this code" | janito
```

!!! note "Pipe mode: stdin is the prompt"
    When input is piped, its content becomes the prompt — janito reads it as
    a whole and it **replaces** any positional prompt argument. To ask about
    piped content, include the instruction in the piped text itself:

    ```bash
    cat readme.md | janito        # the README content is the prompt
    (echo "Summarize this:"; cat readme.md) | janito
    ```

    Because stdin is consumed by the prompt, nobody can answer interactive
    questions: the `AskUser` tool is skipped in pipe mode, so the agent
    proceeds with its best judgement instead of stalling on a question.

!!! warning "Do not combine `--set` with a prompt"
    Batch configuration operations (`--set`, `--unset`, `--get`,
    `--set-secret`, `--delete-secret`) are handled first and janito exits
    after applying them — the prompt on the same line is **not** sent.
    Run the configuration step and the prompt step separately:

    ```bash
    janito --set provider=openai --set model=gpt-6-luna   # Step 1: configure
    janito "Your question here"                      # Step 2: run
    ```

## Examples

### Quick Question

```bash
janito "What is 2+2?"
```

### With Tools

```bash
janito "List all Python files in the current directory"
```

### With Plugins

```bash
janito --plugin ../plugins/janito-gmail-plugin "Show my unread emails from today"
janito --plugin ../plugins/janito-onedrive-plugin "List my files in Documents"
```

## Exit Codes

Single prompt mode returns standard exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (configuration, API, etc.) |
| `130` | Interrupted (Ctrl+C or Enter) |

## Use Cases

Single prompt mode is ideal for:

- Quick questions
- Scripting and automation
- Integration with other tools
- One-off tasks

For multi-turn conversations, use [interactive mode](interactive-mode.md) instead.
