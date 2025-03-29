"""
Property getters and setters for the Config class.
"""
import os
import typer
from typing import Optional, Any

class ConfigProperties:
    """
    Mixin class containing property getters and setters for the Config class.
    This class is not meant to be instantiated directly.
    """
    
    @property
    def workspace_dir(self) -> str:
        """Get the current workspace directory."""
        return self._workspace_dir
    
    @workspace_dir.setter
    def workspace_dir(self, path: str) -> None:
        """
        Set the workspace directory.
        
        Args:
            path: Path to set as workspace directory
            
        Raises:
            ValueError: If the directory doesn't exist and can't be created
        """
        # Convert to absolute path if not already
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.abspath(path))
        else:
            # Ensure Windows paths are properly formatted
            path = os.path.normpath(path)
        
        # Check if the directory exists
        if not os.path.isdir(path):
            create_dir = typer.confirm(f"Workspace directory does not exist: {path}\nDo you want to create it?")
            if create_dir:
                try:
                    os.makedirs(path, exist_ok=True)
                    print(f"Created workspace directory: {path}")
                except Exception as e:
                    raise ValueError(f"Failed to create workspace directory: {str(e)}") from e
            else:
                raise ValueError(f"Workspace directory does not exist: {path}")
        
        self._workspace_dir = path
    
    @property
    def verbose(self) -> bool:
        """Get the verbose mode status."""
        return self._verbose
    
    @verbose.setter
    def verbose(self, value: bool) -> None:
        """Set the verbose mode status."""
        self._verbose = value
        # This is a runtime setting, not persisted
    
    # For backward compatibility
    @property
    def debug_mode(self) -> bool:
        """Get the debug mode status (alias for verbose)."""
        return self._verbose
    
    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        """Set the debug mode status (alias for verbose)."""
        self._verbose = value
        # This is a runtime setting, not persisted
        
    @property
    def ask_mode(self) -> bool:
        """Get the ask mode status."""
        return self._ask_mode
        
    @ask_mode.setter
    def ask_mode(self, value: bool, config_type: str = "local") -> None:
        """
        Set the ask mode status.
        
        Args:
            value: Boolean value to set
            config_type: Type of configuration to update ("local" or "global")
        """
        self._ask_mode = value
        
        if config_type == "local":
            self.set_local_config("ask_mode", value)
        else:
            self.set_global_config("ask_mode", value)
    
    @property
    def trust_mode(self) -> bool:
        """Get the trust mode status."""
        return self._trust_mode
        
    @trust_mode.setter
    def trust_mode(self, value: bool) -> None:
        """
        Set the trust mode status.
        
        Note: This setting is not persisted to config file
        as it's meant to be a per-session setting.
        """
        self._trust_mode = value
        # Don't save to config file - this is a per-session setting
        
    @property
    def no_tools(self) -> bool:
        """Get the no-tools mode status."""
        return self._no_tools
        
    @no_tools.setter
    def no_tools(self, value: bool) -> None:
        """
        Set the no-tools mode status.
        
        Note: This setting is not persisted to config file
        as it's meant to be a per-session setting.
        """
        self._no_tools = value
        # Don't save to config file - this is a per-session setting
        
    @property
    def temperature(self) -> float:
        """Get the temperature value for model generation."""
        return self._temperature
        
    @temperature.setter
    def temperature(self, value: float, config_type: str = "local") -> None:
        """
        Set the temperature value for model generation.
        
        Args:
            value: Temperature value (0.0 to 1.0)
            config_type: Type of configuration to update ("local" or "global")
            
        Raises:
            ValueError: If temperature is not between 0.0 and 1.0
        """
        if value < 0.0 or value > 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")
            
        self._temperature = value
        
        if config_type == "local":
            self.set_local_config("temperature", value)
        else:
            self.set_global_config("temperature", value)
    
    # top_k and top_p are now only accessible through profiles
        
    @property
    def role(self) -> str:
        """Get the role for the assistant."""
        return self._role
        
    @role.setter
    def role(self, value: str, config_type: str = "local") -> None:
        """
        Set the role for the assistant.
        
        Args:
            value: Role string
            config_type: Type of configuration to update ("local" or "global")
        """
        self._role = value
        
        if config_type == "local":
            self.set_local_config("role", value)
        else:
            self.set_global_config("role", value)
    
    @property
    def gitbash_path(self) -> Optional[str]:
        """Get the path to the GitBash executable."""
        return self._gitbash_path
        
    @gitbash_path.setter
    def gitbash_path(self, value: Optional[str], config_type: str = "local") -> None:
        """
        Set the path to the GitBash executable.
        
        Args:
            value: Path to the GitBash executable, or None to use auto-detection
            config_type: Type of configuration to update ("local" or "global")
            
        Raises:
            ValueError: If the provided path doesn't exist
        """
        # If a path is provided, verify it exists
        if value is not None and not os.path.exists(value):
            raise ValueError(f"GitBash executable not found at: {value}")
        
        self._gitbash_path = value
        
        if config_type == "local":
            self.set_local_config("gitbash_path", value)
        else:
            self.set_global_config("gitbash_path", value)
    
    @property
    def profile(self) -> Optional[str]:
        """Get the current profile name."""
        return self._profile
        
    @property
    def max_view_lines(self) -> int:
        """Get the maximum number of lines to display before showing a warning."""
        return self._merged_config.get("max_view_lines", 500)
        
    @max_view_lines.setter
    def max_view_lines(self, value: int, config_type: str = "local") -> None:
        """
        Set the maximum number of lines to display before showing a warning.
        
        Args:
            value: Maximum number of lines (must be positive)
            config_type: Type of configuration to update ("local" or "global")
            
        Raises:
            ValueError: If the value is not a positive integer
        """
        if not isinstance(value, int) or value <= 0:
            raise ValueError("max_view_lines must be a positive integer")
            
        if config_type == "local":
            self.set_local_config("max_view_lines", value)
        else:
            self.set_global_config("max_view_lines", value)