"""
Singleton implementation of the Config class for Janito.
"""
import os
from typing import Dict, Any, Optional, Union

from .properties import ConfigProperties
from .file_operations import (
    get_global_config_path,
    get_local_config_path,
    load_config_file,
    save_config_file,
    merge_configs
)
from ..profiles.manager import get_profile
from ..profiles.definitions import PROFILES

class Config(ConfigProperties):
    """Singleton configuration class for Janito."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._workspace_dir = os.getcwd()
            cls._instance._verbose = False
            cls._instance._ask_mode = False
            cls._instance._trust_mode = False
            cls._instance._no_tools = False
            
            # Set technical profile as default
            profile_data = PROFILES["technical"]
            cls._instance._temperature = profile_data["temperature"]
            cls._instance._profile = "technical"
            cls._instance._role = "software engineer"
            cls._instance._gitbash_path = None  # Default to None for auto-detection
            # Default max_view_lines will be retrieved from merged_config
            
            # Initialize configuration storage
            cls._instance._global_config = {}
            cls._instance._local_config = {}
            cls._instance._merged_config = {}
            
            # Load configurations
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load both global and local configurations and merge them."""
        # Load global config
        global_config_path = get_global_config_path()
        self._global_config = load_config_file(global_config_path)
        
        # Load local config
        local_config_path = get_local_config_path(self._workspace_dir)
        self._local_config = load_config_file(local_config_path)
        
        # Merge configurations (local overrides global)
        self._merge_configs()
        
        # Apply merged configuration to instance variables
        self._apply_config()
    
    def _merge_configs(self) -> None:
        """Merge global and local configurations with local taking precedence."""
        self._merged_config = merge_configs(self._global_config, self._local_config)
    
    def _apply_config(self) -> None:
        """Apply the merged configuration to instance variables."""
        config_data = self._merged_config
        
        # Apply configuration values to instance variables
        if "debug_mode" in config_data:
            self._verbose = config_data["debug_mode"]
        if "verbose" in config_data:
            self._verbose = config_data["verbose"]
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
        # max_view_lines is accessed directly from merged_config
    
    def _save_local_config(self) -> None:
        """Save local configuration to file."""
        config_path = get_local_config_path(self._workspace_dir)
        save_config_file(config_path, self._local_config)
    
    def _save_global_config(self) -> None:
        """Save global configuration to file."""
        config_path = get_global_config_path()
        save_config_file(config_path, self._global_config)
    
    def _save_config(self) -> None:
        """Save local configuration to file (for backward compatibility)."""
        self._save_local_config()
    
    def set_profile(self, profile_name: str, config_type: str = "local") -> None:
        """
        Set parameter values based on a predefined profile.
        
        Args:
            profile_name: Name of the profile to use (precise, balanced, conversational, creative, technical)
            config_type: Type of configuration to update ("local" or "global")
            
        Raises:
            ValueError: If the profile name is not recognized or config_type is invalid
        """
        if config_type not in ["local", "global"]:
            raise ValueError(f"Invalid config_type: {config_type}. Must be 'local' or 'global'")
            
        profile = get_profile(profile_name)
        
        # Update the appropriate configuration
        if config_type == "local":
            self.set_local_config("temperature", profile["temperature"])
            self.set_local_config("profile", profile_name)
        else:
            self.set_global_config("temperature", profile["temperature"])
            self.set_global_config("profile", profile_name)
    
    @staticmethod
    def get_available_profiles() -> Dict[str, Dict[str, Any]]:
        """Get all available predefined profiles."""
        from ..profiles.manager import get_available_profiles
        return get_available_profiles()
    
    def set_local_config(self, key: str, value: Any) -> None:
        """
        Set a configuration value in the local configuration.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self._local_config[key] = value
        self._save_local_config()
        
        # Re-merge and apply configurations
        self._merge_configs()
        self._apply_config()
    
    def set_global_config(self, key: str, value: Any) -> None:
        """
        Set a configuration value in the global configuration.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self._global_config[key] = value
        self._save_global_config()
        
        # Re-merge and apply configurations
        self._merge_configs()
        self._apply_config()
    
    def get_local_config(self) -> Dict[str, Any]:
        """
        Get the local configuration.
        
        Returns:
            Dict containing the local configuration
        """
        return self._local_config.copy()
    
    def get_global_config(self) -> Dict[str, Any]:
        """
        Get the global configuration.
        
        Returns:
            Dict containing the global configuration
        """
        return self._global_config.copy()
    
    def get_merged_config(self) -> Dict[str, Any]:
        """
        Get the merged configuration.
        
        Returns:
            Dict containing the merged configuration
        """
        return self._merged_config.copy()
    
    @staticmethod
    def set_api_key(api_key: str) -> None:
        """
        Set the API key in the global configuration file.
        
        Args:
            api_key: The Anthropic API key to store
        """
        # Get the singleton instance
        config = Config()
        
        # Set the API key in the global configuration
        config.set_global_config("api_key", api_key)
        print(f"API key saved to {get_global_config_path()}")
    
    @staticmethod
    def get_api_key() -> Optional[str]:
        """
        Get the API key from the global configuration file.
        
        Returns:
            The API key if found, None otherwise
        """
        # Get the singleton instance
        config = Config()
        
        # Get the API key from the merged configuration
        return config.get_merged_config().get("api_key")
    
    def reset_local_config(self) -> bool:
        """
        Reset local configuration by removing the local config file.
        
        Returns:
            bool: True if the config file was removed, False if it didn't exist
        """
        config_path = get_local_config_path(self._workspace_dir)
        if config_path.exists():
            config_path.unlink()
            # Clear local configuration
            self._local_config = {}
            # Re-merge and apply configurations
            self._merge_configs()
            self._apply_config()
            return True
        return False
    
    def reset_global_config(self) -> bool:
        """
        Reset global configuration by removing the global config file.
        
        Returns:
            bool: True if the config file was removed, False if it didn't exist
        """
        config_path = get_global_config_path()
        if config_path.exists():
            config_path.unlink()
            # Clear global configuration
            self._global_config = {}
            # Re-merge and apply configurations
            self._merge_configs()
            self._apply_config()
            return True
        return False