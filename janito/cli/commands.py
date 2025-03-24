"""
Command handling logic for Janito CLI.
This module serves as a compatibility layer for the reorganized commands module.
"""
# Re-export the functions from the new module structure
from janito.cli.commands import handle_config_commands, validate_parameters, handle_history

__all__ = [
    "handle_config_commands",
    "validate_parameters",
    "handle_history",
]