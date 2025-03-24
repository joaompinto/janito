"""
Conversation management functionality for Janito CLI.
"""
import json
import datetime
import sys
from typing import Optional, List, Dict, Any
from rich.console import Console
from pathlib import Path
import claudine

from janito.config import get_config

console = Console()

def generate_message_id() -> str:
    """
    Generate a message ID based on timestamp with seconds granularity
    
    Returns:
        str: A timestamp-based message ID
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    return timestamp

def save_messages(agent: claudine.Agent) -> Optional[str]:
    """
    Save agent messages to .janito/last_messages/{message_id}.json
    
    Args:
        agent: The claudine agent instance
        
    Returns:
        str: The message ID used for saving, or None if saving failed
    """
    try:
        # Get the workspace directory
        workspace_dir = Path(get_config().workspace_dir)
        
        # Create .janito directory if it doesn't exist
        janito_dir = workspace_dir / ".janito"
        janito_dir.mkdir(exist_ok=True)
        
        # Create last_messages directory if it doesn't exist
        messages_dir = janito_dir / "last_messages"
        messages_dir.mkdir(exist_ok=True)
        
        # Generate a unique message ID
        message_id = generate_message_id()
        
        # Get messages from the agent
        messages = agent.get_messages()
        
        # Create a message object with metadata
        message_object = {
            "id": message_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "messages": messages
        }
        
        # Save messages to file
        message_file = messages_dir / f"{message_id}.json"
        with open(message_file, "w", encoding="utf-8") as f:
            json.dump(message_object, f, ensure_ascii=False, indent=2)
            
        if get_config().verbose:
            console.print(f"[bold green]✅ Conversation saved to {message_file}[/bold green]")
            
        return message_id
    except Exception as e:
        console.print(f"[bold red]❌ Error saving conversation:[/bold red] {str(e)}")
        return None

def load_messages(message_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Load messages from .janito/last_messages/{message_id}.json or the latest message file
    
    Args:
        message_id: Optional message ID to load specific conversation
        
    Returns:
        List of message dictionaries or None if file doesn't exist
    """
    try:
        # Get the workspace directory
        workspace_dir = Path(get_config().workspace_dir)
        janito_dir = workspace_dir / ".janito"
        messages_dir = janito_dir / "last_messages"
        
        # If message_id is provided, try to load that specific conversation
        if message_id:
            # Check if the message ID is a file name or just the ID
            if message_id.endswith('.json'):
                message_file = messages_dir / message_id
            else:
                message_file = messages_dir / f"{message_id}.json"
                
            if not message_file.exists():
                console.print(f"[bold yellow]⚠️ No conversation found with ID {message_id}[/bold yellow]")
                return None
                
            # Load messages from file
            with open(message_file, "r", encoding="utf-8") as f:
                message_object = json.load(f)
                
            # Extract messages from the message object
            if isinstance(message_object, dict) and "messages" in message_object:
                messages = message_object["messages"]
            else:
                # Handle legacy format
                messages = message_object
                
            if get_config().verbose:
                console.print(f"[bold green]✅ Loaded conversation from {message_file}[/bold green]")
                console.print(f"[dim]📝 Conversation has {len(messages)} messages[/dim]")
                
            return messages
        
        # If no message_id is provided, try to load the latest message from last_messages directory
        if not messages_dir.exists() or not any(messages_dir.iterdir()):
            console.print("[bold yellow]⚠️ No previous conversation found[/bold yellow]")
            return None
        
        # Find the latest message file (based on filename which is a timestamp)
        latest_file = max(
            [f for f in messages_dir.iterdir() if f.is_file() and f.suffix == '.json'],
            key=lambda x: x.stem
        )
        
        # Load messages from the latest file
        with open(latest_file, "r", encoding="utf-8") as f:
            message_object = json.load(f)
            
        # Extract messages from the message object
        if isinstance(message_object, dict) and "messages" in message_object:
            messages = message_object["messages"]
        else:
            # Handle legacy format
            messages = message_object
            
        if get_config().verbose:
            console.print(f"[bold green]✅ Loaded latest conversation from {latest_file}[/bold green]")
            console.print(f"[dim]📝 Conversation has {len(messages)} messages[/dim]")
            
        return messages
    except Exception as e:
        console.print(f"[bold red]❌ Error loading conversation:[/bold red] {str(e)}")
        return None

