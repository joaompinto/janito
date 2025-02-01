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

def _format_line(text: Text, line: str, line_type: str, width: int, min_indent: int = 0,
                full_width: bool = False) -> None:
    """Helper function to format a single line with consistent styling.
    
    Args:
        text: Text object to append formatted line to
        line: Line content to format
        line_type: Type of line (unchanged, added, deleted, etc.)
        width: Maximum line width
        min_indent: Minimum indentation to remove
        full_width: Whether to use full width background
    """
    bg_color = current_theme.line_backgrounds.get(line_type, current_theme.line_backgrounds['unchanged'])
    style = f"{current_theme.text_color} on {bg_color}"
    
    # Process line content
    processed_line = line
    if line.strip() and min_indent > 0:
        processed_line = line[min_indent:]
    
    # Handle line wrapping
    if len(processed_line) > width and not full_width:
        wrapped_lines = wrap(processed_line, width=width, break_long_words=True, break_on_hyphens=False)
        for wrapped in wrapped_lines:
            text.append(apply_line_style(wrapped, style, width, full_width))
    else:
        text.append(apply_line_style(processed_line, style, width, full_width))

def format_content(lines: List[str], search_lines: List[str] = None, replace_lines: List[str] = None,
                  is_search: bool = False, width: int = 80, is_delete: bool = False,
                  is_removal: bool = False, syntax_type: str = None, is_append: bool = False) -> Text:
    """Format content with appropriate styling based on operation type."""
    text = Text()
    min_indent = get_min_indent(lines)

    # Handle special cases first
    if is_delete or is_removal:
        line_type = 'removed' if is_removal else 'deleted'
        for line in lines:
            _format_line(text, line, line_type, width, min_indent, full_width=True)
        return text

    if is_append:
        for line in lines:
            _format_line(text, line, 'added', width, min_indent, full_width=True)
        return text

    # Regular diff formatting
    if search_lines and replace_lines:
        search_set = set(search_lines)
        replace_set = set(replace_lines)
        common_lines = search_set & replace_set

        for line in lines:
            if not line.strip():
                _format_line(text, "", 'unchanged', width)
            elif line in common_lines:
                _format_line(text, line, 'unchanged', width, min_indent)
            elif not is_search:
                _format_line(text, line, 'added', width, min_indent)
            else:
                _format_line(text, line, 'deleted', width, min_indent)

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