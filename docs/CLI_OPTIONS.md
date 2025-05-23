# 📝 Full CLI Options Reference

Below is a comprehensive list of CLI options supported by Janito. You can combine these flags as needed for your workflow.

- `input_arg` (positional): Prompt to send to the model, or session ID if --continue is used.
- `--list [N]`: List the last N sessions (default: 10) and exit.
- `--view SESSION_ID`: View the content of a conversation history by session id and exit.
- `--set-provider-config NAME KEY VALUE`: Set a provider config parameter (e.g., --set-provider-config openai api_key sk-xxx).
- `--lang LANG`: Language for interface messages (e.g., en, pt). Overrides config if set.
- `--app-shell`: Use the new prompt_toolkit Application-based chat shell (experimental).
- `--max-tokens N`: Maximum tokens for model response (overrides config, default: 32000).
- `--max-tools N`: Maximum number of tool calls allowed within a chat session (default: unlimited).
- `--model, -m MODEL`: Model name to use for this session (overrides config, does not persist).
- `--max-rounds N`: Maximum number of agent rounds per prompt (overrides config, default: 50).
- `--system PROMPT, -s PROMPT`: Optional system prompt as a raw string.
- `--system-file PATH`: Path to a plain text file to use as the system prompt (takes precedence over --system).
- `--role ROLE, -r ROLE`: Role description for the default system prompt.
- `--temperature, -t FLOAT`: Sampling temperature (e.g., 0.0 - 2.0).
- `--verbose-http`: Enable verbose HTTP logging.
- `--verbose-http-raw`: Enable raw HTTP wire-level logging.
- `--verbose-response`: Pretty print the full response object.
- `--list-tools`: List all registered tools and exit.
- `--show-system`: Show model, parameters, system prompt, and tool definitions, then exit.
- `--verbose-reason`: Print the tool call reason whenever a tool is invoked (for debugging).
- `--verbose-tools`: Print tool call parameters and results.
- `--no-tools, -n`: Disable tool use (default: enabled).
- `--set-local-config "key=val"`: Set a local config key-value pair.
- `--set-global-config "key=val"`: Set a global config key-value pair.
- `--run-config "key=val"`: Set a runtime (in-memory only) config key-value pair. Can be repeated.
- `--show-config`: Show effective configuration and exit.
- `--set-api-key KEY`: Set and save the API key globally.
- `--version`: Show program's version number and exit.
- `--help-config`: Show all configuration options and exit.
- `--continue-session, --continue`: Continue from a saved conversation. Uses the session ID from the positional argument if provided, otherwise resumes the most recent session.
- `--web`: Launch the Janito web server instead of CLI.
- `--live`: Launch the Janito live reload server for web development.
- `--config-reset-local`: Remove the local config file (~/.janito/config.json).
- `--config-reset-global`: Remove the global config file (~/.janito/config.json).
- `--verbose-events`: Print all agent events before dispatching to the message handler (for debugging).
- `--vanilla, -V`: Vanilla mode: disables tools, system prompt, and temperature (unless -t is set).
- `--trust-tools, -T`: Suppress all tool output (trusted tools mode: only shows output file locations).
- `--profile PROFILE`: Agent Profile name (only 'base' is supported).
- `--no-termweb`: Disable the built-in lightweight web file viewer for terminal links (enabled by default).
- `--termweb-port PORT`: Port for the termweb server (default: 8088).
- `--info, -i`: Show basic program info and exit (useful for one-shot shell execution).
- `--ntt`: Disable tool call reason tracking (no tools tracking).

For configuration details and advanced usage, see [CONFIGURATION.md](CONFIGURATION.md).
