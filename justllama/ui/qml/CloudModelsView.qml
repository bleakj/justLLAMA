import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: root
    title: "Cloud Models"

    // ── JS helpers ──
    function applyFilter(provider, searchField, enabledSwitch, listView) {
        var all = externalModels.get_cached_models(provider);
        var search = searchField.text.toLowerCase();
        var showEnabled = enabledSwitch.checked;
        var enabledList = showEnabled ? externalModels.get_enabled_models(provider) : [];

        var filtered = [];
        for (var i = 0; i < all.length; i++) {
            var m = all[i];
            if (search && m.toLowerCase().indexOf(search) === -1) continue;
            if (showEnabled && enabledList.indexOf(m) === -1) continue;
            filtered.push(m);
        }
        listView.model = filtered;
    }

    function isModelEnabled(provider, modelId) {
        var list = externalModels.get_enabled_models(provider);
        return list.indexOf(modelId) >= 0;
    }

    function refreshList(provider, searchField, enabledSwitch, listView) {
        listView.model = externalModels.get_cached_models(provider);
        root.applyFilter(provider, searchField, enabledSwitch, listView);
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TabBar {
            id: tabBar
            Layout.fillWidth: true

            TabButton { text: "NVIDIA" }
            TabButton { text: "OpenRouter" }
            TabButton { text: "Opencode" }
            TabButton { text: "Gemini" }
            TabButton { text: "Kilocode" }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // ── NVIDIA ──
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Layout.margins: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Fetch models"
                        onClicked: externalModels.refresh("nvidia")
                    }
                    Button {
                        text: "Clear"
                        onClicked: {
                            externalModels.clear_cache("nvidia");
                            root.refreshList("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia);
                        }
                    }
                    TextField {
                        id: searchNvidia
                        Layout.fillWidth: true
                        placeholderText: "Search models..."
                        onTextChanged: root.applyFilter("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia)
                    }
                    Switch {
                        id: enabledSwitchNvidia
                        text: "Enabled Only"
                        onToggled: root.applyFilter("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia)
                    }
                }

                ListView {
                    id: listNvidia
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: externalModels.get_cached_models("nvidia")

                    delegate: ItemDelegate {
                        width: parent ? parent.width : undefined
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pointSize: 11
                            }

                            Switch {
                                checked: root.isModelEnabled("nvidia", modelData)
                                onToggled: {
                                    externalModels.set_model_enabled("nvidia", modelData, checked);
                                    root.applyFilter("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia);
                                }
                            }

                            Button {
                                text: "S1"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 1"
                                onClicked: {
                                    var result = externalModels.select_model("nvidia", 1, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 1", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S2"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 2"
                                onClicked: {
                                    var result = externalModels.select_model("nvidia", 2, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 2", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S3"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 3"
                                onClicked: {
                                    var result = externalModels.select_model("nvidia", 3, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 3", "success");
                                    }
                                }
                            }
                        }
                    }
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "nvidia") {
                            root.refreshList("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia);
                            toast.show(ids.length + " NVIDIA models fetched", "success");
                        }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "nvidia") {
                            toast.show("NVIDIA: " + message, "error");
                        }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "nvidia") {
                            root.refreshList("nvidia", searchNvidia, enabledSwitchNvidia, listNvidia);
                        }
                    }
                }
            }

            // ── OpenRouter ──
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Layout.margins: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Fetch models"
                        onClicked: externalModels.refresh("openrouter")
                    }
                    Button {
                        text: "Clear"
                        onClicked: {
                            externalModels.clear_cache("openrouter");
                            root.refreshList("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter);
                        }
                    }
                    TextField {
                        id: searchOpenrouter
                        Layout.fillWidth: true
                        placeholderText: "Search models..."
                        onTextChanged: root.applyFilter("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter)
                    }
                    Switch {
                        id: enabledSwitchOpenrouter
                        text: "Enabled Only"
                        onToggled: root.applyFilter("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter)
                    }
                }

                ListView {
                    id: listOpenrouter
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: externalModels.get_cached_models("openrouter")

                    delegate: ItemDelegate {
                        width: parent ? parent.width : undefined
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pointSize: 11
                            }

                            Switch {
                                checked: root.isModelEnabled("openrouter", modelData)
                                onToggled: {
                                    externalModels.set_model_enabled("openrouter", modelData, checked);
                                    root.applyFilter("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter);
                                }
                            }

                            Button {
                                text: "S1"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 1"
                                onClicked: {
                                    var result = externalModels.select_model("openrouter", 1, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 1", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S2"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 2"
                                onClicked: {
                                    var result = externalModels.select_model("openrouter", 2, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 2", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S3"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 3"
                                onClicked: {
                                    var result = externalModels.select_model("openrouter", 3, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 3", "success");
                                    }
                                }
                            }
                        }
                    }
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "openrouter") {
                            root.refreshList("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter);
                            toast.show(ids.length + " OpenRouter models fetched", "success");
                        }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "openrouter") {
                            toast.show("OpenRouter: " + message, "error");
                        }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "openrouter") {
                            root.refreshList("openrouter", searchOpenrouter, enabledSwitchOpenrouter, listOpenrouter);
                        }
                    }
                }
            }

            // ── Opencode ──
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Layout.margins: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Fetch models"
                        onClicked: externalModels.refresh("opencode")
                    }
                    Button {
                        text: "Clear"
                        onClicked: {
                            externalModels.clear_cache("opencode");
                            root.refreshList("opencode", searchOpencode, enabledSwitchOpencode, listOpencode);
                        }
                    }
                    TextField {
                        id: searchOpencode
                        Layout.fillWidth: true
                        placeholderText: "Search models..."
                        onTextChanged: root.applyFilter("opencode", searchOpencode, enabledSwitchOpencode, listOpencode)
                    }
                    Switch {
                        id: enabledSwitchOpencode
                        text: "Enabled Only"
                        onToggled: root.applyFilter("opencode", searchOpencode, enabledSwitchOpencode, listOpencode)
                    }
                }

                ListView {
                    id: listOpencode
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: externalModels.get_cached_models("opencode")

                    delegate: ItemDelegate {
                        width: parent ? parent.width : undefined
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pointSize: 11
                            }

                            Switch {
                                checked: root.isModelEnabled("opencode", modelData)
                                onToggled: {
                                    externalModels.set_model_enabled("opencode", modelData, checked);
                                    root.applyFilter("opencode", searchOpencode, enabledSwitchOpencode, listOpencode);
                                }
                            }

                            Button {
                                text: "S1"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 1"
                                onClicked: {
                                    var result = externalModels.select_model("opencode", 1, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 1", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S2"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 2"
                                onClicked: {
                                    var result = externalModels.select_model("opencode", 2, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 2", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S3"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 3"
                                onClicked: {
                                    var result = externalModels.select_model("opencode", 3, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 3", "success");
                                    }
                                }
                            }
                        }
                    }
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "opencode") {
                            root.refreshList("opencode", searchOpencode, enabledSwitchOpencode, listOpencode);
                            toast.show(ids.length + " Opencode models fetched", "success");
                        }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "opencode") {
                            toast.show("Opencode: " + message, "error");
                        }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "opencode") {
                            root.refreshList("opencode", searchOpencode, enabledSwitchOpencode, listOpencode);
                        }
                    }
                }
            }

            // ── Gemini ──
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Layout.margins: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Fetch models"
                        onClicked: externalModels.refresh("gemini")
                    }
                    Button {
                        text: "Clear"
                        onClicked: {
                            externalModels.clear_cache("gemini");
                            root.refreshList("gemini", searchGemini, enabledSwitchGemini, listGemini);
                        }
                    }
                    TextField {
                        id: searchGemini
                        Layout.fillWidth: true
                        placeholderText: "Search models..."
                        onTextChanged: root.applyFilter("gemini", searchGemini, enabledSwitchGemini, listGemini)
                    }
                    Switch {
                        id: enabledSwitchGemini
                        text: "Enabled Only"
                        onToggled: root.applyFilter("gemini", searchGemini, enabledSwitchGemini, listGemini)
                    }
                }

                ListView {
                    id: listGemini
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: externalModels.get_cached_models("gemini")

                    delegate: ItemDelegate {
                        width: parent ? parent.width : undefined
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pointSize: 11
                            }

                            Switch {
                                checked: root.isModelEnabled("gemini", modelData)
                                onToggled: {
                                    externalModels.set_model_enabled("gemini", modelData, checked);
                                    root.applyFilter("gemini", searchGemini, enabledSwitchGemini, listGemini);
                                }
                            }

                            Button {
                                text: "S1"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 1"
                                onClicked: {
                                    var result = externalModels.select_model("gemini", 1, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 1", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S2"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 2"
                                onClicked: {
                                    var result = externalModels.select_model("gemini", 2, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 2", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S3"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 3"
                                onClicked: {
                                    var result = externalModels.select_model("gemini", 3, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 3", "success");
                                    }
                                }
                            }
                        }
                    }
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "gemini") {
                            root.refreshList("gemini", searchGemini, enabledSwitchGemini, listGemini);
                            toast.show(ids.length + " Gemini models fetched", "success");
                        }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "gemini") {
                            toast.show("Gemini: " + message, "error");
                        }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "gemini") {
                            root.refreshList("gemini", searchGemini, enabledSwitchGemini, listGemini);
                        }
                    }
                }
            }

            // ── Kilocode ──
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Layout.margins: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Button {
                        text: "Fetch models"
                        onClicked: externalModels.refresh("kilocode")
                    }
                    Button {
                        text: "Clear"
                        onClicked: {
                            externalModels.clear_cache("kilocode");
                            root.refreshList("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode);
                        }
                    }
                    TextField {
                        id: searchKilocode
                        Layout.fillWidth: true
                        placeholderText: "Search models..."
                        onTextChanged: root.applyFilter("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode)
                    }
                    Switch {
                        id: enabledSwitchKilocode
                        text: "Enabled Only"
                        onToggled: root.applyFilter("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode)
                    }
                }

                ListView {
                    id: listKilocode
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: externalModels.get_cached_models("kilocode")

                    delegate: ItemDelegate {
                        width: parent ? parent.width : undefined
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Label {
                                text: modelData
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                font.pointSize: 11
                            }

                            Switch {
                                checked: root.isModelEnabled("kilocode", modelData)
                                onToggled: {
                                    externalModels.set_model_enabled("kilocode", modelData, checked);
                                    root.applyFilter("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode);
                                }
                            }

                            Button {
                                text: "S1"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 1"
                                onClicked: {
                                    var result = externalModels.select_model("kilocode", 1, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 1", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S2"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 2"
                                onClicked: {
                                    var result = externalModels.select_model("kilocode", 2, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 2", "success");
                                    }
                                }
                            }
                            Button {
                                text: "S3"
                                implicitWidth: 36
                                ToolTip.visible: hovered
                                ToolTip.text: "Assign to Council Slot 3"
                                onClicked: {
                                    var result = externalModels.select_model("kilocode", 3, modelData);
                                    if (result !== "") {
                                        toast.show(result, "error");
                                    } else {
                                        toast.show("Assigned to Council Slot 3", "success");
                                    }
                                }
                            }
                        }
                    }
                }

                Connections {
                    target: externalModels
                    function onModels_fetched(provider, ids) {
                        if (provider === "kilocode") {
                            root.refreshList("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode);
                            toast.show(ids.length + " Kilocode models fetched", "success");
                        }
                    }
                    function onModels_error(provider, message) {
                        if (provider === "kilocode") {
                            toast.show("Kilocode: " + message, "error");
                        }
                    }
                    function onCache_cleared(provider) {
                        if (provider === "kilocode") {
                            root.refreshList("kilocode", searchKilocode, enabledSwitchKilocode, listKilocode);
                        }
                    }
                }
            }
        }
    }

    // ── Toast notifications ──
    Toast {
        id: toast
        anchors.fill: parent
    }
}
