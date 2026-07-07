import QtQuick.Dialogs
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: ragPage
    title: "RAG"

    property var documents: []

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        // Header
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Retrieval-Augmented Generation"
                font.bold: true
                font.pointSize: 16
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "Enabled:"
                color: appSettings.get_bool("rag/enabled") ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                font.bold: appSettings.get_bool("rag/enabled")
            }
            Switch {
                checked: appSettings.get_bool("rag/enabled")
                onCheckedChanged: appSettings.set_bool("rag/enabled", checked)
                indicator: Rectangle {
                    implicitWidth: 48
                    implicitHeight: 26
                    x: parent.leftPadding
                    y: parent.height / 2 - height / 2
                    radius: 13
                    color: parent.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor

                    Rectangle {
                        x: parent.parent.checked ? parent.width - width - 2 : 2
                        width: 22
                        height: 22
                        radius: 11
                        color: "white"

                        Behavior on x {
                            NumberAnimation { duration: 150 }
                        }
                    }
                }
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
                    text: "📁 Select Files"
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

                    Button {
                        text: "🗑️"
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
                    text: "Vector Store: " + vectorStore.count() + " chunks"
                    color: Kirigami.Theme.disabledTextColor
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "🧹 Clear All"
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
        // Call Python ingestion via short-term memory bridge
        // This is a simplified approach - in production, use direct Python calls
        var xhr = new XMLHttpRequest()
        xhr.open("POST", "http://localhost:" + (appSettings.get_int("server/port") || 8080) + "/rag/ingest", true)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                var result = JSON.parse(xhr.responseText)
                documents.push({
                    filename: result.filename,
                    chunks: result.chunks,
                    size: result.size
                })
                documentsChanged()
            }
        }
        xhr.send(JSON.stringify({"path": filePath}))
    }

    function removeDocument(index) {
        documents.splice(index, 1)
        documentsChanged()
    }

    function clearAll() {
        documents = []
        vectorStore.clear()
    }
}
