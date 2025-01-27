from abc import ABC, abstractmethod
from typing import Optional

class Agent(ABC):
    """Abstract base class for AI agents"""
    friendly_name = "Unknown"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.last_prompt = None
        self.last_full_message = None
        self.last_response = None
        self.model = None

    @abstractmethod
    def send_message(self, message: str, system: str) -> str:
        """Send message to the AI agent
        
        Args:
            message: The message to send
            stop_event: Optional event to signal cancellation
            
        Returns:
            The response from the AI agent
        """
        pass