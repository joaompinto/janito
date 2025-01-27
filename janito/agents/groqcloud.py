from openai import OpenAI
import os
from typing import Optional
from threading import Event
from .agent import Agent

from groq import Groq

class GroqCloudAgent(Agent):
    """ GroqCloud AI Agent """
    DEFAULT_MODEL = "deepseek-r1-distill-llama-70b"
    friendly_name = "GroqCloud-DeepSeek"
    
    def __init__(self):
        self.api_key = os.getenv('GROQ_API_KEY')
        super().__init__(self.api_key)
        
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is required")
    
        self.client = Groq(
            api_key=os.environ.get("GROQ_API_KEY"),
        )
        self.model = self.DEFAULT_MODEL
    
    def send_message(self, message: str, system_message: str) -> str:
        """Send message to OpenAI API and return response"""
        self.last_full_message = message
        
        try:
            messages = [
                { "role": "user", "content": system_message},
                { "role": "user", "content": message}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=4096,
                temperature=0,
            )
            
            response_text = response.choices[0].message.content
            self.last_response = response_text
            
            return response_text
            
        except KeyboardInterrupt:
            return ""