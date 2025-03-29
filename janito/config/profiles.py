"""
Predefined parameter profiles for Janito.
"""
from typing import Dict, Any

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

def get_available_profiles() -> Dict[str, Dict[str, Any]]:
    """Get all available predefined profiles."""
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