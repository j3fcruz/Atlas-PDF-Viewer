"""atlas_viewer.config — application configuration package."""

from .version import VERSION, APP_NAME, APP_FULL_NAME, WINDOW_TITLE, COPYRIGHT, GUMROAD_URL
from .settings import settings
from .theme import Colors, Fonts, Styles, Spacing, Sizing, FontSize
from .logging_config import configure_logging


__all__ = [
    "VERSION", "APP_NAME", "APP_FULL_NAME", "WINDOW_TITLE", "COPYRIGHT", "GUMROAD_URL",
    "settings",
    "Colors", "Fonts", "Styles", "Spacing", "Sizing", "FontSize",
]
