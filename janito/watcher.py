import os
from pathlib import Path
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import sys
from janito.error import handle_error, error_handler, JanitoError

"""
File watching system for Janito.
Monitors Python files for changes and triggers callbacks when modifications occur.
Provides debouncing and filtering capabilities to handle file system events efficiently.
"""

class PackageFileHandler(FileSystemEventHandler):
    """Watches for changes in Python package files and triggers restart callbacks"""
    def __init__(self, callback, base_path='.'):
        self.callback = callback
        self.last_modified = time.time()
        self.package_dir = os.path.normpath(os.path.dirname(os.path.dirname(__file__)))
        self.watched_extensions = {'.py'}
        self.debounce_time = 1
        
    @error_handler(exit_on_error=False)
    def on_modified(self, event):
        if event.is_directory:
            return
            
        current_time = time.time()
        if current_time - self.last_modified < self.debounce_time:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix not in self.watched_extensions:
            return
            
        event_path = os.path.normpath(os.path.abspath(event.src_path))
        try:
            rel_path = os.path.relpath(event_path, self.package_dir)
            if not rel_path.startswith('..'):  # File is within package
                self.last_modified = current_time
                print(f"\nJanito package file modified: {rel_path}")
                self.callback(event.src_path, file_path.read_text())
        except Exception as e:
            print(f"\nError processing file {event_path}: {e}")

class FileWatcher:
    def __init__(self, callback, base_path='.'):
        self.observer = None
        # Update to use PackageFileHandler instead of ProjectFileHandler
        self.handler = PackageFileHandler(callback, base_path)
        self.base_path = os.path.abspath(base_path)
        self.is_running = False  # Add state tracking
        
    @error_handler(exit_on_error=False)
    def start(self):
        """Start watching for file changes"""
        try:
            if not self.is_running:
                self.is_running = True
                print("\nStarting file watcher:")
                print(f"📂 Monitoring Janito package in: {self.base_path}")
                print("🔍 Watching for Python file changes")
                print("⚡ Auto-restart enabled for package modifications")
                self.observer = Observer()
                self.observer.schedule(self.handler, self.base_path, recursive=True)
                self.observer.start()
        except Exception as e:
            raise JanitoError("Failed to start file watcher", cause=e)
        
    @error_handler(exit_on_error=False)
    def stop(self):
        if self.observer and self.is_running:
            try:
                self.is_running = False
                self.observer.stop()
                # Add timeout to prevent hanging
                self.observer.join(timeout=1.0)
            except RuntimeError as e:
                if "cannot join current thread" not in str(e):
                    print(f"Warning: Error stopping file watcher: {e}")
            except Exception as e:
                raise JanitoError("Failed to stop file watcher", cause=e)
            finally:
                self.observer = None