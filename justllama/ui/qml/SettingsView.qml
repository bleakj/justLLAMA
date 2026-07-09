import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: settingsPage
    title: "Settings"

    // Update state machine
    property string updateState: "idle"
    property bool serverRunning: false
    property bool showServerLog: false
    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)

    Component.onCompleted: {
        serverRunning = serverManager.is_running()
    }
    Connections {
        target: serverManager
        function onServer_started(port) { serverRunning = true }
        function onServer_stopped() { serverRunning = false }
        function onServer_error(msg) { serverRunning = false; errorToast.show("Server error: " + msg) }
    }
    // Updater signal handlers
    Connections {
        target: updater
        function onChecking() {
            updateState = "checking"
            updateBtn.text = "Checking..."
            updateBtn.enabled = false
            updateStatus.text = ""
        }
        function onUpdate_available(tag) {
            updateState = "available"
            updateBtn.text = "Download " + tag
            updateBtn.enabled = true
            updateBtn.icon.name = "document-download"
            updateStatus.text = "New version available: " + tag
            updateStatus.color = Kirigami.Theme.highlightColor
        }
        function onUp_to_date(version) {
            updateState = "up_to_date"
            updateBtn.text = "Check for Updates"
            updateBtn.enabled = true
            updateBtn.icon.name = "system-software-update"
            updateStatus.text = "You have the newest version already! (" + version + ")"
            updateStatus.color = Kirigami.Theme.positiveTextColor
        }
        function onDownload_started() {
            updateState = "downloading"
            updateBtn.text = "Downloading..."
            updateBtn.enabled = false
            updateBtn.icon.name = "download"
            downloadProgress.visible = true
            downloadProgress.value = 0
            updateStatus.text = "Downloading update..."
            updateStatus.color = Kirigami.Theme.highlightColor
        }
        function onDownload_progress(progress) {
            downloadProgress.value = progress
        }
        function onDownload_finished(tag) {
            updateState = "downloaded"
            updateBtn.text = "Install " + tag
            updateBtn.enabled = true
            updateBtn.icon.name = "system-software-update"
            downloadProgress.visible = false
            updateStatus.text = "Ready to install " + tag + ". App will restart after installation."
            updateStatus.color = Kirigami.Theme.positiveTextColor
        }
        function onDownload_error(msg) {
            updateState = "idle"
            updateBtn.text = "Check for Updates"
            updateBtn.enabled = true
            updateBtn.icon.name = "system-software-update"
            downloadProgress.visible = false
            updateStatus.text = "Download failed: " + msg
            updateStatus.color = Kirigami.Theme.negativeTextColor
        }
        function onInstall_error(msg) {
            updateState = "downloaded"
            updateBtn.text = "Install"
            updateBtn.enabled = true
            updateStatus.text = "Install failed: " + msg
            updateStatus.color = Kirigami.Theme.negativeTextColor
        }
    }


    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        // Branding header
        Rectangle {
            Layout.fillWidth: true
            height: 48
            radius: Kirigami.Units.cornerRadius
            color: Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.1)

            Label {
                anchors.centerIn: parent
                text: "⚙️ justLLAMA Settings"
                font.bold: true
                font.pointSize: 16
                color: Kirigami.Theme.highlightColor
            }
        }

        // Server Settings
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Server Settings"
                    font.bold: true
                    font.pointSize: 14
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Port:"; Layout.preferredWidth: 120 }
                    SpinBox {
                        from: 1024
                        to: 65535
                        value: appSettings.get_int("server/port")
                        onValueModified: appSettings.set_int("server/port", value)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Context Size:"; Layout.preferredWidth: 120 }
                    ComboBox {
                        id: ctxSizeCombo
                        property bool _ready: false
                        model: ["8K (8192)", "16K (16384)", "32K (32768)", "64K (65536)", "128K (131072)", "200K (204800)"]
                        currentIndex: {
                            var v = appSettings.get_int("server/ctx_size")
                            var sizes = [8192, 16384, 32768, 65536, 131072, 204800]
                            var idx = sizes.indexOf(v)
                            if (idx >= 0) return idx
                            // Coerce to nearest predefined size
                            var closest = sizes[0], minDist = Math.abs(v - sizes[0])
                            for (var i = 1; i < sizes.length; i++) {
                                var d = Math.abs(v - sizes[i])
                                if (d < minDist) { minDist = d; closest = sizes[i] }
                            }
                            appSettings.set_int("server/ctx_size", closest)
                            return sizes.indexOf(closest)
                        }
                        Component.onCompleted: _ready = true
                        onCurrentIndexChanged: {
                            if (!_ready) return
                            var sizes = [8192, 16384, 32768, 65536, 131072, 204800]
                            appSettings.set_int("server/ctx_size", sizes[currentIndex])
                        }
                        Layout.fillWidth: true
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "GPU Layers:"; Layout.preferredWidth: 120 }
                    SpinBox {
                        from: 0
                        to: 200
                        value: appSettings.get_int("server/n_gpu_layers")
                        onValueModified: appSettings.set_int("server/n_gpu_layers", value)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Threads:"; Layout.preferredWidth: 120 }
                    SpinBox {
                        from: -1
                        to: 64
                        value: appSettings.get_int("server/threads")
                        onValueModified: appSettings.set_int("server/threads", value)
                    }
                    Label {
                        text: "(-1 = auto)"
                        color: Kirigami.Theme.disabledTextColor
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Binary:"; Layout.preferredWidth: 120 }
                    TextField {
                        id: binaryField
                        Layout.fillWidth: true
                        text: appSettings.get_string("server/binary")
                        onEditingFinished: appSettings.set_string("server/binary", text)
                    }
                }
            }
        }

        // Model Directory
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Model Directory"
                    font.bold: true
                    font.pointSize: 14
                }

                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: modelDirField
                        Layout.fillWidth: true
                        text: appSettings.get_string("models/directory")
                        onEditingFinished: appSettings.set_string("models/directory", text)
                    }
                    Button {
                        text: "Browse"
                        onClicked: folderDialog.open()
                    }
                }
            }
        }
        // Council Models Settings
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Council Models"
                    font.bold: true
                    font.pointSize: 14
                }

                Label {
                    text: "Select three different models to query in Council mode. They will run sequentially."
                    font.italic: true
                    color: Kirigami.Theme.disabledTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                // Model 1
                Label { text: "Council Model 1:" }
                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: councilModel1Field
                        Layout.fillWidth: true
                        text: appSettings.get_string("council/model_1")
                        placeholderText: "Path to first model (.gguf)"
                        onEditingFinished: appSettings.set_string("council/model_1", text)
                    }
                    Button {
                        text: "Browse"
                        onClicked: {
                            modelFileDialog.targetSettingKey = "council/model_1"
                            modelFileDialog.open()
                        }
                    }
                }

                // Model 2
                Label { text: "Council Model 2:" }
                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: councilModel2Field
                        Layout.fillWidth: true
                        text: appSettings.get_string("council/model_2")
                        placeholderText: "Path to second model (.gguf)"
                        onEditingFinished: appSettings.set_string("council/model_2", text)
                    }
                    Button {
                        text: "Browse"
                        onClicked: {
                            modelFileDialog.targetSettingKey = "council/model_2"
                            modelFileDialog.open()
                        }
                    }
                }

                // Model 3
                Label { text: "Council Model 3:" }
                RowLayout {
                    Layout.fillWidth: true
                    TextField {
                        id: councilModel3Field
                        Layout.fillWidth: true
                        text: appSettings.get_string("council/model_3")
                        placeholderText: "Path to third model (.gguf)"
                        onEditingFinished: appSettings.set_string("council/model_3", text)
                    }
                    Button {
                        text: "Browse"
                        onClicked: {
                            modelFileDialog.targetSettingKey = "council/model_3"
                            modelFileDialog.open()
                        }
                    }
                }
            }
        }

        // RAG Settings
        Rectangle {
            Layout.fillWidth: true
            clip: true
            radius: Kirigami.Units.cornerRadius
            color: ragEnabledSwitch.checked
                ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.15)
                : Kirigami.Theme.backgroundColor
            border.color: ragEnabledSwitch.checked
                ? Kirigami.Theme.highlightColor
                : safeBorderColor
            border.width: ragEnabledSwitch.checked ? 2 : 1

            Behavior on color { ColorAnimation { duration: 300 } }
            Behavior on border.color { ColorAnimation { duration: 300 } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: ragEnabledSwitch.checked ? "📚 RAG Enabled" : "RAG Settings"
                        font.bold: true
                        font.pointSize: 14
                        color: ragEnabledSwitch.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
                        Behavior on color { ColorAnimation { duration: 300 } }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Enabled:"
                        Layout.preferredWidth: 120
                        color: ragEnabledSwitch.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                    }
                    Switch {
                        id: ragEnabledSwitch
                        checked: appSettings.get_bool("rag/enabled")
                        onCheckedChanged: appSettings.set_bool("rag/enabled", checked)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Chunk Size:"; Layout.preferredWidth: 120 }
                    SpinBox {
                        from: 64
                        to: 4096
                        stepSize: 64
                        value: appSettings.get_int("rag/chunk_size")
                        onValueModified: appSettings.set_int("rag/chunk_size", value)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Chunk Overlap:"; Layout.preferredWidth: 120 }
                    SpinBox {
                        from: 0
                        to: 512
                        stepSize: 32
                        value: appSettings.get_int("rag/chunk_overlap")
                        onValueModified: appSettings.set_int("rag/chunk_overlap", value)
                    }
                }
            }
        }

        // Memory Settings
        Rectangle {
            Layout.fillWidth: true
            clip: true
            radius: Kirigami.Units.cornerRadius
            color: memEnabledSwitch.checked
                ? Qt.rgba(Kirigami.Theme.positiveTextColor.r, Kirigami.Theme.positiveTextColor.g, Kirigami.Theme.positiveTextColor.b, 0.15)
                : Kirigami.Theme.backgroundColor
            border.color: memEnabledSwitch.checked
                ? Kirigami.Theme.positiveTextColor
                : safeBorderColor
            border.width: memEnabledSwitch.checked ? 2 : 1

            Behavior on color { ColorAnimation { duration: 300 } }
            Behavior on border.color { ColorAnimation { duration: 300 } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: memEnabledSwitch.checked ? "🧠 Memory Enabled" : "Memory Settings"
                        font.bold: true
                        font.pointSize: 14
                        color: memEnabledSwitch.checked ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.textColor
                        Behavior on color { ColorAnimation { duration: 300 } }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Enabled:"
                        Layout.preferredWidth: 120
                        color: memEnabledSwitch.checked ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                    }
                    Switch {
                        id: memEnabledSwitch
                        checked: appSettings.get_bool("memory/enabled")
                        onCheckedChanged: {
                            appSettings.set_bool("memory/enabled", checked)
                            memoryManager.set_enabled(checked)
                        }
                    }
                }
            }
        }

        // Voice Input Settings
        Rectangle {
            Layout.fillWidth: true
            clip: true
            radius: Kirigami.Units.cornerRadius
            color: voiceEnabledSwitch.checked
                ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.15)
                : Kirigami.Theme.backgroundColor
            border.color: voiceEnabledSwitch.checked
                ? Kirigami.Theme.highlightColor
                : safeBorderColor
            border.width: voiceEnabledSwitch.checked ? 2 : 1

            Behavior on color { ColorAnimation { duration: 300 } }
            Behavior on border.color { ColorAnimation { duration: 300 } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: voiceEnabledSwitch.checked ? "🎙️ Voice Input Enabled" : "Voice Input Settings"
                        font.bold: true
                        font.pointSize: 14
                        color: voiceEnabledSwitch.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
                        Behavior on color { ColorAnimation { duration: 300 } }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Enabled:"
                        Layout.preferredWidth: 120
                        color: voiceEnabledSwitch.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                    }
                    Switch {
                        id: voiceEnabledSwitch
                        checked: appSettings.get_bool("chat/voice_input_enabled")
                        onCheckedChanged: {
                            appSettings.set_bool("chat/voice_input_enabled", checked)
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    enabled: voiceEnabledSwitch.checked
                    Label {
                        text: "Whisper Model:"
                        Layout.preferredWidth: 120
                        color: voiceEnabledSwitch.checked ? Kirigami.Theme.textColor : Kirigami.Theme.disabledTextColor
                    }
                    ComboBox {
                        id: voiceModelCombo
                        model: ["tiny.en", "base.en", "small.en", "tiny", "base", "small"]
                        currentIndex: {
                            var v = appSettings.get_string("chat/voice_model")
                            var idx = model.indexOf(v)
                            return idx >= 0 ? idx : 1 // default to base.en
                        }
                        onActivated: {
                            appSettings.set_string("chat/voice_model", currentText)
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    enabled: voiceEnabledSwitch.checked
                    Label {
                        text: "Send Automatically:"
                        Layout.preferredWidth: 120
                        color: voiceEnabledSwitch.checked ? Kirigami.Theme.textColor : Kirigami.Theme.disabledTextColor
                    }
                    Switch {
                        id: voiceSendAutomaticallySwitch
                        checked: appSettings.get_bool("chat/voice_send_automatically")
                        onCheckedChanged: {
                            appSettings.set_bool("chat/voice_send_automatically", checked)
                        }
                    }
                }
            }
        }

        // Server Control
        Kirigami.AbstractCard {
            background: Rectangle {
                color: Kirigami.Theme.backgroundColor
                radius: Kirigami.Units.cornerRadius
            }
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    
                    Label {
                        text: "Server Control"
                        font.bold: true
                        font.pointSize: 14
                    }
                    
                    Item { Layout.fillWidth: true }
                    
                    Button {
                        text: showServerLog ? "▾ Log" : "▸ Log"
                        flat: true
                        onClicked: showServerLog = !showServerLog
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing

                    Button {
                        text: "Start Server"
                        enabled: !settingsPage.serverRunning
                        onClicked: startServer()
                        Layout.fillWidth: true
                    }

                    Button {
                        text: "Stop Server"
                        enabled: settingsPage.serverRunning
                        onClicked: serverManager.stop()
                        Layout.fillWidth: true
                    }

                    Button {
                        text: "Restart"
                        enabled: settingsPage.serverRunning
                        onClicked: {
                            serverManager.stop()
                            startServer()
                        }
                        Layout.fillWidth: true
                    }

                }

                // Server log
                ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 80
                    Layout.maximumHeight: 80
                    visible: showServerLog
                    clip: true

                    TextEdit {
                        id: serverLog
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        font.family: "monospace"
                        font.pointSize: 10
                    }
                }
            }
        }
        // ── External API Keys ──
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "External API Keys"
                    font.bold: true
                    font.pointSize: 14
                }

                Label {
                    text: "To use cloud models in Council mode, configure your API keys here and prefix the model paths in settings with 'nvidia:', 'openrouter:', or 'opencode:' (e.g., 'openrouter:meta-llama/llama-3-8b-instruct')."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 11
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "NVIDIA API Key:"
                        font.bold: true
                        Layout.preferredWidth: 150
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: appSettings.get_api_key("nvidia")
                        echoMode: TextInput.Password
                        placeholderText: "nvapi-..."
                        onEditingFinished: appSettings.set_api_key("nvidia", text)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "OpenRouter API Key:"
                        font.bold: true
                        Layout.preferredWidth: 150
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: appSettings.get_api_key("openrouter")
                        echoMode: TextInput.Password
                        placeholderText: "sk-or-v1-..."
                        onEditingFinished: appSettings.set_api_key("openrouter", text)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Opencode API Key:"
                        font.bold: true
                        Layout.preferredWidth: 150
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: appSettings.get_api_key("opencode")
                        echoMode: TextInput.Password
                        placeholderText: "sk-..."
                        onEditingFinished: appSettings.set_api_key("opencode", text)
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "Opencode Endpoint:"
                        font.bold: true
                        Layout.preferredWidth: 150
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: appSettings.get_string("cloud_endpoints/opencode")
                        placeholderText: "https://api.opencode.com"
                        onEditingFinished: appSettings.set_string("cloud_endpoints/opencode", text)
                    }
                }
                Label {
                    text: "Cloud Model Selection"
                    font.bold: true
                    font.pointSize: 12
                }
                Label {
                    text: "Fetch a provider's model list, pick a model, and assign it to a Council slot (council/model_1–3)."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 11
                }

                // NVIDIA
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "NVIDIA"; font.bold: true; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: modelCombo_nvidia
                        Layout.fillWidth: true
                        enabled: count > 0
                        displayText: count > 0 ? currentText : "No models cached — click Fetch"
                    }
                    Button {
                        text: "Fetch models"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 130
                        onClicked: externalModels.refresh("nvidia")
                    }
                    Button {
                        text: "Clear"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 80
                        onClicked: externalModels.clear_cache("nvidia")
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Council slot:"; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: slotCombo_nvidia
                        model: [1, 2, 3]
                        Layout.preferredWidth: 80
                    }
                    Button {
                        text: "Use in Council"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 150
                        enabled: modelCombo_nvidia.count > 0
                        onClicked: externalModels.select_model("nvidia", slotCombo_nvidia.currentIndex + 1, modelCombo_nvidia.currentText)
                    }
                }
                Label {
                    id: errLabel_nvidia
                    text: ""
                    color: Kirigami.Theme.negativeTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 10
                    visible: false
                }

                // OpenRouter
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "OpenRouter"; font.bold: true; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: modelCombo_openrouter
                        Layout.fillWidth: true
                        enabled: count > 0
                        displayText: count > 0 ? currentText : "No models cached — click Fetch"
                    }
                    Button {
                        text: "Fetch models"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 130
                        onClicked: externalModels.refresh("openrouter")
                    }
                    Button {
                        text: "Clear"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 80
                        onClicked: externalModels.clear_cache("openrouter")
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Council slot:"; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: slotCombo_openrouter
                        model: [1, 2, 3]
                        Layout.preferredWidth: 80
                    }
                    Button {
                        text: "Use in Council"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 150
                        enabled: modelCombo_openrouter.count > 0
                        onClicked: externalModels.select_model("openrouter", slotCombo_openrouter.currentIndex + 1, modelCombo_openrouter.currentText)
                    }
                }
                Label {
                    id: errLabel_openrouter
                    text: ""
                    color: Kirigami.Theme.negativeTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 10
                    visible: false
                }

                // Opencode
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Opencode"; font.bold: true; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: modelCombo_opencode
                        Layout.fillWidth: true
                        enabled: count > 0
                        displayText: count > 0 ? currentText : "No models cached — click Fetch"
                    }
                    Button {
                        text: "Fetch models"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 130
                        onClicked: externalModels.refresh("opencode")
                    }
                    Button {
                        text: "Clear"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 80
                        onClicked: externalModels.clear_cache("opencode")
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Council slot:"; Layout.preferredWidth: 90 }
                    ComboBox {
                        id: slotCombo_opencode
                        model: [1, 2, 3]
                        Layout.preferredWidth: 80
                    }
                    Button {
                        text: "Use in Council"
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 150
                        enabled: modelCombo_opencode.count > 0
                        onClicked: externalModels.select_model("opencode", slotCombo_opencode.currentIndex + 1, modelCombo_opencode.currentText)
                    }
                }
                Label {
                    id: errLabel_opencode
                    text: ""
                    color: Kirigami.Theme.negativeTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 10
                    visible: false
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "nvidia") { modelCombo_nvidia.model = ids; errLabel_nvidia.visible = false }
                        else if (provider === "openrouter") { modelCombo_openrouter.model = ids; errLabel_openrouter.visible = false }
                        else if (provider === "opencode") { modelCombo_opencode.model = ids; errLabel_opencode.visible = false }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "nvidia") { modelCombo_nvidia.model = []; errLabel_nvidia.visible = false }
                        else if (provider === "openrouter") { modelCombo_openrouter.model = []; errLabel_openrouter.visible = false }
                        else if (provider === "opencode") { modelCombo_opencode.model = []; errLabel_opencode.visible = false }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "nvidia") { errLabel_nvidia.text = message; errLabel_nvidia.visible = true }
                        else if (provider === "openrouter") { errLabel_openrouter.text = message; errLabel_openrouter.visible = true }
                        else if (provider === "opencode") { errLabel_opencode.text = message; errLabel_opencode.visible = true }
                    }
                }

                Component.onCompleted: {
                    modelCombo_nvidia.model = externalModels.get_cached_models("nvidia")
                    modelCombo_openrouter.model = externalModels.get_cached_models("openrouter")
                    modelCombo_opencode.model = externalModels.get_cached_models("opencode")
                }
            }
        }

        // ── MCP Servers ──
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                id: mcpLayout
                spacing: Kirigami.Units.smallSpacing

                property var mcpServersList: []

                Label {
                    text: "MCP Servers"
                    font.bold: true
                    font.pointSize: 14
                }

                Label {
                    text: "Enter the exact command to run the server, e.g., <code>npx -y @modelcontextprotocol/server-everything</code>"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    font.pointSize: 11
                }

                Repeater {
                    model: mcpLayout.mcpServersList

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        TextField {
                            Layout.fillWidth: true
                            text: modelData
                            placeholderText: "MCP server command..."
                            onEditingFinished: {
                                var newList = mcpLayout.mcpServersList.slice()
                                newList[index] = text
                                mcpLayout.mcpServersList = newList
                                appSettings.set_list("mcp/servers", newList)
                            }
                        }

                        Button {
                            text: "Remove"
                            Layout.preferredWidth: 100
                            onClicked: {
                                var newList = mcpLayout.mcpServersList.slice()
                                newList.splice(index, 1)
                                mcpLayout.mcpServersList = newList
                                appSettings.set_list("mcp/servers", newList)
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    TextField {
                        id: newServerField
                        Layout.fillWidth: true
                        placeholderText: "New MCP server command..."
                    }

                    Button {
                        text: "Add Server"
                        Layout.preferredWidth: 120
                        enabled: newServerField.text.trim() !== ""
                        onClicked: {
                            var cmd = newServerField.text.trim()
                            if (cmd) {
                                var newList = mcpLayout.mcpServersList.slice()
                                newList.push(cmd)
                                mcpLayout.mcpServersList = newList
                                appSettings.set_list("mcp/servers", newList)
                                newServerField.text = ""
                            }
                        }
                    }
                }

                Component.onCompleted: {
                    mcpServersList = appSettings.get_list("mcp/servers")
                }
            }
        }
        // ── llama.cpp Update ──
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "llama.cpp Update"
                    font.bold: true
                    font.pointSize: 14
                }

                Label {
                    text: "Current version: " + updater.current_version()
                    font.pointSize: 11
                }

                // Status message
                Label {
                    id: updateStatus
                    text: ""
                    font.pointSize: 11
                    visible: text.length > 0
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                // Progress bar
                ProgressBar {
                    id: downloadProgress
                    Layout.fillWidth: true
                    visible: false
                    value: 0
                }

                // Action button
                Button {
                    id: updateBtn
                    text: "Check for Updates"
                    icon.name: "system-software-update"
                    Layout.alignment: Qt.AlignLeft

                    onClicked: {
                        if (updateState === "idle") {
                            updater.check_for_updates()
                        } else if (updateState === "available") {
                            updater.download_update()
                        } else if (updateState === "downloaded") {
                            updater.install_update()
                        }
                    }
                }
            }
        }

    }

    // Model file dialog
    FileDialog {
        id: modelFileDialog
        title: "Select GGUF Model File"
        nameFilters: ["GGUF Models (*.gguf)"]
        property string targetSettingKey: ""
        onAccepted: {
            var path = selectedFile.toString()
            if (path.startsWith("file:///")) {
                path = path.slice(8)
            } else if (path.startsWith("file://")) {
                path = path.slice(7)
            }
            path = decodeURIComponent(path)
            appSettings.set_string(targetSettingKey, path)
            if (targetSettingKey === "council/model_1") {
                councilModel1Field.text = path
            } else if (targetSettingKey === "council/model_2") {
                councilModel2Field.text = path
            } else if (targetSettingKey === "council/model_3") {
                councilModel3Field.text = path
            }
        }
    }
    // Folder dialog
    FolderDialog {
        id: folderDialog
        onAccepted: {
            var path = selectedFolder.toString().replace("file://", "")
            appSettings.set_string("models/directory", path)
            modelDirField.text = path
            modelBrowser.set_directory(path)
        }
    }

    function startServer() {
        var modelPath = appSettings.get_string("server/model_path")
        if (modelPath.length === 0) {
            serverLog.text += "ERROR: No model selected. Go to Models tab to select one.\n"
            return
        }
        var bin = appSettings.get_string("server/binary")
        var port = appSettings.get_int("server/port")
        var ctx = appSettings.get_int("server/ctx_size")
        var gpu = appSettings.get_int("server/n_gpu_layers")
        var threads = appSettings.get_int("server/threads")
        var ok = serverManager.start(bin, modelPath, port, ctx, gpu, threads)
        if (!ok) {
            serverLog.text += "ERROR: Failed to start server\n"
        }
    }

    Connections {
        target: serverManager
        function onLog_line(line) {
            serverLog.text += line + "\n"
        }
        function onServer_error(msg) {
            serverLog.text += "ERROR: " + msg + "\n"
        }
    }
    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
