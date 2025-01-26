from rich.text import Text
from rich.console import Console
from typing import List
from .diff import find_similar_lines
from .themes import DEFAULT_THEME, ColorTheme, ThemeType, get_theme_by_type

current_theme = DEFAULT_THEME

def set_theme(theme: ColorTheme) -> None:
    """Set the current color theme"""
    global current_theme
    current_theme = theme

def get_min_indent(lines: List[str]) -> int:
    """Calculate the minimum indentation level across all non-empty lines."""
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        return 0
    return min(len(line) - len(line.lstrip()) for line in non_empty_lines)

def apply_line_style(line: str, style: str, width: int, full_width: bool = False) -> Text:
    """Apply consistent styling to a single line with optional full width background"""
    text = Text()
    if full_width:
        # For full width, pad the entire line
        padded_line = line.ljust(width)
        text.append(padded_line, style=style)
    else:
        # Left align the content and pad to width
        text.append(line, style=style)
        padding = " " * max(0, width - len(line))
        text.append(padding, style=style)
    
    text.append("\n", style=style)
    return text

from textwrap import wrap

def format_content(lines: List[str], search_lines: List[str] = None, replace_lines: List[str] = None,
                  is_search: bool = False, width: int = 80, is_delete: bool = False, 
                  is_removal: bool = False, syntax_type: str = None, is_append: bool = False) -> Text:
    """Format content with appropriate styling based on operation type.
    
    Handles different content types:
    - Regular content with diff highlighting
    - Delete operations (red background)
    - Append operations (green background)
    - Text wrapping for long lines
    """
    text = Text()

    # For delete operations, show all content with red background in a single column
    if is_delete or is_removal:
        bg_color = current_theme.line_backgrounds['removed' if is_removal else 'deleted']
        style = f"{current_theme.text_color} on {bg_color}"
        min_indent = get_min_indent(lines)
        for line in lines:
            processed_line = line[min_indent:] if line.strip() else line
            text.append(apply_line_style(processed_line, style, width, full_width=True))
        return text

    # For append operations, show all lines as added
    if is_append:
        bg_color = current_theme.line_backgrounds['added']
        style = f"{current_theme.text_color} on {bg_color}"
        min_indent = get_min_indent(lines)
        for line in lines:
            if line.strip():
                line = line[min_indent:]
            text.append(apply_line_style(line, style, width, full_width=True))
        return text

    # Regular diff formatting
    if search_lines and replace_lines:
        # Find similar lines for better diff visualization
        similar_pairs = find_similar_lines(search_lines, replace_lines)
        similar_added = {j for _, j, _ in similar_pairs}
        similar_deleted = {i for i, _, _ in similar_pairs}

        # Create sets for comparison
        search_set = set(search_lines)
        replace_set = set(replace_lines)
        common_lines = search_set & replace_set

        def add_line(line: str, line_type: str = 'unchanged'):
            bg_color = current_theme.line_backgrounds.get(line_type, current_theme.line_backgrounds['unchanged'])
            style = f"{current_theme.text_color} on {bg_color}"

            if syntax_type == 'python':
                # Just use the background color without syntax highlighting
                text.append(apply_line_style(line, style, width))
                return

            # Wrap long lines
            if len(line) > width:
                wrapped_lines = wrap(line, width=width, break_long_words=True, break_on_hyphens=False)
                for wrapped in wrapped_lines:
                    text.append(apply_line_style(wrapped, style, width))
            else:
                text.append(apply_line_style(line, style, width))

        for i, line in enumerate(lines):
            if not line.strip():  # Handle empty lines
                add_line("", 'unchanged')
            elif line in common_lines:
                add_line(line, 'unchanged')
            elif not is_search:
                add_line(line, 'added')
            else:
                add_line(line, 'deleted')

    return text

from rich.panel import Panel
from rich.columns import Columns

def create_legend_items(console: Console) -> Panel:
    """Create a compact legend panel with color blocks

    Args:
        console: Console instance for width calculation
    """
    text = Text()
    term_width = console.width or 120

    # Add color blocks for each type
    for label, bg_type in [("Unchanged", "unchanged"),
                          ("Deleted", "deleted"),
                          ("Added", "added")]:
        style = f"{current_theme.text_color} on {current_theme.line_backgrounds[bg_type]}"
        text.append("  ", style=style)  # Color block
        text.append(" " + label + " ")  # Label with spacing

    return Panel(
        text,
        padding=(0, 1),
        expand=False,
        title="Legend",
        title_align="center"
    )