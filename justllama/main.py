"""Entry point: QGuiApplication + QQuickView with all context properties wired."""

import sys
import os
import atexit
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from justllama.config.settings import AppSettings
from justllama.server.manager import ServerManager
from justllama.server.client import LlamaClient
from justllama.server.updater import Updater
from justllama.models.browser import ModelBrowser
from justllama.models.downloader import ModelDownloader
from justllama.models.profiles import ModelProfiles
from justllama.rag.vectorstore import VectorStore
from justllama.rag.retriever import Retriever
from justllama.memory.short_term import ShortTermMemory
from justllama.memory.long_term import LongTermMemory
from justllama.memory.manager import MemoryManager


def main():
    app = QGuiApplication(sys.argv)
    app.setOrganizationName("justllama")
    app.setApplicationName("justllama")

    # Ensure QML import path includes our QML directory
    qml_dir = str(Path(__file__).parent / "ui" / "qml")
    os.environ["QML2_IMPORT_PATH"] = qml_dir

    # Initialize all components
    settings = AppSettings()
    server_manager = ServerManager()
    client = LlamaClient(port=settings.server_port)
    model_browser = ModelBrowser(settings.models_directory)
    model_downloader = ModelDownloader(settings.models_directory)
    model_profiles = ModelProfiles()
    vector_store = VectorStore(settings.get_string("rag/vectorstore_path"))
    retriever = Retriever(vector_store)

    short_term = ShortTermMemory(max_size=settings.get_int("memory/max_short_term"))
    long_term = LongTermMemory(db_path=settings.get_string("memory/db_path"))
    memory_manager = MemoryManager(
        short_term, long_term, settings.memory_enabled
    )
    updater = Updater()

    # Ensure server is killed on app close
    def _shutdown():
        if server_manager.is_running():
            server_manager.stop()
    atexit.register(_shutdown)
    app.aboutToQuit.connect(_shutdown)


    # Create QML engine
    engine = QQmlApplicationEngine()

    # Expose Python objects to QML
    ctx = engine.rootContext()
    ctx.setContextProperty("appSettings", settings)
    ctx.setContextProperty("serverManager", server_manager)
    ctx.setContextProperty("llamaClient", client)
    ctx.setContextProperty("modelBrowser", model_browser)
    ctx.setContextProperty("downloader", model_downloader)
    ctx.setContextProperty("profiles", model_profiles)
    ctx.setContextProperty("vectorStore", vector_store)
    ctx.setContextProperty("retriever", retriever)
    ctx.setContextProperty("memoryManager", memory_manager)
    ctx.setContextProperty("updater", updater)
    qml_file = Path(__file__).parent / "ui" / "qml" / "Main.qml"
    if qml_file.exists():
        engine.load(qml_file.as_uri())
    else:
        # Fallback: load as module
        engine.addImportPath(qml_dir)
        engine.loadFromModule("Main", "Main")

    if not engine.rootObjects():
        print("Error: Failed to load QML", file=sys.stderr)
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
