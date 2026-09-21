"""CLI argument parser for janito."""

import argparse

from .. import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the CLI argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="janito",
        description="OpenAI CLI - Send prompts to OpenAI-compatible endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  Configuration is resolved from local files (no OPENAI_* environment variables):
    - API key:  ~/.janito/auth.json for the active provider (--set-api-key)
    - Endpoint: the provider's built-in default, or an override in
                ~/.janito/config.json (--set endpoint=...)
    - Model:    --model, or the provider's configured model (--set model=...)

  API keys are stored securely in ~/.janito/auth.json using --set-api-key

  With -l/--local, config/auth/secrets are stored in ./.janito (the current
  working directory) instead of ~/.janito; reads resolve local values first,
  falling back to the global ~/.janito, and list operations show both.

Options:
  --set-api-key KEY  Set API key for a provider (uses --provider, or the
                     configured default provider when --provider is omitted;
                     prompts before overwriting an existing key, use -f/--force
                     to overwrite without prompting)
  --provider NAME    Provider name (e.g., openai)
  -m, --model NAME   Model name to use (overrides the provider's configured model)
  --log LEVELS       Enable logging (e.g., --log=info,debug or --log=warning)
  --list-keys        List configured providers and keys
  --show-providers   List all supported providers and variants
  --list-models      List all config-available models for the provider
                     (--provider, or the provider defined in config.json)
  --list-tools       List all available built-in tools
  --list-mcp         List all MCP services and their tools
  -Z, --no-system-prompt  Do not set a system prompt or pass any tools to the CLI
  --no-tools              Do not load tools (disables built-in, skill, plugin, MCP and server-side tools)
  --no-tasks              Do not load the tasks toolset (StartTask/StopTask/WaitForTask/ListTasks)

Examples:
  janito "What is the capital of France?"                    # Single prompt mode
  echo "Tell me a joke" | janito                             # Pipe input mode
  janito                                                     # Interactive chat mode
  janito --set-api-key sk-xxx --provider openai             # Store OpenAI API key
  janito --set-api-key sk-xxx                               # Store key for the configured provider
  janito --list-keys                                        # Show configured providers
  janito --show-providers                                   # List all providers and variants
  janito --list-models                                      # List models for the configured provider
  janito --list-models --provider openai                    # List models for a specific provider
  janito --list-tools                                       # List available built-in tools
  janito --list-mcp                                         # List MCP services and tools
  janito --info                                             # Show resolved config info
  janito --show-config                                      # Show configured provider and model
  janito --show-system-prompt                               # Show the resolved system prompt
  janito --log=info,debug "Your prompt"                     # Enable logging
  janito --model gpt-5.6-luna "Your prompt"               # Use specific model
  janito --effort xhigh "Your prompt"               # Set reasoning depth
  janito --api-type Completions "Your prompt"                # Force the Chat Completions API
  janito --set model=gpt-5.6-luna                         # Set model for the active provider
  janito --provider openai --set model=gpt-5.6-luna       # Set model for a specific provider
  janito --set api-type=completions                         # Force the Chat Completions API
  janito --set api-type=responses                           # Use the Responses API
  janito --unset model                                      # Remove config value
  janito --get model                                        # Get config value
  janito --set-secret mykey=myvalue                        # Store a secret
  janito --get-secret mykey                                # Retrieve a secret
  janito --list-secrets                                    # List all secrets
  janito --delete-secret mykey                             # Delete a secret
  janito --config                                           # Interactive configuration setup
  janito -c ~/myconf --set provider=openai                 # Use a custom config dir for all config
  janito -l --set model=gpt-5.6-luna                      # Store config in ./.janito (project-local)
  janito -l --set-api-key sk-xxx --provider openai         # Store API key in ./.janito
  janito -l --list-keys                                    # Show global and local keys
  janito --provider custom --set endpoint=https://api.example.com/v1  # Use custom provider (set endpoint in config)
  janito --no-history                                          # Interactive chat without file history
  janito -t                                                    # Enable thinking mode
  janito -r -w                                                   # Grant READ and WRITE privileges
  janito -r -w -x                                                # Grant READ, WRITE, and EXEC privileges
  janito --set privileges=rwx                                    # Default privileges for every session

  Defaults to READ-only when no -r/-w/-x flag is given. The 'privileges'
  config default (--set privileges=rwx) applies when no flag is given;
  explicit -r/-w/-x flags always take priority. In the interactive shell,
  /rwx switches the session to full privileges.
  janito -S "You are a cow"                                   # Override system prompt (tools stay enabled)
  janito --no-tools "Your prompt"                             # No tools loaded (all tool surfaces disabled)
  janito --no-tasks "Your prompt"                             # No tasks tools (other tools stay enabled)
  janito --no-plugins "Your prompt"                           # Do not autoload plugins from ~/.janito/plugins
  janito --install-skill https://github.com/user/repo/tree/main/skills/git-commit  # Install a skill
  janito --list-skills                                        # List installed skills
  janito --uninstall-skill git-commit                         # Uninstall a skill
  janito --install-plugin https://github.com/user/janito-codesearch-plugin  # Install a plugin
  janito --uninstall-plugin codesearch                  # Uninstall an installed plugin by name
  janito --plugin ../plugins/janito-codesearch-plugin  # Load the codesearch plugin (tools, /codesearch)
  janito --list-plugins                                     # List loaded plugins and their on_start errors
  janito --create-variant alibaba-tokenplan                  # Register a provider variant (<provider>-<word>)
  janito --provider alibaba-tokenplan --set model=qwen3.8-flash  # Configure the variant (per-variant model)
  janito --set-api-key sk-xxx --provider alibaba-tokenplan   # Store an API key for the variant
  janito --set provider=alibaba-tokenplan                    # Use the variant as the default provider
  janito --delete-variant alibaba-tokenplan                  # Delete the variant and its config/API key

Note: --set and --set-api-key must be used in separate commands.
  The 'model' key is stored per-provider (e.g. "openai.model"); the provider is
  taken from --provider or the configured 'provider' value.
  Example:
    janito --set provider=openai                              # Step 1: Set provider
    janito --set model=gpt-5.6-luna                            # Step 2: Set model (stored as openai.model)
    janito --set-api-key sk-xxx --provider openai             # Step 3: Store API key
        """,
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        help="The prompt to send to the AI (if not provided, starts interactive chat)",
    )

    parser.add_argument(
        "-c",
        "--config-dir",
        metavar="DIR",
        help="Directory for all janito config (config, auth, secrets, MCP, skills). " "Defaults to ~/.janito",
    )

    parser.add_argument(
        "-l",
        "--local",
        action="store_true",
        help="Use the project-local config directory ./.janito (in the current "
        "working directory) for --set, --set-api-key, --set-secret, etc. "
        "instead of ~/.janito. Reads resolve local values first and fall back "
        "to the global ~/.janito; list operations show both.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output: model/backend/MCP info plus the API call "
        "parameters (messages shown as tail only) and a response summary",
    )

    parser.add_argument(
        "--log",
        metavar="LEVELS",
        help="Enable logging (e.g., --log=info,debug or --log=warning,error)",
    )

    parser.add_argument(
        "--info",
        action="store_true",
        help="Print resolved configuration (provider, model, API key) and exit",
    )

    parser.add_argument(
        "-Z",
        "--no-system-prompt",
        action="store_true",
        help="Do not set a system prompt (send user prompt directly)",
    )

    parser.add_argument(
        "-S",
        "--system-prompt",
        metavar="PROMPT",
        help="Override the system prompt (tools stay enabled)",
    )

    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Do not load tools (disables built-in, skill, plugin, MCP and server-side tools)",
    )

    parser.add_argument(
        "--no-tasks",
        action="store_true",
        help="Do not load the tasks toolset (StartTask, StopTask, "
        "WaitForTask, ListTasks). All other tools stay enabled.",
    )

    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Do not autoload plugins from ~/.janito/plugins (plugins "
        "explicitly loaded with --plugin DIR are still loaded)",
    )

    parser.add_argument(
        "-t",
        "--thinking",
        action="store_true",
        help="Enable thinking mode (sends extra_body={'enable_thinking': True} "
        "to the API). DeepSeek, Alibaba/Qwen and MiniMax-M3 have thinking "
        "enabled by default. Gemini-flavored providers (google) do not accept "
        "this flag; use --effort to control their thinking depth.",
    )

    parser.add_argument(
        "-e",
        "--effort",
        metavar="LEVEL",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        help="Reasoning depth for the API call (sends reasoning_effort=<LEVEL>). "
        "Overrides the provider's configured value and built-in default "
        "(e.g. qwen3.8-max defaults to 'low'). "
        "Examples: low, medium, high, xhigh",
    )

    parser.add_argument(
        "--api-type",
        metavar="TYPE",
        choices=["Responses", "Completions", "Anthropic", "DashScope", "Gemini"],
        help="API type to use for the provider: 'Responses' (the Responses "
        "API, server-side conversation state), 'Completions' (the Chat "
        "Completions API), 'Anthropic' (the native Anthropic SDK, only for "
        "providers that declare it and when the optional 'anthropic' package "
        "is installed), 'DashScope' (the native DashScope SDK, only for "
        "the alibaba provider and when the optional 'dashscope' package is "
        "installed) or 'Gemini' (the native Gemini SDK, only for the google "
        "provider and when the optional 'google-genai' package is "
        "installed). Overrides the provider's configured value "
        "(--set api-type=...) and built-in default (the model's "
        "default_api_type entry, e.g. 'Responses' for OpenAI).",
    )

    parser.add_argument(
        "-r",
        "--read",
        action="store_true",
        help="Grant READ privilege (the default when no -r/-w/-x flag is given)",
    )

    parser.add_argument("-w", "--write", action="store_true", help="Grant WRITE privilege")

    parser.add_argument("-x", "--exec", action="store_true", help="Grant EXEC privilege")

    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all available built-in tools and exit",
    )

    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all config-available models for the active provider "
        "(--provider, or the provider defined in config.json) and exit",
    )

    parser.add_argument("--list-mcp", action="store_true", help="List all MCP services and their tools")

    parser.add_argument(
        "--set-api-key",
        metavar="KEY",
        help="Set API key for a provider (uses --provider, or the configured " "default provider when omitted)",
    )

    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite an existing API key without prompting (used with --set-api-key)",
    )

    parser.add_argument(
        "-m",
        "--model",
        metavar="NAME",
        help="Model name to use for completions (overrides the provider's configured model)",
    )

    parser.add_argument(
        "-p",
        "--provider",
        metavar="NAME",
        help="Provider name (e.g., openai, custom)",
    )

    parser.add_argument("--list-keys", action="store_true", help="List configured providers and keys")

    parser.add_argument(
        "--show-providers",
        action="store_true",
        help="List all supported providers and their built-in defaults, "
        "followed by the registered provider variants",
    )

    parser.add_argument(
        "--set",
        nargs="*",
        action="append",
        metavar="KEY=VALUE",
        help="Set one or more config key-value pairs in ~/.janito/config.json\n"
        "  The 'model' key is stored per-provider (e.g. openai.model); the\n"
        "  provider is taken from --provider or the configured 'provider'.\n"
        "  Examples:\n"
        "    janito --set model=gpt-5.6-luna endpoint=https://api.example.com/v1\n"
        "    janito --provider openai --set model=gpt-5.6-luna\n"
        "    janito --set api-type=completions   # or api-type=responses",
    )

    parser.add_argument(
        "--unset",
        nargs="*",
        action="append",
        metavar="KEY",
        help="Remove one or more config keys from ~/.janito/config.json\n"
        "  Examples:\n"
        "    janito --unset model provider\n"
        "    janito --unset model --unset provider",
    )

    parser.add_argument(
        "--get",
        nargs="*",
        action="append",
        metavar="KEY",
        help="Get one or more config values from ~/.janito/config.json\n"
        "  Examples:\n"
        "    janito --get model provider\n"
        "    janito --get model --get provider",
    )

    parser.add_argument(
        "--set-secret",
        nargs="*",
        action="append",
        metavar="KEY=VALUE",
        help="Set one or more secrets in ~/.janito/secrets.json\n"
        "  Examples:\n"
        "    janito --set-secret mykey=myvalue api_key=abc123\n"
        "    janito --set-secret mykey=myvalue --set-secret api_key=abc123",
    )

    parser.add_argument(
        "--get-secret",
        nargs="*",
        action="append",
        metavar="KEY",
        help="Get one or more secret values from ~/.janito/secrets.json\n"
        "  Examples:\n"
        "    janito --get-secret mykey api_key\n"
        "    janito --get-secret mykey --get-secret api_key",
    )

    parser.add_argument(
        "--delete-secret",
        nargs="*",
        action="append",
        metavar="KEY",
        help="Delete one or more secrets from ~/.janito/secrets.json\n"
        "  Examples:\n"
        "    janito --delete-secret mykey old_secret\n"
        "    janito --delete-secret mykey --delete-secret old_secret",
    )

    parser.add_argument("--list-secrets", action="store_true", help="List all configured secrets")

    parser.add_argument(
        "--config",
        action="store_true",
        help="Interactive configuration setup for provider, API key, and max output tokens",
    )

    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Don't persist input history to file (store only in memory). "
        "Also disables the conversation-session snapshot used by -C/--continue.",
    )

    parser.add_argument(
        "-C",
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Resume the last interactive conversation saved in the current "
        "working directory (./.janito/session.json). The session reuses its "
        "previous provider/model/API type, so the restored context stays "
        "valid. Only meaningful for interactive chat (no prompt argument).",
    )

    parser.add_argument(
        "--install-skill",
        metavar="URL",
        help="Install a skill from a GitHub URL (e.g., https://github.com/user/awesome-copilot/tree/main/skills/git-commit)",
    )

    parser.add_argument("--list-skills", action="store_true", help="List all installed skills")

    parser.add_argument("--uninstall-skill", metavar="NAME", help="Uninstall a skill by name")

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit",
    )

    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Display the currently configured provider and model from config files",
    )

    parser.add_argument(
        "--show-system-prompt",
        action="store_true",
        help="Display the resolved system prompt and exit",
    )

    parser.add_argument(
        "--plugin",
        metavar="DIR",
        action="append",
        help="Load a plugin package from DIR (repeatable; e.g. "
        "--plugin ../plugins/janito-codesearch-plugin). "
        "DIR is a Python package directory; "
        "its parent is temporarily added to sys.path so relative imports "
        "inside the plugin work. Plugin tools, commands and system-prompt "
        "sections are registered before the session starts.",
    )

    parser.add_argument(
        "--install-plugin",
        metavar="URL",
        help="Install a plugin from a GitHub URL (e.g., "
        "https://github.com/joaompinto/janito-codesearch-plugin). "
        "Downloads the repository's master zip and extracts it to "
        "~/.janito/plugins/<repo-name>.",
    )

    parser.add_argument(
        "--uninstall-plugin",
        metavar="NAME",
        help="Uninstall an installed plugin by its plugin name (the 'name' "
        "the plugin exports, as shown by --list-plugins; e.g. 'codesearch' "
        "for the janito-codesearch-plugin). Removes the plugin's directory "
        "from the plugins dir. Broken plugins that cannot be imported are "
        "matched by their directory name.",
    )

    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List loaded plugins (from --plugin and autoloaded from "
        "~/.janito/plugins) and their on_start errors, then exit",
    )

    parser.add_argument(
        "--create-variant",
        metavar="NAME",
        help="Create a provider variant '<provider>-<word>' (e.g. "
        "alibaba-tokenplan) and register it in config.json, so the variant "
        "name can be used as a provider (--provider, --set provider=, "
        "--set-api-key). The variant inherits its base provider's built-in "
        "defaults and keeps its own per-variant model/endpoint/API key.",
    )

    parser.add_argument(
        "--delete-variant",
        metavar="NAME",
        help="Delete a provider variant and its per-variant configuration "
        "(model, endpoint, API type, tokens, reasoning level, API key). "
        "Refuses to delete the configured default provider.",
    )

    # --- Web UI options ---
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start the web UI server instead of the terminal chat " "(alpha: interface and behavior may change)",
    )

    parser.add_argument(
        "--web-port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Port for the web server (default: 8080, used with --web)",
    )

    parser.add_argument(
        "--web-host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind address for the web server (default: 127.0.0.1, used with --web)",
    )

    parser.add_argument(
        "--no-web-open",
        action="store_true",
        help="Don't automatically open the browser (used with --web)",
    )

    parser.add_argument(
        "--web-session-ttl",
        type=int,
        default=0,
        metavar="SECONDS",
        help="Evict web sessions idle longer than SECONDS from memory "
        "(lazy TTL: dropped on access, transparently reloaded from "
        ".janito/sessions/ on demand; 0 disables TTL expiry \u2014 the "
        "default). Ignored with --no-history (nothing to reload from)",
    )

    return parser


def parse_args():
    """Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = create_parser()
    return parser.parse_args()
