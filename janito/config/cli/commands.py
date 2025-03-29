"""
Command handling functions for configuration-related CLI commands.
"""
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import typer
from rich.console import Console

from ..core.singleton import Config
from .validators import validate_temperature, validate_boolean_value, validate_config_key_value

console = Console()

def handle_reset_config(reset_config: bool, ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --reset-config parameter (deprecated, kept for backward compatibility).
    This function now does nothing as --reset-config has been replaced by --reset-local-config and --reset-global-config.
    
    Args:
        reset_config: Whether to reset the configuration (ignored)
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: Always returns False
    """
    # This function is kept for backward compatibility but does nothing
    # Users should use --reset-local-config or --reset-global-config instead
    return False

def handle_reset_local_config(reset_local_config: bool, ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --reset-local-config parameter.
    This removes the local configuration file (.janito/config.json) in the current workspace.
    
    Args:
        reset_local_config: Whether to reset the local configuration
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if reset_local_config:
        try:
            config_path = Path(Config().workspace_dir) / ".janito" / "config.json"
            if Config().reset_local_config():
                console.print(f"[bold green]✅ Local configuration file removed: {config_path}[/bold green]")
            else:
                console.print(f"[bold yellow]⚠️ Local configuration file does not exist: {config_path}[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]Error removing configuration file:[/bold red] {str(e)}")
        
        # Exit after resetting config if no other operation is requested
        return ctx.invoked_subcommand is None and not query
    
    return False

def handle_reset_global_config(reset_global_config: bool, ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --reset-global-config parameter.
    This removes the global configuration file (~/.janito/config.json) in the user's home directory.
    
    Args:
        reset_global_config: Whether to reset the global configuration
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if reset_global_config:
        try:
            config_path = Path.home() / ".janito" / "config.json"
            if Config().reset_global_config():
                console.print(f"[bold green]✅ Global configuration file removed: {config_path}[/bold green]")
            else:
                console.print(f"[bold yellow]⚠️ Global configuration file does not exist: {config_path}[/bold yellow]")
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
        config = Config()
        console.print("[bold blue]⚙️  Current Configuration:[/bold blue]")
        
        # Show configuration file paths
        local_config_path = Path(config.workspace_dir) / ".janito" / "config.json"
        global_config_path = Path.home() / ".janito" / "config.json"
        console.print(f"[bold]📁 Local Configuration File:[/bold] {local_config_path}")
        console.print(f"[bold]🏠 Global Configuration File:[/bold] {global_config_path}")
        
        # Show API key status
        api_key_global = Config().get_api_key()
        api_key_env = os.environ.get("ANTHROPIC_API_KEY")
        if api_key_global:
            console.print(f"[bold]🔑 API Key:[/bold] [green]Set in global config[/green]")
        elif api_key_env:
            console.print(f"[bold]🔑 API Key:[/bold] [yellow]Set in environment variable[/yellow]")
        else:
            console.print(f"[bold]🔑 API Key:[/bold] [red]Not set[/red]")
        
        # Show merged configuration (effective settings)
        console.print("\n[bold blue]🔄 Merged Configuration (Effective Settings):[/bold blue]")
        console.print(f"[bold]🔊 Verbose Mode:[/bold] {'Enabled' if config.verbose else 'Disabled'}")
        console.print(f"[bold]❓ Ask Mode:[/bold] {'Enabled' if config.ask_mode else 'Disabled'}")
        console.print(f"[bold]👤 Role:[/bold] {config.role}")
        console.print(f"[bold]🌡️ Temperature:[/bold] {config.temperature}")
        
        # Show profile information if one is set
        if config.profile:
            profile_data = config.get_available_profiles()[config.profile]
            console.print(f"[bold]📋 Active Profile:[/bold] {config.profile} - {profile_data['description']}")
        
        # Show local configuration
        local_config = config.get_local_config()
        if local_config:
            console.print("\n[bold blue]📁 Local Configuration:[/bold blue]")
            for key, value in local_config.items():
                if key != "api_key":  # Don't show API key
                    console.print(f"[bold]🔹 {key}:[/bold] {value}")
        else:
            console.print("\n[bold blue]📁 Local Configuration:[/bold blue] [dim]Empty[/dim]")
        
        # Show global configuration
        global_config = config.get_global_config()
        if global_config:
            console.print("\n[bold blue]🏠 Global Configuration:[/bold blue]")
            for key, value in global_config.items():
                if key != "api_key":  # Don't show API key
                    console.print(f"[bold]🔹 {key}:[/bold] {value}")
        else:
            console.print("\n[bold blue]🏠 Global Configuration:[/bold blue] [dim]Empty[/dim]")
        
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
            Config().set_api_key(set_api_key)
            console.print(f"[bold green]✅ API key saved to global configuration[/bold green]")
            console.print(f"[dim]📁 Location: {Path.home() / '.janito' / 'config.json'}[/dim]")
            
            # Exit after setting API key if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False

def _handle_config_setting(key: str, value: str, config_type: str = "local") -> bool:
    """
    Handle setting a configuration value.
    
    Args:
        key: Configuration key
        value: Configuration value
        config_type: Type of configuration to update ("local" or "global")
        
    Returns:
        bool: True if the operation was successful
    """
    try:
        if key == "profile":
            try:
                Config().set_profile(value, config_type)
                profile_data = Config().get_available_profiles()[value.lower()]
                console.print(f"[bold green]✅ Profile set to '{value.lower()}' in {config_type} configuration[/bold green]")
                console.print(f"[dim]📝 Description: {profile_data['description']}[/dim]")
                return True
            except ValueError as e:
                console.print(f"[bold red]Error:[/bold red] {str(e)}")
                return False
        elif key == "temperature":
            is_valid, result = validate_temperature(value)
            if not is_valid:
                console.print(f"[bold red]Error:[/bold red] {result}")
                return False
            
            if config_type == "local":
                Config().temperature = result, "local"
            else:
                Config().temperature = result, "global"
            console.print(f"[bold green]✅ Temperature set to {result} in {config_type} configuration[/bold green]")
            return True
        # top_k and top_p are now only accessible through profiles
        elif key == "role":
            if config_type == "local":
                Config().role = value, "local"
            else:
                Config().role = value, "global"
            console.print(f"[bold green]✅ Role set to '{value}' in {config_type} configuration[/bold green]")
            return True
        elif key == "ask_mode":
            is_valid, result = validate_boolean_value(value)
            if not is_valid:
                console.print(f"[bold red]Error:[/bold red] {result}")
                return False
            
            if config_type == "local":
                Config().ask_mode = result, "local"
            else:
                Config().ask_mode = result, "global"
            console.print(f"[bold green]✅ Ask mode set to {result} in {config_type} configuration[/bold green]")
            return True
        else:
            # For other keys, set them directly in the configuration
            if config_type == "local":
                Config().set_local_config(key, value)
            else:
                Config().set_global_config(key, value)
            console.print(f"[bold green]✅ {key} set to '{value}' in {config_type} configuration[/bold green]")
            return True
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return False


def handle_set_local_config(config_str: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --set-local-config parameter.
    
    Args:
        config_str: Configuration string in format 'key=value'
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if config_str is not None:
        is_valid, result = validate_config_key_value(config_str)
        if not is_valid:
            console.print(f"[bold red]Error:[/bold red] {result}")
            return ctx.invoked_subcommand is None and not query
        
        key, value = result
        _handle_config_setting(key, value, "local")
        
        # Exit after applying config changes if no other operation is requested
        return ctx.invoked_subcommand is None and not query
    
    return False

def handle_set_global_config(config_str: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --set-global-config parameter.
    
    Args:
        config_str: Configuration string in format 'key=value'
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if config_str is not None:
        is_valid, result = validate_config_key_value(config_str)
        if not is_valid:
            console.print(f"[bold red]Error:[/bold red] {result}")
            return ctx.invoked_subcommand is None and not query
        
        key, value = result
        _handle_config_setting(key, value, "global")
        
        # Exit after applying config changes if no other operation is requested
        return ctx.invoked_subcommand is None and not query
    
    return False

def handle_config_commands(
    ctx: typer.Context,
    reset_config: bool,
    reset_local_config: bool = False,
    reset_global_config: bool = False,
    workspace: Optional[str] = None,
    show_config: bool = False,
    profile: Optional[str] = None,
    role: Optional[str] = None,
    set_api_key: Optional[str] = None,
    set_local_config: Optional[str] = None,
    set_global_config: Optional[str] = None,
    query: Optional[str] = None,
    continue_flag: Optional[str] = None,
    history_flag: bool = False,
    history_count: Optional[int] = None
) -> bool:
    """
    Handle all configuration-related commands.
    
    Args:
        ctx: Typer context
        reset_config: Deprecated parameter kept for backward compatibility
        reset_local_config: Whether to reset the local configuration
        reset_global_config: Whether to reset the global configuration
        workspace: Workspace directory path
        show_config: Whether to show the configuration
        profile: Profile name
        role: Role name
        set_api_key: API key
        set_local_config: Configuration string in format 'key=value' for local config
        set_global_config: Configuration string in format 'key=value' for global config
        query: Query string
        continue_flag: Optional string that can be empty (flag only) or contain a chat ID
        history_flag: Whether to show conversation history (--history flag)
        history_count: Number of history entries to display (value after --history)
        
    Returns:
        bool: True if the program should exit after these operations
    """
    # Import these here to avoid circular imports
    from janito.cli.commands.workspace import handle_workspace
    from janito.cli.commands.profile import handle_profile, handle_role
    from janito.cli.commands.history import handle_history
    
    # Handle each command and check if we should exit after it
    if handle_reset_config(reset_config, ctx, query):
        return True
    
    if handle_reset_local_config(reset_local_config, ctx, query):
        return True
    
    if handle_reset_global_config(reset_global_config, ctx, query):
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
    
    if handle_set_local_config(set_local_config, ctx, query):
        return True
    
    if handle_set_global_config(set_global_config, ctx, query):
        return True
    
    if handle_history(history_flag, history_count, ctx, query):
        return True
        
    return False