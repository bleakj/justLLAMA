"""Theme manager for justLLAMA with Catppuccin palette support."""

from PySide6.QtCore import QObject, Signal, Slot


# Catppuccin color palettes mapped to Kirigami.Theme roles
# Roles: backgroundColor, alternateBackgroundColor, textColor, highlightColor,
#        highlightedTextColor, positiveTextColor, negativeTextColor,
#        disabledTextColor, borderColor

CATPPUCCIN_THEMES = {
    "catppuccin-latte": {
        "backgroundColor": "#eff1f5",       # Base
        "alternateBackgroundColor": "#e6e9ef",  # Mantle
        "textColor": "#4c4f69",             # Text
        "highlightColor": "#1e66f5",        # Blue
        "highlightedTextColor": "#eff1f5",  # Base (readable on blue)
        "positiveTextColor": "#40a02b",     # Green
        "negativeTextColor": "#d20f39",     # Red
        "disabledTextColor": "#9ca0b0",     # Overlay0
        "borderColor": "#bcc0cc",           # Surface1
    },
    "catppuccin-frappe": {
        "backgroundColor": "#303446",       # Base
        "alternateBackgroundColor": "#292c3c",  # Mantle
        "textColor": "#c6d0f5",             # Text
        "highlightColor": "#8caaee",        # Blue
        "highlightedTextColor": "#303446",  # Base (readable on blue)
        "positiveTextColor": "#a6d189",     # Green
        "negativeTextColor": "#e78284",     # Red
        "disabledTextColor": "#737994",     # Overlay0
        "borderColor": "#51576d",           # Surface1
    },
    "catppuccin-macchiato": {
        "backgroundColor": "#24273a",       # Base
        "alternateBackgroundColor": "#1e2030",  # Mantle
        "textColor": "#cad3f5",             # Text
        "highlightColor": "#8aadf4",        # Blue
        "highlightedTextColor": "#24273a",  # Base (readable on blue)
        "positiveTextColor": "#a6da95",     # Green
        "negativeTextColor": "#ed8796",     # Red
        "disabledTextColor": "#6e738d",     # Overlay0
        "borderColor": "#494d64",           # Surface1
    },
    "catppuccin-mocha": {
        "backgroundColor": "#1e1e2e",       # Base
        "alternateBackgroundColor": "#181825",  # Mantle
        "textColor": "#cdd6f4",             # Text
        "highlightColor": "#89b4fa",        # Blue
        "highlightedTextColor": "#1e1e2e",  # Base (readable on blue)
        "positiveTextColor": "#a6e3a1",     # Green
        "negativeTextColor": "#f38ba8",     # Red
        "disabledTextColor": "#6c7086",     # Overlay0
        "borderColor": "#45475a",           # Surface1
    },
}

# All available themes (default = system Kirigami colors)
ALL_THEMES = {
    "default": {},  # No overrides — use system theme
    **CATPPUCCIN_THEMES,
}

# Display names for the UI
THEME_DISPLAY_NAMES = {
    "default": "Default",
    "catppuccin-latte": "Catppuccin Latte",
    "catppuccin-frappe": "Catppuccin Frappe",
    "catppuccin-macchiato": "Catppuccin Macchiato",
    "catppuccin-mocha": "Catppuccin Mocha",
}


class ThemeManager(QObject):
    """Manages application theme selection and exposes colors to QML.

    Signals:
        theme_changed(str): Emitted when theme changes (theme name).
        colors_changed(): Emitted to trigger QML color refresh.
    """

    theme_changed = Signal(str)
    colors_changed = Signal()

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._current = "default"
        if settings:
            saved = settings.get_string("ui/theme")
            if saved in ALL_THEMES:
                self._current = saved

    @Slot(result=list)
    def available_themes(self) -> list:
        """Return list of available theme keys."""
        return list(ALL_THEMES.keys())

    @Slot(result=str)
    def current_theme(self) -> str:
        """Return the currently active theme key."""
        return self._current

    @Slot(str)
    def set_theme(self, name: str):
        """Set the active theme by key. Persists to settings."""
        if name not in ALL_THEMES:
            return
        self._current = name
        if self._settings:
            self._settings.set_string("ui/theme", name)
        self.theme_changed.emit(name)
        self.colors_changed.emit()

    @Slot(str, result=str)
    def color(self, role: str) -> str:
        """Get the color hex for a Kirigami.Theme role in the current theme.

        Returns empty string for 'default' theme (use system colors).
        """
        if self._current == "default":
            return ""
        theme_colors = ALL_THEMES.get(self._current, {})
        return theme_colors.get(role, "")

    @Slot(str, result=str)
    def display_name(self, theme_key: str) -> str:
        """Get the human-readable display name for a theme key."""
        return THEME_DISPLAY_NAMES.get(theme_key, theme_key)

    @Slot(result=str)
    def theme_key_from_display_name(self, display_name: str) -> str:
        """Reverse lookup: display name -> theme key."""
        for key, name in THEME_DISPLAY_NAMES.items():
            if name == display_name:
                return key
        return "default"
