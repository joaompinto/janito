from typing import Optional
import os
from pathlib import Path

class ConfigManager:
    """Singleton configuration manager for the application."""
    
    _instance = None

    def __init__(self):
        """Initialize configuration with default values."""
        self.debug = False
        self.verbose = False
        self.test_cmd = os.getenv('JANITO_TEST_CMD')
        self.workspace_dir = Path.cwd()
        self.raw = False
        self.auto_apply: bool = False
        self.skip_work: bool = False

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """Return the singleton instance of ConfigManager.
        
        Returns:
            ConfigManager: The singleton instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_debug(self, enabled: bool) -> None:
        """Set debug mode.
        
        Args:
            enabled: True to enable debug mode, False to disable
        """
        self.debug = enabled

    def set_verbose(self, enabled: bool) -> None:
        """Set verbose output mode.
        
        Args:
            enabled: True to enable verbose output, False to disable
        """
        self.verbose = enabled

    def set_debug_line(self, line: Optional[int]) -> None:
        """Set specific line number for debug output.
        
        Args:
            line: Line number to debug, or None for all lines
        """
        self.debug_line = line

    def should_debug_line(self, line: int) -> bool:
        """Return True if we should show debug for this line number"""
        return self.debug and (self.debug_line is None or self.debug_line == line)

    def set_test_cmd(self, cmd: Optional[str]) -> None:
        """Set the test command, overriding environment variable"""
        self.test_cmd = cmd if cmd is not None else os.getenv('JANITO_TEST_CMD')

    def set_workspace_dir(self, path: Optional[Path]) -> None:
        """Set the workspace directory"""
        self.workspace_dir = path if path is not None else Path.cwd()

    def set_raw(self, enabled: bool) -> None:
        """Set raw output mode.
        
        Args:
            enabled: True to enable raw output mode, False to disable
        """
        self.raw = enabled

    def set_auto_apply(self, enabled: bool) -> None:
        """Set auto apply mode for changes.
        
        Args:
            enabled: True to enable auto apply mode, False to disable
        """
        self.auto_apply = enabled

    def set_tui(self, enabled: bool) -> None:
        """Set Text User Interface mode.
        
        Args:
            enabled: True to enable TUI mode, False to disable
        """
        self.tui = enabled

    def set_skip_work(self, enabled: bool) -> None:
        """Set whether to skip scanning the workspace directory.
        
        Args:
            enabled: True to skip workspace directory, False to include it
        """
        self.skip_work = enabled

# Create a singleton instance
config = ConfigManager.get_instance()