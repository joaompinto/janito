"""
Profile management functions for Janito configuration.
"""
from typing import Dict, Any

from .definitions import PROFILES

def get_available_profiles() -> Dict[str, Dict[str, Any]]:
    """
    Get all available predefined profiles.
    
    Returns:
        Dictionary of profile names to profile settings
    """
    return PROFILES

def get_profile(profile_name: str) -> Dict[str, Any]:
    """
    Get a specific profile by name.
    
    Args:
        profile_name: Name of the profile to retrieve
        
    Returns:
        Dict containing the profile settings
        
    Raises:
        ValueError: If the profile name is not recognized
    """
    profile_name = profile_name.lower()
    if profile_name not in PROFILES:
        valid_profiles = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown profile: {profile_name}. Valid profiles are: {valid_profiles}")
    
    return PROFILES[profile_name]

def create_custom_profile(name: str, temperature: float, description: str = None) -> Dict[str, Any]:
    """
    Create a custom profile with the given parameters.
    
    Args:
        name: Name for the custom profile
        temperature: Temperature value (0.0 to 1.0)
        description: Optional description for the profile
        
    Returns:
        Dict containing the profile settings
        
    Raises:
        ValueError: If temperature is not between 0.0 and 1.0
    """
    if temperature < 0.0 or temperature > 1.0:
        raise ValueError("Temperature must be between 0.0 and 1.0")
    
    # Determine top_p and top_k based on temperature
    if temperature <= 0.3:
        top_p = 0.85
        top_k = 15
    elif temperature <= 0.6:
        top_p = 0.9
        top_k = 40
    else:
        top_p = 0.95
        top_k = 60
    
    # Use provided description or generate a default one
    if description is None:
        if temperature <= 0.3:
            description = "Custom precise profile"
        elif temperature <= 0.6:
            description = "Custom balanced profile"
        else:
            description = "Custom creative profile"
    
    return {
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "description": description
    }