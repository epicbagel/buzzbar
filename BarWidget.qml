import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Buzz unread on the bar, and a way into it. The list is a shell panel like
// every other widget's, anchored under the glyph.
BarWidget {
  id: root
  moduleName: "io.github.epicbagel.buzzbar"

  readonly property string barIcon: setting("icon", Model.defaultIcon())
  readonly property bool showCount: setting("showCount", true) !== false
  readonly property int pollSeconds: Math.max(5, Number(setting("pollSeconds", 15)))

  property var inbox: Model.emptyState()

  // Only DMs and mentions colour the bar. An unread channel is something to
  // read when you next look; being addressed by name is something to be told.
  readonly property bool wantsAttention: !root.opened
    && root.inbox.ok
    && root.inbox.attention > 0

  readonly property string pluginDir: {
    var url = decodeURIComponent(String(Qt.resolvedUrl(".")))
    var path = url.indexOf("file://") === 0 ? url.substring(7) : url
    return path.charAt(path.length - 1) === "/" ? path.substring(0, path.length - 1) : path
  }

  function applyState(state) {
    inbox = state || Model.emptyState()
  }

  // A bar surface is built per monitor, so this widget is live once per
  // screen. One instance runs the poll and hands the answer to its peers,
  // rather than every display reading the same cache on the same timer.
  function peers() {
    return bar && typeof bar.moduleWidgets === "function"
      ? bar.moduleWidgets(moduleName)
      : []
  }

  function publishState(state) {
    var live = peers()
    if (live.length === 0) {
      applyState(state)
      return
    }
    for (var i = 0; i < live.length; i++) {
      if (live[i] && live[i].applyState) live[i].applyState(state)
    }
  }

  function poll() {
    if (statusProcess.running) return
    var live = peers()
    if (live.length > 0 && live[0] !== root) return
    statusProcess.command = [root.pluginDir + "/buzzctl.py", "status"]
    statusProcess.running = true
  }

  readonly property bool opened: panelLoader.item
    ? panelLoader.item.opened === true
    : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true
    : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function injectPanel() {
    if (!panelLoader.item) return
    panelLoader.item.bar = root.bar
    panelLoader.item.anchorItem = button
    panelLoader.item.hostWidget = root
  }

  function openBuzz() {
    Quickshell.execDetached(["gtk-launch", "buzz.desktop"])
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  Timer {
    id: pollTimer
    interval: root.pollSeconds * 1000
    repeat: true
    triggeredOnStart: true
    running: true
    onTriggered: root.poll()
  }

  Process {
    id: statusProcess
    command: ["true"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) root.publishState(Model.parseState(text))
    }
  }

  IpcHandler {
    target: "io.github.epicbagel.buzzbar"

    function refresh(): void { root.poll() }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Model.barLabel(root.inbox, root.vertical, root.barIcon, root.showCount)
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: Model.barTooltip(root.inbox)

    // The glyph itself recoloured, nothing added beside it — the mechanism the
    // bar's own indicators use to say a thing wants you. Accent rather than
    // the inherited urgent: a colleague saying your name is not an alarm.
    active: root.wantsAttention
    activeColor: Color.accent

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.openBuzz()
      else root.toggle()
    }
  }
}
