from openai import OpenAI
import os
from typing import Optional
from threading import Event
from .agent import Agent

class OpenAIAgent(Agent):
    """ OpenAI Agent """
    friendly_name = "OpenAI"
    
    def __init__(self):
        super().__init__(self.api_key)
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.model = os.getenv('OPENAI_MODEL')
        self.base_url = os.getenv('OPENAI_URL')
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        if not self.model:
            raise ValueError("OPENAI_MODEL environment variable is required")
        if not self.base_url:
            raise ValueError("OPENAI_URL environment variable is required")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.friendly_name = f"openai-{self.model}"

    def send_message(self, message: str, system_message: str) -> str:
        """Send message to OpenAI API and return response"""
        self.last_full_message = message
        
        try:
            messages = [
                { "role": "system", "content": system_message},
                { "role": "user", "content": message}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
            )
            
            response_text = response.choices[0].message.content
            self.last_response = response_text
            
            return response_text
            
        except KeyboardInterrupt:
            return ""