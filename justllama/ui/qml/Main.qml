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

    // Theme color overrides — when themeManager returns "" we fall back to Kirigami defaults
    property bool hasCustomTheme: themeManager.current_theme() !== "default"
    property color themeBg: hasCustomTheme && themeManager.color("backgroundColor") !== "" ? themeManager.color("backgroundColor") : Kirigami.Theme.backgroundColor
    property color themeAltBg: hasCustomTheme && themeManager.color("alternateBackgroundColor") !== "" ? themeManager.color("alternateBackgroundColor") : Kirigami.Theme.alternateBackgroundColor
    property color themeText: hasCustomTheme && themeManager.color("textColor") !== "" ? themeManager.color("textColor") : Kirigami.Theme.textColor
    property color themeHighlight: hasCustomTheme && themeManager.color("highlightColor") !== "" ? themeManager.color("highlightColor") : Kirigami.Theme.highlightColor
    property color themeHighlightText: hasCustomTheme && themeManager.color("highlightedTextColor") !== "" ? themeManager.color("highlightedTextColor") : Kirigami.Theme.highlightedTextColor
    property color themePositive: hasCustomTheme && themeManager.color("positiveTextColor") !== "" ? themeManager.color("positiveTextColor") : Kirigami.Theme.positiveTextColor
    property color themeNegative: hasCustomTheme && themeManager.color("negativeTextColor") !== "" ? themeManager.color("negativeTextColor") : Kirigami.Theme.negativeTextColor
    property color themeDisabled: hasCustomTheme && themeManager.color("disabledTextColor") !== "" ? themeManager.color("disabledTextColor") : Kirigami.Theme.disabledTextColor

    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.backgroundColor: themeBg
    Kirigami.Theme.alternateBackgroundColor: themeAltBg
    Kirigami.Theme.textColor: themeText
    Kirigami.Theme.highlightColor: themeHighlight
    Kirigami.Theme.highlightedTextColor: themeHighlightText
    Kirigami.Theme.positiveTextColor: themePositive
    Kirigami.Theme.negativeTextColor: themeNegative
    Kirigami.Theme.disabledTextColor: themeDisabled

    // Refresh theme colors when theme changes
    Connections {
        target: themeManager
        function onColors_changed() {
            // Force property re-evaluation by toggling hasCustomTheme
            hasCustomTheme = themeManager.current_theme() !== "default"
        }
    }

    // Navigation destinations — order matches the StackLayout children below.
    readonly property var navDestinations: [
        { label: "Chat", icon: "chat-bubbles" },
        { label: "Models", icon: "folder-games" },
        { label: "Cloud Models", icon: "folder-cloud" },
        { label: "RAG", icon: "folder-documents" },
        { label: "Memory", icon: "user-group-properties" },
        { label: "Settings", icon: "configure" },
        { label: "Images", icon: "image-x-generic" },
        { label: "Videos", icon: "video-display" },
        { label: "API", icon: "network-server" },
        { label: "Skills / MCP", icon: "configure-plugins" }
    ]

    // Top navigation toolbar — icon-only buttons with tooltips, plus the
    // active section title (compensates for the missing page-title chrome).
    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            Repeater {
                model: root.navDestinations
                ToolButton {
                    required property var modelData
                    required property int index
                    display: AbstractButton.IconOnly
                    icon.name: modelData.icon
                    checked: mainStack.currentIndex === index
                    onClicked: mainStack.currentIndex = index
                    ToolTip.visible: hovered
                    ToolTip.text: modelData.label
                }
            }

            Kirigami.Separator {
                Layout.fillHeight: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.bottomMargin: Kirigami.Units.smallSpacing
            }

            Item { Layout.fillWidth: true }

            Label {
                text: root.navDestinations[mainStack.currentIndex].label
                font.bold: true
                color: Kirigami.Theme.highlightColor
                elide: Text.ElideRight
                Layout.rightMargin: Kirigami.Units.smallSpacing
            }
        }
    }
    // Single navigation container — only one child visible at a time
    StackLayout {
        id: mainStack
        objectName: "mainStack"
        anchors.fill: parent
        currentIndex: 0

        ChatView { objectName: "chatView" }
        ModelBrowser { objectName: "modelBrowser" }
        CloudModelsView {}
        RAGView {}
        MemoryView {}
        SettingsView {}
        ImageGenView {}
        VideoGenView {}
        APIView {}
        SkillsView { objectName: "skillsView" }
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
            toast.show("Server error: " + msg, "error")
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

    Toast {
        id: toast
        anchors.fill: parent
    }

}
