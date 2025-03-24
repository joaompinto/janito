"""
History management functions for Janito CLI.
"""
import sys
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import typer
from rich.console import Console
from rich.table import Table

from janito.config import get_config

console = Console()

def handle_history(history_flag: bool, history_count: Optional[int], ctx: typer.Context, query: Optional[str]) -> bool:
    """
    Handle the --history and --history-count parameters to display conversation history.
    
    Args:
        history_flag: Whether to show history (--history flag)
        history_count: Number of history entries to display (--history-count option or value after --history)
        ctx: Typer context
        query: Query string
        
    Returns:
        bool: True if the program should exit after this operation
    """
    # Check if either --history or --history-count was used
    if history_flag or history_count is not None:
        try:
            # If --history is used with a count value passed from app.py, use that
            # Otherwise, if --history-count is provided, use that
            # If neither specifies a count, default to 20
            count = 20 if history_count is None else history_count
            
            # Get the workspace directory
            workspace_dir = Path(get_config().workspace_dir)
            janito_dir = workspace_dir / ".janito"
            messages_dir = janito_dir / "last_messages"
            
            if not messages_dir.exists() or not any(messages_dir.iterdir()):
                console.print("[bold yellow]⚠️ No conversation history found[/bold yellow]")
                return True  # Always exit after displaying history
            
            # Find all message files and sort by timestamp (newest first)
            message_files = [f for f in messages_dir.iterdir() if f.is_file() and f.suffix == '.json']
            message_files.sort(key=lambda x: x.stem, reverse=True)
            
            # Limit to the requested number of entries
            message_files = message_files[:count]
            
            # Create a table for the history
            table = Table(title=f"Conversation History (Last {min(count, len(message_files))} Entries)")
            table.add_column("ID", style="cyan")
            table.add_column("Date", style="green")
            table.add_column("Time", style="green")
            table.add_column("First Query", style="yellow")
            
            # Add rows to the table
            for file in message_files:
                try:
                    with open(file, "r", encoding="utf-8") as f:
                        message_object = json.load(f)
                    
                    # Extract message ID and timestamp
                    message_id = message_object.get("id", file.stem)
                    
                    # Parse timestamp
                    timestamp_str = message_object.get("timestamp")
                    if timestamp_str:
                        timestamp = datetime.datetime.fromisoformat(timestamp_str)
                        date_str = timestamp.strftime("%Y-%m-%d")
                        time_str = timestamp.strftime("%H:%M:%S")
                    else:
                        # Fallback to file name which is a timestamp
                        timestamp_str = file.stem
                        date_str = timestamp_str[:8]  # YYYYMMDD
                        time_str = timestamp_str[8:]  # HHMMSS
                        
                        # Format the date and time
                        if len(date_str) == 8:
                            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                        if len(time_str) == 6:
                            time_str = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                    
                    # Extract the first user message
                    messages = message_object.get("messages", [])
                    first_query = "N/A"
                    for msg in messages:
                        if msg.get("role") == "user":
                            first_query = msg.get("content", "N/A")
                            # Truncate long queries
                            if len(first_query) > 60:
                                first_query = first_query[:57] + "..."
                            break
                    
                    table.add_row(message_id, date_str, time_str, first_query)
                except Exception as e:
                    table.add_row(file.stem, "Error", "Error", f"Failed to parse: {str(e)}")
            
            console.print(table)
            
            # Display information about how to continue conversations
            console.print("\n[bold blue]💡 To continue a conversation:[/bold blue]")
            script_name = "janito"
            if sys.argv[0].endswith(('janito', 'janito.exe')):
                console.print(f"  {script_name} --continue <ID> <request>")
            else:
                console.print(f"  python -m janito --continue <ID> <request>")
            
            # If --history flag is used, always exit regardless of whether a query is provided
            if history_flag:
                # Simply exit without showing a warning about ignored query
                return True
                
            # For --history-count, only exit if no query is provided
            # This maintains backward compatibility for commands like "janito --history-count 5 <query>"
            if history_count is not None and not query:
                return True
                
        except Exception as e:
            console.print(f"[bold red]Error displaying history:[/bold red] {str(e)}")
            return True  # Exit on error
            
    return False