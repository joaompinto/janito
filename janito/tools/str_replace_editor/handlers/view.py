"""
Handler for the view command in str_replace_editor.
"""
import os
import pathlib
from typing import Dict, Any, Tuple
from janito.config import get_config
from janito.tools.rich_console import print_info, print_error, console
from janito.tools.usage_tracker import get_tracker
from ..utils import normalize_path

def handle_view(args: Dict[str, Any]) -> Tuple[str, bool]:
    """
    View the contents of a file or list directory contents.
    
    Args:
        args: Dictionary containing:
            - path: Path to the file or directory to view
            - view_range (optional): Array of two integers specifying start and end line numbers
        
    Returns:
        A tuple containing (content_or_message, is_error)
    """
    path = args.get("path")
    view_range = args.get("view_range")
    
    # First normalize the path to check if it's a file or directory
    normalized_path = normalize_path(path)
    file_path = pathlib.Path(normalized_path)
    
    if file_path.exists():
        if file_path.is_dir():
            print_info(f"Viewing directory: {path}: ", "Directory View")
        else:
            if view_range:
                # Print with proper title for File View
                print_info(f"Viewing file: {path}, from line {view_range[0]} to {view_range[1]}: ", "File View")
            else:
                # Print with proper title for File View
                print_info(f"Viewing file: {path}, all lines: ", "File View")
    else:
        # If path doesn't exist yet, assume it's a file (will be validated later)
        if view_range:
            # Print with proper title for File View
            print_info(f"Viewing file: {path}, from line {view_range[0]} to {view_range[1]}: ", "File View")
        else:
            # Print with proper title for File View
            print_info(f"Viewing file: {path}, all lines: ", "File View")
    
    if not path:
        print_error("Missing required parameter: path", "Error")
        return ("Missing required parameter: path", True)
    
    path = normalize_path(path)
    file_path = pathlib.Path(path)
    
    if not file_path.exists():
        print_error(f"File or directory {path} does not exist", "Error")
        return (f"File or directory {path} does not exist", True)
    
    # If the path is a directory, list non-hidden files and directories up to 2 levels deep
    if file_path.is_dir():
        try:
            result = []
            # Process the first level
            for item in sorted(file_path.iterdir()):
                if item.name.startswith('.'):
                    continue  # Skip hidden files/directories
                
                if item.is_dir():
                    result.append(f"{item.name}/")
                    # Process the second level
                    try:
                        for subitem in sorted(item.iterdir()):
                            if subitem.name.startswith('.'):
                                continue  # Skip hidden files/directories
                                
                            if subitem.is_dir():
                                result.append(f"{item.name}/{subitem.name}/")
                            else:
                                result.append(f"{item.name}/{subitem.name}")
                    except PermissionError:
                        # Skip directories we can't access
                        pass
                else:
                    result.append(item.name)
            
            if not result:
                return (f"Directory {path} is empty or contains only hidden files", False)
            
            # Track directory view
            get_tracker().increment('file_views')
            
            # Directory listings should not be truncated
            file_dir_count = len(result)
            output = "\n".join(result)
            console.print(f"Found ", style="default", end="")
            console.print(f"{file_dir_count}", style="cyan", end="")
            console.print(" files and directories")
            return (output, False)
        except Exception as e:
            return (f"Error listing directory {path}: {str(e)}", True)
    
    # If the path is a file, view its contents with cat -n style output
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        # If view_range is specified, return only the specified lines
        if view_range:
            start_line = max(1, view_range[0]) - 1  # Convert to 0-indexed
            end_line = view_range[1] if view_range[1] != -1 else len(content)
            end_line = min(end_line, len(content))
            
            # Adjust content to only include the specified lines
            content = content[start_line:end_line]
            
            # Track partial file view
            get_tracker().increment('partial_file_views')
        else:
            # Track full file view
            get_tracker().increment('file_views')
        
        # Add line numbers to each line (cat -n style)
        numbered_content = []
        start_idx = 1 if view_range is None else view_range[0]
        for i, line in enumerate(content):
            line_number = start_idx + i
            # Ensure line ends with newline
            if not line.endswith('\n'):
                line += '\n'
            # Format line number in cyan color using Rich's styling
            # Use a simpler approach with f-strings and Rich's console
            
            # Create a string with the line number that will be styled as cyan
            line_num_str = f"{line_number:6d}\t{line}"
            numbered_content.append(line_num_str)
        
        # Check if we need to truncate the output
        MAX_LINES = 500  # Arbitrary limit for demonstration
        if len(numbered_content) > MAX_LINES:
            truncated_content = "".join(numbered_content[:MAX_LINES])
            print(truncated_content + "\n<response clipped>")
            return (truncated_content + "\n<response clipped>", False)
        
        content_to_print = "".join(numbered_content)
        console.print("(", style="default", end="")
        console.print(f"{len(numbered_content)}", style="cyan", end="")
        console.print(")")
        # Return the content as a string without any Rich objects
        return (content_to_print, False)
    except Exception as e:
        return (f"Error viewing file {path}: {str(e)}", True)