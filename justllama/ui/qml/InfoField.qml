import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

// Reusable label/value + Copy row. Replaces the near-identical hand-rolled
// Rectangle info blocks in APIView (Base URL, API Key, Model Name, ComfyUI URL).
Rectangle {
    id: infoField

    property string label: ""
    property string value: ""
    property string copyValue: value
    property bool mono: true
    property bool valueMuted: false
    property bool copyEnabled: true
    signal copy()

    Layout.fillWidth: true
    Layout.preferredHeight: fieldRow.implicitHeight + Kirigami.Units.largeSpacing * 2
    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)
    radius: Kirigami.Units.cornerRadius
    border.color: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    border.width: 1

    RowLayout {
        id: fieldRow
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Label {
                text: infoField.label
                font.bold: true
                font.pointSize: 11
            }
            Label {
                text: infoField.value
                font.pointSize: 12
                font.family: infoField.mono ? "monospace" : Kirigami.Theme.defaultFont.family
                color: infoField.valueMuted
                    ? (Kirigami.Theme.disabledTextColor || Qt.rgba(0.5, 0.5, 0.5, 1))
                    : (Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1))
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }

        Button {
            text: "Copy"
            icon.name: "edit-copy"
            enabled: infoField.copyEnabled
            onClicked: infoField.copy()
        }
    }
}
