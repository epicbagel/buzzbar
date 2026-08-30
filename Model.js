.pragma library

var DEFAULT_ICON = ""   // nf-fa-comment, solid

function defaultIcon() {
  return DEFAULT_ICON
}

function cleanText(value) {
  return String(value === undefined || value === null ? "" : value).trim()
}

function emptyState() {
  return {
    known: false,
    ok: false,
    error: "",
    attention: 0,
    unread: 0,
    communities: 0,
    cacheAgeSeconds: -1,
    items: []
  }
}

function normalizeItem(value) {
  var source = value || {}
  return {
    id: cleanText(source.id),
    name: cleanText(source.name) || "channel",
    kind: source.kind === "dm" ? "dm" : "stream",
    community: cleanText(source.community),
    unread: source.unread === true,
    attention: source.attention === true,
    mentions: Math.max(0, Number(source.mentions || 0)),
    lastMessageEpoch: Number(source.lastMessageEpoch || 0)
  }
}

function parseState(raw) {
  try {
    var parsed = JSON.parse(String(raw || "{}"))
    var items = []
    var source = Array.isArray(parsed.items) ? parsed.items : []
    for (var i = 0; i < source.length; i++) {
      var item = normalizeItem(source[i])
      if (item.id) items.push(item)
    }
    return {
      known: true,
      ok: parsed.ok === true,
      error: cleanText(parsed.error),
      attention: Math.max(0, Number(parsed.attention || 0)),
      unread: Math.max(0, Number(parsed.unread || 0)),
      communities: Math.max(0, Number(parsed.communities || 0)),
      cacheAgeSeconds: Number(parsed.cacheAgeSeconds === undefined ? -1 : parsed.cacheAgeSeconds),
      items: items
    }
  } catch (error) {
    return emptyState()
  }
}

// The bar label. The count is of things wanting attention, not of everything
// unread: a number that ticks up for every message in every busy channel is a
// number you stop reading.
function barLabel(state, vertical, icon, showCount) {
  var glyph = cleanText(icon) || DEFAULT_ICON
  var count = state ? Math.max(0, Number(state.attention || 0)) : 0
  if (!state || !state.known || count === 0) return glyph
  if (showCount === false) return glyph
  return vertical ? glyph + "\n" + count : glyph + " " + count
}

function barTooltip(state) {
  if (!state || !state.known) return "Buzz"
  if (!state.ok) return "Buzz · " + (state.error || "cache unavailable")
  var parts = []
  if (state.attention === 1) parts.push("1 needs you")
  else if (state.attention > 1) parts.push(state.attention + " need you")
  var quiet = Math.max(0, state.unread - state.attention)
  if (quiet === 1) parts.push("1 other unread")
  else if (quiet > 1) parts.push(quiet + " other unread")
  // Minutes old is normal; hours old means Buzz is not running and the
  // counts are a memory rather than an inbox, which the bar should admit.
  if (state.cacheAgeSeconds > 3600) {
    var hours = Math.floor(state.cacheAgeSeconds / 3600)
    parts.push(hours >= 48 ? "Buzz last ran " + Math.floor(hours / 24) + " days ago"
                           : "Buzz last ran " + hours + "h ago")
  }
  if (parts.length === 0) return "Buzz · all caught up"
  return "Buzz · " + parts.join(" · ")
}

// ---------------------------------------------------------------- panel text

function summaryText(state) {
  if (!state || !state.known) return "Reading the Buzz cache…"
  if (!state.ok) return state.error || "Buzz cache unavailable"
  if (state.cacheAgeSeconds > 3600) {
    var hours = Math.floor(state.cacheAgeSeconds / 3600)
    return hours >= 48 ? "Buzz last ran " + Math.floor(hours / 24) + " days ago"
                       : "Buzz last ran " + hours + "h ago"
  }
  if (state.unread === 0) return "All caught up"
  var parts = []
  if (state.attention > 0) parts.push(state.attention + " needing you")
  var quiet = Math.max(0, state.unread - state.attention)
  if (quiet > 0) parts.push(quiet + " other unread")
  return parts.join(" · ")
}

// Buzz is the only thing that knows how to show a channel; this is a jump, not
// a second reader. Path segments, not a query string — the app rejects a
// channel link that carries one.
function channelLink(item) {
  var id = cleanText((item || {}).id)
  return id ? "buzz://channel/" + encodeURIComponent(id) : ""
}

function pad(value) {
  return value < 10 ? "0" + value : String(value)
}

var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

function whenText(epochSeconds) {
  var seconds = Number(epochSeconds || 0)
  if (!seconds) return ""
  var date = new Date(seconds * 1000)
  var now = new Date()
  if (date.getFullYear() === now.getFullYear()
      && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate())
    return pad(date.getHours()) + ":" + pad(date.getMinutes())
  if (now.getTime() - date.getTime() < 6 * 24 * 3600 * 1000) return DAYS[date.getDay()]
  return date.getDate() + " " + MONTHS[date.getMonth()]
}

function kindGlyph(item) {
  return (item || {}).kind === "dm" ? "󰀄" : "󰐣"   // md-account / md-pound
}

function rowSubtitle(item, showCommunity) {
  var value = item || {}
  var parts = []
  if (value.mentions === 1) parts.push("1 mention")
  else if (value.mentions > 1) parts.push(value.mentions + " mentions")
  if (showCommunity && value.community) parts.push(value.community)
  return parts.join("  ·  ")
}
