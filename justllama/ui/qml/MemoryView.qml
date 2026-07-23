import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: memoryPage
    title: "Memory"

    property var memories: []
    property string selectedCategory: "all"
    property bool isMemoryEnabled: appSettings.get_bool("memory/enabled")
    property var statsObj: (function() {
        try { return JSON.parse(memoryManager.stats()) }
        catch (e) {
            console.error("Failed to parse memory stats:", e)
            return { short_term_count: 0, long_term_count: 0, enabled: false }
        }
    })()

    Connections {
        target: appSettings
        function onSettings_changed(key, value) {
            if (key === "memory/enabled") memoryPage.isMemoryEnabled = value
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        // Header
        SectionHeader {
            title: "Memory Management"

            Label {
                text: "Enabled:"
                color: memoryPage.isMemoryEnabled ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                font.bold: memoryPage.isMemoryEnabled
            }
            Switch {
                checked: memoryPage.isMemoryEnabled
                onCheckedChanged: {
                    memoryManager.set_enabled(checked)
                    appSettings.set_bool("memory/enabled", checked)
                }
            }
        }

        // Stats
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: RowLayout {
                Label {
                    text: "Short-term: " + statsObj.short_term_count + " messages"
                    color: Kirigami.Theme.disabledTextColor
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: "Long-term: " + statsObj.long_term_count + " memories"
                    color: Kirigami.Theme.disabledTextColor
                }
            }
        }

        // Category filter
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Filter:"
            }

            ComboBox {
                id: categoryFilter
                model: ["all", "fact", "preference", "conversation", "general"]
                onCurrentTextChanged: {
                    selectedCategory = currentText
                    refreshMemories()
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Refresh"
                icon.name: "view-refresh"
                onClicked: refreshMemories()
            }
        }

        // Memory list
        ListView {
            id: memoryList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: memories

            delegate: Kirigami.AbstractCard {
                width: memoryList.width
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Label {
                            text: modelData.category
                            font.bold: true
                            color: Kirigami.Theme.highlightColor
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: new Date(modelData.created_at * 1000).toLocaleString()
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: 10
                        }
                        ToolButton {
                            icon.name: "edit-delete"
                            display: AbstractButton.IconOnly
                            ToolTip.visible: hovered
                            ToolTip.text: "Forget"
                            onClicked: forgetMemory(modelData.id)
                        }
                    }

                    Label {
                        text: modelData.content
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    Label {
                        text: "Accessed " + modelData.access_count + " times"
                        color: Kirigami.Theme.disabledTextColor
                        font.pointSize: 10
                    }
                }
            }

            // Empty state
            Label {
                anchors.centerIn: parent
                visible: memoryList.count === 0
                text: "No memories stored.\nEnable memory and start chatting."
                horizontalAlignment: Text.AlignHCenter
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // Actions
        RowLayout {
            Layout.fillWidth: true

            Button {
                text: "Clear Short-term"
                icon.name: "edit-clear-history"
                onClicked: memoryManager.clear_short_term()
            }

            Button {
                text: "Clear Long-term"
                icon.name: "edit-delete"
                onClicked: {
                    memoryManager.clear_long_term()
                    refreshMemories()
                }
            }

            Button {
                text: "Clear All"
                icon.name: "edit-clear-all"
                onClicked: {
                    memoryManager.clear_all()
                    refreshMemories()
                }
            }
        }
    }

    function refreshMemories() {
        console.log("MemoryView: Refreshing memories...")
        try {
            statsObj = JSON.parse(memoryManager.stats())
            if (selectedCategory === "all") {
                memories = JSON.parse(memoryManager.list_all_memories())
            } else {
                memories = JSON.parse(memoryManager.list_memories_by_category(selectedCategory))
            }
        } catch (e) {
            console.error("Failed to refresh memories:", e)
            toast.show("Failed to refresh memories: " + e.message, "error")
        }
    }

    function forgetMemory(id) {
        memoryManager.forget_memory(id)
        refreshMemories()
    }

    Component.onCompleted: refreshMemories()
    Toast {
        id: toast
        anchors.fill: parent
    }
}
