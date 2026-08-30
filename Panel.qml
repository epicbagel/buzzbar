pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The inbox: every unread channel and DM, newest first, with the ones that
// want you at the top. A row is a jump into Buzz, not a reader — the app is
// the only thing that knows how to show a conversation.
Panel {
  id: root
  moduleName: "io.github.epicbagel.buzzbar"
  ipcTarget: "io.github.epicbagel.buzzbar"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var inbox: Model.emptyState()

  readonly property var barIdentity: hostWidget || root
  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property color contentDim: Qt.darker(contentForeground, 1.5)
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool busy: inboxProcess.running
  readonly property bool multiCommunity: root.inbox.communities > 1
  readonly property var rows: {
    var all = root.inbox.items || []
    var out = []
    for (var i = 0; i < all.length; i++) if (all[i].unread) out.push(all[i])
    return out
  }

  readonly property string helperPath: {
    var url = decodeURIComponent(String(Qt.resolvedUrl("buzzctl.py")))
    return url.indexOf("file://") === 0 ? url.substring(7) : url
  }

  function open() {
    root.controller.show()
    refresh()
  }

  function close() { root.controller.hide() }
  function toggle() { if (root.opened) root.close(); else root.open() }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  function refresh() {
    if (root.busy) return
    inboxProcess.command = [root.helperPath, "inbox"]
    inboxProcess.running = true
  }

  function applyInbox(state) {
    root.inbox = state || Model.emptyState()
    if (root.hostWidget && root.hostWidget.applyState) root.hostWidget.applyState(state)
  }

  // Hand off and get out of the way: opening the conversation is the whole
  // point of the row, so the panel closes rather than sitting over the window
  // the user just asked for.
  function openChannel(item) {
    var link = Model.channelLink(item)
    if (!link) return
    Quickshell.execDetached(["xdg-open", link])
    root.close()
  }

  function openBuzz() {
    Quickshell.execDetached(["gtk-launch", "buzz.desktop"])
    root.close()
  }

  Timer {
    id: autoRefreshTimer
    interval: 5000
    repeat: true
    running: root.opened && !root.busy
    onTriggered: root.refresh()
  }

  Process {
    id: inboxProcess
    command: ["true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) root.applyInbox(Model.parseState(text))
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(10)

        RowLayout {
          width: parent.width
          spacing: Style.space(8)

          Text {
            textFormat: Text.PlainText
            text: root.hostWidget && root.hostWidget.barIcon
              ? root.hostWidget.barIcon
              : Model.defaultIcon()
            color: root.inbox.attention > 0 ? Color.accent : root.contentForeground
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.heading
            Layout.alignment: Qt.AlignVCenter
          }

          ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space(1)

            Text {
              textFormat: Text.PlainText
              Layout.fillWidth: true
              text: "Buzz"
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.subtitle
              font.bold: true
            }

            Text {
              textFormat: Text.PlainText
              Layout.fillWidth: true
              text: Model.summaryText(root.inbox)
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }

          PanelActionButton {
            iconText: "󰏌"
            tooltipText: "Open Buzz"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            onClicked: root.openBuzz()
          }

          PanelActionButton {
            iconText: "󰑐"
            tooltipText: "Refresh"
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            enabled: !root.busy
            onClicked: root.refresh()
          }
        }

        PanelSeparator { width: parent.width }

        Text {
          textFormat: Text.PlainText
          width: parent.width
          visible: root.rows.length === 0
          text: root.inbox.known && root.inbox.ok
            ? "Nothing unread."
            : (root.inbox.error || "Reading the Buzz cache…")
          color: root.contentDim
          font.family: root.contentFontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.WordWrap
        }

        Column {
          id: list
          width: parent.width
          spacing: Style.space(2)

          Repeater {
            model: root.rows

            delegate: Rectangle {
              id: row
              required property var modelData

              // Width from the list, whose width comes from above; height from
              // the row's own content. Sizing off `parent` in both directions
              // would make the row's height depend on a layout that depends on
              // the row.
              width: list.width
              height: rowContent.implicitHeight + Style.space(12)
              radius: Style.space(6)
              color: rowArea.containsMouse
                ? Qt.rgba(root.contentForeground.r, root.contentForeground.g,
                          root.contentForeground.b, 0.08)
                : "transparent"

              RowLayout {
                id: rowContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Style.space(8)
                anchors.rightMargin: Style.space(8)
                spacing: Style.space(8)

                Text {
                  textFormat: Text.PlainText
                  text: "●"
                  color: row.modelData.attention ? Color.accent : root.contentDim
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                  Layout.alignment: Qt.AlignVCenter
                }

                Text {
                  textFormat: Text.PlainText
                  text: Model.kindGlyph(row.modelData)
                  color: root.contentDim
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.body
                  Layout.alignment: Qt.AlignVCenter
                }

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: 0

                  Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: row.modelData.name
                    color: row.modelData.attention ? Color.accent : root.contentForeground
                    font.family: root.contentFontFamily
                    font.pixelSize: Style.font.body
                    font.bold: row.modelData.attention
                    elide: Text.ElideRight
                  }

                  Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: Model.rowSubtitle(row.modelData, root.multiCommunity)
                    color: root.contentDim
                    font.family: root.contentFontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }

                Text {
                  textFormat: Text.PlainText
                  text: Model.whenText(row.modelData.lastMessageEpoch)
                  color: root.contentDim
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.caption
                  Layout.alignment: Qt.AlignVCenter
                }
              }

              MouseArea {
                id: rowArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openChannel(row.modelData)
              }
            }
          }
        }
      }
    }
  }
}
