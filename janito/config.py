"""
Configuration module for Janito.
Provides a singleton Config class to access configuration values.
"""
import os
import json
from pathlib import Path
import typer
from typing import Dict, Any, Optional

# Predefined parameter profiles
PROFILES = {
    "precise": {
        "temperature": 0.2,
        "top_p": 0.85,
        "top_k": 20,
        "description": "Factual answers, documentation, structured data, avoiding hallucinations"
    },
    "balanced": {
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
        "description": "Professional writing, summarization, everyday tasks with moderate creativity"
    },
    "conversational": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 45,
        "description": "Natural dialogue, educational content, support conversations"
    },
    "creative": {
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 70,
        "description": "Storytelling, brainstorming, marketing copy, poetry"
    },
    "technical": {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 15,
        "description": "Code generation, debugging, decision analysis, technical problem-solving"
    }
}

class Config:
    """Singleton configuration class for Janito."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._workspace_dir = os.getcwd()
            cls._instance._verbose = False
            # Chat history context feature has been removed
            cls._instance._ask_mode = False
            cls._instance._trust_mode = False  # New trust mode setting
            cls._instance._no_tools = False  # New no-tools mode setting
            # Set technical profile as default
            profile_data = PROFILES["technical"]
            cls._instance._temperature = profile_data["temperature"]
            cls._instance._profile = "technical"
            cls._instance._role = "software engineer"
            cls._instance._gitbash_path = None  # Default to None for auto-detection
            cls._instance._load_config()
        return cls._instance
        
    def _load_config(self) -> None:
        """Load configuration from file."""
        config_path = Path(self._workspace_dir) / ".janito" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    # Chat history context feature has been removed
                    if "debug_mode" in config_data:
                        self._verbose = config_data["debug_mode"]
                    if "ask_mode" in config_data:
                        self._ask_mode = config_data["ask_mode"]
                    if "trust_mode" in config_data:
                        self._trust_mode = config_data["trust_mode"]
                    if "temperature" in config_data:
                        self._temperature = config_data["temperature"]
                    if "profile" in config_data:
                        self._profile = config_data["profile"]
                    if "role" in config_data:
                        self._role = config_data["role"]
                    if "gitbash_path" in config_data:
                        self._gitbash_path = config_data["gitbash_path"]
            except Exception as e:
                print(f"Warning: Failed to load configuration: {str(e)}")
                
    def _save_config(self) -> None:
        """Save configuration to file."""
        config_dir = Path(self._workspace_dir) / ".janito"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.json"
        
        config_data = {
            # Chat history context feature has been removed
            "verbose": self._verbose,
            "ask_mode": self._ask_mode,
            # trust_mode is not saved as it's a per-session setting
            "temperature": self._temperature,
            "role": self._role
        }
        
        # Save profile name if one is set
        if self._profile:
            config_data["profile"] = self._profile
            
        # Save GitBash path if one is set
        if self._gitbash_path:
            config_data["gitbash_path"] = self._gitbash_path
        
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save configuration: {str(e)}")
            
    def set_profile(self, profile_name: str) -> None:
        """Set parameter values based on a predefined profile.
        
        Args:
            profile_name: Name of the profile to use (precise, balanced, conversational, creative, technical)
            
        Raises:
            ValueError: If the profile name is not recognized
        """
        profile_name = profile_name.lower()
        if profile_name not in PROFILES:
            valid_profiles = ", ".join(PROFILES.keys())
            raise ValueError(f"Unknown profile: {profile_name}. Valid profiles are: {valid_profiles}")
            
        profile = PROFILES[profile_name]
        self._temperature = profile["temperature"]
        self._profile = profile_name
        self._save_config()
        
    @property
    def profile(self) -> Optional[str]:
        """Get the current profile name."""
        return self._profile
        
    @staticmethod
    def get_available_profiles() -> Dict[str, Dict[str, Any]]:
        """Get all available predefined profiles."""
        return PROFILES
        
    @staticmethod
    def set_api_key(api_key: str) -> None:
        """Set the API key in the global configuration file.
        
        Args:
            api_key: The Anthropic API key to store
            
        Returns:
            None
        """
        # Create .janito directory in user's home directory if it doesn't exist
        home_dir = Path.home()
        config_dir = home_dir / ".janito"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create or update the config.json file
        config_path = config_dir / "config.json"
        
        # Load existing config if it exists
        config_data = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load global configuration: {str(e)}")
        
        # Update the API key
        config_data["api_key"] = api_key
        
        # Save the updated config
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            print(f"API key saved to {config_path}")
        except Exception as e:
            raise ValueError(f"Failed to save API key: {str(e)}")
            
    @staticmethod
    def get_api_key() -> Optional[str]:
        """Get the API key from the global configuration file.
        
        Returns:
            The API key if found, None otherwise
        """
        # Look for config.json in user's home directory
        home_dir = Path.home()
        config_path = home_dir / ".janito" / "config.json"
        
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    return config_data.get("api_key")
            except Exception:
                # Silently fail and return None
                pass
                
        return None
    
    @property
    def workspace_dir(self) -> str:
        """Get the current workspace directory."""
        return self._workspace_dir
    
    @workspace_dir.setter
    def workspace_dir(self, path: str) -> None:
        """Set the workspace directory."""
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
    
    # For backward compatibility
    @property
    def debug_mode(self) -> bool:
        """Get the debug mode status (alias for verbose)."""
        return self._verbose
    
    @debug_mode.setter
    def debug_mode(self, value: bool) -> None:
        """Set the debug mode status (alias for verbose)."""
        self._verbose = value

    # Chat history context feature has been removed
        
    @property
    def ask_mode(self) -> bool:
        """Get the ask mode status."""
        return self._ask_mode
        
    @ask_mode.setter
    def ask_mode(self, value: bool) -> None:
        """Set the ask mode status."""
        self._ask_mode = value
        self._save_config()
        
    @property
    def trust_mode(self) -> bool:
        """Get the trust mode status."""
        return self._trust_mode
        
    @trust_mode.setter
    def trust_mode(self, value: bool) -> None:
        """Set the trust mode status.
        
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
        """Set the no-tools mode status.
        
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
    def temperature(self, value: float) -> None:
        """Set the temperature value for model generation."""
        if value < 0.0 or value > 1.0:
            raise ValueError("Temperature must be between 0.0 and 1.0")
        self._temperature = value
        self._save_config()
        
    # top_k and top_p are now only accessible through profiles
        
    @property
    def role(self) -> str:
        """Get the role for the assistant."""
        return self._role
        
    @role.setter
    def role(self, value: str) -> None:
        """Set the role for the assistant."""
        self._role = value
        self._save_config()
        
    @property
    def gitbash_path(self) -> Optional[str]:
        """Get the path to the GitBash executable."""
        return self._gitbash_path
        
    @gitbash_path.setter
    def gitbash_path(self, value: Optional[str]) -> None:
        """Set the path to the GitBash executable.
        
        Args:
            value: Path to the GitBash executable, or None to use auto-detection
        """
        # If a path is provided, verify it exists
        if value is not None and not os.path.exists(value):
            raise ValueError(f"GitBash executable not found at: {value}")
        
        self._gitbash_path = value
        self._save_config()
        
    def reset_config(self) -> bool:
        """Reset configuration by removing the config file.
        
        Returns:
            bool: True if the config file was removed, False if it didn't exist
        """
        config_path = Path(self._workspace_dir) / ".janito" / "config.json"
        if config_path.exists():
            config_path.unlink()
            # Reset instance variables to defaults
            self._verbose = False
            # Chat history context feature has been removed
            self._ask_mode = False
            self._trust_mode = False
            self._no_tools = False
            # Set technical profile as default
            profile_data = PROFILES["technical"]
            self._temperature = profile_data["temperature"]
            self._profile = "technical"
            self._role = "software engineer"
            self._gitbash_path = None  # Reset to auto-detection
            return True
        return False

# Convenience function to get the config instance
def get_config() -> Config:
    """Get the singleton Config instance."""
    return Config()
