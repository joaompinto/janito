"""
Janito tools package.
"""

from .str_replace_editor import str_replace_editor
from .find_files import find_files
from .delete_file import delete_file
from .search_text import search_text
from .replace_file import replace_file
from .prompt_user import prompt_user
from .move_file import move_file
from janito.tools.fetch_webpage import fetch_webpage
from .think import think
from .usage_tracker import get_tracker, reset_tracker, print_usage_stats
from janito.config import get_config

__all__ = ["str_replace_editor", "find_files", "delete_file", "search_text", "replace_file", 
           "prompt_user", "move_file", "fetch_webpage", "think", "get_tools", 
           "get_tracker", "reset_tracker", "print_usage_stats"]

def get_tools():
    """
    Get a list of all available tools.
    
    Returns:
        List of tool functions (excluding str_replace_editor which is passed separately)
        If no_tools mode is enabled, returns an empty list
        If ask_mode is enabled, only returns tools that don't perform changes
    """
    # If no_tools mode is enabled, return an empty list
    if get_config().no_tools:
        return []
        
    # Tools that only read or view but don't modify anything
    read_only_tools = [find_files, search_text, prompt_user, fetch_webpage, think]
    
    # Tools that modify the filesystem
    write_tools = [delete_file, replace_file, move_file]
    
    # If ask_mode is enabled, only return read-only tools
    if get_config().ask_mode:
        return read_only_tools
    else:
        return read_only_tools + write_tools
