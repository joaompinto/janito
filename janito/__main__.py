import typer
from typing import Optional, Dict, Any, List
from pathlib import Path
from janito.claude import ClaudeAPIAgent
from janito.prompts import (
    build_request_analisys_prompt,
    build_selected_option_prompt,
    SYSTEM_PROMPT
)
from rich.console import Console
from rich.markdown import Markdown
import re
import tempfile
import json
from rich.syntax import Syntax
from janito.contentchange import (
    handle_changes_file, 
    get_file_type,
    parse_block_changes
)
from rich.table import Table
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich import box
from datetime import datetime
from itertools import chain
from janito.scan import collect_files_content, is_dir_empty
from rich.prompt import Prompt

def format_analysis(analysis: str, raw: bool = False, claude: Optional[ClaudeAPIAgent] = None) -> None:
    """Format and display the analysis output"""
    console = Console()
    if raw and claude:
        console.print("\n=== Message History ===")
        for role, content in claude.messages_history:
            console.print(f"\n[bold cyan]{role.upper()}:[/bold cyan]")
            console.print(content)
        console.print("\n=== End Message History ===\n")
    else:
        md = Markdown(analysis)
        console.print(md)

def prompt_user(message: str, choices: List[str] = None) -> str:
    """Display a prominent user prompt with optional choices"""
    console = Console()
    console.print()
    console.print(Rule(" User Input Required ", style="bold cyan"))
    
    if choices:
        choice_text = f"[cyan]Options: {', '.join(choices)}[/cyan]"
        console.print(Panel(choice_text, box=box.ROUNDED))
    
    return Prompt.ask(f"[bold cyan]> {message}[/bold cyan]")

def get_option_selection() -> int:
    """Get user input for option selection"""
    while True:
        try:
            option = int(prompt_user("Select option number"))
            return option
        except ValueError:
            console = Console()
            console.print("[red]Please enter a valid number[/red]")

def get_history_path(workdir: Path) -> Path:
    """Create and return the history directory path"""
    history_dir = workdir / '.janito' / 'history'
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir

def get_timestamp() -> str:
    """Get current UTC timestamp in YMD_HMS format with leading zeros"""
    return datetime.utcnow().strftime('%Y%m%d_%H%M%S')

def save_prompt_to_file(prompt: str) -> Path:
    """Save prompt to a named temporary file that won't be deleted"""
    temp_file = tempfile.NamedTemporaryFile(prefix='selected_', suffix='.txt', delete=False)
    temp_path = Path(temp_file.name)
    temp_path.write_text(prompt)
    return temp_path

def save_to_file(content: str, prefix: str, workdir: Path) -> Path:
    """Save content to a timestamped file in history directory"""
    history_dir = get_history_path(workdir)
    timestamp = get_timestamp()
    filename = f"{timestamp}_{prefix}.txt"
    file_path = history_dir / filename
    file_path.write_text(content)
    return file_path

def format_parsed_changes(changes: List[Dict[str, Any]]) -> None:
    """Format and display parsed changes in a readable way"""
    console = Console()
    
    # Print summary header
    console.print(Rule(" Changes Summary ", style="bold blue"))
    for change in changes:
        filename = change["filename"]
        if "content" in change:
            console.print(f"[green]• Create new file:[/green] {filename}")
        else:
            operations = [c["type"] for c in change.get("changes", [])]
            console.print(f"[yellow]• Modify file:[/yellow] {filename}")
            for op in operations:
                console.print(f"  - {op}")
    
    # Display detailed changes
    for change in changes:
        filename = change["filename"]
        # Fix: Don't concatenate Rule object with string
        console.print()  # Add newline
        console.print(Rule(f" File: {filename} ", style="bold blue"))
        
        if "content" in change:
            console.print("[green]✨ Creating new file[/green]")
            ext = Path(filename).suffix.lstrip('.')
            syntax = Syntax(
                change["content"],
                ext or "python",
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            )
            console.print(Panel(
                syntax,
                border_style="green",
                box=box.ROUNDED
            ))
        else:
            for c in change.get("changes", []):
                operation = c["type"]
                ext = Path(filename).suffix.lstrip('.')
                
                # Create panels with line numbers and proper syntax highlighting
                original = Panel(
                    Syntax(
                        c["original"],
                        ext or "python",
                        theme="monokai",
                        line_numbers=True,
                        word_wrap=True
                    ),
                    title=f"[yellow]{operation}[/yellow] - Original",
                    border_style="red",
                    box=box.ROUNDED
                )
                new = Panel(
                    Syntax(
                        c["text"],
                        ext or "python",
                        theme="monokai",
                        line_numbers=True,
                        word_wrap=True
                    ),
                    title="After Change",
                    border_style="green",
                    box=box.ROUNDED
                )
                
                # Display side by side with proper spacing
                console.print(Columns(
                    [original, new],
                    padding=(0, 2),
                    expand=False,
                    align="left"
                ))

def handle_option_selection(claude: ClaudeAPIAgent, initial_response: str, request: str, raw: bool = False, workdir: Optional[Path] = None, include: Optional[List[Path]] = None) -> None:
    """Handle option selection and implementation details"""
    option = get_option_selection()
    try:
        # Get current files content with included paths
        paths_to_scan = [workdir] if workdir else []
        if include:
            paths_to_scan.extend(include)
        files_content = collect_files_content(paths_to_scan, workdir) if paths_to_scan else ""
        
        selected_prompt = build_selected_option_prompt(option, request, initial_response, files_content)
        prompt_file = save_to_file(selected_prompt, 'selected_', workdir)
        print(f"\nSelected prompt saved to: {prompt_file}")
        
        selected_response = claude.send_message(selected_prompt)
        # Save response to changes file
        changes_file = save_to_file(selected_response, 'changes_', workdir)
        print(f"\nChanges saved to: {changes_file}")
        
        # Parse and format changes
        changes = parse_block_changes(selected_response)  # Convert text blocks to structured data
        format_parsed_changes(changes)                    # Display formatted changes
        
        if workdir:
            handle_changes_file(changes_file, workdir)    # Preview and apply changes
            
    except ValueError as e:
        console = Console()
        console.print(f"\nError: {e}")

def replay_saved_file(filepath: Path, claude: ClaudeAPIAgent, workdir: Path, raw: bool = False) -> None:
    """Process a saved prompt file and display the response"""
    if not filepath.exists():
        print(f"Error: File {filepath} not found")
        return
    
    file_type = get_file_type(filepath)
    content = filepath.read_text()
    
    if file_type == 'changes':
        # Display formatted changes before applying them
        changes = parse_block_changes(content)
        format_parsed_changes(changes)
        handle_changes_file(filepath, workdir)
    elif file_type == 'analysis':
        format_analysis(content, raw, claude)
        handle_option_selection(claude, content, content, raw, workdir)  # Pass original content as request
    elif file_type == 'selected':
        if raw:
            console = Console()
            console.print("\n=== Prompt Content ===")
            console.print(content)
            console.print("=== End Prompt Content ===\n")
        response = claude.send_message(content)
        changes_file = save_to_file(response, 'changes_', workdir)
        print(f"\nChanges saved to: {changes_file}")
        
        # Display formatted changes
        changes = parse_block_changes(response)
        format_parsed_changes(changes)
        
        handle_changes_file(changes_file, workdir)
    else:
        response = claude.send_message(content)
        format_analysis(response, raw)

def main(
    workdir: Path = typer.Argument(..., help="Working directory containing the files", exists=True, file_okay=False, dir_okay=True),
    request: str = typer.Argument(..., help="The modification request"),
    raw: bool = typer.Option(False, "--raw", help="Print raw response instead of markdown format"),
    play: Optional[Path] = typer.Option(None, "--play", help="Replay a saved prompt file"),
    include: Optional[List[Path]] = typer.Option(None, "-i", "--include", help="Additional paths to include in analysis", exists=True),
) -> None:
    """
    Analyze files and provide modification instructions.
    """
    claude = ClaudeAPIAgent(system_prompt=SYSTEM_PROMPT)
    
    if play:
        replay_saved_file(play, claude, workdir, raw)
        return
    
    # Regular flow
    paths_to_scan = [workdir]
    if include:
        paths_to_scan.extend(include)
    
    is_empty = is_dir_empty(workdir)
    if is_empty and not include:
        console = Console()
        console.print("\n[bold blue]Empty directory - will create new files[/bold blue]")
        files_content = ""
    else:
        files_content = collect_files_content(paths_to_scan, workdir)
    
    # Get initial analysis and save it
    initial_prompt = build_request_analisys_prompt(files_content, request)
    initial_response = claude.send_message(initial_prompt)
    analysis_file = save_to_file(initial_response, 'analysis_', workdir)
    print(f"\nAnalysis saved to: {analysis_file}")
    
    # Show initial response
    format_analysis(initial_response, raw, claude)
    
    # Always prompt for option selection
    handle_option_selection(claude, initial_response, request, raw, workdir, include)

if __name__ == "__main__":
    typer.run(main)
