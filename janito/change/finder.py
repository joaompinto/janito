from typing import List, Tuple, Optional
from difflib import SequenceMatcher
import os
import sys
import argparse

class EditContentNotFoundError(Exception):
    """Raised when edit content cannot be found in the file."""
    pass



def find_range(full_lines: List[str], changed_lines: List[str], start: int = 0) -> Tuple[int, int]:
    if start < 0 or start >= len(full_lines):
        raise ValueError("Invalid start position")

    def exact_match(start: int) -> Tuple[int, int]:
        for i in range(start, len(full_lines) - len(changed_lines) + 1):
            if full_lines[i:i + len(changed_lines)] == changed_lines:
                return i, i + len(changed_lines)  # Note: This returns exclusive end index
        return None

    def indent_match(start: int) -> Tuple[int, int]:
        def get_indent(line: str) -> int:
            return len(line) - len(line.lstrip())

        for i in range(start, len(full_lines) - len(changed_lines) + 1):
            if all(get_indent(full_lines[i + j]) == get_indent(changed_lines[j]) and full_lines[i + j].lstrip() == changed_lines[j].lstrip() for j in range(len(changed_lines))):
                return i, i + len(changed_lines)  # Changed to exclusive end index
        return None

    def stripped_match(start: int) -> Tuple[int, int]:
        stripped_changed_lines = [line.strip() for line in changed_lines]
        for i in range(start, len(full_lines) - len(changed_lines) + 1):
            if all(full_lines[i + j].strip() == stripped_changed_lines[j] for j in range(len(changed_lines))):
                return i, i + len(changed_lines)  # Changed to exclusive end index
        return None

    # Try each strategy in order
    for strategy in [exact_match, indent_match, stripped_match]:
        result = strategy(start)
        if result:
            return result

    raise EditContentNotFoundError("Code block not found in the file")


def _parse_debug_file(debug_file_path: str) -> Tuple[List[str], List[str]]:
    """Parse a debug file containing FIND: and ORIGINAL: sections.
    
    Returns:
        Tuple[List[str], List[str]]: (original_content, find_pattern)
        - original_content: The file content to search in
        - find_pattern: The code block to find
        
    The debug file format helps diagnose matching failures by showing:
    - What we're trying to find (FIND: section)
    - Where we're trying to find it (ORIGINAL: section)
    - What went wrong if it failed (ERROR: section)
    """
    with open(debug_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into sections using the headers
    sections = {}
    current_section = None
    current_lines = []
    
    for line in content.splitlines():
        # Check for section headers
        if line in ["FIND:", "ORIGINAL:", "ERROR:"]:
            if current_section:
                sections[current_section] = current_lines
            current_section = line.rstrip(':')
            current_lines = []
            continue
            
        # Only collect lines if we're in a section
        if current_section:
            current_lines.append(line)
    
    # Store the last section
    if current_section:
        sections[current_section] = current_lines
    
    if 'FIND' not in sections or 'ORIGINAL' not in sections:
        raise ValueError("Debug file must contain both 'FIND:' and 'ORIGINAL:' sections")
    
    # Remove empty lines at start/end of each section but keep empty lines in middle
    find_content = _trim_empty_lines(sections['FIND'])
    original_content = _trim_empty_lines(sections['ORIGINAL'])
    
    # Return original_content first (the content to search in), then find_content (the pattern to find)
    return original_content, find_content

def _trim_empty_lines(lines: List[str]) -> List[str]:
    """Remove empty lines from start and end but keep them in the middle."""
    # Find first non-empty line
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
        
    # Find last non-empty line
    end = len(lines)
    while end > start and not lines[end - 1].strip():
        end -= 1
        
    return lines[start:end]

def main():
    
    # Set DEBUG flag when running directly
    os.environ['DEBUG'] = '1'
    
    parser = argparse.ArgumentParser(description='Test content finding in a debug file')
    parser.add_argument('debug_file', help='Path to the debug file')
    args = parser.parse_args()
    
    try:
        full_content, search_content = _parse_debug_file(args.debug_file)
        
        print(f"Searching for {len(search_content)} lines in content of {len(full_content)} lines")
        print("\nSearch content:")
        print("-" * 40)
        print("\n".join(search_content))
        print("-" * 40)
        
        try:
            match_range = find_range(full_content, search_content)
            print(f"\nFound match at lines {match_range[0]+1}-{match_range[1]}")
            print("\nMatched content:")
            print("-" * 40)
            print("\n".join(full_content[match_range[0]:match_range[1]]))
            print("-" * 40)
        except EditContentNotFoundError as e:
            print(f"\nError: {str(e)}")
            
    except Exception as e:
        print(f"Error processing debug file: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()