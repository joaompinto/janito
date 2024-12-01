from rich.traceback import install  # Add import at top
import anthropic
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from hashlib import sha256
import re
import threading
from typing import List, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn
from threading import Event
import time
from janito.prompts import SYSTEM_PROMPT, build_info_prompt, build_change_prompt, build_general_prompt  # Update imports

# Install rich traceback handler
install(show_locals=True)

class ClaudeAPIAgent:
    """Handles interaction with Claude API, including message handling"""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = anthropic.Client(api_key=self.api_key)
        self.conversation_history = []
        self.debug = False
        self.stop_progress = Event()
        self.system_message = SYSTEM_PROMPT
        self.last_prompt = None
        self.last_full_message = None
        self.last_response = None
        # Remove workspace instance since it's not used

    # Remove _get_files_content method since it's not used

    def send_message(self, message: str, system_prompt: str = None, stop_event: Event = None) -> str:
        """Send message to Claude API and return response"""
        try:
            # Store the full message
            self.last_full_message = message
            
            try:
                # Check if already cancelled
                if stop_event and stop_event.is_set():
                    return ""
                
                # Start API request
                response = self.client.messages.create(
                    model="claude-3-opus-20240229",
                    system=self.system_message,
                    max_tokens=4000,
                    messages=[
                        {"role": "user", "content": message}
                    ],
                    temperature=0,
                )
                
                # Handle response
                response_text = response.content[0].text
                
                # Only store and process response if not cancelled
                if not (stop_event and stop_event.is_set()):
                    self.last_response = response_text
                    
                    if self.debug:
                        print("\n[Debug] Received response:")
                        print("=" * 80)
                        print(response_text)
                        print("=" * 80)
                    
                    # Update conversation history
                    self.conversation_history.append({"role": "user", "content": message})
                    self.conversation_history.append({"role": "assistant", "content": response_text})
                
                # Always return the response, let caller handle cancellation
                return response_text
                
            except KeyboardInterrupt:
                if stop_event:
                    stop_event.set()
                return ""
                
        except Exception as e:
            if stop_event and stop_event.is_set():
                return ""
            return f"Error: {str(e)}"

    def toggle_debug(self) -> str:
        """Toggle debug mode on/off"""
        self.debug = not self.debug
        return f"Debug mode {'enabled' if self.debug else 'disabled'}"
    
    def clear_history(self) -> str:
        self.conversation_history = []
        return "Conversation history cleared"
    
    def save_history(self, filename: str) -> str:
        try:
            with open(filename, 'w') as f:
                json.dump(self.conversation_history, f)
            return f"History saved to {filename}"
        except Exception as e:
            return f"Error saving history: {str(e)}"
    
    def load_history(self, filename: str) -> str:
        try:
            with open(filename, 'r') as f:
                self.conversation_history = json.load(f)
            return f"History loaded from {filename}"
        except Exception as e:
            return f"Error loading history: {str(e)}"