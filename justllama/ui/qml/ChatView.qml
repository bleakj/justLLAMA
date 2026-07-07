import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: chatPage
    title: "Chat"

    property var messageHistory: []
    property bool isGenerating: false
    // Context tracking
    property int contextUsed: 0
    property int contextMax: appSettings ? appSettings.get_int("server/ctx_size") : 32768
    property real contextPercent: contextMax > 0 ? (contextUsed / contextMax) * 100 : 0
    // Generation parameters
    property real genTemperature: 0.7
    property real genTopP: 0.9
    property int genTopK: 40
    property real genRepeatPenalty: 1.1
    property int genMaxTokens: 2048
    property bool showGenSettings: false

    // Safe theme colors with fallbacks for navigation transitions
    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    readonly property color safeHighlightColor: Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
    readonly property color safePositiveColor: Kirigami.Theme.positiveTextColor || Qt.rgba(0.2, 0.7, 0.3, 1)
    readonly property color safeNegativeColor: Kirigami.Theme.negativeTextColor || Qt.rgba(0.8, 0.2, 0.2, 1)
    readonly property color safeTextColor: Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1)
    readonly property color safeBgColor: Kirigami.Theme.backgroundColor || Qt.rgba(0.15, 0.15, 0.15, 1)
    readonly property color safeAltBgColor: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)
    readonly property color safeDisabledColor: Kirigami.Theme.disabledTextColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    // Poll context usage when server is running
    Timer {
        id: contextPollTimer
        interval: 2000
        running: root.serverRunning
        repeat: true
        onTriggered: fetchContextUsage()
    }
    // Update contextMax when settings change
    Connections {
        target: appSettings
        function onSettings_changed(key, value) {
            if (key === "server/ctx_size") {
                chatPage.contextMax = value
            }
        }
    }


    RowLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing

        // ── Left: main chat column ──
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Kirigami.Units.smallSpacing

            // Message history area
            ListView {
                id: messageList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: messageHistory

                delegate: ColumnLayout {
                    width: messageList.width
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.AbstractCard {
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing

                        contentItem: ColumnLayout {
                            property string assistantName: {
                                var p = appSettings.get_string("server/model_path")
                                return p ? p.split('/').pop().replace('.gguf', '') : "Assistant"
                            }
                            Label {
                                text: modelData.role === "user" ? "You" : assistantName
                                font.bold: true
                                color: modelData.role === "user"
                                    ? safeHighlightColor
                                    : safePositiveColor
                            }
                            Label {
                                text: modelData.content
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                onCountChanged: { positionViewAtEnd() }
            }

            // RAG / Memory indicators
            Label {
                id: ragIndicator
                visible: false
                text: "📚 RAG context active"
                color: safeHighlightColor
                font.italic: true
            }
            Label {
                id: memoryIndicator
                visible: memoryManager.is_enabled()
                text: "🧠 Memory active (" + memoryManager.stats() + ")"
                color: safeHighlightColor
                font.italic: true
            }
            // Generation settings toggle
            RowLayout {
                Layout.fillWidth: true

                Button {
                    text: showGenSettings ? "▾ Generation" : "▸ Generation"
                    flat: true
                    onClicked: showGenSettings = !showGenSettings
                }

                Label {
                    text: "T:" + genTemperature.toFixed(2) + "  P:" + genTopP.toFixed(2) + "  K:" + genTopK
                    font.pointSize: 9
                    color: safeDisabledColor
                }

                Item { Layout.fillWidth: true }
            }

            // Collapsible generation settings
            Rectangle {
                Layout.fillWidth: true
                visible: showGenSettings
                color: safeAltBgColor
                radius: Kirigami.Units.cornerRadius
                border.color: safeBorderColor
                border.width: 1
                height: genSettingsGrid.implicitHeight + Kirigami.Units.largeSpacing * 2

                GridLayout {
                    id: genSettingsGrid
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    columns: 4
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: Kirigami.Units.smallSpacing

                    // Temperature
                    Label { text: "Temperature"; font.pointSize: 10 }
                    Slider {
                        id: tempSlider
                        from: 0.0; to: 2.0; stepSize: 0.05
                        value: chatPage.genTemperature
                        onMoved: chatPage.genTemperature = value
                        Layout.fillWidth: true
                    }
                    Label { text: tempSlider.value.toFixed(2); font.pointSize: 10; Layout.preferredWidth: 40 }
                    Button {
                        text: "Reset"
                        flat: true
                        font.pointSize: 9
                        onClicked: tempSlider.value = 0.7
                    }

                    // Top P
                    Label { text: "Top P"; font.pointSize: 10 }
                    Slider {
                        id: topPSlider
                        from: 0.0; to: 1.0; stepSize: 0.05
                        value: chatPage.genTopP
                        onMoved: chatPage.genTopP = value
                        Layout.fillWidth: true
                    }
                    Label { text: topPSlider.value.toFixed(2); font.pointSize: 10; Layout.preferredWidth: 40 }
                    Button {
                        text: "Reset"
                        flat: true
                        font.pointSize: 9
                        onClicked: topPSlider.value = 0.9
                    }

                    // Top K
                    Label { text: "Top K"; font.pointSize: 10 }
                    Slider {
                        id: topKSlider
                        from: 1; to: 100; stepSize: 1
                        value: chatPage.genTopK
                        onMoved: chatPage.genTopK = value
                        Layout.fillWidth: true
                    }
                    Label { text: topKSlider.value.toFixed(0); font.pointSize: 10; Layout.preferredWidth: 40 }
                    Button {
                        text: "Reset"
                        flat: true
                        font.pointSize: 9
                        onClicked: topKSlider.value = 40
                    }

                    // Repeat Penalty
                    Label { text: "Repeat Penalty"; font.pointSize: 10 }
                    Slider {
                        id: repPenaltySlider
                        from: 1.0; to: 2.0; stepSize: 0.05
                        value: chatPage.genRepeatPenalty
                        onMoved: chatPage.genRepeatPenalty = value
                        Layout.fillWidth: true
                    }
                    Label { text: repPenaltySlider.value.toFixed(2); font.pointSize: 10; Layout.preferredWidth: 40 }
                    Button {
                        text: "Reset"
                        flat: true
                        font.pointSize: 9
                        onClicked: repPenaltySlider.value = 1.1
                    }

                    // Max Tokens
                    Label { text: "Max Tokens"; font.pointSize: 10 }
                    SpinBox {
                        id: maxTokensSpin
                        from: 128; to: 8192; stepSize: 128
                        value: chatPage.genMaxTokens
                        onValueModified: chatPage.genMaxTokens = value
                        Layout.fillWidth: true
                    }
                    Label { text: maxTokensSpin.value; font.pointSize: 10; Layout.preferredWidth: 40 }
                    Button {
                        text: "Reset"
                        flat: true
                        font.pointSize: 9
                        onClicked: maxTokensSpin.value = 2048
                    }
                }
            }


            // Input area
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                TextField {
                    id: inputField
                    Layout.fillWidth: true
                    placeholderText: "Type a message..."
                    enabled: !isGenerating
                    onAccepted: sendMessage()
                    Keys.onReturnPressed: sendMessage()
                }

                Button {
                    text: isGenerating ? "⏹️ Stop" : "▶️ Send"
                    enabled: inputField.text.length > 0 || isGenerating
                    onClicked: {
                        if (isGenerating) { stopGeneration() }
                        else { sendMessage() }
                    }
                }
            }

            // Streaming response area
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: streamingText.height + Kirigami.Units.largeSpacing * 2
                visible: isGenerating
                color: safeAltBgColor
                border.color: safeHighlightColor
                border.width: 1
                radius: Kirigami.Units.cornerRadius

                Label {
                    id: streamingText
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.largeSpacing
                    text: "Generating..."
                    wrapMode: Text.Wrap
                }
            }
        }

        // ── Right: context sidebar ──
        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: safeBgColor
            border.color: safeBorderColor
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.mediumSpacing

                // Header
                Label {
                    text: "justLLAMA"
                    font.bold: true
                    font.pointSize: 16
                    color: safeHighlightColor
                    Layout.alignment: Qt.AlignHCenter
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: safeBorderColor }

                // Context usage
                Label {
                    text: "Context"
                    font.bold: true
                    font.pointSize: 12
                }

                // Usage bar background
                Rectangle {
                    Layout.fillWidth: true
                    height: 20
                    radius: 4
                    color: chatPage.safeAltBgColor

                    // Fill bar
                    Rectangle {
                        width: Math.min(parent.width * (chatPage.contextPercent / 100), parent.width)
                        height: parent.height
                        radius: 4
                        color: chatPage.contextPercent > 90
                            ? chatPage.safeNegativeColor
                            : chatPage.contextPercent > 70
                                ? chatPage.safeHighlightColor
                                : chatPage.safePositiveColor

                        Behavior on width { NumberAnimation { duration: 300 } }
                        Behavior on color { ColorAnimation { duration: 300 } }
                    }

                    Label {
                        anchors.centerIn: parent
                        text: chatPage.contextPercent.toFixed(1) + "%"
                        font.bold: true
                        font.pointSize: 9
                        color: chatPage.contextPercent > 50 ? chatPage.safeBgColor : chatPage.safeTextColor
                    }
                }

                // Token counts
                Label {
                    text: chatPage.contextUsed.toLocaleString() + " / " + chatPage.contextMax.toLocaleString()
                    font.pointSize: 10
                    color: chatPage.safeDisabledColor
                    Layout.alignment: Qt.AlignHCenter
                }

                Label {
                    text: {
                        var remaining = chatPage.contextMax - chatPage.contextUsed
                        return remaining.toLocaleString() + " remaining"
                    }
                    font.pointSize: 10
                    color: chatPage.safeDisabledColor
                    Layout.alignment: Qt.AlignHCenter
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: chatPage.safeBorderColor }

                // Action buttons
                Button {
                    text: "🗑️ Clear Context"
                    Layout.fillWidth: true
                    onClicked: {
                        chatPage.messageHistory = []
                        chatPage.contextUsed = 0
                    }
                }

                Button {
                    text: "📦 Compact"
                    Layout.fillWidth: true
                    enabled: chatPage.contextPercent > 30
                    onClicked: compactContext()
                }

                Item { Layout.fillHeight: true }

                // Model info
                Rectangle { Layout.fillWidth: true; height: 1; color: chatPage.safeBorderColor }
                Label {
                    text: "Model"
                    font.bold: true
                    font.pointSize: 12
                }
                Label {
                    text: {
                        var p = appSettings.get_string("server/model_path")
                        return p ? p.split('/').pop().replace('.gguf', '') : "None loaded"
                    }
                    font.pointSize: 10
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                // Server status
                Rectangle { Layout.fillWidth: true; height: 1; color: chatPage.safeBorderColor }
                Label {
                    text: root.serverRunning ? "● Server online" : "● Server offline"
                    font.pointSize: 10
                    color: root.serverRunning ? chatPage.safePositiveColor : chatPage.safeNegativeColor
                }
            }
        }
    }

    // ── Functions ──

    function fetchContextUsage() {
        var xhr = new XMLHttpRequest()
        var port = appSettings.get_int("server/port") || 8080
        xhr.open("GET", "http://localhost:" + port + "/props", true)
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var props = JSON.parse(xhr.responseText)
                    if (props && props.slots) {
                        // Sum up prompt tokens from all slots
                        var used = 0
                        for (var i = 0; i < props.slots.length; i++) {
                            used += props.slots[i].n_past || 0
                        }
                        chatPage.contextUsed = used
                        if (props.default_generation_settings && props.default_generation_settings.n_ctx) {
                            chatPage.contextMax = props.default_generation_settings.n_ctx
                        }
                    }
                } catch (e) {
                    // Ignore parse errors
                }
            }
        }
        xhr.send()
    }

    function compactContext() {
        // Build a summary prompt asking the model to compact the conversation
        var summaryMessages = [
            {"role": "system", "content": "Summarize the following conversation concisely, preserving key facts, decisions, and context. Output ONLY the summary."},
            {"role": "user", "content": JSON.stringify(messageHistory)}
        ]
        var xhr = new XMLHttpRequest()
        var port = appSettings.get_int("server/port") || 8080
        xhr.open("POST", "http://localhost:" + port + "/v1/chat/completions", true)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    var resp = JSON.parse(xhr.responseText)
                    var summary = resp.choices[0].message.content || resp.choices[0].message.reasoning_content || ""
                    // Replace history with summary context
                    chatPage.messageHistory = [{"role": "system", "content": "[Compacted context] " + summary}]
                    chatPage.contextUsed = 0
                }
            }
        }
        var modelPath = appSettings.get_string("server/model_path")
        var modelName = modelPath.split('/').pop().replace('.gguf', '')
        xhr.send(JSON.stringify({
            "model": modelName,
            "messages": summaryMessages,
            "temperature": 0.3,
            "max_tokens": 1024,
            "stream": false
        }))
    }

    function sendMessage() {
        var text = inputField.text.trim()
        if (text.length === 0 || isGenerating) return

        var userMsg = {"role": "user", "content": text}
        messageHistory.push(userMsg)
        messageHistoryChanged()

        memoryManager.add_message("user", text)

        inputField.text = ""
        isGenerating = true

        var messages = []
        var sysPrompt = memoryManager.get_system_prompt_addition()
        if (sysPrompt.length > 0) {
            messages.push({"role": "system", "content": sysPrompt})
        }

        var history = JSON.parse(memoryManager.get_short_term_history(-1))
        messages = messages.concat(history)

        callChatCompletion(messages)
    }

    function callChatCompletion(messages) {
        var xhr = new XMLHttpRequest()
        var port = appSettings.get_int("server/port") || 8080
        xhr.open("POST", "http://localhost:" + port + "/v1/chat/completions", true)
        xhr.setRequestHeader("Content-Type", "application/json")

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                isGenerating = false
                fetchContextUsage()
                if (xhr.status === 200) {
                    var response = JSON.parse(xhr.responseText)
                    var msg = response.choices[0].message
                    var content = msg.content || msg.reasoning_content || "No response"
                    var assistantMsg = {"role": "assistant", "content": content}
                    messageHistory.push(assistantMsg)
                    messageHistoryChanged()
                    memoryManager.add_message("assistant", content)
                } else {
                    var errorMsg = {"role": "assistant", "content": "Error: Server returned " + xhr.status}
                    messageHistory.push(errorMsg)
                    messageHistoryChanged()
                }
            }
        }

        var modelPath = appSettings.get_string("server/model_path")
        var modelName = modelPath.split('/').pop().replace('.gguf', '')
        xhr.send(JSON.stringify({
            "model": modelName,
            "messages": messages,
            "temperature": chatPage.genTemperature,
            "top_p": chatPage.genTopP,
            "top_k": chatPage.genTopK,
            "repeat_penalty": chatPage.genRepeatPenalty,
            "max_tokens": chatPage.genMaxTokens,
            "stream": false
        }))
    }

    function stopGeneration() {
        isGenerating = false
    }
}
