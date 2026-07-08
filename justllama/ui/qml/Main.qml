import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    title: "justLLAMA"
    width: 1024
    height: 768
    visible: true

    // Reactive server status
    property bool serverRunning: false
    property int serverPort: 8080

    globalDrawer: Kirigami.GlobalDrawer {
        title: "justLLAMA"
        isMenu: true

        actions: [
            Kirigami.Action {
                text: "Chat"
                icon.name: "chat-bubbles"
                onTriggered: mainStack.currentIndex = 0
            },
            Kirigami.Action {
                text: "Models"
                icon.name: "folder-games"
                onTriggered: mainStack.currentIndex = 1
            },
            Kirigami.Action {
                text: "RAG"
                icon.name: "folder-documents"
                onTriggered: mainStack.currentIndex = 2
            },
            Kirigami.Action {
                text: "Memory"
                icon.name: "user-group-properties"
                onTriggered: mainStack.currentIndex = 3
            },
            Kirigami.Action {
                text: "Settings"
                icon.name: "configure"
                onTriggered: mainStack.currentIndex = 4
            },
            Kirigami.Action {
                text: "API"
                icon.name: "network-server"
                onTriggered: mainStack.currentIndex = 5
            }
        ]
    }

    contextDrawer: Kirigami.ContextDrawer {
        id: contextDrawer
    }

    // Top navigation toolbar
    header: ToolBar {
        RowLayout {
            anchors.fill: parent

            Repeater {
                model: ["Chat", "Models", "RAG", "Memory", "Settings", "API"]
                ToolButton {
                    required property string modelData
                    required property int index
                    text: modelData
                    checked: mainStack.currentIndex === index
                    onClicked: mainStack.currentIndex = index
                    Layout.fillWidth: true
                }
            }
        }
    }

    // Single navigation container — only one child visible at a time
    StackLayout {
        id: mainStack
        anchors.fill: parent
        currentIndex: 0

        ChatView { objectName: "chatView" }
        ModelBrowser {}
        RAGView {}
        MemoryView {}
        SettingsView {}
        APIView {}
    }

    // Server status tracking
    Connections {
        target: serverManager
        function onServer_started(port) {
            root.serverRunning = true
            root.serverPort = port
        }
        function onServer_stopped() {
            root.serverRunning = false
        }
        function onServer_error(msg) {
            console.log("Server error:", msg)
            errorToast.show("Server error: " + msg)
        }
    }

    // Initialize
    Component.onCompleted: {
        root.serverRunning = serverManager.is_running()
        root.serverPort = serverManager.port()
    }

    // Status bar
    footer: ToolBar {
        RowLayout {
            anchors.fill: parent

            Label {
                text: "justLLAMA"
                font.bold: true
                color: Kirigami.Theme.highlightColor
                Layout.preferredWidth: 100
            }

            Label {
                text: root.serverRunning
                    ? "Server running on port " + root.serverPort
                    : "Server stopped"
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                color: root.serverRunning ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
            }
        }
    }

    ErrorToast {
        id: errorToast
        anchors.fill: parent
    }
}
