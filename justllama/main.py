"""Entry point: QGuiApplication + QQuickView with all context properties wired."""

import sys
import os
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from justllama.config.settings import AppSettings
from justllama.server.manager import ServerManager
from justllama.server.council import CouncilManager
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
    # Expose qml_dir to Qt's QML discovery — append to any existing entries
    # the launcher or test harness set up.
    qml_dir = str(Path(__file__).parent / "ui" / "qml")
    existing_qml = os.environ.get("QML2_IMPORT_PATH", "")
    parts = [p for p in existing_qml.split(os.pathsep) if p]
    if qml_dir not in parts:
        parts.insert(0, qml_dir)
    os.environ["QML2_IMPORT_PATH"] = os.pathsep.join(parts)
    qml_file = Path(__file__).parent / "ui" / "qml" / "Main.qml"

    # Initialize all components
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
    long_term = LongTermMemory(db_path=settings.get_string("memory/db_path"))
    memory_manager = MemoryManager(
        short_term, long_term, settings.memory_enabled
    )
    updater = Updater()
    council_manager = CouncilManager(settings, server_manager)
    model_profiles = ModelProfiles()

    # Ensure server is killed and resources released on app close.
    # Always run ``stop()`` (now a no-op-cleanup if the process is already
    # gone) so log-reader threads don't outlive the process.
    def _shutdown():
        server_manager.stop()
        long_term.close()
    app.aboutToQuit.connect(_shutdown)


    # Create QML engine
    engine = QQmlApplicationEngine()

    # Expose Python objects to QML
    ctx = engine.rootContext()
    ctx.setContextProperty("appSettings", settings)
    ctx.setContextProperty("serverManager", server_manager)
    ctx.setContextProperty("modelBrowser", model_browser)
    ctx.setContextProperty("downloader", model_downloader)
    ctx.setContextProperty("vectorStore", vector_store)
    ctx.setContextProperty("retriever", retriever)
    ctx.setContextProperty("memoryManager", memory_manager)
    ctx.setContextProperty("updater", updater)
    ctx.setContextProperty("councilManager", council_manager)
    ctx.setContextProperty("modelProfiles", model_profiles)
    if qml_file.exists():
        engine.load(qml_file.as_uri())
    else:
        # Fallback: load as module
        engine.addImportPath(str(Path(__file__).parent.parent))
        engine.loadFromModule("justllama.ui.qml", "Main")

    if not engine.rootObjects():
        print("Error: Failed to load QML", file=sys.stderr)
        sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
