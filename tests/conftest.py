"""Shared fixtures for the justllama test suite."""

import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication — required for QObject / Signal lifecycle."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
