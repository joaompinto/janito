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

class ClaudeAPIAgent:
    """Handles interaction with Claude API, including caching and message handling"""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = anthropic.Client(api_key=self.api_key)
        self.conversation_history = []
        self.cache_dir = Path.home() / '.claudesh' / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.debug = False
        self.stop_progress = Event()
        self.cache_ext = '.xml'

    def _get_files_content(self) -> str:
        """Get content of all Python files in current directory"""
        content = []
        try:
            for file in sorted(Path().glob("*.py")):
                content.append(f"### {file.name} ###\n{file.read_text()}\n")
            return "\n".join(content)
        except Exception as e:
            return f"Error reading files: {e}"
            
    def _get_cache_key(self, message: str) -> str:
        """Generate cache key from message content and files state"""
        files_content = self._get_files_content()
        combined = f"{message}\n{files_content}"
        return sha256(combined.encode()).hexdigest()[:12]  # Shorter hash for readability
        
    def _get_from_cache(self, message: str, max_age_hours: int = 24) -> Optional[str]:
        """Get response from cache if it exists and is not too old"""
        cache_key = self._get_cache_key(message)
        cache_file = self.cache_dir / f"{cache_key}{self.cache_ext}"
        
        if not cache_file.exists():
            if self.debug:
                print("\n[Debug] Cache miss - file not found")
            return None
            
        try:
            # Read and parse cache file directly
            with open(cache_file) as f:
                lines = f.readlines()
                for line in lines:
                    if '<response>' in line:
                        response = re.search(r'<response>(.*?)</response>', line, re.DOTALL)
                        if response:
                            return response.group(1)
            return None
            
        except Exception as e:
            if self.debug:
                print(f"\n[Debug] Cache error: {str(e)}")
            return None

    def _save_to_cache(self, message: str, response: str):
        """Save response and context to cache in simple format"""
        cache_key = self._get_cache_key(message)
        files_content = self.__get_files_content()
        
        cache_content = f"""<cache>
  <timestamp>{datetime.now().isoformat()}</timestamp>
  <message>{message}</message>
  <response>{response}</response>
  <context>
    <system_message>You are a helpful coding assistant. Here are the Python files in the current directory:</system_message>
    <files_content>{files_content}</files_content>
    <user_message>{message}</user_message>
  </context>
</cache>"""
        
        try:
            cache_file = self.cache_dir / f"{cache_key}{self.cache_ext}"
            cache_file.write_text(cache_content)
            if self.debug:
                print(f"\n[Debug] Saved response to cache: {cache_file}")
        except Exception as e:
            if self.debug:
                print(f"\n[Debug] Cache save error: {str(e)}")

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

    def send_message(self, message: str) -> str:
        """Consolidated file content reading to avoid duplication"""
        files_content = self._get_files_content()
        system_message = "You are a helpful coding assistant. Here are the Python files in the current directory:\n\n"
        
        cached_response = self._get_from_cache(message)
        if (cached_response):
            if self.debug:
                print("\n[Debug] Cache hit! Using cached response")
                try:
                    tree = ET.parse(self.cache_dir / f"{self._get_cache_key(message)}{self.cache_ext}")
                    root = tree.getroot()
                    context = root.find('context')
                    
                    print("\n[Debug] Original request context:")
                    print("=" * 80)
                    print("[System prompt]:")
                    print(context.find('system_message').text)
                    print("-" * 40)
                    print("[Files context]:")
                    print(context.find('files_content').text)
                    print("-" * 40)
                    print("[User message]:")
                    print(context.find('user_message').text)
                    print("=" * 80)
                    print("\n[Debug] Cached response:")
                    print("=" * 80)
                    print(cached_response)
                    print("=" * 80)
                except Exception as e:
                    print(f"\n[Debug] Error reading cache details: {e}")
            return cached_response
            
        try:
            # Start progress indicator in background thread
            self.stop_progress.clear()
            progress_thread = threading.Thread(
                target=self._show_progress,
                args=("Waiting for Claude's response...",)
            )
            progress_thread.start()
            
            try:
                user_message = f"User request:\n{message}"
                context_message = system_message + files_content + user_message
                
                if self.debug:
                    print("\n[Debug] Sending request to Claude:")
                    print("=" * 80)
                    print("[System prompt]:")
                    print(system_message)
                    print("-" * 40)
                    print("[Files context]:")
                    print(files_content)
                    print("-" * 40)
                    print("[User message]:")
                    print(user_message)
                    print("=" * 80)
                
                response = self.client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": context_message}]
                )
                response_text = response.content[0].text
            finally:
                self.stop_progress.set()
                progress_thread.join()
            
            if self.debug:
                print("\n[Debug] Received response:")
                print("=" * 80)
                print(response_text)
                print("=" * 80)
            
            # Update conversation history with original message, not the context-enhanced one
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            # Cache the response
            self._save_to_cache(message, response_text)
            
            return response_text
        except Exception as e:
            self.stop_progress.set()  # Ensure progress stops on error
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
    
    def clear_cache(self) -> str:
        """Clear all cached responses"""
        try:
            for cache_file in self.cache_dir.glob(f"*{self.cache_ext}"):
                cache_file.unlink()
            return "Cache cleared"
        except Exception as e:
            return f"Error clearing cache: {str(e)}"

    def handle_info_request(self, request: str, workspace_status: str) -> str:
        """Handle information request without file modifications"""
        files_content = self._get_files_content()
        
        message = f"""Current workspace status:
{workspace_status}

{files_content if files_content else ""}

Information request: {request}

Please provide information based on the current project context.
Focus on explaining and analyzing without suggesting any file modifications.
"""
        return self.send_message(message)