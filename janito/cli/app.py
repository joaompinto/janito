"""
Main CLI application for Janito.
"""
import sys
from typing import Optional
import typer
from rich.console import Console
import importlib.metadata

from janito import __version__
from janito.config import Config
from janito.cli.commands import handle_config_commands, validate_parameters
from janito.cli.agent import handle_query
from janito.cli.utils import get_stdin_termination_hint

app = typer.Typer()
console = Console()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, 
         query: Optional[str] = typer.Argument(None, help="Query to send to the claudine agent"),
         verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose mode with detailed output"),
         show_tokens: bool = typer.Option(False, "--show-tokens", "--tokens", help="Show detailed token usage and pricing information"),
         workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Set the workspace directory"),
         set_local_config: Optional[str] = typer.Option(None, "--set-local-config", help="Set a local configuration value in format 'key=value' (overrides global config)"),
         set_global_config: Optional[str] = typer.Option(None, "--set-global-config", help="Set a global configuration value in format 'key=value' (used as default)"),
         show_config: bool = typer.Option(False, "--show-config", help="Show current configuration"),
         reset_local_config: bool = typer.Option(False, "--reset-local-config", help="Reset local configuration by removing the local config file"),
         reset_global_config: bool = typer.Option(False, "--reset-global-config", help="Reset global configuration by removing the global config file"),
         set_api_key: Optional[str] = typer.Option(None, "--set-api-key", help="Set the Anthropic API key globally in the user's home directory"),
         ask: bool = typer.Option(False, "--ask", help="Enable ask mode which disables tools that perform changes"),
         trust: bool = typer.Option(False, "--trust", "-t", help="Enable trust mode which suppresses tool outputs for a more concise execution"),
         no_tools: bool = typer.Option(False, "--no-tools", help="Disable all tools for this session (per-session setting, not saved to config)"),
         temperature: float = typer.Option(0.0, "--temperature", help="Set the temperature for model generation (0.0 to 1.0)"),
         profile: Optional[str] = typer.Option(None, "--profile", help="Use a predefined parameter profile (precise, balanced, conversational, creative, technical)"),
         role: Optional[str] = typer.Option(None, "--role", help="Set the assistant's role (default: 'software engineer')"),
         system: Optional[str] = typer.Option(None, "--system", "-s", help="Provide custom system instructions, bypassing the default file load method"),
         version: bool = typer.Option(False, "--version", help="Show the version and exit"),
         continue_flag: Optional[str] = typer.Option(None, "--continue", "-c", help="Continue a conversation. Can be used as: 1) --continue (to continue most recent), 2) --continue 123 (to continue conversation with ID 123), or 3) --continue \"query\" (to continue most recent with new query)"),
         history_flag: bool = typer.Option(False, "--history", help="Show a summary of conversations. Use --history for default (20) or --history n to specify count")):
    """
    Janito CLI tool. If a query is provided without a command, it will be sent to the claudine agent.
    """    
    # Set verbose mode in config
    Config().verbose = verbose
    
    # Set ask mode in config
    Config().ask_mode = ask
    
    # Set trust mode in config
    Config().trust_mode = trust
    
    # Set no-tools mode in config
    Config().no_tools = no_tools
    
    # Show a message if ask mode is enabled
    if ask:
        console.print("[bold yellow]⚠️ Ask Mode enabled:[/bold yellow] 🔒 Tools that perform changes are disabled")
        
    # Show a message if trust mode is enabled
    if trust:
        console.print("[bold blue]⚡ Trust Mode enabled:[/bold blue] Tool outputs are suppressed for concise execution")
        
    # Show a message if no-tools mode is enabled
    if no_tools:
        console.print("[bold magenta]🚫 No-Tools Mode enabled:[/bold magenta] All tools are disabled for this session")
    
    # Show version and exit if requested
    if version:
        console.print(f"🚀 Janito version: {__version__}")
        sys.exit(0)
    
    # Validate temperature
    validate_parameters(temperature)
    
    # Process continue flags before handling other options
    continue_conversation = None
    
    # First, parse continue_flag and continue_id from original sys.argv to avoid typer issues
    # This is necessary because typer has trouble with quotes in some edge cases
    try:
        # Check if --continue or -c is in sys.argv
        args = sys.argv
        
        # Handle the --history flag with optional count parameter
        history_count_override = None
        if "--history" in args:
            history_idx = args.index("--history")
            history_flag = True
            
            # Check if there's a number after --history and it's not another flag
            if history_idx + 1 < len(args) and not args[history_idx + 1].startswith("-"):
                try:
                    # Try to convert to int - if successful, it's a count
                    history_count_override = int(args[history_idx + 1])
                except ValueError:
                    # Not a number, ignore it
                    pass
        
        if "--continue" in args or "-c" in args:
            continue_idx = args.index("--continue") if "--continue" in args else args.index("-c")
            
            # Check if there's at least one argument after --continue
            if continue_idx + 1 < len(args) and not args[continue_idx + 1].startswith("-"):
                # If next arg doesn't start with "-", it's our continue value
                continue_value = args[continue_idx + 1]
                
                # Check if continue_value is a numeric ID or a query
                if continue_value.isdigit():
                    # It's an ID
                    continue_conversation = continue_value
                    
                    # Check if there's a query after the ID
                    if continue_idx + 2 < len(args) and not args[continue_idx + 2].startswith("-"):
                        query = args[continue_idx + 2]
                else:
                    # It's a query string for the most recent conversation
                    continue_conversation = ""  # Empty string means continue most recent
                    query = continue_value
                    
                    if verbose:
                        console.print(f"[bold blue]🔄 Continuing most recent conversation[/bold blue]")
                        console.print(f"[dim]📝 Query: {query}[/dim]")
            else:
                # --continue with no args means continue most recent conversation
                continue_conversation = ""
        
        # --continue-id has been removed in favor of --continue
    except Exception as e:
        if verbose:
            console.print(f"[bold yellow]⚠️ Error parsing continue arguments: {str(e)}[/bold yellow]")
    
    # Fall back to typer-processed args if our parsing failed
    if continue_conversation is None:
        # Handle the --continue flag option (processed by typer)
        if continue_flag is not None:
            if continue_flag == "":
                continue_conversation = ""  # Empty string means continue most recent
            elif continue_flag.isdigit():
                continue_conversation = continue_flag
            else:
                continue_conversation = ""  # Empty string means continue most recent
                query = continue_flag  # Use the continue_flag as the query
    
    # Handle configuration-related commands
    exit_after_config = handle_config_commands(
        ctx, 
        False,  # reset_config is removed, passing False for backward compatibility
        reset_local_config,
        reset_global_config,
        workspace, 
        show_config, 
        profile, 
        role, 
        set_api_key,
        set_local_config,
        set_global_config,
        query,
        continue_flag,
        history_flag,
        history_count_override
    )
    
    if exit_after_config:
        sys.exit(0)
    
    # Handle query if no subcommand was invoked
    if ctx.invoked_subcommand is None:
        # If no query provided in command line, read from stdin
        # Only prompt for stdin if query is still None after processing --continue flag
        if not query:
            console.print("[bold blue]📝 No query provided in command line. Reading from stdin...[/bold blue]")
            console.print(get_stdin_termination_hint())
            query = sys.stdin.read().strip()
            
        # Only proceed if we have a query (either from command line or stdin)
        if query:
            handle_query(query, temperature, verbose, show_tokens, continue_conversation, system)