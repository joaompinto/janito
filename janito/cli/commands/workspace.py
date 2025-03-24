"""
Workspace management functions for Janito CLI.
"""
import sys
from typing import Optional
from rich.console import Console

from janito.config import get_config

console = Console()

def handle_workspace(workspace: Optional[str]) -> bool:
    """
    Handle the --workspace parameter.
    
    Args:
        workspace: Workspace directory path
        
    Returns:
        bool: True if the program should exit after this operation
    """
    if workspace:
        try:
            console.print(f"[bold]📂 Setting workspace directory to: {workspace}[/bold]")
            get_config().workspace_dir = workspace
            console.print(f"[bold green]✅ Workspace directory set to: {get_config().workspace_dir}[/bold green]")
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
            sys.exit(1)
    
    return False