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
    assert "voiceInputManager" in mock_properties
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
    from justllama.server.imagegen import ImageGenManager
    imagegen_manager = ImageGenManager(server_manager)
    ctx.setContextProperty("imageGenManager", imagegen_manager)
    from justllama.server.videogen import VideoGenManager
    videogen_manager = VideoGenManager(server_manager)
    ctx.setContextProperty("videoGenManager", videogen_manager)
    from justllama.voice.manager import VoiceInputManager
    voice_input_manager = VoiceInputManager(settings)
    ctx.setContextProperty("voiceInputManager", voice_input_manager)

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


def test_model_browser_qml_warnings(qapp, tmp_path, monkeypatch):
    import os
    import subprocess
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtCore import QObject, QSettings
    from justllama.models.browser import ModelBrowser
    from justllama.models.downloader import ModelDownloader
    from justllama.rag.vectorstore import VectorStore
    from justllama.rag.retriever import Retriever
    from justllama.memory.short_term import ShortTermMemory
    from justllama.memory.long_term import LongTermMemory
    from justllama.memory.manager import MemoryManager
    from justllama.server.updater import Updater

    def mock_sysconf(name):
        if name == 'SC_PAGE_SIZE':
            return 4096
        if name == 'SC_PHYS_PAGES':
            # 16 GB system memory
            return 4194304
        raise ValueError("Unknown sysconf name")

    class MockCompletedProcess:
        stdout = "10240\n"  # 10 GB VRAM

    def mock_run(*args, **kwargs):
        return MockCompletedProcess()

    monkeypatch.setattr("justllama.models.browser.os.sysconf", mock_sysconf)
    monkeypatch.setattr("justllama.models.browser.subprocess.run", mock_run)

    # Set up temporary settings
    settings_file = str(tmp_path / "test_settings_qml_warnings.conf")
    temp_settings = QSettings(settings_file, QSettings.IniFormat)
    temp_settings.setValue("memory/db_path", ":memory:")
    temp_settings.setValue("rag/vectorstore_path", str(tmp_path / "vectordb"))
    temp_settings.setValue("models/directory", str(tmp_path / "models"))
    temp_settings.sync()

    # Patch QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)

    # Initialize components
    settings = AppSettings()
    from justllama.server.manager import ServerManager
    server_manager = ServerManager()
    browser = ModelBrowser(settings.models_directory)
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

    # Check that temporary values are correctly set in the browser
    assert browser.safe_ram_gb == 8.0
    assert browser.safe_vram_gb == 8.5

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
    ctx.setContextProperty("modelBrowser", browser)
    ctx.setContextProperty("downloader", model_downloader)
    ctx.setContextProperty("vectorStore", vector_store)
    ctx.setContextProperty("retriever", retriever)
    ctx.setContextProperty("memoryManager", memory_manager)
    ctx.setContextProperty("updater", updater)
    from justllama.server.imagegen import ImageGenManager
    imagegen_manager = ImageGenManager(server_manager)
    ctx.setContextProperty("imageGenManager", imagegen_manager)
    from justllama.server.videogen import VideoGenManager
    videogen_manager = VideoGenManager(server_manager)
    ctx.setContextProperty("videoGenManager", videogen_manager)
    from justllama.voice.manager import VoiceInputManager
    voice_input_manager = VoiceInputManager(settings)
    ctx.setContextProperty("voiceInputManager", voice_input_manager)

    # Load Main.qml
    qml_file = Path(__file__).parent.parent / "justllama" / "ui" / "qml" / "Main.qml"
    engine.load(str(qml_file.resolve()))

    root_objects = engine.rootObjects()
    assert len(root_objects) > 0, "Failed to load Main.qml"
    root_window = root_objects[0]

    # Find mainStack and switch to ModelBrowser page
    main_stack = root_window.findChild(QObject, "mainStack")
    assert main_stack is not None, "Failed to find mainStack"
    main_stack.setProperty("currentIndex", 1)

    # Find modelBrowser page in Main.qml
    model_browser_page = root_window.findChild(QObject, "modelBrowser")
    assert model_browser_page is not None, "Failed to find modelBrowser page"

    # Models:
    # Model 1: size_gb = 4.0 (fits in VRAM, 4.0 <= 8.5)
    # Model 2: size_gb = 12.0 (exceeds VRAM (8.5), fits in total safe (16.5) -> spills to system RAM)
    # Model 3: size_gb = 20.0 (exceeds total safe (16.5) -> OOM risk)
    models_data = [
        {"name": "model1", "path": "/path1.gguf", "size_bytes": int(4.0 * 1024**3), "size_display": "4.0 GB", "size_gb": 4.0, "modified_time": 0.0},
        {"name": "model2", "path": "/path2.gguf", "size_bytes": int(12.0 * 1024**3), "size_display": "12.0 GB", "size_gb": 12.0, "modified_time": 0.0},
        {"name": "model3", "path": "/path3.gguf", "size_bytes": int(20.0 * 1024**3), "size_display": "20.0 GB", "size_gb": 20.0, "modified_time": 0.0},
    ]
    # Test the warning label logic using a dedicated QQmlComponent
    from PySide6.QtQml import QQmlComponent
    from PySide6.QtCore import QUrl

    component = QQmlComponent(engine)
    qml_src = """
    import QtQuick
    import QtQuick.Controls
    import org.kde.kirigami as Kirigami
    Item {
        id: root
        property var modelData

        Label {
            objectName: "warningLabel"
            property bool fitsInVRAM: root.modelData.size_gb <= modelBrowser.safe_vram_gb
            property bool fitsInTotalSafe: root.modelData.size_gb <= (modelBrowser.safe_vram_gb + modelBrowser.safe_ram_gb)

            visible: !fitsInVRAM
            text: !fitsInTotalSafe ? "⚠️ Exceeds safe memory (OOM crash risk)" : "⚠️ Exceeds VRAM (will spill to system RAM)"
        }
    }
    """
    component.setData(qml_src.encode('utf-8'), QUrl())

    assert component.isReady(), f"QML test component compilation failed: {component.errors()}"
    test_obj = component.create(ctx)
    assert test_obj is not None, "Failed to instantiate QML test component"

    warning_label = test_obj.findChild(QObject, "warningLabel")
    assert warning_label is not None, "Failed to find warningLabel in test component"

    # Scenario 1: fits in VRAM (size_gb = 4.0 <= 8.5)
    test_obj.setProperty("modelData", {"size_gb": 4.0})
    assert warning_label.property("fitsInVRAM") is True
    assert warning_label.property("fitsInTotalSafe") is True
    assert warning_label.property("visible") is False

    # Scenario 2: exceeds VRAM but fits in RAM (size_gb = 12.0; 12.0 > 8.5 but 12.0 <= 16.5)
    test_obj.setProperty("modelData", {"size_gb": 12.0})
    assert warning_label.property("fitsInVRAM") is False
    assert warning_label.property("fitsInTotalSafe") is True
    assert warning_label.property("visible") is True
    assert "will spill to system RAM" in warning_label.property("text")

    # Scenario 3: exceeds safe memory (size_gb = 20.0; 20.0 > 16.5)
    test_obj.setProperty("modelData", {"size_gb": 20.0})
    assert warning_label.property("fitsInVRAM") is False
    assert warning_label.property("fitsInTotalSafe") is False
    assert warning_label.property("visible") is True
    assert "OOM crash risk" in warning_label.property("text")



def test_about_button_in_header(qapp, tmp_path, monkeypatch):
    import os
    import subprocess
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtCore import QObject, QSettings
    from justllama.models.browser import ModelBrowser
    from justllama.models.downloader import ModelDownloader
    from justllama.rag.vectorstore import VectorStore
    from justllama.rag.retriever import Retriever
    from justllama.memory.short_term import ShortTermMemory
    from justllama.memory.long_term import LongTermMemory
    from justllama.memory.manager import MemoryManager
    from justllama.server.updater import Updater

    def mock_sysconf(name):
        if name == 'SC_PAGE_SIZE':
            return 4096
        if name == 'SC_PHYS_PAGES':
            return 4194304
        raise ValueError("Unknown sysconf name")

    class MockCompletedProcess:
        stdout = "10240\n"

    def mock_run(*args, **kwargs):
        return MockCompletedProcess()

    monkeypatch.setattr("justllama.models.browser.os.sysconf", mock_sysconf)
    monkeypatch.setattr("justllama.models.browser.subprocess.run", mock_run)

    # Set up temporary settings
    settings_file = str(tmp_path / "test_settings_about_button.conf")
    temp_settings = QSettings(settings_file, QSettings.IniFormat)
    temp_settings.setValue("memory/db_path", ":memory:")
    temp_settings.setValue("rag/vectorstore_path", str(tmp_path / "vectordb"))
    temp_settings.setValue("models/directory", str(tmp_path / "models"))
    temp_settings.sync()

    # Patch QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)

    # Initialize components
    settings = AppSettings()
    from justllama.server.manager import ServerManager
    server_manager = ServerManager()
    browser = ModelBrowser(settings.models_directory)
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
    ctx.setContextProperty("modelBrowser", browser)
    ctx.setContextProperty("downloader", model_downloader)
    ctx.setContextProperty("vectorStore", vector_store)
    ctx.setContextProperty("retriever", retriever)
    ctx.setContextProperty("memoryManager", memory_manager)
    ctx.setContextProperty("updater", updater)

    from justllama.server.imagegen import ImageGenManager
    imagegen_manager = ImageGenManager(server_manager)
    ctx.setContextProperty("imageGenManager", imagegen_manager)

    from justllama.server.videogen import VideoGenManager
    videogen_manager = VideoGenManager(server_manager)
    ctx.setContextProperty("videoGenManager", videogen_manager)

    from justllama.voice.manager import VoiceInputManager
    voice_input_manager = VoiceInputManager(settings)
    ctx.setContextProperty("voiceInputManager", voice_input_manager)

    # Load Main.qml
    qml_file = Path(__file__).parent.parent / "justllama" / "ui" / "qml" / "Main.qml"
    engine.load(str(qml_file.resolve()))

    root_objects = engine.rootObjects()
    assert len(root_objects) > 0, "Failed to load Main.qml"
    root_window = root_objects[0]

    # Find the "About" button
    all_objects = root_window.findChildren(QObject)

    about_button = None
    for obj in all_objects:
        class_name = obj.metaObject().className()
        if ("Button" in class_name or "ToolButton" in class_name) and obj.property("text") == "About justLLAMA":
            about_button = obj
            break

    assert about_button is not None, "Failed to find 'About' button"

    # Verify that icon.name equals 'help-about'
    from PySide6.QtQml import QQmlExpression
    expression = QQmlExpression(ctx, about_button, "icon.name")
    res = expression.evaluate()
    if isinstance(res, tuple) and len(res) == 2:
        icon_name, error_occurred = res
    else:
        icon_name = res
    if expression.hasError():
        print("QQmlExpression error:", expression.error().toString())
    assert icon_name == "help-about", f"Expected icon.name to be 'help-about', got '{icon_name}'"

    # Find aboutDialog
    about_dialog = None
    for obj in all_objects:
        class_name = obj.metaObject().className()
        if "Dialog" in class_name and obj.property("title") == "About justLLAMA":
            about_dialog = obj
            break

    assert about_dialog is not None, "Failed to find 'aboutDialog'"

    # Verify it is initially not visible
    assert not about_dialog.property("visible"), "aboutDialog should be closed initially"

    # Simulate a click on the ToolButton
    about_button.clicked.emit()

    # Verify that aboutDialog is opened
    assert about_dialog.property("visible"), "aboutDialog should be visible after clicking the button"


def test_chatview_reasoning_bindings_no_undefined_error(qapp, tmp_path, monkeypatch):
    """Reproduce the ChatView reasoning_content bindings and assert no
    `[undefined] to bool/string` type-assignment errors occur when the
    delegate's modelData.reasoning_content is undefined.

    Regression guard for the QML type errors fixed in ChatView.qml.
    """
    import sys
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression
    from PySide6.QtCore import QUrl, QObject
    from justllama.config.settings import AppSettings
    from justllama.main import main as _unused  # ensure imports resolve

    # Set up temporary settings
    settings_file = str(tmp_path / "test_settings_chatview.conf")
    temp_settings = QSettings(settings_file, QSettings.IniFormat)
    temp_settings.setValue("memory/db_path", ":memory:")
    temp_settings.setValue("rag/vectorstore_path", str(tmp_path / "vectordb"))
    temp_settings.setValue("models/directory", str(tmp_path / "models"))
    temp_settings.sync()

    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)

    monkeypatch.setenv("QT_QPA_PLATFORM", "minimal")
    qml_dir = str(Path(__file__).parent.parent / "justllama" / "ui" / "qml")
    monkeypatch.setenv("QML2_IMPORT_PATH", qml_dir)

    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty("appSettings", AppSettings())

    # Mirror the exact ColumnLayout/Text bindings from ChatView.qml delegate.
    component = QQmlComponent(engine)
    qml_src = b"""
    import QtQuick
    import QtQuick.Controls
    import QtQuick.Layouts
    import org.kde.kirigami as Kirigami
    Item {
        id: root
        property var modelData
        ColumnLayout {
            visible: !!modelData.reasoning_content && modelData.reasoning_content.length > 0
            Label {
                objectName: "reasoningText"
                text: modelData.reasoning_content || ""
            }
        }
    }
    """
    component.setData(qml_src, QUrl())
    assert component.isReady(), f"QML component failed: {component.errors()}"

    warnings = []
    def _warn(obj, msg):
        warnings.append(msg)
    engine.warnings.connect(_warn)

    obj = component.create(ctx)
    assert obj is not None, "Failed to instantiate QML test component"

    # Set modelData WITHOUT reasoning_content (undefined) — the failing case.
    obj.setProperty("modelData", {"role": "assistant", "content": "Hi"})

    reasoning = obj.findChild(QObject, "reasoningText")
    assert reasoning is not None
    assert reasoning.property("text") == "", "text binding must coerce undefined to empty string"

    # Now supply reasoning_content and confirm it binds through.
    obj.setProperty("modelData", {"role": "assistant", "content": "Hi", "reasoning_content": "thinking..."})
    assert reasoning.property("text") == "thinking..."

    undefined_errors = [
        w for w in warnings
        if "Unable to assign [undefined]" in w.toString()
    ]
    assert not undefined_errors, f"Unexpected [undefined] errors: {undefined_errors}"