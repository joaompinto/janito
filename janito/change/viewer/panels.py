from rich.console import Console
from typing import List, Union, Tuple, Optional

from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from pathlib import Path
from typing import List, Union, Tuple
from janito.file_operations import (
    CreateFile, DeleteFile, RenameFile, ReplaceFile, ModifyFile,
    ChangeType
)
from .styling import format_content
from .content import create_content_preview, get_file_syntax
from .sections import find_modified_sections
from rich.rule import Rule
from rich.columns import Columns
from rich import box
from rich.text import Text
from rich.layout import Layout

# Constants for panel layout
PANEL_MIN_WIDTH = 40
PANEL_MAX_WIDTH = 120  # Maximum width for a single column
PANEL_PADDING = 4
COLUMN_SPACING = 4

def create_progress_header(operation: str, filename: str, current: int, total: int,
                          reason: str = None, style: str = "cyan") -> Tuple[str, str]:
    """Create a header showing filename and global change counter.

    Args:
        operation: Type of operation being performed
        filename: Name of the file being modified
        current: Current global change number
        total: Total number of changes
        reason: Optional reason for the change
        style: Color style for the header

    Returns:
        Tuple of (header text, style)
    """
    # Format header with operation type and global counter
    header = f"[{style}]{operation}:[/{style}] {filename} | Progress {current}/{total}"

    # Add reason if provided
    if reason:
        header += f" | {reason}"

    return header, style

FileOperationType = Union[CreateFile, DeleteFile, RenameFile, ReplaceFile, ModifyFile]

def show_all_changes(changes: List[FileOperationType]) -> None:
    """Show a summary of all changes with side-by-side comparison.

    Args:
        changes: List of file operations to preview
    """
    console = Console()

    # Initialize global counters
    global_total = count_total_changes(changes)
    global_current = 0

    console.print("[yellow]Starting changes preview...[/yellow]", justify="center")
    console.print(f"[yellow]Total changes to process: {global_total}[/yellow]", justify="center")
    console.print()
    
    # Group changes by type
    create_files = []
    delete_files = []
    rename_files = []
    replace_files = []
    modify_files = []

    for change in changes:
        if isinstance(change, CreateFile):
            create_files.append(change)
        elif isinstance(change, DeleteFile):
            delete_files.append(change)
        elif isinstance(change, RenameFile):
            rename_files.append(change)
        elif isinstance(change, ReplaceFile):
            replace_files.append(change)
        elif isinstance(change, ModifyFile):
            modify_files.append(change)

    # Show file creations first
    if create_files:
        for change in create_files:
            global_current += 1
            header, style = create_progress_header("Create", change.name, global_current, global_total, style="green")
            console.print(Rule(header, style=style, align="center"))
            if hasattr(change, 'content'):
                preview = create_content_preview(Path(change.name), change.content, is_new=True)
                console.print(preview, justify="center")
            console.print()

    # Show file removals
    if delete_files:
        console.print("\n[bold red]File Removals:[/bold red]")
        for change in delete_files:
            global_current += 1  # Increment counter before showing panel
            show_delete_panel(console, change, global_current, global_total)
            console.print()

    # Show file renames
    if rename_files:
        console.print("\n[bold yellow]File Renames:[/bold yellow]")
        for change in rename_files:
            global_current += 1
            header, style = create_progress_header("Rename", f"{change.name} → {change.new_name}", global_current, global_total, style="yellow")
            console.print(Rule(header, style=style, align="center"))
            console.print()

    # Show file replacements
    if replace_files:
        console.print("\n[bold magenta]File Replacements:[/bold magenta]")
        for change in replace_files:
            global_current += 1
            header, style = create_progress_header("Replace", change.name, global_current, global_total, style="magenta")
            console.print(Rule(header, style=style, align="center"))
            preview = create_content_preview(Path(change.name), change.content, is_new=False)
            console.print(preview, justify="center")
            console.print()

    # Show content modifications
    for modify_change in modify_files:
        for i, content_change in enumerate(modify_change.get_changes()):
            # Update global counter
            global_current += 1

            # Show progress header for each change
            header, style = create_progress_header(
                operation="Modify",
                filename=modify_change.name,
                current=global_current,
                total=global_total,
                reason=None
            )
            console.print(Rule(header, style=style, align="center"))

            # Get the content based on change type
            if content_change.change_type in (ChangeType.REPLACE, ChangeType.ADD):
                orig_lines = content_change.original_content
                new_lines = content_change.new_content
            elif content_change.change_type == ChangeType.DELETE:
                orig_lines = content_change.original_content
                new_lines = []  # Empty list for deletions
            else:
                raise NotImplementedError(f"Unsupported change type: {content_change.change_type}")

            # Show the diff without operation header
            show_side_by_side_diff(
                console,
                modify_change.name,
                orig_lines,
                new_lines,
                global_current,
                global_total,
                f"Lines {content_change.start_line + 1}-{content_change.end_line}",
                show_header=False
            )
            console.print()  # Add spacing between changes

    # Show final success message
    console.print()
    success_text = Text("🎉 All changes have been previewed successfully! 🎉", style="bold green")
    console.print(Panel(
        success_text,
        box=box.ROUNDED,
        style="green",
        padding=(1, 2)
    ), justify="center")
    console.print()

def _show_file_operations(console: Console, grouped_changes: dict) -> None:
    """Display file operation summaries with content preview for new files."""
    # Show file creations first
    if ChangeOperation.CREATE_FILE in grouped_changes:
        for change in grouped_changes[ChangeOperation.CREATE_FILE]:
            console.print(Rule(f"[green]Creating new file: {change.name}[/green]", style="green"), justify="center")
            if change.content:
                preview = create_content_preview(Path(change.name), change.content, is_new=True)
                console.print(preview, justify="center")
            console.print()

    # Show file and directory removals
    if ChangeOperation.REMOVE_FILE in grouped_changes:
        console.print("\n[bold red]File Removals:[/bold red]")
        for change in grouped_changes[ChangeOperation.REMOVE_FILE]:
            console.print(Rule(f"[red]Removing file: {change.name}[/red]", style="red"))
            console.print()

    # Show file renames
    if ChangeOperation.RENAME_FILE in grouped_changes:
        console.print("\n[bold yellow]File Renames:[/bold yellow]")
        for change in grouped_changes[ChangeOperation.RENAME_FILE]:
            console.print(Rule(f"[yellow]Renaming file: {change.name} → {change.target}[/yellow]", style="yellow"))
            console.print()

    # Show file moves
    if ChangeOperation.MOVE_FILE in grouped_changes:
        console.print("\n[bold blue]File Moves:[/bold blue]")
        for change in grouped_changes[ChangeOperation.MOVE_FILE]:
            console.print(Rule(f"[blue]Moving file: {change.name} → {change.target}[/blue]", style="blue"))
            console.print()

def calculate_panel_widths(left_content: str, right_content: str, term_width: int) -> Tuple[int, int]:
    """Calculate optimal widths for side-by-side panels with overflow protection."""
    # Reserve space for padding and spacing
    available_width = term_width - PANEL_PADDING - COLUMN_SPACING

    # Calculate maximum content widths
    left_max = max((len(line) for line in left_content.splitlines()), default=0)
    right_max = max((len(line) for line in right_content.splitlines()), default=0)

    # Ensure minimum width requirements
    left_max = max(PANEL_MIN_WIDTH, min(left_max, PANEL_MAX_WIDTH))
    right_max = max(PANEL_MIN_WIDTH, min(right_max, PANEL_MAX_WIDTH))

    # If total width exceeds available space, scale proportionally
    total_width = left_max + right_max
    if total_width > available_width:
        ratio = left_max / total_width
        left_width = max(PANEL_MIN_WIDTH, min(PANEL_MAX_WIDTH, int(available_width * ratio)))
        right_width = max(PANEL_MIN_WIDTH, min(PANEL_MAX_WIDTH, available_width - left_width))
    else:
        left_width = left_max
        right_width = right_max

    # If content fits within available width, use constrained sizes
    total_width = left_max + right_max
    if total_width <= available_width:
        return left_max, right_max

    # Otherwise distribute proportionally while respecting min/max constraints
    ratio = left_max / (total_width or 1)
    left_width = min(
        PANEL_MAX_WIDTH,
        max(PANEL_MIN_WIDTH, int(available_width * ratio))
    )
    right_width = min(
        PANEL_MAX_WIDTH,
        max(PANEL_MIN_WIDTH, available_width - left_width)
    )

    return left_width, right_width

def create_side_by_side_columns(orig_section: List[str], new_section: List[str], filename: str,
                           can_do_side_by_side: bool, term_width: int) -> Columns:
    """Create side-by-side diff view using Columns with consistent styling"""
    # Get syntax type using centralized function
    syntax_type = get_file_syntax(Path(filename))

    # Calculate max line widths for each section
    left_max_width = max((len(line) for line in orig_section), default=0)
    right_max_width = max((len(line) for line in new_section), default=0)

    # Add some padding for the titles
    left_max_width = max(left_max_width, len("Original") + 2)
    right_max_width = max(right_max_width, len("Modified") + 2)

    # Calculate optimal widths while respecting max line widths
    total_width = term_width - 4  # Account for padding
    if can_do_side_by_side:
        # Use actual content widths, but ensure they fit in available space
        available_width = total_width - COLUMN_SPACING  # Account for spacing column
        if (left_max_width + right_max_width) > available_width:
            # Scale proportionally if content is too wide
            ratio = left_max_width / (left_max_width + right_max_width)
            left_width = min(left_max_width, int(available_width * ratio))
            right_width = min(right_max_width, available_width - left_width)
        else:
            left_width = left_max_width
            right_width = right_max_width
    else:
        left_width = right_width = total_width

    # Format content with calculated widths
    left_content = format_content(orig_section, orig_section, new_section, True,
                                width=left_width, syntax_type=syntax_type)
    right_content = format_content(new_section, orig_section, new_section, False,
                                width=right_width, syntax_type=syntax_type)

    # Create text containers with centered titles
    left_text = Text()
    title_padding = (left_width - len("Original")) // 2
    left_text.append(" " * title_padding + "Original" + " " * title_padding, style="red bold")
    left_text.append("\n")
    left_text.append(left_content)

    # Create spacing column
    spacing_text = Text(" " * COLUMN_SPACING)

    right_text = Text()
    title_padding = (right_width - len("Modified")) // 2
    right_text.append(" " * title_padding + "Modified" + " " * title_padding, style="green bold")
    right_text.append("\n")
    right_text.append(right_content)

    # Calculate padding for centering the entire columns
    content_width = left_width + COLUMN_SPACING + right_width
    side_padding = " " * ((term_width - content_width) // 2)

    # Create centered columns with fixed spacing
    return Columns(
        [
            Text(side_padding),
            left_text,
            spacing_text,
            right_text,
            Text(side_padding)
        ],
        equal=False,
        expand=False,
        padding=(0, 0)  # Remove padding since we're using explicit spacing
    )

def show_side_by_side_diff(
    console: Console,
    filename: str,
    original_content: List[str],
    new_content: List[str],
    change_index: int,
    total_changes: int,
    reason: str = None,
    show_header: bool = True
) -> bool:
    """Show diff content using appropriate panel style based on operation type"""
    term_width = console.width or 120

    # Only show header if explicitly requested
    if show_header:
        header, style = create_progress_header("Modify", filename, change_index + 1, total_changes, reason=reason)
        console.print(Rule(header, style=style, align="center"))

    # For add operations where original_content is empty, show only the new content
    if not original_content:
        syntax_type = get_file_syntax(Path(filename))
        console.print(Rule("[green]Added Content[/green]", style="green"))
        content = format_content(new_content, [], new_content, False,
                               width=term_width - 4, syntax_type=syntax_type)
        console.print(content)
    # For delete operations where new_content is empty, show with header and red background
    elif not new_content:
        syntax_type = get_file_syntax(Path(filename))
        console.print(Rule("[red]Deleted Content[/red]", style="red"))
        content = format_content(original_content, original_content, [], True,
                               width=term_width - 4, syntax_type=syntax_type,
                               is_delete=True)
        console.print(content)
    else:
        # Find modified sections and show side-by-side diff
        sections = find_modified_sections(original_content, new_content)
        for i, (orig_section, new_section) in enumerate(sections):
            layout = create_side_by_side_columns(
                orig_section,
                new_section,
                filename,
                True,
                term_width
            )
            console.print(layout)
            if i < len(sections) - 1:
                console.print(Rule(style="dim"))

def show_delete_panel(
    console: Console,
    delete_op: DeleteFile,
    change_index: int = 0,
    total_changes: int = 1
) -> None:
    """Show file deletion operation with simple header."""
    header, _ = create_progress_header(
        "Delete",
        delete_op.name,
        change_index + 1,
        total_changes,
        style="red"
    )

    # Show header with consistent format
    console.print(Rule(header, style="red", align="center"))

    # Show file content if exists
    if Path(delete_op.name).exists():
        file_content = Path(delete_op.name).read_text()
        syntax_type = get_file_syntax(Path(delete_op.name))

        syntax = Syntax(
            file_content,
            syntax_type,
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
            background_color="#330000"
        )
        console.print(syntax)

def count_total_changes(changes: List[FileOperationType]) -> int:
    """Count total number of changes (file operations + content changes)

    Returns:
        Total number of changes
    """
    return sum(
        len(change.get_changes()) if isinstance(change, ModifyFile) else 1
        for change in changes
    )

def format_change_progress(current: int, total: int) -> str:
    """Format change progress counter

    Args:
        current: Current change number
        total: Total number of changes
    """
    return f"Change {current}/{total}"

def get_human_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def get_file_stats(content: Union[str, Text]) -> str:
    """Get file statistics in human readable format"""
    if isinstance(content, Text):
        lines = content.plain.splitlines()
        size = len(content.plain.encode('utf-8'))
    else:
        lines = content.splitlines()
        size = len(content.encode('utf-8'))
    return f"{len(lines)} lines, {get_human_size(size)}"
