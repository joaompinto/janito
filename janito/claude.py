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
from janito.utils import generate_file_structure, format_tree, get_files_content  # Update import
from janito.prompts import SYSTEM_PROMPT, build_info_prompt, build_change_prompt, build_general_prompt  # Add to imports

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
        self.system_message = "You are Janito, an AI assistant focused on Python software development."
        self.last_prompt = None
        self.last_full_message = None
        self.last_response = None

    def _get_files_content(self) -> str:
        return get_files_content(Path().absolute())

    def _show_progress(self, description: str):
        """Show progress spinner while waiting"""
        # Create new Progress instance each time
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task(description, total=None)
            while not self.stop_progress.is_set():
                progress.update(task)
                time.sleep(0.1)

    def send_message(self, message: str, system_prompt: str = None) -> str:
        """Send message to Claude API and return response"""
        try:
            # Store the full message including system prompt
            self.last_full_message = f"""=== SYSTEM PROMPT ===
{system_prompt or self.system_message}

=== USER MESSAGE ===
{message}"""
            
            # Start progress indicator
            self.stop_progress.clear()
            progress_thread = threading.Thread(
                target=self._show_progress,
                args=("Waiting for Claude's response...",)
            )
            progress_thread.start()
            
            try:
                response = self.client.messages.create(
                    model="claude-3-sonnet-20240229",
                    system=self.system_message,
                    max_tokens=4096,
                    messages=[
                        {"role": "user", "content": message}
                    ]
                )
                response_text = response.content[0].text
                self.last_response = response_text  # Add this line
            finally:
                self.stop_progress.set()
                progress_thread.join()
            
            if self.debug:
                print("\n[Debug] Received response:")
                print("=" * 80)
                print(response_text)
                print("=" * 80)
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            return response_text
            
        except Exception as e:
            self.stop_progress.set()
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
    
    def handle_info_request(self, request: str, workspace_status: str) -> str:
        """Handle information request without file modifications"""
        files_content = self._get_files_content()
        message = build_info_prompt(files_content, request)
        return self.send_message(message)