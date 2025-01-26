from openai import OpenAI
import os
from typing import Optional
from threading import Event
from .agent import Agent

class DeepSeekAIAgent(Agent):
    """ DeepSeek AI Agent """
    DEFAULT_MODEL = "deepseek-chat"
    friendly_name = "DeepSeek"
    api_key = None
    
    def __init__(self, system_prompt: str = None):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        super().__init__(self.api_key, system_prompt)
        if not system_prompt:
            raise ValueError("system_prompt is required")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
        self.model = self.DEFAULT_MODEL
        self.system_message = system_prompt

    def send_message(self, message: str, system_message: str = None) -> str:
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
                max_completion_tokens=4096,
                temperature=0,
            )
            
            response_text = response.choices[0].message.content
            self.last_response = response_text
            
            return response
            
        except KeyboardInterrupt:
            return ""