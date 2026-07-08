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
    property var currentXhr: null
    property string assistantName: "Assistant"
    property var pendingOperations: []
    readonly property color modeAccentColor: {
        switch (modeSelector.currentIndex) {
            case 1: return Qt.rgba(0.85, 0.55, 0.2, 1)    // Plan — warm amber
            case 2: return Qt.rgba(0.25, 0.7, 0.4, 1)     // Build — green
            case 3: return Qt.rgba(0.6, 0.3, 0.85, 1)     // Council — purple
            default: return safeHighlightColor             // Chat — default blue
        }
    }
    readonly property string modeName: {
        switch (modeSelector.currentIndex) {
            case 1: return "Plan Mode"
            case 2: return "Build Mode"
            case 3: return "Council Mode"
            default: return "Chat Mode"
        }
    }

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
            if (key === "server/model_path") {
                chatPage.updateAssistantName(value)
            }
            if (key === "memory/enabled") {
                memoryIndicator.visible = value
                refreshIndicator()
            }
        }
    }
    Connections {
        target: councilManager
        function onProgress_update(msg) {
            streamingText.text = msg
        }
        function onSynthesis_ready(synthesis_prompt) {
            var messages = []
            if (appSettings.get_bool("rag/enabled")) {
                var lastMsg = messageHistory[messageHistory.length - 1]
                var text = lastMsg ? lastMsg.content : ""
                var ragResults = retriever.search(text, 3)
                if (ragResults) {
                    try {
                        var ragData = JSON.parse(ragResults)
                        if (ragData.length > 0) {
                            var ragContext = ragData.map(function(r) { return r.text }).join("\n\n")
                            messages.push({"role": "system", "content": "Relevant context:\n" + ragContext})
                        }
                    } catch (e) {}
                }
            }
            var sysPrompt = memoryManager.get_system_prompt_addition()
            if (sysPrompt.length > 0) {
                messages.push({"role": "system", "content": sysPrompt})
            }
            var history = JSON.parse(memoryManager.get_short_term_history(-1))
            if (history.length > 0 && history[history.length - 1].role === "user") {
                history[history.length - 1].content = synthesis_prompt
            } else {
                history.push({"role": "user", "content": synthesis_prompt})
            }
            messages = messages.concat(history)
            callChatCompletion(messages)
        }
        function onError(msg) {
            isGenerating = false
            streamingText.text = "ERROR: " + msg
            errorToast.show("Council error: " + msg)
        }
    }

    Component.onCompleted: {
        chatPage.updateAssistantName()
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
                            Label {
                                text: modelData.role === "user" ? "You" : chatPage.assistantName
                                font.bold: true
                                color: modelData.role === "user"
                                    ? safeHighlightColor
                                    : safePositiveColor
                            }
                            Label {
                                text: modelData.content
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                                selectable: true
                            }
                            RowLayout {
                                Layout.topMargin: Kirigami.Units.smallSpacing
                                Button {
                                    text: "Copy"
                                    flat: true
                                    icon.name: "edit-copy"
                                    font.pointSize: 9
                                    onClicked: chatPage.copyMessage(modelData.content)
                                }
                                Item { Layout.fillWidth: true }
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
                visible: appSettings.get_bool("memory/enabled")
                property string indicatorText: ""
                text: indicatorText ? "🧠 Memory active (" + indicatorText + ")" : ""
                color: safeHighlightColor
                font.italic: true
                Component.onCompleted: refreshIndicator()
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


            // Streaming response area
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: streamingText.height + Kirigami.Units.largeSpacing * 2
                visible: isGenerating
                color: safeAltBgColor
                border.color: chatPage.modeAccentColor
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

            // Input area
            RowLayout {
                spacing: Kirigami.Units.smallSpacing

                ComboBox {
                    id: modeSelector
                    model: ["Chat", "Plan", "Build", "Council"]
                    enabled: !isGenerating
                    Component.onCompleted: {
                        var mode = appSettings.get_string("chat/mode")
                        if (mode === "plan") currentIndex = 1
                        else if (mode === "build") currentIndex = 2
                        else if (mode === "council") currentIndex = 3
                        else currentIndex = 0
                    }
                    onActivated: {
                        var mode = "chat"
                        if (currentIndex === 1) mode = "plan"
                        else if (currentIndex === 2) mode = "build"
                        else if (currentIndex === 3) mode = "council"
                        appSettings.set_string("chat/mode", mode)
                    }
                }

                TextField {
                    id: inputField
                    Layout.fillWidth: true
                    placeholderText: {
                        if (modeSelector.currentIndex === 1) return "Type a goal to plan..."
                        if (modeSelector.currentIndex === 2) return "Type a step to build..."
                        if (modeSelector.currentIndex === 3) return "Type a question for the council..."
                        return "Type a message..."
                    }
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
        }

        // ── Right: context sidebar ──
        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: safeBgColor
            border.color: chatPage.modeAccentColor
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
                    color: chatPage.modeAccentColor
                    Layout.alignment: Qt.AlignHCenter
                }
                Label {
                    text: chatPage.modeName
                    font.pointSize: 11
                    color: chatPage.modeAccentColor
                    Layout.alignment: Qt.AlignHCenter
                    opacity: 0.85
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: chatPage.modeAccentColor }

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
                        memoryManager.clear_short_term()
                    }
                }

                Button {
                    text: "📦 Compact"
                    Layout.fillWidth: true
                    enabled: chatPage.contextPercent > 30
                    onClicked: compactContext()
                }

                        // Pending Build Operations panel (visible only in Build mode)
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: buildOpsColumn.implicitHeight + Kirigami.Units.largeSpacing * 2
                            visible: modeSelector.currentIndex === 2 && chatPage.pendingOperations.length > 0
                            color: safeAltBgColor
                            border.color: chatPage.modeAccentColor
                            border.width: 1
                            radius: Kirigami.Units.cornerRadius

                            ColumnLayout {
                                id: buildOpsColumn
                                anchors.fill: parent
                                anchors.margins: Kirigami.Units.smallSpacing
                                spacing: Kirigami.Units.smallSpacing

                                Label { text: "Pending Build Operations"; font.bold: true; font.pointSize: 11 }

                                Repeater {
                                    model: chatPage.pendingOperations

                                    delegate: ColumnLayout {
                                        spacing: 2
                                        Label {
                                            text: "[" + modelData.op.toUpperCase() + "] " + (modelData.path || "") + (modelData.command || "")
                                            font.family: "monospace"
                                            font.pointSize: 9
                                            elide: Text.ElideRight
                                            wrapMode: Text.Wrap
                                            Layout.fillWidth: true
                                        }
                                        RowLayout {
                                            Button {
                                                text: "Apply"
                                                flat: true
                                                icon.name: "dialog-ok"
                                                onClicked: {
                                                    var result = buildManager.apply_operation(JSON.stringify(modelData))
                                                    var ops = chatPage.pendingOperations
                                                    ops.splice(index, 1)
                                                    chatPage.pendingOperations = ops
                                                    chatPage.pendingOperationsChanged()
                                                    errorToast.show("Build op applied: " + result)
                                                }
                                            }
                                            Button {
                                                text: "Discard"
                                                flat: true
                                                icon.name: "dialog-cancel"
                                                onClicked: {
                                                    var ops = chatPage.pendingOperations
                                                    ops.splice(index, 1)
                                                    chatPage.pendingOperations = ops
                                                    chatPage.pendingOperationsChanged()
                                                }
                                            }
                                        }
                                    }
                                }

                                Button {
                                    text: "Apply All (" + chatPage.pendingOperations.length + ")"
                                    Layout.fillWidth: true
                                    onClicked: {
                                        var ops = chatPage.pendingOperations.slice()  // copy
                                        var results = []
                                        for (var i = 0; i < ops.length; i++) {
                                            var r = buildManager.apply_operation(JSON.stringify(ops[i]))
                                            results.push(r)
                                        }
                                        chatPage.pendingOperations = []
                                        chatPage.pendingOperationsChanged()
                                        errorToast.show("Applied " + ops.length + " ops (" + results.filter(function(r) { return r === "OK" }).length + " OK)")
                                    }
                                }
                            }
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
        xhr.open("GET", "http://localhost:" + port + "/slots", true)
        xhr.timeout = 10000
        xhr.ontimeout = function() {
            console.warn("fetchContextUsage timed out")
            errorToast.show("Failed to fetch context usage: timeout")
        }
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var slots = JSON.parse(xhr.responseText)
                    if (slots && Array.isArray(slots)) {
                        var used = 0
                        var max = 0
                        for (var i = 0; i < slots.length; i++) {
                            used += slots[i].n_past || 0
                            max += slots[i].n_ctx || 0
                        }
                        chatPage.contextUsed = used
                        if (max > 0) {
                            chatPage.contextMax = max
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
        xhr.timeout = 30000
        xhr.ontimeout = function() {
            console.error("compactContext timed out")
            errorToast.show("Context compaction failed: timeout")
        }
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    var resp = JSON.parse(xhr.responseText)
                    var summary = resp.choices[0].message.content || resp.choices[0].message.reasoning_content || ""
                    chatPage.messageHistory = [{"role": "system", "content": "[Compacted context] " + summary}]
                    chatPage.contextUsed = 0
                    memoryManager.clear_short_term()
                    memoryManager.add_message("system", "[Compacted context] " + summary)
                } else {
                    console.error("Compact failed: server returned " + xhr.status)
                    errorToast.show("Context compaction failed: server returned " + xhr.status)
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

    function parseBuildOps(text) {
        if (modeSelector.currentIndex !== 2) return
        var newOps = []
        var lines = text.split('\n')
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim()
            if (line.indexOf("=== BUILD_OP === ") === 0) {
                try {
                    var op = JSON.parse(line.substring("=== BUILD_OP === ".length))
                    newOps.push(op)
                } catch (e) {
                    console.warn("Failed to parse BUILD_OP:", line, e.message)
                }
            }
        }
        pendingOperations = newOps
        pendingOperationsChanged()
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
        if (modeSelector.currentIndex === 3) {
            streamingText.text = "Initializing Council..."
            councilManager.start_council(text)
            return
        }
        var messages = []
        
        // Try to retrieve RAG context for the user's question (only if enabled)
        if (appSettings.get_bool("rag/enabled")) {
            ragIndicator.visible = false
            var ragResults = retriever.search(text, 3)
            if (ragResults) {
                try {
                    var ragData = JSON.parse(ragResults)
                    if (ragData.length > 0) {
                        var ragContext = ragData.map(function(r) { return r.text }).join("\n\n")
                        messages.push({"role": "system", "content": "Relevant context:\n" + ragContext})
                        ragIndicator.visible = true
                    }
                } catch (e) {
                    errorToast.show("RAG search failed: " + e.message)
                }
            }
        }
        
        var sysPrompt = memoryManager.get_system_prompt_addition()
        if (sysPrompt.length > 0) {
            messages.push({"role": "system", "content": sysPrompt})
        }

        if (modeSelector.currentIndex === 1) {
            messages.push({"role": "system", "content": "You are in Plan Mode. You MUST perform READ-ONLY work, analyze the request, and output a detailed step-by-step markdown plan. Do NOT write full implementation code."})
        } else if (modeSelector.currentIndex === 2) {
            messages.push({"role": "system", "content": [
                "You are in Build Mode. You can create, edit, and read local files.",
                "To perform file operations, output them as a JSON block on its own line, one per line:",
                "",
                "=== BUILD_OP === {\"op\": \"write\", \"path\": \"relative/path/to/file.py\", \"content\": \"print('hello')\"}",
                "=== BUILD_OP === {\"op\": \"edit\", \"path\": \"src/main.py\", \"old\": \"old text\", \"new\": \"new text\"}",
                "=== BUILD_OP === {\"op\": \"read\", \"path\": \"src/main.py\"}",
                "=== BUILD_OP === {\"op\": \"run\", \"command\": \"python -m pytest\"}",
                "",
                "Operations are executed in order. Read results are available to you as context.",
                "You MUST NOT include any explanatory text (like ```) inside or around the BUILD_OP lines.",
                "Maximum one operation per line. Each line MUST start with exactly \"=== BUILD_OP === \".",
                "You should explain your plan in natural language, then output the BUILD_OP lines.",
                "When writing code, prefer the write operation over edit for new files."
            ].join("\n")})
        }
        
        var history = JSON.parse(memoryManager.get_short_term_history(-1))
        messages = messages.concat(history)
        
        callChatCompletion(messages)
    }

    function callChatCompletion(messages) {
        var xhr = new XMLHttpRequest()
        chatPage.currentXhr = xhr
        var port = appSettings.get_int("server/port") || 8080
        xhr.open("POST", "http://localhost:" + port + "/v1/chat/completions", true)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.timeout = 30000
        
        var fullContent = ""
        var lastIndex = 0
        var sseLineBuffer = ""

        xhr.ontimeout = function() {
            chatPage.currentXhr = null
            isGenerating = false
            streamingText.text = "Error: Request timed out."
        }

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 3 || xhr.readyState === 4) {
                var newText = xhr.responseText.substring(lastIndex)
                lastIndex = xhr.responseText.length

                // Prepend leftover from previous chunk
                newText = sseLineBuffer + newText

                var lines = newText.split('\n')
                // Last element may be an incomplete line — save for next chunk
                sseLineBuffer = lines.pop() || ""

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim()
                    if (line.indexOf("data: ") === 0) {
                        var data = line.substring(6).trim()
                        if (data === "[DONE]") continue
                        try {
                            var parsed = JSON.parse(data)
                            var delta = parsed.choices && parsed.choices[0] && parsed.choices[0].delta
                            if (delta && delta.content) {
                                fullContent += delta.content
                            }
                        } catch (e) {
                            // Skip unparseable chunks
                        }
                    }
                }
                
                streamingText.text = fullContent || "Generating..."
                chatPage.parseBuildOps(fullContent)
            }
            
            if (xhr.readyState === 4) {
                chatPage.currentXhr = null
                isGenerating = false
                fetchContextUsage()
                
                if (xhr.status === 0) return  // Aborted
                
                if (xhr.status === 200) {
                    if (fullContent.length > 0) {
                        var assistantMsg = {"role": "assistant", "content": fullContent}
                        messageHistory.push(assistantMsg)
                        messageHistoryChanged()
                        memoryManager.add_message("assistant", fullContent)
                    } else {
                        try {
                            var response = JSON.parse(xhr.responseText)
                            var msg = response.choices[0].message
                            var content = msg.content || msg.reasoning_content || "No response"
                            var fallbackMsg = {"role": "assistant", "content": content}
                            messageHistory.push(fallbackMsg)
                            messageHistoryChanged()
                            memoryManager.add_message("assistant", content)
                        } catch (e) {
                            streamingText.text = "Error: Failed to parse response."
                        }
                    }
                } else {
                    var errorContent = "Error: Server returned " + xhr.status
                    streamingText.text = errorContent
                    var errorMsg = {"role": "assistant", "content": errorContent}
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
            "stream": true
        }))
    }

    function stopGeneration() {
        isGenerating = false
        if (chatPage.currentXhr) {
            chatPage.currentXhr.abort()
            chatPage.currentXhr = null
        }
        streamingText.text = "Generation stopped."
    }

    function refreshIndicator() {
        try {
            var s = JSON.parse(memoryManager.stats())
            memoryIndicator.indicatorText = s.short_term_count + " short, " + s.long_term_count + " long"
        } catch (e) {
            memoryIndicator.indicatorText = ""
            errorToast.show("Failed to refresh memory stats: " + e.message)
        }
    }

    function updateAssistantName(path) {
        var p = path !== undefined ? path : (appSettings ? appSettings.get_string("server/model_path") : "")
        if (!p) {
            assistantName = "Assistant"
            return
        }
        assistantName = p.split('/').pop().replace('.gguf', '')
    }
    function copyMessage(text) {
        hiddenCopyField.text = text
        hiddenCopyField.selectAll()
        hiddenCopyField.copy()
        errorToast.show("Copied!")
    }
    TextField {
        id: hiddenCopyField
        visible: false
        width: 0
        height: 0
    }
    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
