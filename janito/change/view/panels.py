from rich.console import Console
from typing import List, Tuple
from rich.panel import Panel
from rich.syntax import Syntax
from pathlib import Path
from rich.columns import Columns
from rich.text import Text
from rich.layout import Layout
from ..instructions_parser import EditType, CodeChange
from .styling import format_content
from .sections import find_modified_sections

# Constants for panel layout
PANEL_MIN_WIDTH = 40
PANEL_MAX_WIDTH = 120
PANEL_PADDING = 4
COLUMN_SPACING = 4

def create_diff_columns(
    original_section: List[str], 
    modified_section: List[str], 
    filename: str,
    start: int,
    term_width: int,
    context_lines: int = 3,
    current_change: int = 1,
    total_changes: int = 1,
    edit_command: str = "Edit",
    reason: str = None,
    is_removal: bool = False
) -> Tuple[Text, Columns]:  # Changed return type to return header and content separately
    """Create side-by-side diff view with consistent styling and context."""
    # Create header with progress info and rule
    header = Text()
    header_text, _ = create_progress_header(
        edit_command=edit_command,
        filename=filename,
        current=current_change,
        total=total_changes,
        term_width=term_width,
        reason=reason
    )
    
    header.append(header_text)
    header.append("\n")

    # Find sections that have changed
    sections = find_modified_sections(
        original_section,
        modified_section,
        context_lines=context_lines
    )
    
    if not sections:
        # If no differences, show full content
        diff_columns = _create_single_section_columns(
            original_section,
            modified_section,
            filename,
            start,
            term_width,
            is_removal=is_removal
        )
    else:
        # Create columns for each modified section
        rendered_sections = []
        for i, (orig, mod) in enumerate(sections):
            if i > 0:
                rendered_sections.append(Text("...\n", style="dim"))
                
            section_columns = _create_single_section_columns(
                orig, mod, filename, start, term_width, is_removal=is_removal
            )
            rendered_sections.append(section_columns)
        
        # Create single column containing all sections
        diff_columns = Columns(
            rendered_sections,
            equal=False,
            expand=False,
            padding=(0, 0)
        )

    return header, diff_columns

def _create_single_section_columns(
    original: List[str],
    modified: List[str],
    filename: str, 
    start: int,
    term_width: int,
    is_removal: bool = False  # Add parameter with default value
) -> Columns:
    """Create columns for a single diff section."""
    left_width, right_width = calculate_panel_widths(
        '\n'.join(original),
        '\n'.join(modified),
        term_width
    )

    # Format content with correct parameters
    left_content = format_content(
        original,
        search_lines=original,
        replace_lines=modified,
        is_search=True,  # This indicates it's the original/search content
        width=left_width,
        is_removal=is_removal  # Pass the parameter
    )
    right_content = format_content(
        modified,
        search_lines=original,
        replace_lines=modified,
        is_search=False,  # This indicates it's the modified/replace content
        width=right_width
    )

    left_text = create_panel_text("Original", left_content, left_width)
    right_text = create_panel_text("Modified", right_content, right_width)

    # Create columns without manual padding
    columns = Columns(
        [
            left_text,
            Text(" " * COLUMN_SPACING),
            right_text
        ],
        equal=False,
        expand=False,
        padding=(0, 0)
    )

    return columns

def calculate_panel_widths(left_content: str, right_content: str, term_width: int) -> Tuple[int, int]:
    """Calculate optimal widths for side-by-side panels with overflow protection."""
    available_width = term_width - PANEL_PADDING - COLUMN_SPACING

    left_max = max((len(line) for line in left_content.splitlines()), default=0)
    right_max = max((len(line) for line in right_content.splitlines()), default=0)

    left_max = max(PANEL_MIN_WIDTH, min(left_max, PANEL_MAX_WIDTH))
    right_max = max(PANEL_MIN_WIDTH, min(right_max, PANEL_MAX_WIDTH))

    if (left_max + right_max) <= available_width:
        return left_max, right_max

    ratio = left_max / (left_max + right_max)
    left_width = min(
        PANEL_MAX_WIDTH,
        max(PANEL_MIN_WIDTH, int(available_width * ratio))
    )
    right_width = min(
        PANEL_MAX_WIDTH,
        max(PANEL_MIN_WIDTH, available_width - left_width)
    )

    return left_width, right_width

def create_panel_text(title: str, content: str, width: int) -> Text:
    """Create a text container with centered title."""
    text = Text()
    title_padding = (width - len(title)) // 2
    color = "red" if title == "Original" else "green"
    text.append(" " * title_padding + title + " " * title_padding, style=f"{color} bold")
    text.append("\n")
    text.append(content)
    return text

def create_header(header_text: str, term_width: int, bg_color: str = "dark_blue",
                 include_rule: bool = True) -> Text:
    """Create a centered header with optional horizontal rule.

    Args:
        header_text: Text to display in the header
        term_width: Width of the terminal
        bg_color: Background color for the header
        include_rule: Whether to include a horizontal rule below the header

    Returns:
        Rich Text object containing the formatted header
    """
    text = Text()
    
    # Calculate padding for centering
    padding = (term_width - len(header_text)) // 2
    
    # Create full-width background by padding both sides
    full_line = " " * padding + header_text + " " * (term_width - len(header_text) - padding)
    
    # Apply background color to entire line
    text.append(full_line, style=f"white on {bg_color}")
    text.append("\n")
    
    if include_rule:
        text.append("─" * term_width, style="dim")
    
    return text

def create_progress_header(edit_command: str, filename: str, current: int, total: int,
                         term_width: int, reason: str = None, style: str = "cyan") -> Tuple[Text, str]:
    """Create a header showing filename and global change counter.

    Args:
        edit_command: Type of edit command being performed
        filename: Name of the file being modified
        current: Current global change number
        total: Total number of changes
        term_width: Width of the terminal
        reason: Optional reason for the change
        style: Color style for the header

    Returns:
        Tuple of (Rich Text object, style)
    """
    header = f"{edit_command}: {filename} | Progress {current}/{total}"
    if reason:
        header += f" | {reason}"
    
    text = create_header(header, term_width, "dark_blue", include_rule=True)
    return text, style