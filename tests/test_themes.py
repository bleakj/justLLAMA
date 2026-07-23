"""Tests for the ThemeManager."""

import pytest
from unittest.mock import MagicMock

from justllama.config.themes import ThemeManager, ALL_THEMES, THEME_DISPLAY_NAMES


class TestThemeManagerInit:
    def test_default_theme_when_no_settings(self):
        tm = ThemeManager(settings=None)
        assert tm.current_theme() == "default"

    def test_default_theme_with_no_saved_setting(self):
        settings = MagicMock()
        settings.get_string.return_value = ""
        tm = ThemeManager(settings=settings)
        assert tm.current_theme() == "default"

    def test_loads_saved_theme_from_settings(self):
        settings = MagicMock()
        settings.get_string.return_value = "catppuccin-mocha"
        tm = ThemeManager(settings=settings)
        assert tm.current_theme() == "catppuccin-mocha"

    def test_invalid_saved_theme_falls_back_to_default(self):
        settings = MagicMock()
        settings.get_string.return_value = "nonexistent-theme"
        tm = ThemeManager(settings=settings)
        assert tm.current_theme() == "default"


class TestAvailableThemes:
    def test_returns_five_themes(self):
        tm = ThemeManager(settings=None)
        themes = tm.available_themes()
        assert len(themes) == 5

    def test_includes_default(self):
        tm = ThemeManager(settings=None)
        assert "default" in tm.available_themes()

    def test_includes_all_catppuccin_variants(self):
        tm = ThemeManager(settings=None)
        themes = tm.available_themes()
        assert "catppuccin-latte" in themes
        assert "catppuccin-frappe" in themes
        assert "catppuccin-macchiato" in themes
        assert "catppuccin-mocha" in themes


class TestSetTheme:
    def test_set_valid_theme(self):
        settings = MagicMock()
        tm = ThemeManager(settings=settings)
        tm.set_theme("catppuccin-mocha")
        assert tm.current_theme() == "catppuccin-mocha"

    def test_set_theme_persists_to_settings(self):
        settings = MagicMock()
        tm = ThemeManager(settings=settings)
        tm.set_theme("catppuccin-latte")
        settings.set_string.assert_called_once_with("ui/theme", "catppuccin-latte")

    def test_set_invalid_theme_ignored(self):
        settings = MagicMock()
        tm = ThemeManager(settings=settings)
        tm.set_theme("nonexistent")
        assert tm.current_theme() == "default"
        settings.set_string.assert_not_called()

    def test_set_default_theme(self):
        settings = MagicMock()
        settings.get_string.return_value = "catppuccin-mocha"
        tm = ThemeManager(settings=settings)
        tm.set_theme("default")
        assert tm.current_theme() == "default"

    def test_emits_signals(self):
        tm = ThemeManager(settings=None)
        theme_changed_calls = []
        colors_changed_calls = []
        tm.theme_changed.connect(lambda name: theme_changed_calls.append(name))
        tm.colors_changed.connect(lambda: colors_changed_calls.append(True))
        tm.set_theme("catppuccin-frappe")
        assert theme_changed_calls == ["catppuccin-frappe"]
        assert len(colors_changed_calls) == 1


class TestColor:
    def test_default_theme_returns_empty(self):
        tm = ThemeManager(settings=None)
        assert tm.color("backgroundColor") == ""
        assert tm.color("textColor") == ""

    def test_catppuccin_mocha_returns_colors(self):
        settings = MagicMock()
        settings.get_string.return_value = "catppuccin-mocha"
        tm = ThemeManager(settings=settings)
        assert tm.color("backgroundColor") == "#1e1e2e"
        assert tm.color("textColor") == "#cdd6f4"
        assert tm.color("highlightColor") == "#89b4fa"

    def test_catppuccin_latte_returns_colors(self):
        settings = MagicMock()
        settings.get_string.return_value = "catppuccin-latte"
        tm = ThemeManager(settings=settings)
        assert tm.color("backgroundColor") == "#eff1f5"
        assert tm.color("textColor") == "#4c4f69"

    def test_unknown_role_returns_empty(self):
        settings = MagicMock()
        settings.get_string.return_value = "catppuccin-mocha"
        tm = ThemeManager(settings=settings)
        assert tm.color("nonexistentRole") == ""

    def test_all_themes_have_all_roles(self):
        """Every non-default theme must define all 9 Kirigami roles."""
        required_roles = {
            "backgroundColor", "alternateBackgroundColor", "textColor",
            "highlightColor", "highlightedTextColor", "positiveTextColor",
            "negativeTextColor", "disabledTextColor", "borderColor",
        }
        for theme_key, colors in ALL_THEMES.items():
            if theme_key == "default":
                continue
            assert set(colors.keys()) == required_roles, (
                f"Theme {theme_key} is missing roles: {required_roles - set(colors.keys())}"
            )


class TestDisplayNames:
    def test_display_name_for_known_theme(self):
        tm = ThemeManager(settings=None)
        assert tm.display_name("catppuccin-mocha") == "Catppuccin Mocha"
        assert tm.display_name("default") == "Default"

    def test_display_name_for_unknown_returns_key(self):
        tm = ThemeManager(settings=None)
        assert tm.display_name("unknown") == "unknown"

    def test_reverse_lookup(self):
        tm = ThemeManager(settings=None)
        assert tm.theme_key_from_display_name("Catppuccin Mocha") == "catppuccin-mocha"
        assert tm.theme_key_from_display_name("Default") == "default"

    def test_reverse_lookup_unknown_returns_default(self):
        tm = ThemeManager(settings=None)
        assert tm.theme_key_from_display_name("Nonexistent") == "default"

    def test_all_themes_have_display_names(self):
        for key in ALL_THEMES:
            assert key in THEME_DISPLAY_NAMES
