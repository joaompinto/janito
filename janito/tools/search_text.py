import os
import fnmatch
import re
import glob
from typing import List, Tuple
from janito.tools.rich_console import print_info, print_success, print_error, print_warning
from janito.tools.usage_tracker import track_usage


@track_usage('search_operations')
def search_text(text_pattern: str, file_pattern: str = "*", root_dir: str = ".", recursive: bool = True) -> Tuple[str, bool]:
    """
    Search for text patterns within files matching a filename pattern.
    Files in .gitignore are always ignored.
    
    Args:
        text_pattern: Text pattern to search for within files
        file_pattern: Pattern to match file paths against (e.g., "*.py", "*/tools/*.py")
                     Multiple patterns can be specified using semicolons or spaces as separators
        root_dir: Root directory to start search from (default: current directory)
        recursive: Whether to search recursively in subdirectories (default: True)
        
    Returns:
        A tuple containing (message, is_error)
    """
    # Simplified initial message
    print_info(f"Searching for '{text_pattern}' in '{file_pattern}'", "Text Search")
    try:
        # Convert to absolute path if relative
        abs_root = os.path.abspath(root_dir)
        
        if not os.path.isdir(abs_root):
            error_msg = f"Error: Directory '{root_dir}' does not exist"
            print_error(error_msg, "Directory Error")
            return error_msg, True
        
        # Compile the regex pattern for better performance
        try:
            regex = re.compile(text_pattern)
        except re.error:
            # Simplified error message without the specific regex error details
            error_msg = f"Error: Invalid regex pattern '{text_pattern}'"
            print_error(error_msg, "Search Error")
            return error_msg, True
        
        matching_files = []
        match_count = 0
        results = []
        
        # Get gitignore patterns
        ignored_patterns = _get_gitignore_patterns(abs_root)
        
        # Handle multiple patterns separated by semicolons or spaces
        patterns = []
        if ';' in file_pattern:
            patterns = file_pattern.split(';')
        elif ' ' in file_pattern and not (os.path.sep in file_pattern or '/' in file_pattern):
            # Only split by space if the pattern doesn't appear to be a path
            patterns = file_pattern.split()
        else:
            patterns = [file_pattern]
        
        # Process each pattern
        for pattern in patterns:
            # Construct the glob pattern with the root directory
            glob_pattern = os.path.join(abs_root, pattern) if not pattern.startswith(os.path.sep) else pattern
            
            # Use recursive glob if needed
            if recursive:
                # Use ** pattern for recursive search if not already in the pattern
                if '**' not in glob_pattern:
                    # Check if the pattern already has a directory component
                    if os.path.sep in pattern or '/' in pattern:
                        # Pattern already has directory component, keep as is
                        pass
                    else:
                        # Add ** to search in all subdirectories
                        glob_pattern = os.path.join(abs_root, '**', pattern)
                
                # Use recursive=True for Python 3.5+ glob
                glob_files = glob.glob(glob_pattern, recursive=True)
            else:
                # Non-recursive mode - only search in the specified directory
                glob_files = glob.glob(glob_pattern)
            
            # Process matching files
            for file_path in glob_files:
                # Skip directories and already processed files
                if not os.path.isfile(file_path) or file_path in matching_files:
                    continue
                    
                # Skip ignored files
                if _is_ignored(file_path, ignored_patterns, abs_root):
                    continue
                
                file_matches = _search_file(file_path, regex, abs_root)
                if file_matches:
                    matching_files.append(file_path)
                    match_count += len(file_matches)
                    results.append(f"\n{os.path.relpath(file_path, abs_root)} ({len(file_matches)} matches):")
                    results.extend(file_matches)
        
        if matching_files:
            # Only print the count summary, not the full results
            summary = f"{match_count} matches in {len(matching_files)} files"
            print_success(summary, "Search Results")
            
            # Still return the full results for programmatic use
            result_text = "\n".join(results)
            result_msg = f"Searching for '{text_pattern}' in files matching '{file_pattern}':{result_text}\n{summary}"
            return result_msg, False
        else:
            result_msg = f"No matches found for '{text_pattern}' in files matching '{file_pattern}'"
            print_warning("No matches found.")
            return result_msg, False
            
    except Exception as e:
        error_msg = f"Error searching text: {str(e)}"
        print_error(error_msg, "Search Error")
        return error_msg, True


def _search_file(file_path: str, pattern: re.Pattern, root_dir: str) -> List[str]:
    """
    Search for regex pattern in a file and return matching lines with line numbers.
    
    Args:
        file_path: Path to the file to search
        pattern: Compiled regex pattern to search for
        root_dir: Root directory (for path display)
        
    Returns:
        List of formatted matches with line numbers and content
    """
    matches = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f, 1):
                if pattern.search(line):
                    # Truncate long lines for display
                    display_line = line.strip()
                    if len(display_line) > 100:
                        display_line = display_line[:97] + "..."
                    matches.append(f"  Line {i}: {display_line}")
    except (UnicodeDecodeError, IOError):
        # Skip binary files or files with encoding issues
        pass
    return matches


def _get_gitignore_patterns(root_dir: str) -> List[str]:
    """
    Get patterns from .gitignore files.
    
    Args:
        root_dir: Root directory to start from
        
    Returns:
        List of gitignore patterns
    """
    patterns = []
    
    # Check for .gitignore in the root directory
    gitignore_path = os.path.join(root_dir, '.gitignore')
    if os.path.isfile(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        patterns.append(line)
        except Exception:
            pass
    
    # Add common patterns that are always ignored
    common_patterns = [
        '.git/', '.venv/', 'venv/', '__pycache__/', '*.pyc', 
        '*.pyo', '*.pyd', '.DS_Store', '*.so', '*.egg-info/'
    ]
    patterns.extend(common_patterns)
    
    return patterns


def _is_ignored(path: str, patterns: List[str], root_dir: str) -> bool:
    """
    Check if a path should be ignored based on gitignore patterns.
    
    Args:
        path: Path to check
        patterns: List of gitignore patterns
        root_dir: Root directory for relative paths
        
    Returns:
        True if the path should be ignored, False otherwise
    """
    # Get the relative path from the root directory
    rel_path = os.path.relpath(path, root_dir)
    
    # Convert to forward slashes for consistency with gitignore patterns
    rel_path = rel_path.replace(os.sep, '/')
    
    # Add trailing slash for directories
    if os.path.isdir(path) and not rel_path.endswith('/'):
        rel_path += '/'
    
    for pattern in patterns:
        # Handle negation patterns (those starting with !)
        if pattern.startswith('!'):
            continue  # Skip negation patterns for simplicity
        
        # Handle directory-specific patterns (those ending with /)
        if pattern.endswith('/'):
            if os.path.isdir(path) and fnmatch.fnmatch(rel_path, pattern + '*'):
                return True
        
        # Handle file patterns
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        
        # Handle patterns without wildcards as path prefixes
        if '*' not in pattern and '?' not in pattern and rel_path.startswith(pattern):
            return True
    
    return False