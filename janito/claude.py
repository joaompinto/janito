from rich.traceback import install
import anthropic
import os
from typing import Optional
from rich.progress import Progress, SpinnerColumn, TextColumn
from threading import Event

# Install rich traceback handler
install(show_locals=True)

class ClaudeAPIAgent:
    """Handles interaction with Claude API, including message handling"""
    def __init__(self, api_key: Optional[str] = None, system_prompt: str = None):
        if not system_prompt:
            raise ValueError("system_prompt is required")
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = anthropic.Client(api_key=self.api_key)
        self.model = "claude-3-5-sonnet-20241022"
        self.stop_progress = Event()
        self.system_message = system_prompt
        self.last_prompt = None
        self.last_full_message = None
        self.last_response = None
        self.messages_history = []
        if system_prompt:
            self.messages_history.append(("system", system_prompt))

    def send_message(self, message: str, stop_event: Event = None) -> str:
        """Send message to Claude API and return response"""
        try:
            self.messages_history.append(("user", message))
            # Store the full message
            self.last_full_message = message
            
            try:
                # Check if already cancelled
                if stop_event and stop_event.is_set():
                    return ""
                
                # Start API request
                response = self.client.messages.create(
                    model=self.model,  # Use discovered model
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
                    self.messages_history.append(("assistant", response_text))
                
                # Always return the response, let caller handle cancellation
                return response_text
                
            except KeyboardInterrupt:
                if stop_event:
                    stop_event.set()
                return ""
                
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.messages_history.append(("error", error_msg))
            if stop_event and stop_event.is_set():
                return ""
            return error_msg