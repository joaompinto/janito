"""
Profile and role management functions for Janito CLI.
"""
import sys
from typing import Optional
import typer
from rich.console import Console

from janito.config import get_config

console = Console()

def handle_profile(profile: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --profile parameter.
    
    Args:
        profile: Profile name
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if profile is not None:
        try:
            # Apply profile without saving to config
            config = get_config()
            profile_data = config.get_available_profiles()[profile.lower()]
            
            # Set values directly without saving
            config._temperature = profile_data["temperature"]
            config._profile = profile.lower()
            
            console.print(f"[bold green]✅ Profile '{profile.lower()}' applied for this session only[/bold green]")
            console.print(f"[dim]📝 Description: {profile_data['description']}[/dim]")
            
            # Exit after applying profile if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False

def handle_role(role: Optional[str], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --role parameter.
    
    Args:
        role: Role name
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if role is not None:
        try:
            # Set role directly without saving to config
            config = get_config()
            config._role = role
            
            console.print(f"[bold green]✅ Role '{role}' applied for this session only[/bold green]")
            
            # Exit after applying role if no other operation is requested
            return ctx.invoked_subcommand is None and not query
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False