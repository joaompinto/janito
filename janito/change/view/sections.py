from typing import List, Tuple, Set

def find_modified_sections(original: list[str], modified: list[str], context_lines: int = 3) -> list[tuple[list[str], list[str]]]:
    """
    Find modified sections between original and modified text with surrounding context.
    Merges sections with separator lines.

    Args:
        original: List of original lines
        modified: List of modified linesn
        context_lines: Number of unchanged context lines to include

    Returns:
        List of tuples containing (original_section, modified_section) line pairs
    """
    # Find different lines
    different_lines = get_different_lines(original, modified)
    if not different_lines:
        return []

    return create_sections(original, modified, different_lines, context_lines)

def get_different_lines(original: List[str], modified: List[str]) -> Set[int]:
    """Find lines that differ between original and modified content"""
    different_lines = set()
    for i in range(max(len(original), len(modified))):
        if i >= len(original) or i >= len(modified):
            different_lines.add(i)
        elif original[i] != modified[i]:
            different_lines.add(i)
    return different_lines

def create_sections(original: List[str], modified: List[str], 
                   different_lines: Set[int], context_lines: int) -> List[Tuple[List[str], List[str]]]:
    """Create sections from different lines with context"""
    current_section = set()
    orig_content = []
    mod_content = []

    for line_num in sorted(different_lines):
        if not current_section or line_num <= max(current_section) + context_lines * 2:
            current_section.add(line_num)
        else:
            process_section(original, modified, current_section, orig_content, 
                          mod_content, context_lines)
            current_section = {line_num}

    if current_section:
        process_section(original, modified, current_section, orig_content, 
                       mod_content, context_lines)

    return [(orig_content, mod_content)] if orig_content else []

def process_section(original: List[str], modified: List[str], 
                   current_section: Set[int], orig_content: List[str], 
                   mod_content: List[str], context_lines: int) -> None:
    """Process a section and add it to the content lists"""
    start = max(0, min(current_section) - context_lines)
    end = min(max(len(original), len(modified)),
             max(current_section) + context_lines + 1)

    # Add separator if needed
    if orig_content:
        orig_content.append("...")
        mod_content.append("...")

    # Add section content
    orig_content.extend(original[start:end])
    mod_content.extend(modified[start:end])
