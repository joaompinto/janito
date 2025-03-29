"""
Validation functions for configuration-related CLI commands.
"""
from typing import Tuple, Any, Union, Optional

def validate_temperature(value: str) -> Tuple[bool, Union[float, str]]:
    """
    Validate a temperature value from a string input.
    
    Args:
        value: String representation of a temperature value
        
    Returns:
        Tuple of (is_valid, result)
        If valid, result is the float value
        If invalid, result is an error message
    """
    try:
        temp_value = float(value)
        if temp_value < 0.0 or temp_value > 1.0:
            return False, "Temperature must be between 0.0 and 1.0"
        return True, temp_value
    except ValueError:
        return False, f"Invalid temperature value: {value}. Must be a float between 0.0 and 1.0."

def validate_boolean_value(value: str) -> Tuple[bool, Union[bool, str]]:
    """
    Validate a boolean value from a string input.
    
    Args:
        value: String representation of a boolean value
        
    Returns:
        Tuple of (is_valid, result)
        If valid, result is the boolean value
        If invalid, result is an error message
    """
    try:
        lower_value = value.lower()
        if lower_value in ["true", "yes", "1", "on", "y"]:
            return True, True
        elif lower_value in ["false", "no", "0", "off", "n"]:
            return True, False
        else:
            return False, f"Invalid boolean value: {value}. Use 'true', 'false', 'yes', 'no', '1', '0', 'on', or 'off'."
    except Exception:
        return False, f"Invalid boolean value: {value}. Use 'true', 'false', 'yes', 'no', '1', '0', 'on', or 'off'."

def validate_config_key_value(config_str: str) -> Tuple[bool, Union[Tuple[str, str], str]]:
    """
    Validate a configuration key-value pair from a string input.
    
    Args:
        config_str: String in the format 'key=value'
        
    Returns:
        Tuple of (is_valid, result)
        If valid, result is a tuple of (key, value)
        If invalid, result is an error message
    """
    try:
        # Parse the config string
        config_parts = config_str.split("=", 1)
        if len(config_parts) != 2:
            return False, "Invalid configuration format. Use 'key=value' format."
            
        key = config_parts[0].strip()
        value = config_parts[1].strip()
        
        # Remove quotes if present
        if (value.startswith("'") and value.endswith("'")) or \
           (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        
        return True, (key, value)
    except Exception as e:
        return False, f"Invalid configuration format: {str(e)}"