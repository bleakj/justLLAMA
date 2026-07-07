import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: apiPage
    title: "API"

    // Safe theme colors
    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeHighlightColor: Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
    readonly property color safeTextColor: Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1)
    readonly property color safeDisabledColor: Kirigami.Theme.disabledTextColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeBgColor: Kirigami.Theme.backgroundColor || Qt.rgba(0.15, 0.15, 0.15, 1)
    readonly property color safeAltBgColor: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)

    property string baseUrl: "http://localhost:" + (root.serverPort || 8080)
    property string modelFileName: {
        var p = appSettings.get_string("server/model_path")
        return p ? p.split('/').pop().replace('.gguf', '') : ""
    }

    // Clipboard helper
    function copyToClipboard(text) {
        clipboardHelper.text = text
        clipboardHelper.selectAll()
        clipboardHelper.copy()
        copyFeedback.visible = true
        feedbackTimer.restart()
    }

    // Clipboard helper text field (hidden)
    TextField {
        id: clipboardHelper
        visible: false
        width: 0
        height: 0
    }

    // Copy feedback
    Label {
        id: copyFeedback
        visible: false
        text: "Copied!"
        font.bold: true
        color: safeHighlightColor
        anchors.centerIn: parent
        z: 100
    }
    Timer {
        id: feedbackTimer
        interval: 1500
        onTriggered: copyFeedback.visible = false
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.largeSpacing

            // Header
            Label {
                text: "OpenAI-Compatible API"
                font.bold: true
                font.pointSize: 18
                color: safeHighlightColor
            }

            Label {
                text: "justLLAMA exposes an OpenAI-compatible REST API via llama-server.\nUse these settings to connect external tools."
                font.pointSize: 11
                color: safeDisabledColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: safeBorderColor }

            // ── Connection Info ──
            Label {
                text: "Connection"
                font.bold: true
                font.pointSize: 14
            }

            // Base URL
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: urlRow.implicitHeight + Kirigami.Units.largeSpacing * 2
                color: safeAltBgColor
                radius: Kirigami.Units.cornerRadius
                border.color: safeBorderColor
                border.width: 1

                RowLayout {
                    id: urlRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: "Base URL"
                            font.bold: true
                            font.pointSize: 11
                        }
                        Label {
                            text: apiPage.baseUrl
                            font.pointSize: 12
                            font.family: "monospace"
                            color: safeTextColor
                            Layout.fillWidth: true
                        }
                    }

                    Button {
                        text: "Copy"
                        icon.name: "edit-copy"
                        onClicked: apiPage.copyToClipboard(apiPage.baseUrl)
                    }
                }
            }

            // API Key
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: keyRow.implicitHeight + Kirigami.Units.largeSpacing * 2
                color: safeAltBgColor
                radius: Kirigami.Units.cornerRadius
                border.color: safeBorderColor
                border.width: 1

                RowLayout {
                    id: keyRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: "API Key"
                            font.bold: true
                            font.pointSize: 11
                        }
                        Label {
                            text: "No key required (local server)"
                            font.pointSize: 12
                            color: safeDisabledColor
                            Layout.fillWidth: true
                        }
                    }

                    Button {
                        text: "Copy"
                        icon.name: "edit-copy"
                        onClicked: apiPage.copyToClipboard("no-key")
                    }
                }
            }

            // Model Name
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: modelRow.implicitHeight + Kirigami.Units.largeSpacing * 2
                color: safeAltBgColor
                radius: Kirigami.Units.cornerRadius
                border.color: safeBorderColor
                border.width: 1

                RowLayout {
                    id: modelRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: "Model Name"
                            font.bold: true
                            font.pointSize: 11
                        }
                        Label {
                            text: apiPage.modelFileName || "(no model loaded)"
                            font.pointSize: 12
                            font.family: "monospace"
                            color: safeTextColor
                            Layout.fillWidth: true
                        }
                    }

                    Button {
                        text: "Copy"
                        icon.name: "edit-copy"
                        onClicked: apiPage.copyToClipboard(apiPage.modelFileName)
                        enabled: apiPage.modelFileName !== ""
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: safeBorderColor }

            // ── Quick Config Snippets ──
            Label {
                text: "Quick Configuration"
                font.bold: true
                font.pointSize: 14
            }

            // OpenAI Python SDK
            ConfigSnippet {
                title: "OpenAI Python SDK"
                snippet: "import openai\n\nclient = openai.OpenAI(\n    base_url=\"" + apiPage.baseUrl + "/v1\",\n    api_key=\"no-key\"\n)\n\nresponse = client.chat.completions.create(\n    model=\"" + apiPage.modelFileName + "\",\n    messages=[{\"role\": \"user\", \"content\": \"Hello!\"}]\n)\nprint(response.choices[0].message.content)"
                onCopy: apiPage.copyToClipboard(snippet)
            }

            // curl
            ConfigSnippet {
                title: "curl (Chat Completion)"
                snippet: "curl " + apiPage.baseUrl + "/v1/chat/completions \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\n    \"model\": \"" + apiPage.modelFileName + "\",\n    \"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}],\n    \"stream\": true\n  }'"
                onCopy: apiPage.copyToClipboard(snippet)
            }

            // Environment variables
            ConfigSnippet {
                title: "Environment Variables"
                snippet: "OPENAI_API_BASE=" + apiPage.baseUrl + "/v1\nOPENAI_API_KEY=no-key\nMODEL_NAME=" + apiPage.modelFileName
                onCopy: apiPage.copyToClipboard(snippet)
            }

            // JSON config
            ConfigSnippet {
                title: "JSON Config (for tools)"
                snippet: "{\n  \"api_base\": \"" + apiPage.baseUrl + "/v1\",\n  \"api_key\": \"no-key\",\n  \"model\": \"" + apiPage.modelFileName + "\"\n}"
                onCopy: apiPage.copyToClipboard(snippet)
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: safeBorderColor }

            // ── Available Endpoints ──
            Label {
                text: "Available Endpoints"
                font.bold: true
                font.pointSize: 14
            }

            Label {
                text: "GET  /v1/models          List loaded models\nGET  /health             Server health status\nGET  /props              Server properties\nPOST /v1/chat/completions  Chat completion (streaming supported)\nPOST /v1/completions     Text completion\nPOST /v1/embeddings      Generate embeddings"
                font.pointSize: 11
                font.family: "monospace"
                color: safeTextColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            // Server status
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: statusRow.implicitHeight + Kirigami.Units.largeSpacing * 2
                color: root.serverRunning ? Qt.rgba(0.2, 0.7, 0.3, 0.1) : Qt.rgba(0.8, 0.2, 0.2, 0.1)
                radius: Kirigami.Units.cornerRadius
                border.color: root.serverRunning ? Qt.rgba(0.2, 0.7, 0.3, 0.3) : Qt.rgba(0.8, 0.2, 0.2, 0.3)
                border.width: 1

                RowLayout {
                    id: statusRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing

                    Label {
                        text: root.serverRunning
                            ? "● Server online — API ready at " + apiPage.baseUrl
                            : "● Server offline — start the server to use the API"
                        font.pointSize: 11
                        font.bold: true
                        color: root.serverRunning ? Qt.rgba(0.2, 0.7, 0.3, 1) : Qt.rgba(0.8, 0.2, 0.2, 1)
                        Layout.fillWidth: true
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }

    // Re-read values when page becomes visible
    onVisibleChanged: {
        if (visible) {
            var p = appSettings.get_string("server/model_path")
            modelFileName = p ? p.split('/').pop().replace('.gguf', '') : ""
            baseUrl = "http://localhost:" + (root.serverPort || 8080)
        }
    }
}
