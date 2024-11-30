from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.document import Document
from prompt_toolkit.completion.base import CompleteEvent
import anthropic
import os
from pathlib import Path
import json
from typing import List, Optional, AsyncGenerator, Iterable, Tuple
import asyncio
from hashlib import sha256
from datetime import datetime, timedelta
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import traceback  # Add import at the top with other imports
from rich.markdown import Markdown
from rich.console import Console
import subprocess  # Add at the top with other imports
import re  # Add to imports at top
import ast  # Add to imports at top
import tempfile
from janito.change import FileChangeHandler, DeltaResult, DeltaType  # Change relative imports to absolute
from janito.watcher import FileWatcher
from janito.claude import ClaudeAPIAgent
from rich.progress import Progress, SpinnerColumn, TextColumn  # Add to imports at top
from threading import Event
import threading
from rich.syntax import Syntax
from rich.text import Text
import typer
from typing import Optional
from janito.error import handle_error, error_handler, JanitoError, APIError, ConfigError

"""
Main module for Janito - Language-Driven Software Development Assistant.
Provides the core CLI interface and command handling functionality.
Manages user interactions, file operations, and API communication with Claude.
"""

class PathCompleter(Completer):
    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        text = document.text_before_cursor
        
        # Handle dot command completion
        if text.startswith('.') or text == '':
            commands = [
                '.help', '.exit', '.clear', '.save', '.load',
                '.debug', '.cache', '.content'
            ]
            word = text.lstrip('.')
            for cmd in commands:
                if cmd[1:].startswith(word):
                    yield Completion(
                        cmd, 
                        start_position=-len(text),
                        display=HTML(f'<cmd>{cmd}</cmd>')
                    )
            return
            
        # Handle path completion
        path = Path('.' if not text else text)
        
        try:
            if path.is_dir():
                directory = path
                prefix = ''
            else:
                directory = path.parent
                prefix = path.name

            for item in directory.iterdir():
                if item.name.startswith(prefix):
                    yield Completion(
                        str(item),
                        start_position=-len(prefix) if prefix else 0,
                        display=HTML(f'{"/" if item.is_dir() else ""}{item.name}')
                    )
        except Exception:
            pass

    async def get_completions_async(self, document: Document, complete_event: CompleteEvent) -> AsyncGenerator[Completion, None]:
        for completion in self.get_completions(document, complete_event):
            yield completion

class JanitoCommands:  # Renamed from ClaudeCommands
    def __init__(self, api_key: Optional[str] = None):
        try:
            self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
            if not self.api_key:
                raise ConfigError("ANTHROPIC_API_KEY environment variable is required")
            self.client = anthropic.Client(api_key=self.api_key)
            self.conversation_history = []
            self.cache_dir = Path.home() / '.janito' / 'cache'  # Changed from .claudesh
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.debug = False
            self.stop_progress = Event()
            self.cache_ext = '.xml'  # Change cache extension
            self.history_dir = Path.home() / '.janito' / 'history'  # Add history directory
            self.history_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ConfigError("Failed to initialize Janito", cause=e)
        
    def _get_files_content(self) -> str:
        """Get content of all Python files in current directory and subdirectories"""
        content = []
        try:
            base_path = Path().absolute()
            # Walk through directory tree
            for file in sorted(base_path.rglob("*.py")):
                try:
                    # Skip cache directory and files outside workspace
                    if '.janito' not in file.parts and base_path in file.parents:
                        rel_path = file.relative_to(base_path)
                        content.append(f"### {rel_path} ###\n{file.read_text()}\n")
                except Exception:
                    continue  # Skip files we can't read or process
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
        files_content = self._get_files_content()
        
        cache_content = f"""<cache>
  <timestamp>{datetime.now().isoformat()}</timestamp>
  <message>{message}</message>
  <response>{response}</response>
  <context>
    <system_message>You are Janito, a language-driven Software Development Assistant. You help developers understand, modify, and improve their code through natural language interaction. Here are the Python files in the current workspace:</system_message>
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True
        ) as progress:
            task = progress.add_task("Processing request...", total=None)  # Updated message
            while not self.stop_progress.is_set():
                progress.update(task)
                time.sleep(0.1)

    @error_handler(exit_on_error=False)
    def send_message(self, message: str) -> str:
        """Consolidated file content reading to avoid duplication"""
        files_content = self._get_files_content()
        system_message = "You are Janito, a language-driven Software Development Assistant. You help developers understand, modify, and improve their code through natural language interaction. Here are the Python files in the current workspace:\n\n"
        
        cached_response = self._get_from_cache(message)
        if cached_response:
            if self.debug:
                print("\n[Debug] Cache hit! Using cached response")
            return cached_response
            
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
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            # Cache the response
            self._save_to_cache(message, response_text)
            
            return response_text
            
        except anthropic.APIError as e:
            raise APIError("Failed to communicate with Claude API", cause=e)
        except Exception as e:
            raise JanitoError("Failed to process message", cause=e)
        finally:
            self.stop_progress.set()
            progress_thread.join()

    @error_handler(exit_on_error=False)
    def save_history(self, args) -> str:
        """Save conversation history to a file"""
        try:
            if not args:
                filename = f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            else:
                filename = args[0]
                
            filepath = self.history_dir / filename
            with open(filepath, 'w') as f:
                json.dump(self.conversation_history, f, indent=2)
            return f"History saved to {filepath}"
        except Exception as e:
            raise JanitoError("Failed to save history", cause=e)

    @error_handler(exit_on_error=False)
    def load_history(self, args) -> str:
        """Load conversation history from a file"""
        try:
            if not args:
                return "Please specify a history file to load"
                
            filepath = self.history_dir / args[0]
            if not filepath.exists():
                return f"History file not found: {filepath}"
                
            with open(filepath) as f:
                self.conversation_history = json.load(f)
            return f"History loaded from {filepath}"
        except Exception as e:
            raise JanitoError("Failed to load history", cause=e)

    def clear_history(self) -> str:
        """Clear the conversation history"""
        self.conversation_history = []
        return "Conversation history cleared"

    def get_workspace_status(self) -> str:
        """Get a summary of Python files in current workspace"""
        try:
            base_path = Path().absolute()
            tree = {}
            found_files = False
            
            # Build tree structure
            for file in sorted(base_path.rglob("*.py")):
                try:
                    # Skip cache directory and files outside workspace
                    if '.janito' not in file.parts and base_path in file.parents:
                        found_files = True
                        rel_path = file.relative_to(base_path)
                        
                        # Build tree structure
                        current = tree
                        for part in rel_path.parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[rel_path.parts[-1]] = None
                except Exception:
                    continue
            
            if not found_files:
                return "No Python files found in the current workspace."
            
            # Generate tree text representation
            def format_tree(node, prefix="", is_last=True) -> List[str]:
                lines = []
                for i, (name, subtree) in enumerate(node.items()):
                    is_last_item = i == len(node) - 1
                    connector = "└── " if is_last_item else "├── "
                    
                    if subtree is None:  # File
                        lines.append(f"{prefix}{connector}{name}")
                    else:  # Directory
                        lines.append(f"{prefix}{connector}{name}/")
                        next_prefix = prefix + ("    " if is_last_item else "│   ")
                        lines.extend(format_tree(subtree, next_prefix))
                return lines
            
            tree_lines = format_tree(tree)
            return "Python files in workspace:\n" + "\n".join(tree_lines)
            
        except Exception as e:
            raise JanitoError("Failed to get workspace status", cause=e)

    @error_handler(exit_on_error=False)
    def show_content(self) -> str:
        """Show directory structure and Python files in current workspace"""
        try:
            status = self.get_workspace_status()
            print("\nWorkspace structure:")
            print("=" * 80)
            print(status)
            return ""
        except Exception as e:
            raise JanitoError("Failed to show workspace content", cause=e)

class JanitoConsole:
    """Interactive console for Janito with command handling and REPL"""
    def __init__(self):
        self.commands = {
            '.help': self.help,
            '.exit': self.exit
        }
        
        try:
            self.janito = JanitoCommands()
            janito_commands = {
                '.clear': lambda _: self.janito.clear_history(),
                '.save': self.janito.save_history,
                '.load': self.janito.load_history,
                '.debug': lambda _: self.janito.toggle_debug(),
                '.cache': lambda _: self.janito.clear_cache(),
                '.content': lambda _: self.janito.show_content(),
                '.help': lambda _: (
                    "Janito commands:\n"
                    ".clear   - Clear conversation history\n"
                    ".save    - Save history to file\n"
                    ".load    - Load history from file\n"
                    ".debug   - Toggle debug mode\n"
                    ".cache   - Clear cached responses\n"
                    ".content - Show current workspace content\n"
                    ".help    - Show this help"
                )
            }
            self.commands.update(janito_commands)
        except ValueError as e:
            print(f"Warning: Janito initialization failed - {str(e)}")
            self.janito = None
        
        self.session = PromptSession(
            completer=PathCompleter(),
            style=Style.from_dict({
                'ai': '#00aa00 bold',
                'path': '#3388ff bold',
                'sep': '#888888',
                'prompt': '#ff3333 bold',
                'cmd': '#00aa00',
            })
        )
        self.running = True
        self.restart_requested = False
        self._setup_file_watcher()

    def _setup_file_watcher(self):
        """Set up file watcher for auto-restart"""
        def on_file_change(path, content):
            print("\nJanito source file changed - restarting...")
            self.restart_requested = True
            self.running = False
            
            # Force an immediate cleanup and exit of the prompt session
            if hasattr(self, 'session'):
                # Reset the input buffer
                if hasattr(self.session, '_default_buffer'):
                    self.session._default_buffer.reset()
                # Force the app to process the next input cycle
                if hasattr(self.session, 'app'):
                    self.session.app.exit()

        try:
            package_dir = os.path.dirname(os.path.dirname(__file__))
            self.watcher = FileWatcher(on_file_change, package_dir)
            self.watcher.start()
        except Exception as e:
            print(f"Warning: Could not set up file watcher: {e}")

    def get_prompt(self):
        """Generate the command prompt"""
        current_dir = os.getcwd()
        return HTML(
            '<ai>🤖 janito</ai> '
            '<sep>in</sep> '  # Added "in" separator
            '<path>{}</path> '
            '<prompt>⫸</prompt> '.format(current_dir)
        )

    def help(self, args):
        """Show help information"""
        if args:
            cmd = args[0]
            if cmd in self.commands:
                print(f"{cmd}: {self.commands[cmd].__doc__}")
            else:
                print(f"Unknown command: {cmd}")
        else:
            print("Available commands:")
            print("  .help    - Show this help")
            print("  .exit    - End session")
            print("  .clear   - Clear history")
            print("  .save    - Save history to file")
            print("  .load    - Load history from file")
            print("  .debug   - Toggle debug mode")
            print("  .cache   - Clear response cache")
            print("  .content - Show current workspace content")
            print("\nInput formats:")
            print("  !request - Request file changes (e.g. '!add logging to utils.py')")
            print("  request? - Get information without changes")
            print("  request  - General queries to Janito")

    def exit(self, args):
        """Exit the console"""
        self.running = False

    @error_handler(exit_on_error=False)
    def run(self):
        """Main command loop"""
        try:
            while self.running:
                try:
                    command = self.session.prompt(self.get_prompt()).strip()
                    
                    if not command:
                        continue
                        
                    if command.startswith('.'):
                        parts = command.split()
                        cmd, args = parts[0], parts[1:]
                        if cmd in self.commands:
                            result = self.commands[cmd](args)
                            if result:
                                print(result)
                        else:
                            print(f"Unknown command: {cmd}")
                    elif self.janito:
                        result = self.janito.send_message(command)
                        print(f"\n{result}")
                    else:
                        raise JanitoError("Janito not initialized")
                except EOFError:
                    self.exit([])
                    break
                except (KeyboardInterrupt, SystemExit):
                    if self.restart_requested:
                        break
                    continue
        finally:
            if self.watcher:
                self.watcher.stop()

class CLI:
    """Command-line interface handler for Janito using Typer"""
    def __init__(self):
        self.app = typer.Typer(
            help="Janito - Language-Driven Software Development Assistant",
            add_completion=False,
            no_args_is_help=False,  # Don't show help when no args
        )
        self._setup_commands()

    def _setup_commands(self):
        """Setup Typer commands"""
        @self.app.callback(invoke_without_command=True)
        def main(
            debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
            no_watch: bool = typer.Option(False, "--no-watch", help="Disable file watching"),
        ):
            """Language-Driven Software Development Assistant"""
            try:
                console = JanitoConsole()
                if debug:
                    console.janito.debug = True
                if no_watch:
                    if console.watcher:
                        console.watcher.stop()
                        console.watcher = None
                console.run()
            except KeyboardInterrupt:
                print("\nExiting...")
            except Exception as e:
                print(f"\nFatal error: {str(e)}")
                print("\nTraceback:")
                traceback.print_exc()

    @error_handler(exit_on_error=True)
    def run(self, args=None):
        """Run the CLI application"""
        self.app()

def run_cli():
    """Main entry point"""
    cli = CLI()
    cli.run()

# Remove if __main__ block since we use __main__.py now