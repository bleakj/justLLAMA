import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Item {
    id: root

    property int displayDuration: 4000
    property color bgColor: Kirigami.Theme.positiveBackgroundColor || Qt.rgba(0.2, 0.8, 0.2, 0.9)
    property color labelColor: Kirigami.Theme.textColor || "white"
    property real toastMaxWidth: 500

    anchors.fill: parent
    z: 999
    visible: false

    function show(msg, duration) {
        if (msg === undefined || msg.length === 0) return
        if (duration !== undefined) displayDuration = duration
        label.text = msg
        root.visible = true
        showAnim.start()
        hideTimer.interval = displayDuration
        hideTimer.restart()
    }

    function dismiss() {
        hideAnim.start()
    }

    Rectangle {
        id: bg
        anchors.horizontalCenter: parent.horizontalCenter
        y: -bg.height
        width: Math.min(label.implicitWidth + 32, root.toastMaxWidth)
        height: label.implicitHeight + 24
        radius: Kirigami.Units.cornerRadius || 6
        color: root.bgColor

        Label {
            id: label
            anchors.centerIn: parent
            width: parent.width - 16
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            color: root.labelColor
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
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
