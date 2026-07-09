import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: modelsPage
    title: "Models"

    property var models: []
    property string selectedModel: ""
    property string downloadStatus: ""
    property string modelsDir: appSettings.get_string("models/directory")

    Connections {
        target: appSettings
        function onSettings_changed(key, value) {
            if (key === "models/directory") modelsPage.modelsDir = value
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        // Header
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Local Models"
                font.bold: true
                font.pointSize: 16
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "🔄 Refresh"
                onClicked: refreshModels()
            }

            Button {
                text: "📥 Download"
                onClicked: downloadDialog.open()
            }
        }

        // Current model display
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: selectedModel.length > 0

            contentItem: RowLayout {
                Label {
                    text: "Active: " + selectedModel.split('/').pop()
                    font.bold: true
                    color: Kirigami.Theme.highlightColor
                }
            }
        }

        // Model list
        ListView {
            id: modelList
            objectName: "modelList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: models

            delegate: Kirigami.AbstractCard {
                width: modelList.width
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: modelData.name
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData.size_display + " • " + new Date(modelData.modified_time * 1000).toLocaleDateString()
                                color: Kirigami.Theme.disabledTextColor
                            }

                            Label {
                                property bool fitsInVRAM: modelData.size_gb <= modelBrowser.safe_vram_gb
                                property bool fitsInTotalSafe: modelData.size_gb <= (modelBrowser.safe_vram_gb + modelBrowser.safe_ram_gb)

                                visible: !fitsInVRAM
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                text: !fitsInTotalSafe ? "⚠️ Exceeds safe memory (OOM crash risk)" : "⚠️ Exceeds VRAM (will spill to system RAM)"
                                color: !fitsInTotalSafe ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.neutralTextColor
                                font.italic: true
                            }
                        }
                    }

                    Button {
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 100
                        text: "▶️ Load"
                        onClicked: loadModel(modelData.path)
                        enabled: modelData.path !== selectedModel
                    }
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                visible: modelList.count === 0
                text: "No models found in:\n" + modelsPage.modelsDir
                horizontalAlignment: Text.AlignHCenter
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // Status bar
        Label {
            Layout.fillWidth: true
            text: models.length + " model(s) found"
            color: Kirigami.Theme.disabledTextColor
        }

        // Download status
        Label {
            Layout.fillWidth: true
            text: modelsPage.downloadStatus
            color: Kirigami.Theme.highlightColor
            visible: modelsPage.downloadStatus.length > 0
            font.italic: true
        }

    }

    // Download dialog
    Dialog {
        id: downloadDialog
        modal: true
        title: "Download Model"
        anchors.centerIn: parent
        width: 400

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing

            Label {
                text: "HuggingFace Repository ID:"
            }

            TextField {
                id: repoIdField
                Layout.fillWidth: true
                placeholderText: "e.g., TheBloke/Llama-2-7B-GGUF"
            }

            Label {
                text: "Filename (optional):"
            }

            TextField {
                id: filenameField
                Layout.fillWidth: true
                placeholderText: "e.g., llama-2-7b.Q4_K_M.gguf"
            }

            RowLayout {
                Layout.fillWidth: true

                Button {
                    text: "Cancel"
                    onClicked: downloadDialog.close()
                    Layout.fillWidth: true
                }

                Button {
                    text: "Download"
                    onClicked: startDownload()
                    Layout.fillWidth: true
                    enabled: repoIdField.text.length > 0
                }
            }
        }
    }

    function refreshModels() {
        models = modelBrowser.scan()
    }

    function loadModel(path) {
        console.log("Loading model:", path)
        selectedModel = path
        appSettings.set_string("server/model_path", path)

        // Stop server if running
        if (serverManager.is_running()) {
            console.log("Stopping existing server")
            serverManager.stop()
        }

        // Get individual settings
        var bin = appSettings.get_string("server/binary")
        var port = appSettings.get_int("server/port")
        var ctx = appSettings.get_int("server/ctx_size")
        var gpu = appSettings.get_int("server/n_gpu_layers")
        var threads = appSettings.get_int("server/threads")
        console.log("Starting server:", bin, path, port, ctx, gpu, threads)
        var ok = serverManager.start(bin, path, port, ctx, gpu, threads)
        console.log("Server start result:", ok)
        if (!ok) {
            errorToast.show("Failed to start server with model: " + path.split('/').pop())
        }
    }

    function startDownload() {
        var repo = repoIdField.text.trim()
        var filename = filenameField.text.trim()
        downloader.download(repo, filename)
        downloadDialog.close()
        repoIdField.text = ""
        filenameField.text = ""
    }

    Component.onCompleted: refreshModels()

    // Download progress tracking
    Connections {
        target: downloader
        function onDownload_started(filename) {
            modelsPage.downloadStatus = "Downloading " + filename + "..."
        }
        function onDownload_progress(filename, fraction, status) {
            modelsPage.downloadStatus = status || Math.round(fraction * 100) + "%"
        }
        function onDownload_finished(filename, path) {
            modelsPage.downloadStatus = "Downloaded: " + filename
            refreshModels()
        }
        function onDownload_error(filename, error) {
            modelsPage.downloadStatus = "Error: " + error
        }
    }
    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
