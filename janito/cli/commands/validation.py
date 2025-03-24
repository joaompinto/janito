"""
Parameter validation functions for Janito CLI.
"""
import sys
from rich.console import Console

console = Console()

def validate_parameters(temperature: float) -> None:
    """
    Validate temperature parameter.
    
    Args:
        temperature: Temperature value for model generation
    """
    try:
        if temperature < 0.0 or temperature > 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")
            
        # We'll use this value directly in the agent initialization but we don't save it to config
        # Temperature display is hidden
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        sys.exit(1)