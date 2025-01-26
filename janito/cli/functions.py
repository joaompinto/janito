import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from janito.shell.user_prompt import prompt_user
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text

console = Console()

from janito.config import config


def get_change_history_path() -> Path:
    """Create and return the changes history directory path"""
    changes_history_dir = config.workspace_dir / '.janito' / 'change_history'
    changes_history_dir.mkdir(parents=True, exist_ok=True)
    return changes_history_dir

def get_timestamp() -> str:
    """Get current UTC timestamp in YMD_HMS format with leading zeros"""
    return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

def save_prompt_to_file(prompt: str) -> Path:
    """Save prompt to a named temporary file that won't be deleted"""
    temp_file = tempfile.NamedTemporaryFile(prefix='selected_', suffix='.txt', delete=False)
    temp_path = Path(temp_file.name)
    temp_path.write_text(prompt, encoding='utf-8')
    return temp_path

def save_to_file(content: str, prefix: str) -> Path:
    """Save content to a timestamped file in changes history directory"""
    changes_history_dir = get_change_history_path()
    timestamp = get_timestamp()
    filename = f"{timestamp}_{prefix}.txt"
    file_path = changes_history_dir / filename
    file_path.write_text(content)
    return file_path

def modify_request(request: str) -> str:
    """Display current request and get modified version with improved formatting"""
    console = Console()
    
    # Display current request in a panel with clear formatting
    console.print("\n[bold cyan]Current Request:[/bold cyan]")
    console.print(Panel(
        Text(request, style="white"),
        border_style="blue",
        title="Previous Request",
        padding=(1, 2)
    ))
    
    # Get modified request with clear prompt
    console.print("\n[bold cyan]Enter modified request below:[/bold cyan]")
    console.print("[dim](Press Enter to submit, Ctrl+C to cancel)[/dim]")
    try:
        new_request = prompt_user("Modified request")
        if not new_request.strip():
            console.print("[yellow]No changes made, keeping original request[/yellow]")
            return request
        return new_request
    except KeyboardInterrupt:
        console.print("\n[yellow]Modification cancelled, keeping original request[/yellow]")
        return request
