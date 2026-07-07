import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: modelsPage
    title: "Models"

    property var models: []
    property string selectedModel: ""

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
                            text: modelData.name
                            font.bold: true
                        }
                        Label {
                            text: modelData.size_display + " • " + new Date(modelData.modified_time * 1000).toLocaleDateString()
                            color: Kirigami.Theme.disabledTextColor
                        }
                    }

                    Button {
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
                text: "No models found in:\n" + appSettings.get_string("models/directory")
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
}
