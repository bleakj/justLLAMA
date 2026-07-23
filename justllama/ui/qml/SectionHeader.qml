import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

// Reusable in-content page header. Main.qml uses a plain StackLayout, so
// Kirigami's page-title chrome is never shown; this provides a consistent
// bold title with an optional right-aligned trailing slot for controls.
//
// Any child controls declared inside a SectionHeader are appended after the
// title + flexible spacer, so they render right-aligned. Example:
//   SectionHeader {
//       title: "Local Models"
//       Button { text: "Refresh" }
//   }
RowLayout {
    id: sectionHeader

    property string title: ""

    Layout.fillWidth: true
    spacing: Kirigami.Units.smallSpacing

    Label {
        text: sectionHeader.title
        font.bold: true
        font.pointSize: 18
        color: Kirigami.Theme.highlightColor
        elide: Text.ElideRight
    }

    // Pushes any trailing controls to the right edge.
    Item { Layout.fillWidth: true }
}
