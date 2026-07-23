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
                property bool isSelected: modelData.path === selectedModel
                property bool isHovered: hovered
                property bool expanded: false
                background: Rectangle {
                    color: isSelected ? Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 0.2)
                        : isHovered ? Kirigami.Theme.hoverColor || Qt.rgba(1, 1, 1, 0.05)
                        : Kirigami.Theme.backgroundColor
                    border.color: isSelected ? Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
                        : Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
                    border.width: 1
                    radius: Kirigami.Units.cornerRadius

                    // Selected indicator bar
                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 4
                        color: isSelected ? Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1) : Qt.rgba(0, 0, 0, 0)
                        radius: parent.radius
                    }
                }
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing

                    // Row 1: Model name + size badge
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Label {
                            Layout.fillWidth: true
                            text: modelData.name
                            font.bold: true
                            elide: Text.ElideRight
                            color: isSelected ? Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1) : Kirigami.Theme.textColor
                        }
                        Label {
                            text: modelData.size_display
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: 9
                        }
                        // Expand/collapse indicator
                        Label {
                            text: parent.parent.expanded ? "▼" : "▶"
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: 8
                        }
                    }

                    // Row 2: Action buttons
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Button {
                            Layout.fillWidth: true
                            text: isSelected ? "✓ Active" : "▶ Load"
                            icon.name: isSelected ? "dialog-ok" : "go-next"
                            onClicked: {
                                if (!isSelected) showPreLoadDialog(modelData.path, modelData.name)
                            }
                            enabled: !isSelected || modelData.path !== selectedModel
                        }

                        ToolButton {
                            icon.name: "configure"
                            onClicked: openOptionsDialog(modelData.path, modelData.name)
                            ToolTip.text: "Model Profile"
                            ToolTip.visible: hovered
                        }
                    }

                    // Expandable details section
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Kirigami.Units.smallSpacing
                        visible: parent.parent.expanded
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Separator {
                            Layout.fillWidth: true
                        }

                        // GGUF metadata
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            visible: modelData.gguf_arch || modelData.gguf_ctx

                            Label {
                                visible: modelData.gguf_arch
                                text: "Arch: " + modelData.gguf_arch
                                color: Kirigami.Theme.neutralTextColor
                                font.pointSize: 9
                            }
                            Label {
                                visible: modelData.gguf_ctx
                                text: "• Context: " + (modelData.gguf_ctx / 1000).toFixed(0) + "K"
                                color: Kirigami.Theme.neutralTextColor
                                font.pointSize: 9
                            }
                            Label {
                                visible: modelData.gguf_template
                                text: "• Template: " + modelData.gguf_template
                                color: Kirigami.Theme.positiveTextColor
                                font.pointSize: 9
                            }
                            Label {
                                visible: modelData.gguf_is_moe
                                text: "• MoE: " + modelData.gguf_expert_count + " experts"
                                color: Kirigami.Theme.neutralTextColor
                                font.pointSize: 9
                            }
                        }

                        // VRAM warning
                        Label {
                            property bool fitsInVRAM: modelData.size_gb <= modelBrowser.safe_vram_gb
                            property bool fitsInTotalSafe: modelData.size_gb <= (modelBrowser.safe_vram_gb + modelBrowser.safe_ram_gb)

                            visible: !fitsInVRAM
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            text: !fitsInTotalSafe ? "⚠ Exceeds safe memory (OOM crash risk)" : "⚠ Exceeds VRAM (will spill to system RAM)"
                            color: !fitsInTotalSafe ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.neutralTextColor
                            font.italic: true
                            font.pointSize: 9
                        }

                        // Modified date
                        Label {
                            text: "Modified: " + new Date(modelData.modified_time * 1000).toLocaleDateString()
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: 9
                        }
                    }

                    // MouseArea for expand/collapse
                    MouseArea {
                        anchors.fill: parent
                        onClicked: parent.parent.expanded = !parent.parent.expanded
                        // Pass through clicks to buttons
                        propagateComposedEvents: true
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
        var rawModels = modelBrowser.scan()
        // Enrich model data with GGUF metadata
        for (var i = 0; i < rawModels.length; i++) {
            var m = rawModels[i]
            try {
                var info = ggufMetadata.get_model_info(m.path)
                m.gguf_arch = info.architecture || ""
                m.gguf_ctx = info.context_length || 0
                m.gguf_template = info.has_chat_template ? (info.chat_template_name || "detected") : ""
                m.gguf_layers = info.block_count || 0
                m.gguf_is_moe = info.is_moe || false
                m.gguf_expert_count = info.expert_count || 0
            } catch (e) {
                m.gguf_arch = ""
                m.gguf_ctx = 0
                m.gguf_template = ""
                m.gguf_layers = 0
                m.gguf_is_moe = false
                m.gguf_expert_count = 0
            }
        }
        models = rawModels
    }

    property string editingModelPath: ""
    property string editingModelName: ""
    property bool editingModelIsMoe: false

    // Pre-load dialog properties
    property string preLoadModelPath: ""
    property string preLoadModelName: ""

    // Section expansion states
    property bool advancedSectionExpanded: false
    property bool moeSectionExpanded: false
    property bool draftSectionExpanded: false
    property bool lowLevelSectionExpanded: false

    // Reusable collapsible section component
    Component {
        id: collapsibleSectionTemplate
        ColumnLayout {
            property string sectionTitle: ""
            property bool sectionExpanded: false
            spacing: 0
    
            // Section header
            Rectangle {
                Layout.fillWidth: true
                height: 32
                color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.5, 0.5, 0.5, 0.1)
                radius: Kirigami.Units.cornerRadius / 2
    
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Kirigami.Units.smallSpacing
                    anchors.rightMargin: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing
    
                    Label {
                        text: sectionExpanded ? "▼" : "▶"
                        font.pointSize: 8
                        color: Kirigami.Theme.disabledTextColor
                    }
                    Label {
                        text: sectionTitle
                        font.bold: true
                        color: Kirigami.Theme.textColor
                    }
                    Item { Layout.fillWidth: true }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: sectionExpanded = !sectionExpanded
                    }
                }
            }
    
            // Section content
            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.largeSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
                visible: sectionExpanded
                spacing: Kirigami.Units.smallSpacing
            }
        }
    }
    
    Dialog {
        id: optionsDialog
        modal: true
        title: "Model Profile: " + editingModelName
        anchors.centerIn: parent
        width: 520
    
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing
    
            // Section 1: Model Info (always visible)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                visible: detectedInfoLabel.text.length > 0 && detectedInfoLabel.text !== "No GGUF metadata available"
    
                Label {
                    text: "Model Information"
                    font.bold: true
                    color: Kirigami.Theme.textColor
                }
                Label {
                    id: detectedInfoLabel
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    font.pointSize: 9
                    color: Kirigami.Theme.disabledTextColor
                    text: ""
                    visible: text.length > 0
                }
                Kirigami.Separator {
                    Layout.fillWidth: true
                }
            }
    
            // Section 2: Basic Settings (always expanded)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
    
                Label {
                    text: "Basic Settings"
                    font.bold: true
                    color: Kirigami.Theme.textColor
                }
    
                GridLayout {
                    columns: 2
                    rowSpacing: Kirigami.Units.smallSpacing
                    columnSpacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
    
                    Label { text: "Context Window:" }
                    SpinBox {
                        id: optCtxSpin
                        from: 512; to: 131072; stepSize: 1024
                        editable: true
                        Layout.fillWidth: true
                    }
    
                    Label { text: "GPU Offload:" }
                    ComboBox {
                        id: optNglCombo
                        model: ["Auto (VRAM-based)", "CPU only", "Custom"]
                        Layout.fillWidth: true
                    }
    
                    Label {
                        text: "Custom Layers:"
                        visible: optNglCombo.currentIndex === 2
                    }
                    SpinBox {
                        id: optNglSpin
                        visible: optNglCombo.currentIndex === 2
                        from: 0; to: 999
                        editable: true
                        Layout.fillWidth: true
                    }
    
                    Label { text: "Flash Attention:" }
                    ComboBox {
                        id: optFlashCombo
                        model: ["Auto", "On", "Off"]
                        Layout.fillWidth: true
                    }
                }
            }
    
            Kirigami.Separator {
                Layout.fillWidth: true
            }
    
            // Section 3: Advanced Settings (collapsible)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
    
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.5, 0.5, 0.5, 0.1)
                    radius: Kirigami.Units.cornerRadius / 2
    
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Kirigami.Units.smallSpacing
                        anchors.rightMargin: Kirigami.Units.smallSpacing
    
                        Label {
                            text: advancedSectionExpanded ? "▼" : "▶"
                            font.pointSize: 8
                            color: Kirigami.Theme.disabledTextColor
                        }
                        Label {
                            text: "Advanced Settings"
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        MouseArea {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            onClicked: advancedSectionExpanded = !advancedSectionExpanded
                        }
                    }
                }
    
                GridLayout {
                    columns: 2
                    rowSpacing: Kirigami.Units.smallSpacing
                    columnSpacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.smallSpacing
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    visible: advancedSectionExpanded
    
                    Label { text: "Jinja Template:" }
                    CheckBox {
                        id: optJinjaCheck
                        text: "Enable automatic chat template"
                    }
    
                    Label { text: "Chat Template:" }
                    TextField {
                        id: optTemplateField
                        placeholderText: "e.g. llama3 or path to template"
                        Layout.fillWidth: true
                    }
    
                    Label { text: "Threads:" }
                    SpinBox {
                        id: optThreadsSpin
                        from: -1; to: 64
                        editable: true
                        Layout.fillWidth: true
                    }
    
                    Label { text: "Batch Size:" }
                    SpinBox {
                        id: optBatchSpin
                        from: 64; to: 8192; stepSize: 64
                        editable: true
                        Layout.fillWidth: true
                    }
    
                    Label { text: "Micro Batch:" }
                    SpinBox {
                        id: optUbatchSpin
                        from: 64; to: 8192; stepSize: 64
                        editable: true
                        Layout.fillWidth: true
                    }
                }
            }
    
            // Section 4: MoE Expert Options (collapsible, only for MoE models)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                visible: editingModelIsMoe
    
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.5, 0.5, 0.5, 0.1)
                    radius: Kirigami.Units.cornerRadius / 2
    
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Kirigami.Units.smallSpacing
                        anchors.rightMargin: Kirigami.Units.smallSpacing
    
                        Label {
                            text: moeSectionExpanded ? "▼" : "▶"
                            font.pointSize: 8
                            color: Kirigami.Theme.disabledTextColor
                        }
                        Label {
                            text: "MoE Expert Options"
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        MouseArea {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            onClicked: moeSectionExpanded = !moeSectionExpanded
                        }
                    }
                }
    
                GridLayout {
                    columns: 2
                    rowSpacing: Kirigami.Units.smallSpacing
                    columnSpacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.smallSpacing
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    visible: moeSectionExpanded
    
                    Label { text: "Expert Offload:" }
                    RowLayout {
                        CheckBox {
                            id: optCpuMoeCheck
                            text: "All experts to CPU"
                        }
                        Label { text: "or first N layers:" }
                        SpinBox {
                            id: optNCpuMoeSpin
                            from: 0; to: 999
                            editable: true
                            enabled: !optCpuMoeCheck.checked
                        }
                    }
                }
            }
    
            // Section 5: Speculative Decoding (collapsible)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
    
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.5, 0.5, 0.5, 0.1)
                    radius: Kirigami.Units.cornerRadius / 2
    
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Kirigami.Units.smallSpacing
                        anchors.rightMargin: Kirigami.Units.smallSpacing
    
                        Label {
                            text: draftSectionExpanded ? "▼" : "▶"
                            font.pointSize: 8
                            color: Kirigami.Theme.disabledTextColor
                        }
                        Label {
                            text: "Speculative Decoding"
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        MouseArea {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            onClicked: draftSectionExpanded = !draftSectionExpanded
                        }
                    }
                }
    
                GridLayout {
                    columns: 2
                    rowSpacing: Kirigami.Units.smallSpacing
                    columnSpacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.smallSpacing
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    visible: draftSectionExpanded
    
                    Label { text: "Draft Model:" }
                    TextField {
                        id: optDraftField
                        placeholderText: "path to draft model"
                        Layout.fillWidth: true
                    }
    
                    Label {
                        text: "Draft GPU Layers:"
                        visible: optDraftField.text.trim().length > 0
                    }
                    SpinBox {
                        id: optDraftNglSpin
                        from: 0; to: 999
                        editable: true
                        visible: optDraftField.text.trim().length > 0
                        Layout.fillWidth: true
                    }
    
                    Label {
                        text: "Draft Max:"
                        visible: optDraftField.text.trim().length > 0
                    }
                    SpinBox {
                        id: optDraftMaxSpin
                        from: 0; to: 64
                        editable: true
                        visible: optDraftField.text.trim().length > 0
                        Layout.fillWidth: true
                    }
    
                    Label {
                        text: "Draft Min:"
                        visible: optDraftField.text.trim().length > 0
                    }
                    SpinBox {
                        id: optDraftMinSpin
                        from: 0; to: 64
                        editable: true
                        visible: optDraftField.text.trim().length > 0
                        Layout.fillWidth: true
                    }
                }
            }
    
            // Section 6: Low-Level (collapsible)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
    
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.5, 0.5, 0.5, 0.1)
                    radius: Kirigami.Units.cornerRadius / 2
    
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Kirigami.Units.smallSpacing
                        anchors.rightMargin: Kirigami.Units.smallSpacing
    
                        Label {
                            text: lowLevelSectionExpanded ? "▼" : "▶"
                            font.pointSize: 8
                            color: Kirigami.Theme.disabledTextColor
                        }
                        Label {
                            text: "Low-Level Settings"
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        MouseArea {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            onClicked: lowLevelSectionExpanded = !lowLevelSectionExpanded
                        }
                    }
                }
    
                GridLayout {
                    columns: 2
                    rowSpacing: Kirigami.Units.smallSpacing
                    columnSpacing: Kirigami.Units.largeSpacing
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    Layout.rightMargin: Kirigami.Units.smallSpacing
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    visible: lowLevelSectionExpanded
    
                    Label { text: "KV Cache (K / V):" }
                    RowLayout {
                        ComboBox {
                            id: optCacheKCombo
                            model: ["default", "f16", "q8_0", "q4_0"]
                            Layout.fillWidth: true
                        }
                        ComboBox {
                            id: optCacheVCombo
                            model: ["default", "f16", "q8_0", "q4_0"]
                            Layout.fillWidth: true
                        }
                    }
    
                    Label { text: "Extra CLI Flags:" }
                    TextField {
                        id: optExtraField
                        placeholderText: "e.g. --rope-scaling linear"
                        Layout.fillWidth: true
                    }
                }
            }
    
            RowLayout {
                Layout.topMargin: Kirigami.Units.largeSpacing
                Layout.fillWidth: true
    
                Button {
                    text: "Reset Defaults"
                    onClicked: resetOptions()
                }
    
                Item { Layout.fillWidth: true }
    
                Button {
                    text: "Cancel"
                    onClicked: optionsDialog.close()
                }
    
                Button {
                    text: "Save Profile"
                    onClicked: saveOptions()
                }
            }
        }
    }

    function openOptionsDialog(path, name) {
        editingModelPath = path
        editingModelName = name
        var profile = modelProfiles.get_model_profile(path)
        var eff = JSON.parse(modelProfiles.get_effective_config_json(path, appSettings))

        // Read GGUF metadata for info display
        var ggufInfo = {}
        try {
            ggufInfo = ggufMetadata.get_model_info(path)
        } catch (e) {
            // Ignore errors
        }

        // Detect MoE model
        editingModelIsMoe = ggufInfo.is_moe || false

        // Show auto-detected info label
        var autoInfo = ""
        if (ggufInfo.architecture) autoInfo += "Architecture: " + ggufInfo.architecture + "  |  "
        if (ggufInfo.block_count) autoInfo += "Layers: " + ggufInfo.block_count + "  |  "
        if (ggufInfo.context_length) autoInfo += "Training Context: " + ggufInfo.context_length + "  |  "
        if (ggufInfo.has_chat_template) autoInfo += "Template: " + (ggufInfo.chat_template_name || "detected")
        if (ggufInfo.is_moe) autoInfo += "  |  MoE: " + ggufInfo.expert_count + " experts, " + ggufInfo.expert_used_count + " used"
        if (eff._auto_ctx) autoInfo += "\n(Context auto-set to " + eff.ctx_size + " from GGUF metadata)"
        if (eff._ngl_auto) autoInfo += "\n(GPU layers auto-set to " + eff.n_gpu_layers + " based on VRAM)"
        detectedInfoLabel.text = autoInfo.length > 0 ? autoInfo : "No GGUF metadata available"

        // Set context size - show the effective (possibly auto-detected) value
        optCtxSpin.value = eff.ctx_size || 8192

        var ngl = profile.n_gpu_layers !== undefined ? profile.n_gpu_layers : "auto"
        if (ngl === "auto" || ngl === 99 || ngl === -1) {
            optNglCombo.currentIndex = 0
            optNglSpin.value = 0
        } else if (ngl === 0 || ngl === "0") {
            optNglCombo.currentIndex = 1
            optNglSpin.value = 0
        } else {
            optNglCombo.currentIndex = 2
            optNglSpin.value = parseInt(ngl) || 0
        }

        var fa = profile.flash_attn !== undefined ? profile.flash_attn : "auto"
        if (fa === "on" || fa === true) optFlashCombo.currentIndex = 1
        else if (fa === "off" || fa === false) optFlashCombo.currentIndex = 2
        else optFlashCombo.currentIndex = 0

        // Jinja is now enabled by default for automatic chat template
        optJinjaCheck.checked = profile.jinja !== undefined ? !!profile.jinja : true
        optTemplateField.text = profile.chat_template || ""
        optThreadsSpin.value = profile.threads !== undefined ? profile.threads : -1
        optBatchSpin.value = profile.batch_size || 512
        optUbatchSpin.value = profile.ubatch_size || 512
        optExtraField.text = Array.isArray(profile.extra_args) ? profile.extra_args.join(" ") : (profile.extra_args || "")

        var ctk = profile.cache_type_k || ""
        var cvIdx = optCacheKCombo.model.indexOf(ctk)
        optCacheKCombo.currentIndex = cvIdx >= 0 && ctk !== "" ? cvIdx : 0
        var ctv = profile.cache_type_v || ""
        var cvvIdx = optCacheVCombo.model.indexOf(ctv)
        optCacheVCombo.currentIndex = cvvIdx >= 0 && ctv !== "" ? cvvIdx : 0
        optCpuMoeCheck.checked = !!profile.cpu_moe
        optNCpuMoeSpin.value = profile.n_cpu_moe !== undefined ? profile.n_cpu_moe : 0
        optDraftField.text = profile.model_draft || ""
        optDraftNglSpin.value = profile.gpu_layers_draft !== undefined ? profile.gpu_layers_draft : 99
        optDraftMaxSpin.value = profile.draft_max !== undefined ? profile.draft_max : 0
        optDraftMinSpin.value = profile.draft_min !== undefined ? profile.draft_min : 0

        optionsDialog.open()
    }

    function saveOptions() {
        var nglVal = "auto"
        if (optNglCombo.currentIndex === 1) nglVal = 0
        else if (optNglCombo.currentIndex === 2) nglVal = optNglSpin.value

        var faVal = "auto"
        if (optFlashCombo.currentIndex === 1) faVal = "on"
        else if (optFlashCombo.currentIndex === 2) faVal = "off"

        var profile = {
            "ctx_size": optCtxSpin.value,
            "n_gpu_layers": nglVal,
            "flash_attn": faVal,
            "jinja": optJinjaCheck.checked,
            "chat_template": optTemplateField.text.trim(),
            "threads": optThreadsSpin.value,
            "batch_size": optBatchSpin.value,
            "ubatch_size": optUbatchSpin.value,
            "cache_type_k": optCacheKCombo.currentIndex === 0 ? "" : optCacheKCombo.currentText,
            "cache_type_v": optCacheVCombo.currentIndex === 0 ? "" : optCacheVCombo.currentText,
            "cpu_moe": optCpuMoeCheck.checked,
            "n_cpu_moe": optCpuMoeCheck.checked ? 0 : optNCpuMoeSpin.value,
            "model_draft": optDraftField.text.trim(),
            "gpu_layers_draft": optDraftNglSpin.value,
            "draft_max": optDraftMaxSpin.value,
            "draft_min": optDraftMinSpin.value,
            "extra_args": optExtraField.text.trim()
        }

        var ok = modelProfiles.save_model_profile(editingModelPath, JSON.stringify(profile))
        if (ok) {
            toast.show("Saved profile for " + editingModelName, "success")
            optionsDialog.close()
        } else {
            toast.show("Failed to save profile", "error")
        }
    }

    function resetOptions() {
        // Delete existing profile, then re-populate dialog with GGUF-derived defaults
        modelProfiles.delete_profile(editingModelPath)

        // Read GGUF metadata and set smart defaults
        var ggufInfo = {}
        try {
            ggufInfo = ggufMetadata.get_model_info(editingModelPath)
        } catch (e) {
            // Ignore errors
        }

        // Set context size from GGUF or fallback
        if (ggufInfo.context_length > 0) {
            var safeCtx = Math.min(Math.floor(ggufInfo.context_length * 0.75), 32768)
            optCtxSpin.value = safeCtx
        } else {
            optCtxSpin.value = 8192
        }

        // Set NGL to auto
        optNglCombo.currentIndex = 0
        optNglSpin.value = 0

        // Flash attention to auto
        optFlashCombo.currentIndex = 0

        // Jinja enabled by default
        optJinjaCheck.checked = true
        optTemplateField.text = ""

        // Threads to auto
        optThreadsSpin.value = -1

        // Batch sizes to defaults
        optBatchSpin.value = 512
        optUbatchSpin.value = 512

        // Cache types to default
        optCacheKCombo.currentIndex = 0
        optCacheVCombo.currentIndex = 0

        // MoE off
        optCpuMoeCheck.checked = false
        optNCpuMoeSpin.value = 0

        // Draft model empty
        optDraftField.text = ""
        optDraftNglSpin.value = 99
        optDraftMaxSpin.value = 0
        optDraftMinSpin.value = 0

        // Extra args empty
        optExtraField.text = ""

        // Update detected info label
        var autoInfo = ""
        if (ggufInfo.architecture) autoInfo += "Architecture: " + ggufInfo.architecture + "  |  "
        if (ggufInfo.block_count) autoInfo += "Layers: " + ggufInfo.block_count + "  |  "
        if (ggufInfo.context_length) autoInfo += "Training Context: " + ggufInfo.context_length + "  |  "
        if (ggufInfo.has_chat_template) autoInfo += "Template: " + (ggufInfo.chat_template_name || "detected")
        if (ggufInfo.is_moe) autoInfo += "  |  MoE: " + ggufInfo.expert_count + " experts, " + ggufInfo.expert_used_count + " used"
        detectedInfoLabel.text = autoInfo.length > 0 ? autoInfo : "No GGUF metadata available"

        toast.show("Reset to auto-detected defaults for " + editingModelName, "info")
    }

    function loadModel(path) {
        console.log("Loading model:", path)
        selectedModel = path
        appSettings.set_string("server/model_path", path)

        if (serverManager.is_running()) {
            console.log("Stopping existing server")
            serverManager.stop()
        }

        var bin = appSettings.get_string("server/binary")
        var port = appSettings.get_int("server/port")

        // Build profile JSON from pre-load dialog settings
        var preNgl = "auto"
        if (preLoadNglCombo.currentIndex === 1) preNgl = 0
        else if (preLoadNglCombo.currentIndex === 2) preNgl = preLoadNglSpin.value

        var preFa = "auto"
        if (preLoadFlashCombo.currentIndex === 1) preFa = "on"
        else if (preLoadFlashCombo.currentIndex === 2) preFa = "off"

        var profile = {
            "ctx_size": preLoadCtxSpin.value,
            "n_gpu_layers": preNgl,
            "flash_attn": preFa
        }
        var profileJson = JSON.stringify(profile)

        // Save as model profile so settings persist
        modelProfiles.save_model_profile(path, profileJson)

        var eff = JSON.parse(modelProfiles.get_effective_config_json(path, appSettings))
        console.log("Starting server with model profile:", path, JSON.stringify(eff))
        var ok = serverManager.start(bin, path, port, eff.ctx_size, eff.n_gpu_layers, eff.threads, JSON.stringify(eff))
        console.log("Server start result:", ok)
        if (!ok) {
            toast.show("Failed to start server with model: " + path.split('/').pop(), "error")
        }
    }

    function showPreLoadDialog(path, name) {
        preLoadModelPath = path
        preLoadModelName = name

        // Read effective config to pre-fill dialog
        var eff = JSON.parse(modelProfiles.get_effective_config_json(path, appSettings))
        var ggufInfo = {}
        try {
            ggufInfo = ggufMetadata.get_model_info(path)
        } catch (e) {}

        // Populate info label
        var info = name
        if (ggufInfo.architecture) info += "  |  " + ggufInfo.architecture
        if (ggufInfo.block_count) info += "  |  " + ggufInfo.block_count + " layers"
        if (ggufInfo.is_moe) info += "  |  MoE (" + ggufInfo.expert_count + " experts)"
        preLoadInfoLabel.text = info

        // Pre-fill settings
        preLoadCtxSpin.value = eff.ctx_size || 8192

        var ngl = eff.n_gpu_layers
        if (ngl === "auto" || ngl === 99 || ngl === -1) {
            preLoadNglCombo.currentIndex = 0
            preLoadNglSpin.value = 0
        } else if (ngl === 0 || ngl === "0") {
            preLoadNglCombo.currentIndex = 1
            preLoadNglSpin.value = 0
        } else {
            preLoadNglCombo.currentIndex = 2
            preLoadNglSpin.value = parseInt(ngl) || 0
        }

        var fa = eff.flash_attn
        if (fa === "on" || fa === true) preLoadFlashCombo.currentIndex = 1
        else if (fa === "off" || fa === false) preLoadFlashCombo.currentIndex = 2
        else preLoadFlashCombo.currentIndex = 0

        preLoadDialog.title = "Load Model: " + name
        preLoadDialog.open()
    }
    // Pre-load confirmation dialog
    Dialog {
        id: preLoadDialog
        modal: true
        title: "Load Model"
        anchors.centerIn: parent
        width: 440
        standardButtons: Dialog.Cancel

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.mediumSpacing

            // Model info
            Label {
                id: preLoadInfoLabel
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                font.bold: true
                color: Kirigami.Theme.textColor
            }

            Kirigami.Separator {
                Layout.fillWidth: true
            }

            Label {
                text: "Review and adjust settings before loading:"
                font.pointSize: 9
                color: Kirigami.Theme.disabledTextColor
            }

            GridLayout {
                columns: 2
                rowSpacing: Kirigami.Units.smallSpacing
                columnSpacing: Kirigami.Units.largeSpacing
                Layout.fillWidth: true

                Label { text: "Context Window:" }
                SpinBox {
                    id: preLoadCtxSpin
                    from: 512; to: 131072; stepSize: 1024
                    editable: true
                    Layout.fillWidth: true
                }

                Label { text: "GPU Offload:" }
                ComboBox {
                    id: preLoadNglCombo
                    model: ["Auto (VRAM-based)", "CPU only", "Custom"]
                    Layout.fillWidth: true
                }

                Label {
                    text: "Custom Layers:"
                    visible: preLoadNglCombo.currentIndex === 2
                }
                SpinBox {
                    id: preLoadNglSpin
                    visible: preLoadNglCombo.currentIndex === 2
                    from: 0; to: 999
                    editable: true
                    Layout.fillWidth: true
                }

                Label { text: "Flash Attention:" }
                ComboBox {
                    id: preLoadFlashCombo
                    model: ["Auto", "On", "Off"]
                    Layout.fillWidth: true
                }
            }

            RowLayout {
                Layout.topMargin: Kirigami.Units.mediumSpacing
                Layout.fillWidth: true

                Button {
                    text: "Edit Full Profile"
                    onClicked: {
                        preLoadDialog.close()
                        openOptionsDialog(preLoadModelPath, preLoadModelName)
                    }
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: "Cancel"
                    onClicked: preLoadDialog.close()
                }

                Button {
                    text: "Load Model"
                    onClicked: {
                        preLoadDialog.close()
                        loadModel(preLoadModelPath)
                    }
                }
            }
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
    Toast {
        id: toast
        anchors.fill: parent
    }
}
