"""
Profile management for Janito configuration.
Provides predefined parameter profiles and related functionality.
"""
from .definitions import PROFILES
from .manager import get_profile, get_available_profiles

__all__ = ["PROFILES", "get_profile", "get_available_profiles"]