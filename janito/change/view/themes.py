from dataclasses import dataclass
from typing import Dict
from enum import Enum

class ThemeType(Enum):
    DARK = "dark"
    LIGHT = "light"

# Dark theme colors
DARK_LINE_BACKGROUNDS = {
    'unchanged': '#1A1A1A',
    'added': '#003300',
    'deleted': '#330000',
    'removed': '#330000',
    'success': '#004400'  # Dark green for success messages
}

# Light theme colors
LIGHT_LINE_BACKGROUNDS = {
    'unchanged': 'grey93',         # Light gray for unchanged
    'added': 'light_green',       # Semantic light green for additions
    'deleted': '#FFE6E6',         # Soft light red for deletions
    'removed': '#FFE6E6',
    'success': '#E6FFE6'          # Light green for success messages
}

@dataclass
class ColorTheme:
    text_color: str
    line_backgrounds: Dict[str, str]
    theme_type: ThemeType
    success_color: str = "green"

# Predefined themes
DARK_THEME = ColorTheme(
    text_color="white",
    line_backgrounds=DARK_LINE_BACKGROUNDS,
    theme_type=ThemeType.DARK,
    success_color="green"
)

LIGHT_THEME = ColorTheme(
    text_color="black",
    line_backgrounds=LIGHT_LINE_BACKGROUNDS,
    theme_type=ThemeType.LIGHT,
    success_color="dark_green"
)

DEFAULT_THEME = DARK_THEME

def validate_theme(theme: ColorTheme) -> bool:
    """Validate that a theme contains all required colors"""
    required_line_backgrounds = {'unchanged', 'added', 'deleted'}
    
    if not isinstance(theme, ColorTheme):
        return False
        
    return all(bg in theme.line_backgrounds for bg in required_line_backgrounds)

def get_theme_by_type(theme_type: ThemeType) -> ColorTheme:
    """Get a predefined theme by type"""
    return LIGHT_THEME if theme_type == ThemeType.LIGHT else DARK_THEME