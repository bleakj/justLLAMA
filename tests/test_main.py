"""Tests for the main application entry point and QML context registration."""

import sys
from PySide6.QtCore import QSettings
from pathlib import Path

from justllama.main import main
from justllama.config.settings import AppSettings


def test_main_exposes_app_settings(qapp, tmp_path, monkeypatch):
    mock_properties = {}

    # Set up temporary settings so we don't touch the user's config
    settings_file = str(tmp_path / "test_settings.conf")
    
    # Initialize the temporary settings with safe in-memory/temp values
    temp_settings = QSettings(settings_file, QSettings.IniFormat)
    temp_settings.setValue("memory/db_path", ":memory:")
    temp_settings.setValue("rag/vectorstore_path", str(tmp_path / "vectordb"))
    temp_settings.setValue("models/directory", str(tmp_path / "models"))
    temp_settings.sync()

    # Patch QSettings constructor to load the temp settings file
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)

    # Mock QML Engine and Context
    class MockContext:
        def setContextProperty(self, name, value):
            mock_properties[name] = value

    class MockEngine:
        def rootContext(self):
            return MockContext()
        def load(self, *args, **kwargs):
            pass
        def rootObjects(self):
            return [True]

    # Mock QApplication
    class MockApp:
        def setOrganizationName(self, name):
            pass
        def setApplicationName(self, name):
            pass
        @property
        def aboutToQuit(self):
            class Signal:
                def connect(self, slot):
                    pass
            return Signal()
        def exec(self):
            return 0

    monkeypatch.setattr("justllama.main.QGuiApplication", lambda argv: MockApp())
    monkeypatch.setattr("justllama.main.QQmlApplicationEngine", MockEngine)
    monkeypatch.setattr(sys, "exit", lambda code: None)

    # Run the main function
    main()

    # Assert all required QML context properties were exposed
    assert "appSettings" in mock_properties
    assert isinstance(mock_properties["appSettings"], AppSettings)
    assert "serverManager" in mock_properties
    assert "modelBrowser" in mock_properties
    assert "downloader" in mock_properties
    assert "vectorStore" in mock_properties
    assert "retriever" in mock_properties
    assert "memoryManager" in mock_properties
    assert "updater" in mock_properties
def test_qml_assistant_name(qapp, tmp_path, monkeypatch):
    import os
    from PySide6.QtQml import QQmlApplicationEngine
    from justllama.server.manager import ServerManager
    from justllama.models.browser import ModelBrowser
    from justllama.models.downloader import ModelDownloader
    from justllama.rag.vectorstore import VectorStore
    from justllama.rag.retriever import Retriever
    from justllama.memory.short_term import ShortTermMemory
    from justllama.memory.long_term import LongTermMemory
    from justllama.memory.manager import MemoryManager
    from justllama.server.updater import Updater

    # Set up temporary settings
    settings_file = str(tmp_path / "test_settings_qml.conf")
    temp_settings = QSettings(settings_file, QSettings.IniFormat)
    temp_settings.setValue("memory/db_path", ":memory:")
    temp_settings.setValue("rag/vectorstore_path", str(tmp_path / "vectordb"))
    temp_settings.setValue("models/directory", str(tmp_path / "models"))
    temp_settings.setValue("server/model_path", "/path/to/my-custom-model.gguf")
    temp_settings.sync()

    # Patch QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)

    # Initialize components
    settings = AppSettings()
    server_manager = ServerManager()
    model_browser = ModelBrowser(settings.models_directory)
    model_downloader = ModelDownloader(settings.models_directory)
    vector_store = VectorStore(
        settings.get_string("rag/vectorstore_path"),
        chunk_size=settings.get_int("rag/chunk_size"),
        chunk_overlap=settings.get_int("rag/chunk_overlap"),
    )
    retriever = Retriever(vector_store)
    short_term = ShortTermMemory(max_size=settings.get_int("memory/max_short_term"))
    long_term = LongTermMemory(db_path=":memory:")
    memory_manager = MemoryManager(short_term, long_term, settings.memory_enabled)
    updater = Updater()

    # Set QML platform for headless run
    monkeypatch.setenv("QT_QPA_PLATFORM", "minimal")
    
    # Set QML import path
    qml_dir = str(Path(__file__).parent.parent / "justllama" / "ui" / "qml")
    monkeypatch.setenv("QML2_IMPORT_PATH", qml_dir)

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()

    # Expose context properties
    ctx.setContextProperty("appSettings", settings)
    ctx.setContextProperty("serverManager", server_manager)
    ctx.setContextProperty("modelBrowser", model_browser)
    ctx.setContextProperty("downloader", model_downloader)
    ctx.setContextProperty("vectorStore", vector_store)
    ctx.setContextProperty("retriever", retriever)
    ctx.setContextProperty("memoryManager", memory_manager)
    ctx.setContextProperty("updater", updater)

    # Load Main.qml
    qml_file = Path(__file__).parent.parent / "justllama" / "ui" / "qml" / "Main.qml"
    engine.load(str(qml_file.resolve()))

    root_objects = engine.rootObjects()
    assert len(root_objects) > 0, "Failed to load Main.qml"

    # Find assistantName property in the object tree
    from PySide6.QtCore import QObject
    chat_view = root_objects[0].findChild(QObject, "chatView")
    assert chat_view is not None, "Failed to find ChatView in QML tree"
    assistant_name = chat_view.property("assistantName")
    assert assistant_name == "my-custom-model", f"Expected assistantName to be 'my-custom-model', got '{assistant_name}'"

    # Test dynamic update reactively handles PySide6 QVariant wrappers
    settings.set_string("server/model_path", "/path/to/another-model-v3.gguf")
    assistant_name = chat_view.property("assistantName")
    assert assistant_name == "another-model-v3", f"Expected assistantName to be 'another-model-v3', got '{assistant_name}'"
