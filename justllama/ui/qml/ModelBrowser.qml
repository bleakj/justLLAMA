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
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing

                    ColumnLayout {
                        Layout.fillWidth: true

                        Label {
                            Layout.fillWidth: true
                            text: modelData.name
                            font.bold: true
                            elide: Text.ElideRight
                            color: isSelected ? Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1) : Kirigami.Theme.textColor
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData.size_display + " • " + new Date(modelData.modified_time * 1000).toLocaleDateString()
                                color: Kirigami.Theme.disabledTextColor
                            }

                            Label {
                                property bool fitsInVRAM: modelData.size_gb <= modelBrowser.safe_vram_gb
                                property bool fitsInTotalSafe: modelData.size_gb <= (modelBrowser.safe_vram_gb + modelBrowser.safe_ram_gb)

                                visible: !fitsInVRAM
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                text: !fitsInTotalSafe ? "⚠️ Exceeds safe memory (OOM crash risk)" : "⚠️ Exceeds VRAM (will spill to system RAM)"
                                color: !fitsInTotalSafe ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.neutralTextColor
                                font.italic: true
                            }
                        }
                    }

                    Button {
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 80
                        text: "⚙️ Profile"
                        onClicked: openOptionsDialog(modelData.path, modelData.name)
                    }

                    Button {
                        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                        Layout.preferredWidth: 100
                        text: isSelected ? "✓ Active" : "▶️ Load"
                        icon.name: isSelected ? "dialog-ok" : "go-next"
                        onClicked: {
                            if (!isSelected) loadModel(modelData.path)
                        }
                        enabled: !isSelected || modelData.path !== selectedModel
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
        models = modelBrowser.scan()
    }

    property string editingModelPath: ""
    property string editingModelName: ""

    Dialog {
        id: optionsDialog
        modal: true
        title: "Model Profile: " + editingModelName
        anchors.centerIn: parent
        width: 480

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            GridLayout {
                columns: 2
                rowSpacing: Kirigami.Units.smallSpacing
                columnSpacing: Kirigami.Units.largeSpacing

                Label { text: "Context Window (-c):" }
                SpinBox {
                    id: optCtxSpin
                    from: 512; to: 131072; stepSize: 1024
                    editable: true
                    Layout.fillWidth: true
                }

                Label { text: "GPU Offload (-ngl):" }
                ComboBox {
                    id: optNglCombo
                    model: ["auto (automatic split)", "0 (CPU only)", "custom"]
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

                Label { text: "Flash Attention (--flash-attn):" }
                ComboBox {
                    id: optFlashCombo
                    model: ["auto", "on", "off"]
                    Layout.fillWidth: true
                }

                Label { text: "Jinja Template (--jinja):" }
                CheckBox {
                    id: optJinjaCheck
                    text: "Enable Jinja template processing"
                }

                Label { text: "Chat Template (--chat-template):" }
                TextField {
                    id: optTemplateField
                    placeholderText: "e.g. llama3 or path to template"
                    Layout.fillWidth: true
                }

                Label { text: "Threads (-t):" }
                SpinBox {
                    id: optThreadsSpin
                    from: -1; to: 64
                    editable: true
                    Layout.fillWidth: true
                }

                Label { text: "Batch / Micro Batch (-b/-ub):" }
                RowLayout {
                    SpinBox { id: optBatchSpin; from: 64; to: 8192; stepSize: 64; editable: true }
                    SpinBox { id: optUbatchSpin; from: 64; to: 8192; stepSize: 64; editable: true }
                }

                Label { text: "KV Cache Type (K / V):" }
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

                Label { text: "MoE Expert Offload:" }
                RowLayout {
                    CheckBox {
                        id: optCpuMoeCheck
                        text: "All experts \u2192 CPU"
                    }
                    Label { text: "or first N layers:" }
                    SpinBox {
                        id: optNCpuMoeSpin
                        from: 0; to: 999
                        editable: true
                        enabled: !optCpuMoeCheck.checked
                    }
                }

                Label { text: "Draft Model (--model-draft):" }
                TextField {
                    id: optDraftField
                    placeholderText: "path to small draft model (shared vocab required)"
                    Layout.fillWidth: true
                }

                Label {
                    text: "Draft (ngl / max / min):"
                    visible: optDraftField.text.trim().length > 0
                }
                RowLayout {
                    visible: optDraftField.text.trim().length > 0
                    SpinBox { id: optDraftNglSpin; from: 0; to: 999; editable: true }
                    SpinBox { id: optDraftMaxSpin; from: 0; to: 64; editable: true }
                    SpinBox { id: optDraftMinSpin; from: 0; to: 64; editable: true }
                }

                Label { text: "Extra CLI Flags:" }
                TextField {
                    id: optExtraField
                    placeholderText: "e.g. --rope-scaling linear"
                    Layout.fillWidth: true
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

        optCtxSpin.value = eff.ctx_size || 4096
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

        optJinjaCheck.checked = !!profile.jinja
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
        modelProfiles.delete_profile(editingModelPath)
        toast.show("Reset to global defaults for " + editingModelName, "info")
        optionsDialog.close()
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
        var profileJson = modelProfiles.get_effective_config_json(path, appSettings)
        var eff = JSON.parse(profileJson)
        console.log("Starting server with model profile:", path, profileJson)
        var ok = serverManager.start(bin, path, port, eff.ctx_size, eff.n_gpu_layers, eff.threads, profileJson)
        console.log("Server start result:", ok)
        if (!ok) {
            toast.show("Failed to start server with model: " + path.split('/').pop(), "error")
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
