"""
Profile and role management functions for Janito CLI.
"""
import sys
from typing import Optional
import typer
from rich.console import Console

from janito.config import Config

console = Console()

def handle_profile(profile: Optional[str], ctx: typer.Context, query: Optional[str], config_type: str = "session") -> bool:
    """
    Handle the --profile parameter.
    
    Args:
        profile: Profile name
        ctx: Typer context
        query: Query string
        config_type: Type of configuration to update ("session", "local", or "global")
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if profile is not None:
        try:
            # Apply profile
            config = Config()
            profile_data = config.get_available_profiles()[profile.lower()]
            
            if config_type == "session":
                # Set values directly without saving
                config._temperature = profile_data["temperature"]
                config._profile = profile.lower()
                console.print(f"[bold green]✅ Profile '{profile.lower()}' applied for this session only[/bold green]")
            elif config_type in ["local", "global"]:
                # Set profile in the specified configuration
                config.set_profile(profile.lower(), config_type)
                console.print(f"[bold green]✅ Profile '{profile.lower()}' set in {config_type} configuration[/bold green]")
            else:
                console.print(f"[bold red]Error:[/bold red] Invalid config_type: {config_type}")
                return ctx.invoked_subcommand is None and not query
            
            console.print(f"[dim]📝 Description: {profile_data['description']}[/dim]")
            
            # Exit after applying profile if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False

def handle_role(role: Optional[str], ctx: typer.Context, query: Optional[str], config_type: str = "session") -> bool:
    """
    Handle the --role parameter.
    
    Args:
        role: Role name
        ctx: Typer context
        query: Query string
        config_type: Type of configuration to update ("session", "local", or "global")
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if role is not None:
        try:
            config = Config()
            
            if config_type == "session":
                # Set role directly without saving
                config._role = role
                console.print(f"[bold green]✅ Role '{role}' applied for this session only[/bold green]")
            elif config_type in ["local", "global"]:
                # Set role in the specified configuration
                if config_type == "local":
                    config.role = role, "local"
                else:
                    config.role = role, "global"
                console.print(f"[bold green]✅ Role '{role}' set in {config_type} configuration[/bold green]")
            else:
                console.print(f"[bold red]Error:[/bold red] Invalid config_type: {config_type}")
                return ctx.invoked_subcommand is None and not query
            
            # Exit after applying role if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False