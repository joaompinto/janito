from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.text import Text
from typing import List
from ..parser import FileChange, ChangeOperation
from .styling import format_content, create_legend_items
from rich.rule import Rule

def preview_all_changes(console: Console, changes: List[FileChange]) -> None:
    """Show a summary of all changes with side-by-side comparison and progress tracking"""
    total_changes = len(changes)

    # Create summary text for the panel
    summary_text = Text()
    summary_text.append("Change Operations Summary\n\n", style="bold blue")

    # Add change entries to summary
    for change in changes:
        operation = change.operation.name.replace('_', ' ').title()
        path = change.target if change.operation == ChangeOperation.RENAME_FILE else change.name

        # Add colored indicators based on operation type
        if change.operation == ChangeOperation.CREATE_FILE:
            summary_text.append("✚ ", style="green")
        elif change.operation == ChangeOperation.REMOVE_FILE:
            summary_text.append("✕ ", style="red")
        elif change.operation == ChangeOperation.RENAME_FILE:
            summary_text.append("↺ ", style="yellow")
        else:
            summary_text.append("✎ ", style="blue")

        # Add entry to summary text
        if change.operation == ChangeOperation.RENAME_FILE:
            summary_text.append(f"{operation}: ", style="yellow")
            summary_text.append(f"{change.name} → {change.target}\n")
        else:
            summary_text.append(f"{operation}: ", style="yellow")
            summary_text.append(f"{path}\n")

    # Create and display centered panel
    summary_panel = Panel(
        summary_text,
        title="[bold blue]Change Summary[/bold blue]",
        box=box.ROUNDED,
        padding=(1, 2),
        width=min(console.width - 4, 100)  # Limit max width while keeping padding
    )
    console.print(summary_panel, justify="center")

    # Then show side-by-side panels for replacements
    console.print("\n[bold blue]File Changes:[/bold blue]")

    for i, change in enumerate(changes):
        if change.operation in (ChangeOperation.REPLACE_FILE, ChangeOperation.MODIFY_FILE):
            show_side_by_side_diff(console, change, i, total_changes)

def show_side_by_side_diff(console: Console, change: FileChange, change_index: int = 0, total_changes: int = 1) -> None:
    """Show side-by-side diff panels for a file change with progress tracking

    Args:
        console: Rich console instance
        change: FileChange object containing the changes
        change_index: Current change number (0-based)
        total_changes: Total number of changes
    """
    # Get original and new content
    original = change.original_content or ""
    new_content = change.content or ""

    # Split into lines
    original_lines = original.splitlines()
    new_lines = new_content.splitlines()

    # Show compact centered legend
    console.print(create_legend_items(), justify="center")

    # Show the header with minimal spacing after legend
    operation = change.operation.name.replace('_', ' ').title()
    progress = f"Change {change_index + 1}/{total_changes}"
    header = f"[bold blue]{operation}:[/bold blue] {change.name} [dim]({progress})[/dim]"
    console.print(Panel(header, box=box.HEAVY, style="blue"))

    # Handle text changes
    if change.text_changes:
        for text_change in change.text_changes:
            search_lines = text_change.search_content.splitlines() if text_change.search_content else []
            replace_lines = text_change.replace_content.splitlines() if text_change.replace_content else []

            # Find modified sections
            sections = find_modified_sections(search_lines, replace_lines)

            # Show modification type
            if text_change.search_content and text_change.replace_content:
                console.print("\n[blue]Replace Changes:[/blue]")
            elif not text_change.search_content:
                console.print("\n[green]Append Changes:[/green]")
            elif not text_change.replace_content:
                console.print("\n[red]Delete Changes:[/red]")

            # Format and display each section
            for i, (orig_section, new_section) in enumerate(sections):
                left_panel = format_content(orig_section, orig_section, new_section, True)
                right_panel = format_content(new_section, orig_section, new_section, False)

                term_width = console.width or 120
                total_padding = 10  # Space for margins and padding between panels
                panel_width = (term_width - total_padding) // 2
                content_width = panel_width - 4  # Account for panel borders and padding

                # Format content with calculated width
                left_panel = format_content(orig_section, orig_section, new_section, True, content_width)
                right_panel = format_content(new_section, orig_section, new_section, False, content_width)

                panels = [
                    Panel(
                        left_panel,
                        title="[red]Original Content[/red]",
                        title_align="center",
                        subtitle=str(change.name),
                        subtitle_align="center",
                        width=panel_width,
                        padding=(0, 1)
                    ),
                    Panel(
                        right_panel,
                        title="[green]Modified Content[/green]",
                        title_align="center",
                        subtitle=str(change.name),
                        subtitle_align="center",
                        width=panel_width,
                        padding=(0, 1)
                    )
                ]

                console.print(Columns(panels))

                # Show separator between sections
                if i < len(sections) - 1:
                    console.print(Rule(style="dim"))
                else:
                    # Show final section separator with label
                    console.print(Rule(title="End Of Changes", style="bold blue"))
    else:
        # For non-text changes, show full content side by side
        sections = find_modified_sections(original_lines, new_lines)
        for i, (orig_section, new_section) in enumerate(sections):
            left_panel = format_content(orig_section, orig_section, new_section, True)
            right_panel = format_content(new_section, orig_section, new_section, False)

            term_width = console.width or 120
            total_padding = 10  # Space for margins and padding between panels
            panel_width = (term_width - total_padding) // 2
            content_width = panel_width - 4  # Account for panel borders and padding

            # Format content with calculated width
            left_panel = format_content(orig_section, orig_section, new_section, True, content_width)
            right_panel = format_content(new_section, orig_section, new_section, False, content_width)

            panels = [
                Panel(
                    left_panel,
                    title="[red]Original Content[/red]",
                    title_align="center",
                    subtitle=str(change.name),
                    subtitle_align="center",
                    width=panel_width,
                    padding=(0, 1)
                ),
                Panel(
                    right_panel,
                    title="[green]Modified Content[/green]",
                    title_align="center",
                    subtitle=str(change.name),
                    subtitle_align="center",
                    width=panel_width,
                    padding=(0, 1)
                )
            ]

            console.print(Columns(panels))

            # Show separator between sections
            if i < len(sections) - 1:
                console.print(Rule(style="dim"))
            else:
                # Show final section separator with label
                console.print(Rule(title="End Of Changes", style="bold blue"))

    # Add final separator after all changes
    console.print(Rule(title="End Of Changes", style="bold blue"))
    console.print()

def find_modified_sections(original: list[str], modified: list[str], context_lines: int = 3) -> list[tuple[list[str], list[str]]]:
    """
    Find modified sections between original and modified text with surrounding context.
    
    Args:
        original: List of original lines
        modified: List of modified lines
        context_lines: Number of unchanged context lines to include
        
    Returns:
        List of tuples containing (original_section, modified_section) line pairs
    """
    # Find different lines
    different_lines = set()
    for i in range(max(len(original), len(modified))):
        if i >= len(original) or i >= len(modified):
            different_lines.add(i)
        elif original[i] != modified[i]:
            different_lines.add(i)
            
    if not different_lines:
        return []

    # Group differences into sections with context
    sections = []
    current_section = set()
    
    for line_num in sorted(different_lines):
        # If this line is far from current section, start new section
        if not current_section or line_num <= max(current_section) + context_lines * 2:
            current_section.add(line_num)
        else:
            # Process current section
            start = max(0, min(current_section) - context_lines)
            end = min(max(len(original), len(modified)), 
                     max(current_section) + context_lines + 1)
                     
            orig_section = original[start:end]
            mod_section = modified[start:end]
            
            sections.append((orig_section, mod_section))
            current_section = {line_num}
    
    # Process final section
    if current_section:
        start = max(0, min(current_section) - context_lines) 
        end = min(max(len(original), len(modified)),
                 max(current_section) + context_lines + 1)
                 
        orig_section = original[start:end]
        mod_section = modified[start:end]
        
        sections.append((orig_section, mod_section))
        
    return sections

def create_new_file_panel(name: Text, content: Text) -> Panel:
    """Create a panel for new file creation"""
    return Panel(
        format_content(content.splitlines(), [], content.splitlines(), False),
        title=f"[green]New File: {name}[/green]",
        title_align="left",
        box=box.HEAVY
    )

def create_replace_panel(name: Text, change: FileChange) -> Panel:
    """Create a panel for file replacement"""
    original = change.original_content or ""
    new_content = change.content or ""
    
    term_width = Console().width or 120
    panel_width = max(60, (term_width - 10) // 2)
    
    panels = [
        Panel(
            format_content(original.splitlines(), original.splitlines(), new_content.splitlines(), True),
            title="[red]Original Content[/red]",
            title_align="left",
            width=panel_width
        ),
        Panel(
            format_content(new_content.splitlines(), original.splitlines(), new_content.splitlines(), False),
            title="[green]New Content[/green]",
            title_align="left",
            width=panel_width
        )
    ]
    
    return Panel(Columns(panels), title=f"[yellow]Replace: {name}[/yellow]", box=box.HEAVY)

def create_remove_file_panel(name: Text) -> Panel:
    """Create a panel for file removal"""
    return Panel(
        "[red]This file will be removed[/red]",
        title=f"[red]Remove File: {name}[/red]",
        title_align="left",
        box=box.HEAVY
    )

def create_change_panel(search_content: Text, replace_content: Text, description: Text, width: int) -> Panel:
    """Create a panel for text modifications"""
    search_lines = search_content.splitlines() if search_content else []
    replace_lines = replace_content.splitlines() if replace_content else []
    
    term_width = Console().width or 120
    panel_width = max(60, (term_width - 10) // width)
    
    panels = [
        Panel(
            format_content(search_lines, search_lines, replace_lines, True),
            title="[red]Search Content[/red]",
            title_align="left",
            width=panel_width
        ),
        Panel(
            format_content(replace_lines, search_lines, replace_lines, False),
            title="[green]Replace Content[/green]",
            title_align="left",
            width=panel_width
        )
    ]
    
    return Panel(
        Columns(panels),
        title=f"[blue]Modification: {description}[/blue]",
        box=box.HEAVY
    )