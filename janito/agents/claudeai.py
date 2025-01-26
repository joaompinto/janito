import anthropic
import os

from .agent import Agent

class ClaudeAIAgent(Agent):
    """Handles interaction with Claude API, including message handling"""
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    friendly_name = "Claude"
    
    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        super().__init__(self.api_key)
        
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = anthropic.Client(api_key=self.api_key)
        self.model = os.getenv('CLAUDE_MODEL', self.DEFAULT_MODEL)
        self.last_prompt = None
        self.last_full_message = None
        self.last_response = None


    def send_message(self, system_message: str, message: str) -> str:
        """Send message to Claude API and return response"""
        # Store the full message
        self.last_full_message = message
        
        response = self.client.messages.create(
            model=self.model,  # Use discovered model
            system=system_message or self.system_message,
            max_tokens=8192,
            messages=[
                {"role": "user", "content": message}
            ],
            temperature=0,
        )
        

        # Always return the response, let caller handle cancellation
        return response