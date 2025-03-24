"""
Tool for thinking about something without obtaining new information or changing the database.
"""
from typing import Tuple
import logging
from janito.tools.usage_tracker import track_usage
from janito.tools.rich_console import print_info

# Set up logging
logger = logging.getLogger(__name__)

@track_usage('thoughts')
def think(
    thought: str,
) -> Tuple[str, bool]:
    """
    Use the tool to think about something. It will not obtain new information or change the database,
    but just append the thought to the log. Use it when complex reasoning or some cache memory is needed.
    
    Args:
        thought: A thought to think about.
        
    Returns:
        A tuple containing (message, is_error)
    """
    try:
        # Log the thought
        logger.info(f"Thought: {thought}")
        
        # Print a confirmation message
        print_info(f"Thought recorded: {thought[:50]}{'...' if len(thought) > 50 else ''}", "Thinking")
        
        return (f"Thought recorded: {thought}", False)
    except Exception as e:
        error_msg = f"Error recording thought: {str(e)}"
        logger.error(error_msg)
        return (error_msg, True)