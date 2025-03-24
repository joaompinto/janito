"""
Tool usage tracking module for Janito.

This module provides functionality to track tool usage statistics
such as files modified, created, deleted, and lines replaced.
"""

from functools import wraps
from typing import Dict, Any, Callable
import threading

# Global tracker instance
_tracker = None
_tracker_lock = threading.Lock()

class ToolUsageTracker:
    """Tracks usage statistics for Janito tools."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all counters to zero."""
        self.files_modified = 0
        self.files_created = 0
        self.files_deleted = 0
        self.files_moved = 0
        self.lines_replaced = 0
        self.lines_delta = 0  # Track the net change in number of lines
        self.web_requests = 0
        self.bash_commands = 0
        self.user_prompts = 0
        self.search_operations = 0
        self.file_views = 0
        self.partial_file_views = 0
        self.thoughts = 0  # Track the number of thoughts recorded
    
    def increment(self, counter_name: str, value: int = 1):
        """Increment a specific counter by the given value."""
        if hasattr(self, counter_name):
            setattr(self, counter_name, getattr(self, counter_name) + value)
    
    def get_stats(self) -> Dict[str, int]:
        """Get all non-zero statistics as a dictionary."""
        stats = {}
        for attr_name in dir(self):
            if not attr_name.startswith('_') and not callable(getattr(self, attr_name)):
                value = getattr(self, attr_name)
                if value > 0:
                    # Convert attribute_name to "Attribute Name" format
                    display_name = ' '.join(word.capitalize() for word in attr_name.split('_'))
                    stats[display_name] = value
        return stats


def get_tracker() -> ToolUsageTracker:
    """Get the global tracker instance."""
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = ToolUsageTracker()
    return _tracker


def reset_tracker():
    """Reset the global tracker."""
    get_tracker().reset()


def track_usage(counter_name: str, increment_value: int = 1):
    """
    Decorator to track tool usage.
    
    Args:
        counter_name: The name of the counter to increment
        increment_value: Value to increment the counter by (default: 1)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            # Only track successful operations
            if isinstance(result, tuple) and len(result) >= 2:
                message, is_error = result[0], result[1]
                if not is_error:
                    get_tracker().increment(counter_name, increment_value)
            return result
        return wrapper
    return decorator


def count_lines_in_string(old_str: str, new_str: str) -> tuple[int, int]:
    """
    Count the number of lines that differ between old_str and new_str.
    
    Args:
        old_str: Original string
        new_str: New string
        
    Returns:
        Tuple of (number of lines that differ, line delta)
    """
    old_lines = old_str.splitlines()
    new_lines = new_str.splitlines()
    
    # Calculate the line delta (positive for added lines, negative for removed lines)
    line_delta = len(new_lines) - len(old_lines)
    
    # Simple approach: count the total number of lines changed
    # For tracking purposes, we'll use the max to ensure we don't undercount
    return max(len(old_lines), len(new_lines)), line_delta


def print_usage_stats():
    """Print the current usage statistics if any values are non-zero."""
    stats = get_tracker().get_stats()
    if stats:
        from rich.console import Console
        
        console = Console()
        
        # Create a single-line summary of tool usage
        summary_parts = []
        for name, value in stats.items():
            # Format lines delta with a sign
            if name == "Lines Delta":
                sign = "+" if value > 0 else "" if value == 0 else "-"
                formatted_value = f"{sign}{abs(value)}"
                summary_parts.append(f"{name}: {formatted_value}")
            else:
                summary_parts.append(f"{name}: {value}")
        
        summary = " | ".join(summary_parts)
        
        # Display with a rule similar to token usage
        console.rule("[blue]Tool Usage[/blue]")
        console.print(f"[blue]{summary}[/blue]", justify="center")