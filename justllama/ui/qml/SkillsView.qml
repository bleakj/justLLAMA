import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: skillsPage
    title: "Skills / MCP"

    readonly property color safeBorderColor: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)

    // MCP server connection status map: command -> { status, message }
    property var serverStatuses: ({})

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

    // Branding header
    Rectangle {
        Layout.fillWidth: true
        height: 48
        radius: Kirigami.Units.cornerRadius
        color: Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.1)

        Label {
            anchors.centerIn: parent
            text: "🧩 Skills / MCP"
            font.bold: true
            font.pointSize: 16
            color: Kirigami.Theme.highlightColor
        }
    }

    // ── MCP Servers ──
    Kirigami.AbstractCard {
        Layout.fillWidth: true

        contentItem: ColumnLayout {
            id: mcpLayout
            spacing: Kirigami.Units.smallSpacing

            // List of objects: [{ command: "...", enabled: true, env: {}, name: "", description: "" }]
            property var mcpServersList: []

            // Curated catalog of MCP skills.
            property var skillsCatalog: []

            // Save MCP servers: persist full config object and the enabled command list.
            function saveServers(list) {
                appSettings.set_json_string("mcp/servers_config", JSON.stringify(list))
                var enabledList = list.filter(function (s) { return s.enabled }).map(function (s) { return s.command })
                appSettings.set_list("mcp/servers", enabledList)
            }

            Label {
                text: "MCP Servers"
                font.bold: true
                font.pointSize: 14
            }

            Label {
                text: "Enter the exact command to run the server, e.g., <code>npx -y @modelcontextprotocol/server-everything</code>"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                font.pointSize: 11
            }

            // Catalog selection row
            RowLayout {
                id: catalogRow
                property var mcpLayoutRef: parent
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                ComboBox {
                    id: skillsCatalogCombo
                    Layout.fillWidth: true
                    textRole: "name"
                    model: catalogRow.mcpLayoutRef.skillsCatalog

                    Label {
                        anchors.centerIn: parent
                        text: "(No skills in catalog)"
                        visible: skillsCatalogCombo.count === 0
                        color: Kirigami.Theme.disabledTextColor
                    }
                }

                Button {
                    text: "Add from Catalog"
                    Layout.preferredWidth: 140
                    enabled: skillsCatalogCombo.currentIndex >= 0 && skillsCatalogCombo.count > 0
                    onClicked: {
                        var catalog = catalogRow.mcpLayoutRef.skillsCatalog
                        var idx = skillsCatalogCombo.currentIndex
                        if (idx < 0 || idx >= catalog.length) return
                        var selected = catalog[idx]

                        // Avoid duplicates by command
                        if (catalogRow.mcpLayoutRef.mcpServersList.some(function (s) { return (s.command || "") === selected.command })) {
                            errorToast.show("Server '" + selected.name + "' is already added.")
                            return
                        }

                        var newServer = {
                            "command": selected.command,
                            "enabled": false,
                            "env": {},
                            "name": selected.name,
                            "description": selected.description
                        }
                        var newList = catalogRow.mcpLayoutRef.mcpServersList.slice()
                        newList.push(newServer)
                        catalogRow.mcpLayoutRef.mcpServersList = newList
                        catalogRow.mcpLayoutRef.saveServers(newList)
                    }
                }
            }

            Repeater {
                model: mcpLayout.mcpServersList

                delegate: RowLayout {
                    id: delegateRow
                    property var mcpLayoutRef: parent
                    Layout.fillWidth: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 120
                        spacing: 2

                        Label {
                            text: modelData.name || ""
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            visible: modelData.name !== undefined && modelData.name !== null && modelData.name !== ""
                        }

                        Label {
                            text: modelData.description || ""
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: 9
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            visible: modelData.description !== undefined && modelData.description !== null && modelData.description !== ""
                        }

                        TextField {
                            Layout.fillWidth: true
                            text: modelData.command
                            placeholderText: "MCP server command..."
                            readOnly: true
                        }
                    }

                    Switch {
                        Layout.preferredWidth: 60
                        checked: modelData.enabled === true
                        onClicked: {
                            var newList = delegateRow.mcpLayoutRef.mcpServersList.slice()
                            newList[index].enabled = checked
                            delegateRow.mcpLayoutRef.mcpServersList = newList
                            delegateRow.mcpLayoutRef.saveServers(newList)
                        }
                    }

                    Label {
                        Layout.preferredWidth: 200
                        Layout.maximumWidth: 200
                        wrapMode: Text.Wrap
                        font.pointSize: 10
                        elide: Text.ElideRight
                        property var status: serverStatuses[modelData.command] || {}
                        text: status.status === "connected"
                            ? "Connected"
                            : (status.status === "error" ? "Error: " + (status.message || "") : "")
                        color: status.status === "connected"
                            ? Kirigami.Theme.positiveTextColor
                            : (status.status === "error" ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.disabledTextColor)
                    }

                    Button {
                        text: "Edit"
                        icon.name: "configure"
                        Layout.preferredWidth: 100
                        onClicked: {
                            mcpServerDialog.serverIndex = index
                            mcpServerDialog.serverCommand = modelData.command
                            var envObj = modelData.env || {}
                            mcpServerDialog.envText = JSON.stringify(envObj, null, 4)
                            mcpServerDialog.open()
                        }
                    }

                    Button {
                        text: "Remove"
                        icon.name: "edit-delete"
                        Layout.preferredWidth: 100
                        onClicked: {
                            var newList = delegateRow.mcpLayoutRef.mcpServersList.slice()
                            newList.splice(index, 1)
                            delegateRow.mcpLayoutRef.mcpServersList = newList
                            delegateRow.mcpLayoutRef.saveServers(newList)
                        }
                    }
                }
            }

            Button {
                text: "Add MCP Server..."
                icon.name: "list-add"
                Layout.fillWidth: true
                onClicked: {
                    mcpServerDialog.serverIndex = -1
                    mcpServerDialog.serverCommand = ""
                    mcpServerDialog.envText = ""
                    mcpServerDialog.open()
                }
            }

            Component.onCompleted: {
                // Load curated catalog (always, independent of saved servers).
                var catalogRaw = appSettings.get_skills_catalog()
                if (catalogRaw && catalogRaw.trim().length > 0) {
                    try {
                        skillsCatalog = JSON.parse(catalogRaw)
                    } catch (e) {
                        console.warn("Failed to parse skills catalog:", e)
                        skillsCatalog = []
                    }
                }

                // Load saved server config.
                var raw = appSettings.get_json_string("mcp/servers_config")
                if (raw && raw.trim().length > 0) {
                    try {
                        mcpServersList = JSON.parse(raw)
                        return
                    } catch (e) {
                        console.warn("Failed to parse mcp/servers_config JSON:", e)
                    }
                }
                // Migrate existing flat string list to objects.
                var legacy = appSettings.get_list("mcp/servers")
                if (legacy && legacy.length > 0) {
                    mcpServersList = legacy.map(function (cmd) {
                        return { command: cmd, enabled: true }
                    })
                }
            }
        }
    }

    Kirigami.AbstractCard {
        Layout.fillWidth: true

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            Label {
                text: "Native Agent Skills"
                font.bold: true
                font.pointSize: 14
            }

            Label {
                text: "Toggle built-in skills that extend the LLM with local Python tools."
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Repeater {
                id: skillsRepeater
                model: skillsManager.get_skills_list()

                delegate: RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Label {
                            text: modelData.name
                            font.bold: true
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Label {
                            text: modelData.description
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            color: Kirigami.Theme.disabledTextColor
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }

                    Switch {
                        checked: modelData.enabled
                        onToggled: skillsManager.set_enabled(modelData.id, checked)
                    }

                    ToolButton {
                        icon.name: "document-edit"
                        visible: modelData.is_custom === true
                        onClicked: {
                            customSkillSheet.editingFilename = modelData.filename
                            customSkillSheet.filenameField = modelData.filename
                            customSkillSheet.codeArea = skillsManager.read_user_skill(modelData.filename)
                            customSkillSheet.open()
                        }
                    }
                    ToolButton {
                        icon.name: "edit-delete"
                        visible: modelData.is_custom === true
                        onClicked: {
                            skillsManager.delete_user_skill(modelData.filename)
                            skillsRepeater.model = skillsManager.get_skills_list()
                        }
                    }
                }
            }

            Label {
                visible: skillsRepeater.count === 0
                text: "No native skills registered."
                color: Kirigami.Theme.disabledTextColor
                font.italic: true
            }

            Button {
                text: "Create Custom Skill"
                icon.name: "list-add"
                Layout.fillWidth: true
                onClicked: {
                    customSkillSheet.editingFilename = ""
                    customSkillSheet.filenameField = ""
                    customSkillSheet.codeArea = skillsManager.get_skill_template()
                    customSkillSheet.open()
                }
            }
        }
    }
    }

    // MCP server connection status updates
    Connections {
        target: mcpManager
        function onServer_status_changed(cmd, status, msg) {
            var map = serverStatuses
            map[cmd] = { status: status, message: msg }
            serverStatuses = map
        }
    }

    // Custom skill editor dialog
    Dialog {
        id: customSkillSheet
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(600, parent?.width ?? 600)

        property string editingFilename: ""
        property alias filenameField: filenameInput.text
        property alias codeArea: codeEditor.text

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            Label {
                text: customSkillSheet.editingFilename ? "Edit Custom Skill" : "Create Custom Skill"
                font.bold: true
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 1.2
            }
            Kirigami.Separator {
                Layout.fillWidth: true
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            Label { text: "Filename:"; font.bold: true }
            TextField {
                id: filenameInput
                Layout.fillWidth: true
                placeholderText: "my_skill.py"
                readOnly: customSkillSheet.editingFilename !== ""
            }

            Label { text: "Code:"; font.bold: true }
            TextArea {
                id: codeEditor
                Layout.fillWidth: true
                Layout.preferredHeight: 400
                font.family: "monospace"
                wrapMode: TextArea.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: customSkillSheet.close()
                }
                Button {
                    text: "Save"
                    icon.name: "document-save"
                    onClicked: {
                        var fn = filenameInput.text.trim()
                        var code = codeEditor.text
                        if (!fn.endsWith(".py")) { fn += ".py" }
                        var ok = skillsManager.save_user_skill(fn, code)
                        if (ok) {
                            skillsRepeater.model = skillsManager.get_skills_list()
                            customSkillSheet.close()
                        } else {
                            errorToast.show("Failed to save skill. Check the filename.")
                        }
                    }
                }
            }
        }
    }

    // MCP Server Add/Edit dialog
    Dialog {
        id: mcpServerDialog
        property var mcpLayoutRef: mcpLayout
        modal: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(500, parent?.width ?? 500)

        property int serverIndex: -1
        property alias serverCommand: cmdInput.text
        property alias envText: envInput.text

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            Label {
                text: mcpServerDialog.serverIndex >= 0 ? "Edit MCP Server" : "Add MCP Server"
                font.bold: true
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 1.2
            }
            Kirigami.Separator {
                Layout.fillWidth: true
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            Label {
                text: "Command:"
                font.bold: true
            }
            TextField {
                id: cmdInput
                Layout.fillWidth: true
                placeholderText: "e.g., npx -y @modelcontextprotocol/server-postgres"
            }

            Label {
                text: "Environment Variables (JSON dictionary):"
                font.bold: true
            }
            TextArea {
                id: envInput
                Layout.fillWidth: true
                Layout.preferredHeight: 150
                font.family: "monospace"
                placeholderText: '{\n    "VAR_NAME": "value"\n}'
                wrapMode: TextArea.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: "Cancel"
                    onClicked: mcpServerDialog.close()
                }
                Button {
                    text: "Save"
                    icon.name: "document-save"
                    enabled: cmdInput.text.trim() !== ""
                    onClicked: {
                        var cmdText = cmdInput.text.trim();
                        var jsonText = envInput.text.trim();
                        var envObj = {};
                        if (jsonText !== "") {
                            try {
                                envObj = JSON.parse(jsonText);
                                if (typeof envObj !== "object" || Array.isArray(envObj)) {
                                    throw new Error("Must be a JSON object");
                                }
                            } catch (e) {
                                errorToast.show("Invalid JSON: " + e.message);
                                return;
                            }
                        }

                        var newList = mcpServerDialog.mcpLayoutRef.mcpServersList.slice();
                        if (mcpServerDialog.serverIndex >= 0 && mcpServerDialog.serverIndex < newList.length) {
                            // Edit existing
                            newList[mcpServerDialog.serverIndex].command = cmdText;
                            newList[mcpServerDialog.serverIndex].env = envObj;
                        } else {
                            // Add new
                            newList.push({ command: cmdText, enabled: true, env: envObj });
                        }
                        mcpServerDialog.mcpLayoutRef.mcpServersList = newList;
                        mcpServerDialog.mcpLayoutRef.saveServers(newList);
                        mcpServerDialog.close();
                    }
                }
            }
        }
    }

    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
