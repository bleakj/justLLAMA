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

            Kirigami.Separator { Layout.fillWidth: true }

            // ── Connection Info ──
            Label {
                text: "Connection"
                font.bold: true
                font.pointSize: 14
            }

            // Base URL
            InfoField {
                label: "Base URL"
                value: apiPage.baseUrl
                onCopy: apiPage.copyToClipboard(apiPage.baseUrl)
            }

            // API Key
            InfoField {
                label: "API Key"
                value: "No key required (local server)"
                mono: false
                valueMuted: true
                onCopy: apiPage.copyToClipboard("no-key")
            }

            // Model Name
            InfoField {
                label: "Model Name"
                value: apiPage.modelFileName || "(no model loaded)"
                copyEnabled: apiPage.modelFileName !== ""
                onCopy: apiPage.copyToClipboard(apiPage.modelFileName)
            }

            Kirigami.Separator { Layout.fillWidth: true }

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

            Kirigami.Separator { Layout.fillWidth: true }

            // ── Available Endpoints ──
            Label {
                text: "Available Endpoints"
                font.bold: true
                font.pointSize: 14
            }

            Label {
                text: "GET  /v1/models          List loaded models\nGET  /health             Server health status\nGET  /props              Server properties\nGET  /slots              Slot context usage (n_past/n_ctx per slot)\nPOST /v1/chat/completions  Chat completion (streaming supported)\nPOST /v1/completions     Text completion\nPOST /v1/embeddings      Generate embeddings"
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


            Kirigami.Separator { Layout.fillWidth: true }

            Label {
                text: "Image & Video Generation API (ComfyUI)"
                font.bold: true
                font.pointSize: 14
                color: safeHighlightColor
            }

            Label {
                text: "justLLAMA launches a ComfyUI subprocess for image and video generation.\nConnect directly for advanced workflows and custom pipelines."
                font.pointSize: 11
                color: safeDisabledColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            // ComfyUI Base URL
            InfoField {
                label: "ComfyUI Base URL"
                value: "http://localhost:8188"
                onCopy: apiPage.copyToClipboard("http://localhost:8188")
            }

            Kirigami.Separator { Layout.fillWidth: true }

            // ComfyUI Available Endpoints
            Label {
                text: "ComfyUI Endpoints"
                font.bold: true
                font.pointSize: 14
            }

            Label {
                text: "GET  /health             ComfyUI health check\nPOST /prompt             Submit workflow for image/video generation\nGET  /history/{id}       Check execution result by prompt ID"
                font.pointSize: 11
                font.family: "monospace"
                color: safeTextColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            // curl example
            ConfigSnippet {
                title: "curl (Image Generation via ComfyUI)"
                snippet: "# Create a workflow JSON (see flux_workflow.json in justllama source)\n" +
                         "# Replace PROMPT_PLACEHOLDER with your prompt, then:\n" +
                         "WORKFLOW=$(sed 's/PROMPT_PLACEHOLDER/A beautiful landscape/' /path/to/flux_workflow.json)\n\n" +
                         "# Submit to ComfyUI\n" +
                         'curl -X POST http://localhost:8188/prompt \\\n' +
                         "  -H \"Content-Type: application/json\" \\\n" +
                         '  -d "$(echo "{\\"prompt\\": $WORKFLOW, \\"client_id\\": \\"justllama\\"}")"'
                onCopy: apiPage.copyToClipboard(snippet)
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
