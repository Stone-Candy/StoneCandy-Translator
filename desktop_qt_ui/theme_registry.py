"""
Shared theme metadata for the desktop Qt UI.

Keep this module free of Qt imports so config/state code can reuse the same
theme registry as the runtime styling layer.
"""

THEME_OPTIONS = (
    ("light", "Light"),
    ("dark", "Dark"),
    ("gray", "Gray"),
    ("ocean", "Ocean"),
    ("forest", "Forest"),
    ("sunset", "Sunset"),
    ("rose", "Rose"),
    ("system", "Follow System"),
)

DEFAULT_THEME = "light"
AVAILABLE_THEMES = tuple(theme_key for theme_key, _ in THEME_OPTIONS if theme_key != "system")
VALID_THEMES = frozenset(theme_key for theme_key, _ in THEME_OPTIONS)
VALID_THEME_PREFERENCES = frozenset(AVAILABLE_THEMES)
