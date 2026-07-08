import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: memoryPage
    title: "Memory"

    property var memories: []
    property string selectedCategory: "all"
    property var statsObj: (function() {
        try { return JSON.parse(memoryManager.stats()) }
        catch (e) {
            console.error("Failed to parse memory stats:", e)
            return { short_term_count: 0, long_term_count: 0, enabled: false }
        }
    })()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        // Header
        RowLayout {
            Layout.fillWidth: true

            Label {
                text: "Memory Management"
                font.bold: true
                font.pointSize: 16
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "Enabled:"
                color: memoryManager.is_enabled() ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                font.bold: memoryManager.is_enabled()
            }
            Switch {
                checked: memoryManager.is_enabled()
                onCheckedChanged: memoryManager.set_enabled(checked)
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
                text: "🔄 Refresh"
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
                        Button {
                            text: "🗑️"
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
                text: "🧹 Clear Short-term"
                onClicked: memoryManager.clear_short_term()
            }

            Button {
                text: "🗑️ Clear Long-term"
                onClicked: {
                    memoryManager.clear_long_term()
                    refreshMemories()
                }
            }

            Button {
                text: "💥 Clear All"
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
            errorToast.show("Failed to refresh memories: " + e.message)
        }
    }

    function forgetMemory(id) {
        memoryManager.forget_memory(id)
        refreshMemories()
    }

    Component.onCompleted: refreshMemories()
    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
