"""
Core configuration components for Janito.
Provides the base Config class and related functionality.
"""
from .singleton import Config
from .properties import ConfigProperties
from .file_operations import (
    get_global_config_path,
    get_local_config_path,
    load_config_file,
    save_config_file,
    merge_configs
)

__all__ = [
    "Config", 
    "ConfigProperties",
    "get_global_config_path",
    "get_local_config_path",
    "load_config_file",
    "save_config_file",
    "merge_configs"
]