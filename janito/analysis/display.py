"""Display formatting for analysis results."""

from typing import Optional, Dict
from pathlib import Path
from datetime import datetime, timezone
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.columns import Columns
from rich.rule import Rule
from janito.claude import ClaudeAPIAgent
from .options import AnalysisOption

MIN_PANEL_WIDTH = 40

def _display_options(options: Dict[str, AnalysisOption]) -> None:
    """Display available options in a single horizontal row with equal widths."""
    console = Console()
    
    console.print()
    console.print(Rule(" Available Options ", style="bold cyan", align="center"))
    console.print()
    
    term_width = console.width or 100
    spacing = 4
    total_spacing = spacing * (len(options) - 1)
    panel_width = max(MIN_PANEL_WIDTH, (term_width - total_spacing) // len(options))
    
    panels = []
    for letter, option in options.items():
        content = Text()
        
        content.append("Description:\n", style="bold cyan")
        for item in option.description_items:
            content.append(f"• {item}\n", style="white")
        content.append("\n")
        
        if option.affected_files:
            content.append("Affected files:\n", style="bold cyan")
            unique_files = {}
            for file in option.affected_files:
                clean_path = option.get_clean_path(file)
                unique_files[clean_path] = file
                
            for file in unique_files.values():
                if '(new)' in file:
                    color = "green"
                elif '(removed)' in file:
                    color = "red"
                else:
                    color = "yellow"
                content.append(f"• {file}\n", style=color)

        panel = Panel(
            content,
            box=box.ROUNDED,
            border_style="cyan",
            title=f"Option {letter}: {option.summary}",
            title_align="center",
            padding=(1, 2),
            width=panel_width
        )
        panels.append(panel)
    
    if panels:
        columns = Columns(
            panels,
            align="center",
            expand=True,
            equal=True,
            padding=(0, spacing // 2)
        )
        console.print(columns)
        console.print()

def _display_markdown(content: str) -> None:
    """Display content in markdown format."""
    console = Console()
    md = Markdown(content)
    console.print(md)

def _display_raw_history(claude: ClaudeAPIAgent) -> None:
    """Display raw message history from Claude agent."""
    console = Console()
    console.print("\n=== Message History ===")
    for role, content in claude.messages_history:
        console.print(f"\n[bold cyan]{role.upper()}:[/bold cyan]")
        console.print(content)
    console.print("\n=== End Message History ===\n")

def format_analysis(analysis: str, raw: bool = False, claude: Optional[ClaudeAPIAgent] = None, workdir: Optional[Path] = None) -> None:
    """Format and display the analysis output with enhanced capabilities."""
    console = Console()
    
    if raw and claude:
        _display_raw_history(claude)
    else:
        from .options import parse_analysis_options
        options = parse_analysis_options(analysis)
        if options:
            _display_options(options)
        else:
            console.print("\n[yellow]Warning: No valid options found in response. Displaying as markdown.[/yellow]\n")
            _display_markdown(analysis)

def get_history_file_type(filepath: Path) -> str:
    """Determine the type of saved file based on its name"""
    name = filepath.name.lower()
    if 'changes' in name:
        return 'changes'
    elif 'selected' in name:
        return 'selected'
    elif 'analysis' in name:
        return 'analysis'
    elif 'response' in name:
        return 'response'
    return 'unknown'

def get_history_path(workdir: Path) -> Path:
    """Create and return the history directory path"""
    history_dir = workdir / '.janito' / 'history'
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir

def get_timestamp() -> str:
    """Get current UTC timestamp in YMD_HMS format with leading zeros"""
    return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

def save_to_file(content: str, prefix: str, workdir: Path) -> Path:
    """Save content to a timestamped file in history directory"""
    history_dir = get_history_path(workdir)
    timestamp = get_timestamp()
    filename = f"{timestamp}_{prefix}.txt"
    file_path = history_dir / filename
    file_path.write_text(content)
    return file_path
