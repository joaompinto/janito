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

def format_analysis(analysis: str, raw: bool = False) -> None:
    """Format and display the analysis output"""
    console = Console()
    if raw:
        console.print(analysis)
    else:
        md = Markdown(analysis)
        console.print(md)

def is_dir_empty(path: Path) -> bool:
    """Check if directory is empty, ignoring hidden files"""
    return not any(item for item in path.iterdir() if not item.name.startswith('.'))

def get_option_selection() -> int:
    """Get user input for option selection"""
    while True:
        try:
            option = int(input("\nSelect option number: "))
            return option
        except ValueError:
            print("Please enter a valid number")

def save_prompt_to_file(prompt: str) -> Path:
    """Save prompt to a named temporary file that won't be deleted"""
    temp_file = tempfile.NamedTemporaryFile(prefix='selected_', suffix='.txt', delete=False)
    temp_path = Path(temp_file.name)
    temp_path.write_text(prompt)
    return temp_path

def save_to_file(content: str, prefix: str) -> Path:
    """Save content to a named temporary file that won't be deleted"""
    temp_file = tempfile.NamedTemporaryFile(prefix=prefix, suffix='.txt', delete=False)
    temp_path = Path(temp_file.name)
    temp_path.write_text(content)
    return temp_path

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

def handle_option_selection(claude: ClaudeAPIAgent, initial_response: str, request: str, raw: bool = False, workdir: Optional[Path] = None) -> None:
    """Handle option selection and implementation details"""
    option = get_option_selection()
    try:
        selected_prompt = build_selected_option_prompt(option, request, initial_response)
        prompt_file = save_to_file(selected_prompt, 'selected_')
        print(f"\nSelected prompt saved to: {prompt_file}")
        
        selected_response = claude.send_message(selected_prompt)
        # Save response to changes file
        changes_file = save_to_file(selected_response, 'changes_')
        print(f"\nChanges saved to: {changes_file}")
        
        # Parse and format changes
        changes = parse_block_changes(selected_response)  # Convert text blocks to structured data
        format_parsed_changes(changes)                    # Display formatted changes
        
        if workdir:
            handle_changes_file(changes_file, workdir)    # Preview and apply changes
            
    except ValueError as e:
        print(f"\nError: {e}")

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
        format_analysis(content, raw)
        handle_option_selection(claude, content, content, raw)  # Pass original content as request
    elif file_type == 'selected':
        response = claude.send_message(content)
        changes_file = save_to_file(response, 'changes_')
        print(f"\nChanges saved to: {changes_file}")
        
        # Display formatted changes
        changes = parse_block_changes(response)
        format_parsed_changes(changes)
        
        handle_changes_file(changes_file, workdir)
    else:
        response = claude.send_message(content)
        format_analysis(response, raw)

def collect_files_content(workdir: Path) -> str:
    """Collect content from all files in the directory in XML format"""
    content_parts = []
    console = Console()
    
    console.print("\n[bold blue]Files being analyzed:[/bold blue]")
    for file_path in workdir.rglob('*'):
        if file_path.is_file() and not file_path.name.startswith('.'):
            try:
                relative_path = file_path.relative_to(workdir)
                console.print(f"  • {relative_path}")
                file_content = file_path.read_text()
                content_parts.append(f"<file>\n<path>{relative_path}</path>\n<content>\n{file_content}\n</content>\n</file>")
            except Exception as e:
                console.print(f"[red]Warning: Could not read {file_path}: {e}[/red]")
    
    return "\n".join(content_parts)

def main(
    workdir: Path = typer.Argument(..., help="Working directory containing the files", exists=True, file_okay=False, dir_okay=True),
    request: str = typer.Argument(..., help="The modification request"),
    raw: bool = typer.Option(False, "--raw", help="Print raw response instead of markdown format"),
    play: Optional[Path] = typer.Option(None, "--play", help="Replay a saved prompt file"),
) -> None:
    """
    Analyze files and provide modification instructions.
    
    Args:
        workdir: Directory containing the files to analyze
        request: What modifications to make
        raw: Whether to print raw response instead of markdown format
    """
    claude = ClaudeAPIAgent(system_prompt=SYSTEM_PROMPT)
    
    if play:
        replay_saved_file(play, claude, workdir, raw)
        return
        
    # Regular flow
    is_empty = is_dir_empty(workdir)
    if is_empty:
        console = Console()
        console.print("\n[bold blue]Empty directory - will create new files[/bold blue]")
        files_content = ""
    else:
        files_content = collect_files_content(workdir)
    
    # Get initial analysis and save it
    initial_prompt = build_request_analisys_prompt(files_content, request)
    initial_response = claude.send_message(initial_prompt)
    analysis_file = save_to_file(initial_response, 'analysis_')
    print(f"\nAnalysis saved to: {analysis_file}")
    
    # Show initial response
    format_analysis(initial_response, raw)
    
    # Always prompt for option selection
    handle_option_selection(claude, initial_response, request, raw, workdir)  # Pass workdir to handle_option_selection

if __name__ == "__main__":  # Note the double underscore
    typer.run(main)
