import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: videoPage
    title: "Video Generation"

    // ── state ────────────────────────────────────────────────────────
    property var models: []
    property string selectedModel: ""
    property bool isGenerating: false
    property string statusText: ""
    property string previewPath: ""
    property var gallery: []  // list of generated video paths

    // Safe theme colors — match ChatView pattern
    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeHighlightColor: Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
    readonly property color safeTextColor: Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1)
    readonly property color safeDisabledColor: Kirigami.Theme.disabledTextColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeBgColor: Kirigami.Theme.backgroundColor || Qt.rgba(0.15, 0.15, 0.15, 1)
    readonly property color safeAltBgColor: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)

    // ── signals from Python ──────────────────────────────────────────
    Connections {
        target: videoGenManager
        function onProgress_update(msg) { videoPage.statusText = msg }
        function onGeneration_complete(path) {
            videoPage.isGenerating = false
            videoPage.previewPath = path
            videoPage.statusText = "Generation complete"
            // Add to gallery
            var g = videoPage.gallery
            g.unshift(path)
            if (g.length > 50) g.pop()
            videoPage.gallery = g
        }
        function onError(msg) {
            videoPage.isGenerating = false
            videoPage.statusText = "ERROR: " + msg
            errorToast.show(msg)
        }
    }

    Component.onCompleted: {
        refreshModels()
        // Restore previously selected model
        var saved = videoGenManager.selected_model()
        if (saved.length > 0) {
            videoPage.selectedModel = saved
        }
    }

    // ── helpers ──────────────────────────────────────────────────────
    function refreshModels() {
        videoPage.models = videoGenManager.available_models()
    }

    function generateVideo() {
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
        videoGenManager.generate(prompt, widthSpin.value, heightSpin.value, framesSpin.value)
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
                    text: "Video Model"
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
                        model: videoPage.models

                        onCurrentValueChanged: {
                            if (currentValue) {
                                videoPage.selectedModel = currentValue
                                videoGenManager.select_model(currentValue)
                            }
                        }

                        Component.onCompleted: {
                            // Select previously saved model
                            var saved = videoGenManager.selected_model()
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
                            videoPage.models = videoGenManager.available_models()
                        }
                    }
                }

                Label {
                    text: videoPage.models.length + " model(s) found"
                    color: safeDisabledColor
                    font.pointSize: 9
                }
            }
        }

        // ── Parameters & Prompt ──────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Parameters"
                    font.bold: true
                    font.pointSize: 14
                }

                // Dimension controls
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing

                    Label { text: "Width:" }
                    SpinBox {
                        id: widthSpin
                        from: 256; to: 2048; stepSize: 32
                        value: 832
                        editable: true
                    }
                    Label { text: "Height:" }
                    SpinBox {
                        id: heightSpin
                        from: 256; to: 1536; stepSize: 32
                        value: 480
                        editable: true
                    }
                    Label { text: "Frames:" }
                    SpinBox {
                        id: framesSpin
                        from: 1; to: 1024; stepSize: 1
                        value: 49
                        editable: true
                    }
                }

                Label {
                    text: "Prompt"
                    font.bold: true
                    font.pointSize: 14
                }

                TextArea {
                    id: promptField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 80
                    placeholderText: "Describe the video you want to generate..."
                    wrapMode: Text.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true

                    Item { Layout.fillWidth: true }

                    Button {
                        id: generateBtn
                        text: isGenerating ? "Generating..." : "🎬 Generate Video"
                        enabled: !isGenerating && promptField.text.trim().length > 0 && selectedModel.length > 0
                        onClicked: generateVideo()
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

            AnimatedImage {
                anchors.fill: parent
                anchors.margins: 4
                source: previewPath.length > 0 ? "file://" + previewPath : ""
                fillMode: Image.PreserveAspectFit
                playing: true
                visible: previewPath.length > 0 && status === Image.Ready

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

            // Fallback: show static image for non-WEBP formats (e.g. MP4)
            Image {
                anchors.fill: parent
                anchors.margins: 4
                source: previewPath.length > 0 ? "file://" + previewPath : ""
                fillMode: Image.PreserveAspectFit
                visible: previewPath.length > 0
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
                                    videoPage.previewPath = modelData
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Save dialog
    FileDialog {
        id: saveDialog
        title: "Save Video As"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "webp"
        onAccepted: {
            if (previewPath.length > 0) {
                var src = previewPath.replace("file://", "")
                // Copy file to selected location
                videoGenManager.copy_file(src, selectedFile.toString().replace("file://", ""))
            }
        }
    }

    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
