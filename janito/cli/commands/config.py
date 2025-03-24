"""
Configuration management functions for Janito CLI.
"""
import sys
import os
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from janito.config import get_config, Config
from janito.cli.commands.workspace import handle_workspace
from janito.cli.commands.profile import handle_profile, handle_role
from janito.cli.commands.history import handle_history

console = Console()

def handle_reset_config(reset_config: bool, ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --reset-config parameter.
    
    Args:
        reset_config: Whether to reset the configuration
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if reset_config:
        try:
            config_path = Path(get_config().workspace_dir) / ".janito" / "config.json"
            if get_config().reset_config():
                console.print(f"[bold green]✅ Configuration file removed: {config_path}[/bold green]")
            else:
                console.print(f"[bold yellow]⚠️ Configuration file does not exist: {config_path}[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]Error removing configuration file:[/bold red] {str(e)}")
        
        # Exit after resetting config if no other operation is requested
        return ctx.invoked_subcommand is None and not query
    
    return False

def handle_show_config(show_config: bool, ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --show-config parameter.
    
    Args:
        show_config: Whether to show the configuration
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if show_config:
        config = get_config()
        console.print("[bold blue]⚙️  Current Configuration:[/bold blue]")
        console.print(f"[bold]📁 Local Configuration File:[/bold] .janito/config.json")
        console.print(f"[bold]🏠 Global Configuration File:[/bold] {Path.home() / '.janito' / 'config.json'}")
        
        # Show API key status
        api_key_global = Config.get_api_key()
        api_key_env = os.environ.get("ANTHROPIC_API_KEY")
        if api_key_global:
            console.print(f"[bold]🔑 API Key:[/bold] [green]Set in global config[/green]")
        elif api_key_env:
            console.print(f"[bold]🔑 API Key:[/bold] [yellow]Set in environment variable[/yellow]")
        else:
            console.print(f"[bold]🔑 API Key:[/bold] [red]Not set[/red]")
            
        console.print(f"[bold]🔊 Verbose Mode:[/bold] {'Enabled' if config.verbose else 'Disabled'}")
        console.print(f"[bold]❓ Ask Mode:[/bold] {'Enabled' if config.ask_mode else 'Disabled'}")

        console.print(f"[bold]👤 Role:[/bold] {config.role}")
        
        # Show profile information if one is set
        if config.profile:
            profile_data = config.get_available_profiles()[config.profile]
            console.print(f"[bold]📋 Active Profile:[/bold] {config.profile} - {profile_data['description']}")
        
        # Show available profiles
        profiles = config.get_available_profiles()
        if profiles:
            console.print("\n[bold blue]📋 Available Parameter Profiles:[/bold blue]")
            for name, data in profiles.items():
                console.print(f"[bold]🔹 {name}[/bold] - {data['description']}")
            
        # Exit if this was the only operation requested
        return ctx.invoked_subcommand is None and not query
    
    return False

def handle_set_api_key(set_api_key: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --set-api-key parameter.
    
    Args:
        set_api_key: API key
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if set_api_key is not None:
        try:
            Config.set_api_key(set_api_key)
            console.print(f"[bold green]✅ API key saved to global configuration[/bold green]")
            console.print(f"[dim]📁 Location: {Path.home() / '.janito' / 'config.json'}[/dim]")
            
            # Exit after setting API key if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False

def handle_set_config(config_str: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --set-config parameter.
    
    Args:
        config_str: Configuration string in format 'key=value'
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if config_str is not None:
        try:
            # Parse the config string
            config_parts = config_str.split("=", 1)
            if len(config_parts) != 2:
                console.print(f"[bold red]Error:[/bold red] Invalid configuration format. Use 'key=value' format.")
                return ctx.invoked_subcommand is None and not query
                
            key = config_parts[0].strip()
            value = config_parts[1].strip()
            
            # Remove quotes if present
            if (value.startswith("'") and value.endswith("'")) or \
               (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
                
            if key == "profile":
                try:
                    get_config().set_profile(value)
                    profile_data = get_config().get_available_profiles()[value.lower()]
                    console.print(f"[bold green]✅ Profile set to '{value.lower()}'[/bold green]")
                    console.print(f"[dim]📝 Description: {profile_data['description']}[/dim]")
                except ValueError as e:
                    console.print(f"[bold red]Error:[/bold red] {str(e)}")
            elif key == "temperature":
                try:
                    temp_value = float(value)
                    if temp_value < 0.0 or temp_value > 1.0:
                        console.print("[bold red]Error:[/bold red] Temperature must be between 0.0 and 1.0")
                        return ctx.invoked_subcommand is None and not query
                    
                    get_config().temperature = temp_value
                    console.print(f"[bold green]✅ Temperature set to {temp_value} and saved to configuration[/bold green]")
                except ValueError:
                    console.print(f"[bold red]Error:[/bold red] Invalid temperature value: {value}. Must be a float between 0.0 and 1.0.")
            # top_k and top_p are now only accessible through profiles
            elif key == "role":
                get_config().role = value
                console.print(f"[bold green]✅ Role set to '{value}' and saved to configuration[/bold green]")
            else:
                console.print(f"[bold yellow]Warning:[/bold yellow] Unsupported configuration key: {key}")
            
            # Exit after applying config changes if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            
    return False

def handle_config_commands(
    ctx: typer.Context,
    reset_config: bool,
    workspace: Optional[str],
    show_config: bool,
    profile: Optional[str],
    role: Optional[str],
    set_api_key: Optional[str],
    config_str: Optional[str],
    query: Optional[str],
    continue_id: Optional[str] = None,
    continue_flag: Optional[str] = None,
    history_flag: bool = False,
    history_count: Optional[int] = None
) -> bool:
    """
    Handle all configuration-related commands.
    
    Args:
        ctx: Typer context
        reset_config: Whether to reset the configuration
        workspace: Workspace directory path
        show_config: Whether to show the configuration
        profile: Profile name
        role: Role name
        set_api_key: API key
        config_str: Configuration string in format 'key=value'
        query: Query string
        continue_id: Optional message ID to continue a specific conversation
        continue_flag: Optional string that can be empty (flag only) or contain a chat ID
        history_flag: Whether to show conversation history (--history flag)
        history_count: Number of history entries to display (value after --history)
        
    Returns:
        bool: True if the program should exit after these operations
    """
    # Handle each command and check if we should exit after it
    if handle_reset_config(reset_config, ctx, query):
        return True
        
    handle_workspace(workspace)
    
    if handle_show_config(show_config, ctx, query):
        return True
        
    if handle_profile(profile, ctx, query):
        return True
        
    if handle_role(role, ctx, query):
        return True
        
    if handle_set_api_key(set_api_key, ctx, query):
        return True
        
    if handle_set_config(config_str, ctx, query):
        return True
    
    if handle_history(history_flag, history_count, ctx, query):
        return True
        
    return False