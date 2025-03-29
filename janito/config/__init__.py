"""
Configuration module for Janito.
Provides a singleton Config class to access configuration values.
Supports both local and global configuration with merging functionality.
"""
from .core.singleton import Config
from .profiles.definitions import PROFILES
from .profiles.manager import get_available_profiles, get_profile

# Convenience function to get the config instance
def get_config() -> Config:
    """Get the singleton Config instance."""
    return Config()

# Re-export the Config class for backward compatibility
__all__ = ["Config", "PROFILES", "get_config", "get_available_profiles", "get_profile"]