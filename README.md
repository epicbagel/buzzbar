# Buzzbar

Unread across your [Buzz](https://github.com/block/buzz) channels and DMs on the
Omarchy bar, and a way to jump straight into the one you want.

## What it does

- The glyph turns the **theme accent** when a DM or a mention is waiting. An ordinary unread channel does not colour the bar: it is
  something to read when you next look, not something to be told about.
- The count beside the glyph counts **DMs and mentions**, not everything unread.
- **Left-click** opens a panel listing everything unread; clicking a row
  deep-links into that channel in Buzz.
- **Right-click** opens Buzz.

## How it reads your inbox

Buzz keeps what this needs in the desktop app's WebKit localStorage:

| Key | What it gives |
| --- | --- |
| `buzz-communities` | the relay + pubkey for each workspace |
| `buzz-channels.v1:<relay>:<pubkey>` | channels and DMs, each with `lastMessageAt` |
| `buzz.channel-read-state.v2:<pubkey>` | your read mark per channel |
| `buzz-thread-activity.v1:<relay>:<pubkey>` | recent events, used to spot `p`-tag mentions |

A channel is unread when its last message is newer than your read mark. It wants
attention when it is a DM, or when a recent event tags you.

The database is opened **read-only** (`file:…?mode=ro`) and the app stays the
only writer. Nothing here needs your nostr key, and nothing here touches the
network — a poll is a few milliseconds against a local file.

Two consequences worth knowing:

- These are the app's own private cache keys, not a published interface. They
  are versioned (`.v1`, `.v2`), so a Buzz release that changes them makes this
  widget go quiet rather than go wrong — but it will need updating.
- The counts are as fresh as the app's last write. If Buzz is not running, the
  tooltip says how long ago it last ran rather than pretending the list is live.

## Settings

In the widget's entry in `~/.config/omarchy/shell.json`:

```jsonc
{
  "id": "io.github.epicbagel.buzzbar",
  "icon": "",           // any Nerd Font glyph
  "showCount": true,     // false hides the number; the colour still changes
  "pollSeconds": 15      // 5–300
}
```

## DM names

Buzz does not cache participant display names locally, so DM rows fall back to a
short pubkey (`3f9a1c04`). To get real names, write a
`pubkey -> name` map to:

```
~/.local/state/omarchy/buzzbar/names.json
```

```json
{ "3f9a1c04e5b2d7a8f10c6b4e9d2a5c8f3b7e1d049a6c2f8b5e3d7a1c9f4b6e2d0": "Sarah Chen" }
```

Anything in that file wins. Resolving names automatically would mean asking the
relay via `buzz users get`, which needs `BUZZ_PRIVATE_KEY` in the plugin's
environment — a nostr private key where a bar widget can read it. That is why
this reads a file you control instead.

## Requirements

- Buzz desktop, run at least once on this machine

## Testing

```bash
python3 -m unittest test_buzzctl     # 11 tests, no Buzz install needed
./buzzctl.py inbox | jq              # what the panel lists
./buzzctl.py status                  # what the bar polls
```

## Install

```bash
omarchy plugin add https://github.com/epicbagel/buzzbar.git --enable
```

Or add it to a bar section in `~/.config/omarchy/shell.json` by hand:

```jsonc
{ "id": "io.github.epicbagel.buzzbar" }
```

The file hot-reloads on save.

## Remove

```bash
omarchy plugin disable io.github.epicbagel.buzzbar
omarchy plugin remove io.github.epicbagel.buzzbar
```

Nothing outside the plugin's own cache is touched, and no message, channel or key is ever written — the plugin only ever reads
Buzz's cache.

## License

MIT
