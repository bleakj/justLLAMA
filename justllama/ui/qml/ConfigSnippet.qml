import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Rectangle {
    id: snippetRoot
    Layout.fillWidth: true
    Layout.preferredHeight: contentLayout.implicitHeight + Kirigami.Units.largeSpacing * 2
    color: Kirigami.Theme.alternateBackgroundColor || Qt.rgba(0.2, 0.2, 0.2, 1)
    radius: Kirigami.Units.cornerRadius
    border.color: Kirigami.Theme.borderColor || Qt.rgba(0.5, 0.5, 0.5, 1)
    border.width: 1

    required property string title
    required property string snippet
    signal copy()

    ColumnLayout {
        id: contentLayout
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true

            Label {
                text: snippetRoot.title
                font.bold: true
                font.pointSize: 11
                color: Kirigami.Theme.highlightColor || Qt.rgba(0.2, 0.5, 0.8, 1)
                Layout.fillWidth: true
            }

            Button {
                text: "Copy"
                icon.name: "edit-copy"
                onClicked: snippetRoot.copy()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: codeLabel.implicitHeight + Kirigami.Units.smallSpacing * 2
            color: Kirigami.Theme.backgroundColor || Qt.rgba(0.15, 0.15, 0.15, 1)
            radius: 4

            Label {
                id: codeLabel
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                text: snippetRoot.snippet
                font.family: "monospace"
                font.pointSize: 10
                color: Kirigami.Theme.textColor || Qt.rgba(1, 1, 1, 1)
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
            }
        }
    }
}
