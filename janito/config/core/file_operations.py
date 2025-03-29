"""
File operations for configuration management.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional

def get_global_config_path() -> Path:
    """
    Get the path to the global configuration file.
    
    Returns:
        Path object pointing to the global configuration file (~/.janito/config.json)
    """
    return Path.home() / ".janito" / "config.json"

def get_local_config_path(workspace_dir: str) -> Path:
    """
    Get the path to the local configuration file.
    
    Args:
        workspace_dir: Current workspace directory
        
    Returns:
        Path object pointing to the local configuration file (.janito/config.json)
    """
    return Path(workspace_dir) / ".janito" / "config.json"

def load_config_file(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from a file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dict containing the configuration, empty dict if file doesn't exist or error occurs
    """
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load configuration from {config_path}: {str(e)}")
        return {}

def save_config_file(config_path: Path, config_data: Dict[str, Any]) -> bool:
    """
    Save configuration to a file.
    
    Args:
        config_path: Path to the configuration file
        config_data: Configuration data to save
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write configuration to file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Warning: Failed to save configuration to {config_path}: {str(e)}")
        return False

def merge_configs(global_config: Dict[str, Any], local_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge global and local configurations with local taking precedence.
    
    Args:
        global_config: Global configuration dictionary
        local_config: Local configuration dictionary
        
    Returns:
        Merged configuration dictionary
    """
    # Start with global config
    merged_config = global_config.copy()
    
    # Override with local config
    for key, value in local_config.items():
        merged_config[key] = value
    
    return merged_config