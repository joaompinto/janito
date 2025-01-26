"""Version management module for Janito."""
from pathlib import Path
from typing import Optional
import tomli
from importlib.metadata import version as pkg_version

def get_version() -> str:
    """
    Get Janito version from package metadata or pyproject.toml.
    
    Returns:
        str: The version string
    """
    try:
        return pkg_version("janito")
    except Exception:
        # Fallback to pyproject.toml
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)
                return pyproject_data.get("project", {}).get("version", "unknown")
        return "unknown"