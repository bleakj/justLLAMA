import QtQuick.Dialogs
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: ragPage
    title: "RAG"

    property var documents: []
    property int chunkCount: 0
    property bool isRagEnabled: appSettings.get_bool("rag/enabled")
    Component.onCompleted: refreshCount()

    Connections {
        target: appSettings
        function onSettings_changed(key, value) {
            if (key === "rag/enabled") ragPage.isRagEnabled = value
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        // Header
        SectionHeader {
            title: "Retrieval-Augmented Generation"

            Label {
                text: "Enabled:"
                color: ragPage.isRagEnabled ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                font.bold: ragPage.isRagEnabled
            }
            Switch {
                checked: ragPage.isRagEnabled
                onCheckedChanged: appSettings.set_bool("rag/enabled", checked)
            }
        }

        // Upload area
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Label {
                    text: "Upload Documents"
                    font.bold: true
                }

                Label {
                    text: "Supported: PDF, TXT, Markdown, DOCX"
                    color: Kirigami.Theme.disabledTextColor
                }

                Button {
                    text: "Select Files"
                    icon.name: "document-open"
                    onClicked: fileDialog.open()
                    Layout.fillWidth: true
                }
            }
        }

        // Document list
        Label {
            text: "Indexed Documents (" + documents.length + ")"
            font.bold: true
        }

        ListView {
            id: docList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: documents

            delegate: Kirigami.AbstractCard {
                width: docList.width
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true

                        Label {
                            text: modelData.filename
                            font.bold: true
                        }
                        Label {
                            text: modelData.chunks + " chunks • " + modelData.size
                            color: Kirigami.Theme.disabledTextColor
                        }
                    }

                    ToolButton {
                        icon.name: "edit-delete"
                        display: AbstractButton.IconOnly
                        ToolTip.visible: hovered
                        ToolTip.text: "Remove"
                        onClicked: removeDocument(index)
                    }
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                visible: docList.count === 0
                text: "No documents indexed.\nUpload files to start RAG."
                horizontalAlignment: Text.AlignHCenter
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // Vector store stats
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: RowLayout {
                Label {
                    text: "Vector Store: " + ragPage.chunkCount + " chunks"
                    color: Kirigami.Theme.disabledTextColor
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Clear All"
                    icon.name: "edit-clear-all"
                    onClicked: clearAll()
                }
            }
        }
    }

    // File picker
    FileDialog {
        id: fileDialog
        title: "Select Documents"
        nameFilters: ["Documents (*.pdf *.txt *.md *.docx)", "All files (*)"]
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            for (var i = 0; i < selectedFiles.length; i++) {
                ingestDocument(selectedFiles[i].toString().replace("file://", ""))
            }
        }
    }

    function ingestDocument(filePath) {
        var resultJson = vectorStore.ingest_document(filePath)
        var result = JSON.parse(resultJson)
        
        if (result.error) {
            console.error("Ingestion error:", result.error)
            toast.show("Ingestion failed: " + result.error, "error")
            return
        }
        
        documents.push({
            filename: result.filename,
            chunks: result.chunks,
            size: result.size
        })
        documentsChanged()
        refreshCount()
    }

    function removeDocument(index) {
        var doc = documents[index]
        if (doc) {
            vectorStore.remove_document(doc.filename)
        }
        documents.splice(index, 1)
        documentsChanged()
        refreshCount()
    }

    function clearAll() {
        documents = []
        vectorStore.clear()
        refreshCount()
    }

    function refreshCount() {
        try {
            ragPage.chunkCount = vectorStore.count()
        } catch (e) {
            console.error("Failed to refresh count:", e)
            toast.show("Failed to refresh document count: " + e.message, "error")
            ragPage.chunkCount = 0
        }
    }
    Toast {
        id: toast
        anchors.fill: parent
    }
}
