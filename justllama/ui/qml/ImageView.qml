import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: imagePage
    title: "Image Generation"

    // ── state ────────────────────────────────────────────────────────
    property var models: []
    property string selectedModel: ""
    property bool isGenerating: false
    property string statusText: ""
    property string previewPath: ""
    property var gallery: []  // list of generated image paths

    // Safe theme colors — match ChatView pattern
    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeHighlightColor: Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
    readonly property color safeTextColor: Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1)
    readonly property color safeDisabledColor: Kirigami.Theme.disabledTextColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeBgColor: Kirigami.Theme.backgroundColor || Qt.rgba(0.15, 0.15, 0.15, 1)
    readonly property color safeAltBgColor: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)

    // ── signals from Python ──────────────────────────────────────────
    Connections {
        target: imageGenManager
        function onProgress_update(msg) { imagePage.statusText = msg }
        function onGeneration_complete(path) {
            imagePage.isGenerating = false
            imagePage.previewPath = path
            imagePage.statusText = "Generation complete"
            // Add to gallery
            var g = imagePage.gallery
            g.unshift(path)
            if (g.length > 50) g.pop()
            imagePage.gallery = g
        }
        function onError(msg) {
            imagePage.isGenerating = false
            imagePage.statusText = "ERROR: " + msg
            errorToast.show(msg)
        }
    }

    Component.onCompleted: {
        refreshModels()
        // Restore previously selected model
        var saved = imageGenManager.selected_model()
        if (saved.length > 0) {
            imagePage.selectedModel = saved
        }
        // Load gallery from ComfyUI output directory
        scanGallery()
    }

    // ── helpers ──────────────────────────────────────────────────────
    function refreshModels() {
        imagePage.models = imageGenManager.available_models()
    }

    function scanGallery() {
        // We'll scan the output directory by attempting to list recent files
        // This is driven by generation_complete signals; initial load is passive.
    }

    function generateImage() {
        if (isGenerating) return
        var prompt = promptField.text.trim()
        if (prompt.length === 0) {
            statusText = "Please enter a prompt"
            return
        }
        if (selectedModel.length === 0) {
            statusText = "Please select a model"
            return
        }
        isGenerating = true
        previewPath = ""
        statusText = "Starting..."
        imageGenManager.generate(prompt)
    }

    // ── UI ───────────────────────────────────────────────────────────

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        // ── Model Selection ──────────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Image Model"
                    font.bold: true
                    font.pointSize: 14
                }

                RowLayout {
                    Layout.fillWidth: true

                    ComboBox {
                        id: modelCombo
                        Layout.fillWidth: true
                        textRole: "name"
                        valueRole: "path"
                        model: imagePage.models

                        onCurrentValueChanged: {
                            if (currentValue) {
                                imagePage.selectedModel = currentValue
                                imageGenManager.select_model(currentValue)
                            }
                        }

                        Component.onCompleted: {
                            // Select previously saved model
                            var saved = imageGenManager.selected_model()
                            if (saved.length > 0) {
                                for (var i = 0; i < modelCombo.count; i++) {
                                    if (modelCombo.valueAt(i) === saved) {
                                        modelCombo.currentIndex = i
                                        break
                                    }
                                }
                            }
                        }
                    }

                    Button {
                        text: "🔄"
                        implicitWidth: 36
                        onClicked: {
                            imagePage.models = imageGenManager.available_models()
                        }
                    }
                }

                Label {
                    text: imagePage.models.length + " model(s) found"
                    color: safeDisabledColor
                    font.pointSize: 9
                }
            }
        }

        // ── Prompt & Generate ────────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Prompt"
                    font.bold: true
                    font.pointSize: 14
                }

                TextArea {
                    id: promptField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 80
                    placeholderText: "Describe the image you want to generate..."
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing

                    // Dimensions
                    Label { text: "Width:" }
                    SpinBox {
                        id: widthSpin
                        from: 256; to: 2048; stepSize: 64
                        value: 1024
                        editable: true
                    }
                    Label { text: "Height:" }
                    SpinBox {
                        id: heightSpin
                        from: 256; to: 2048; stepSize: 64
                        value: 1024
                        editable: true
                    }

                    Item { Layout.fillWidth: true }

                    Button {
                        id: generateBtn
                        text: isGenerating ? "Generating..." : "✨ Generate"
                        enabled: !isGenerating && promptField.text.trim().length > 0 && selectedModel.length > 0
                        onClicked: generateImage()
                    }
                }

                // Status line
                Label {
                    Layout.fillWidth: true
                    text: statusText
                    color: statusText.startsWith("ERROR")
                        ? Kirigami.Theme.negativeTextColor
                        : safeHighlightColor
                    font.italic: true
                    visible: statusText.length > 0
                    wrapMode: Text.Wrap
                }
            }
        }

        // ── Preview ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 400
            visible: previewPath.length > 0 || isGenerating
            color: safeAltBgColor
            radius: Kirigami.Units.cornerRadius
            border.color: safeBorderColor
            border.width: 1

            Image {
                anchors.fill: parent
                anchors.margins: 4
                source: previewPath.length > 0 ? "file://" + previewPath : ""
                fillMode: Image.PreserveAspectFit
                visible: previewPath.length > 0

                // Save button overlay
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.RightButton
                    onClicked: saveMenu.open()
                }

                Menu {
                    id: saveMenu
                    MenuItem {
                        text: "Save As..."
                        onTriggered: saveDialog.open()
                    }
                }
            }

            BusyIndicator {
                anchors.centerIn: parent
                running: isGenerating && previewPath.length === 0
                visible: running
            }

            Label {
                anchors.centerIn: parent
                text: "Generating..."
                visible: isGenerating && previewPath.length === 0
                color: safeDisabledColor
                font.pointSize: 12
            }
        }

        // ── Gallery ──────────────────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: gallery.length > 0

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Recent Generations"
                    font.bold: true
                    font.pointSize: 14
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    orientation: ListView.Horizontal
                    spacing: Kirigami.Units.smallSpacing
                    model: gallery

                    delegate: Rectangle {
                        width: 120
                        height: 120
                        color: safeAltBgColor
                        radius: 4
                        border.color: safeBorderColor
                        border.width: 1

                        Image {
                            anchors.fill: parent
                            anchors.margins: 2
                            source: "file://" + modelData
                            fillMode: Image.PreserveAspectFit

                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    previewPath = modelData
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Save dialog ────────────────────────────────────────────────
    FileDialog {
        id: saveDialog
        title: "Save Image"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PNG Images (*.png)"]
        currentFile: previewPath.length > 0 ? "file://" + previewPath : ""
        onAccepted: {
            var dest = selectedFile.toString()
            if (dest.startsWith("file:///")) dest = dest.slice(8)
            else if (dest.startsWith("file://")) dest = dest.slice(7)
            dest = decodeURIComponent(dest)
            // Copy file (simple approach: read source, write dest)
            // QML can't copy files, so we use the backend
            // For now just show the path
            statusText = "Save path: " + dest
        }
    }

    // ── Toast notifications ─────────────────────────────────────────
    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
