import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Item {
    id: root

    property int displayDuration: 4000
    property real toastMaxWidth: 500
    property string toastType: "error" // "error" | "success" | "info"

    readonly property color errorBg: Kirigami.Theme.negativeBackgroundColor || Qt.rgba(0.8, 0.2, 0.2, 0.95)
    readonly property color successBg: Kirigami.Theme.positiveBackgroundColor || Qt.rgba(0.2, 0.7, 0.3, 0.95)
    readonly property color infoBg: Kirigami.Theme.neutralBackgroundColor || Qt.rgba(0.3, 0.5, 0.8, 0.95)
    readonly property color labelColor: Kirigami.Theme.textColor || "white"

    anchors.fill: parent
    z: 999
    visible: false

    function show(msg, type, duration) {
        if (msg === undefined || msg.length === 0) return
        if (type !== undefined) toastType = type
        if (duration !== undefined) displayDuration = duration
        label.text = msg
        root.visible = true
        showAnim.start()
        hideTimer.interval = displayDuration
        hideTimer.restart()
        progressAnim.restart()
    }

    function dismiss() {
        hideAnim.start()
        hideTimer.stop()
    }

    Rectangle {
        id: bg
        anchors.horizontalCenter: parent.horizontalCenter
        y: -bg.height
        width: Math.min(label.implicitWidth + 56, root.toastMaxWidth)
        height: label.implicitHeight + 28
        radius: Kirigami.Units.cornerRadius || 6
        color: {
            if (root.toastType === "success") return root.successBg
            if (root.toastType === "info") return root.infoBg
            return root.errorBg
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            Kirigami.Icon {
                source: {
                    if (root.toastType === "success") return "dialog-positive"
                    if (root.toastType === "info") return "information"
                    return "dialog-error"
                }
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
            }

            // Message
            Label {
                id: label
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: root.labelColor
                font.bold: true
            }

            // Progress bar
            Rectangle {
                Layout.preferredWidth: 60
                Layout.preferredHeight: 6
                Layout.alignment: Qt.AlignVCenter
                radius: 3
                color: Qt.rgba(0, 0, 0, 0.2)

                Rectangle {
                    id: progressFill
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: parent.width
                    radius: 3
                    color: Qt.rgba(1, 1, 1, 0.7)

                    NumberAnimation on width {
                        id: progressAnim
                        from: parent.width
                        to: 0
                        duration: root.displayDuration
                        easing.type: Easing.Linear
                    }
                }
            }

            // Close button
            Button {
                text: "×"
                flat: true
                font.bold: true
                font.pointSize: 14
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                onClicked: root.dismiss()
            }
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.RightButton | Qt.MiddleButton
            onClicked: root.dismiss()
        }
    }

    NumberAnimation {
        id: showAnim
        target: bg; property: "y"
        from: -bg.height; to: 10
        duration: 300
        easing.type: Easing.OutCubic
    }

    NumberAnimation {
        id: hideAnim
        target: bg; property: "y"
        from: 10; to: -bg.height
        duration: 300
        easing.type: Easing.InCubic
        onFinished: root.visible = false
    }

    Timer {
        id: hideTimer
        interval: 4000
        onTriggered: hideAnim.start()
    }
}
