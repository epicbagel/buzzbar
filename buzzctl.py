#!/usr/bin/env python3
"""Read-only inbox view over the Buzz desktop app's local cache.

Buzz keeps everything this needs in its WebKit localStorage: the community
list, the per-community channel list (each channel carrying `lastMessageAt`),
the per-channel read marks, and a rolling window of recent activity events. A
channel is unread when its last message is newer than its read mark; it wants
attention when it is a DM, or when one of those recent events tags this user.

Nothing here writes to the app's storage, and nothing here needs the user's
nostr key: the database is opened read-only and the app remains the only
writer.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

APP_ID = "xyz.block.buzz.app"
STORAGE_RELATIVE = f".local/share/{APP_ID}/localstorage/tauri_localhost_0.localstorage"
NAME_CACHE_RELATIVE = "omarchy/buzzbar/names.json"
SHORT_PUBKEY_CHARS = 8
# The activity cache is a rolling window, so a mention that has scrolled out of
# it is no longer visible to us. That is the app's own horizon, not a limit we
# impose, and an unseen mention older than the window is not the thing a bar is
# for.
ACTIVITY_KEY = "buzz-thread-activity.v1"


class BuzzError(RuntimeError):
    pass


def storage_path() -> str:
    return os.path.join(os.path.expanduser("~"), STORAGE_RELATIVE)


def state_directory() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(os.path.abspath(os.path.expanduser(base)), "omarchy", "buzzbar")


def name_cache() -> dict[str, str]:
    """pubkey -> display name, filled in by whatever resolves names."""
    path = os.path.join(state_directory(), "names.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v.strip()}


def open_storage() -> sqlite3.Connection:
    path = storage_path()
    if not os.path.isfile(path):
        raise BuzzError("Buzz has not stored anything on this machine yet")
    try:
        # Read-only, so a poll can never disturb the app that owns this file.
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error as error:
        raise BuzzError("Could not read the Buzz cache") from error


def read_item(connection: sqlite3.Connection, key: str) -> str | None:
    try:
        row = connection.execute("SELECT value FROM ItemTable WHERE key=?", (key,)).fetchone()
    except sqlite3.Error as error:
        raise BuzzError("Could not read the Buzz cache") from error
    if row is None or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, bytes):
        # WebKit stores localStorage strings as UTF-16LE blobs.
        try:
            return value.decode("utf-16-le")
        except UnicodeDecodeError:
            return value.decode("utf-8", errors="replace")
    return str(value)


def read_json(connection: sqlite3.Connection, key: str, fallback):
    raw = read_item(connection, key)
    if raw is None:
        return fallback
    try:
        return json.loads(raw)
    except ValueError:
        return fallback


def to_epoch(value) -> float:
    """Seconds since the epoch from either an ISO string or a number.

    The two sources disagree on shape — channels carry ISO strings, read marks
    carry ISO strings with milliseconds, activity events carry integers — and
    they disagree on precision, so they are compared as numbers rather than as
    text. Comparing the strings would read `...:57Z` as newer than
    `...:57.000Z` and mark a fully-read DM unread forever.
    """
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def short_pubkey(pubkey: str) -> str:
    return str(pubkey or "")[:SHORT_PUBKEY_CHARS]


def dm_label(channel: dict, self_pubkey: str, names: dict[str, str]) -> str:
    others = [
        p for p in (channel.get("participantPubkeys") or channel.get("memberPubkeys") or [])
        if p and p != self_pubkey
    ]
    if not others:
        return "Direct message"
    labelled = [names.get(p) or short_pubkey(p) for p in others]
    if len(labelled) <= 2:
        return " & ".join(labelled)
    return f"{labelled[0]} +{len(labelled) - 1}"


def mention_counts(activity, self_pubkey: str, read_marks: dict) -> dict[str, int]:
    """channelId -> number of recent events tagging this user past the read mark."""
    counts: dict[str, int] = {}
    if not isinstance(activity, list):
        return counts
    for event in activity:
        if not isinstance(event, dict):
            continue
        channel_id = event.get("channelId")
        if not channel_id:
            continue
        if event.get("pubkey") == self_pubkey:
            continue
        tags = event.get("tags")
        if not isinstance(tags, list):
            continue
        tagged = any(
            isinstance(tag, list) and len(tag) > 1 and tag[0] == "p" and tag[1] == self_pubkey
            for tag in tags
        )
        if not tagged:
            continue
        if to_epoch(event.get("createdAt")) <= to_epoch(read_marks.get(channel_id)):
            continue
        counts[channel_id] = counts.get(channel_id, 0) + 1
    return counts


def collect() -> dict[str, object]:
    connection = open_storage()
    names = name_cache()
    try:
        communities = read_json(connection, "buzz-communities", [])
        if not isinstance(communities, list):
            communities = []
        active_community = read_item(connection, "buzz-active-community-id") or ""
        items: list[dict[str, object]] = []
        newest_cache = 0.0

        for community in communities:
            if not isinstance(community, dict):
                continue
            relay = str(community.get("relayUrl") or "")
            self_pubkey = str(community.get("pubkey") or "")
            if not relay or not self_pubkey:
                continue

            channel_blob = read_json(connection, f"buzz-channels.v1:{relay}:{self_pubkey}", None)
            if not isinstance(channel_blob, dict):
                continue
            newest_cache = max(newest_cache, float(channel_blob.get("updatedAt") or 0) / 1000.0)

            read_marks = read_json(connection, f"buzz.channel-read-state.v2:{self_pubkey}", {})
            if not isinstance(read_marks, dict):
                read_marks = {}
            activity = read_json(connection, f"{ACTIVITY_KEY}:{relay}:{self_pubkey}", [])
            mentions = mention_counts(activity, self_pubkey, read_marks)

            for channel in channel_blob.get("channels") or []:
                if not isinstance(channel, dict):
                    continue
                if channel.get("archivedAt") or channel.get("isMember") is False:
                    continue
                channel_id = str(channel.get("id") or "")
                if not channel_id:
                    continue
                kind = "dm" if channel.get("channelType") == "dm" else "stream"
                last = to_epoch(channel.get("lastMessageAt"))
                read = to_epoch(read_marks.get(channel_id))
                unread = last > 0 and last > read
                mention_count = mentions.get(channel_id, 0)
                items.append({
                    "id": channel_id,
                    "name": dm_label(channel, self_pubkey, names) if kind == "dm"
                            else str(channel.get("name") or "channel"),
                    "kind": kind,
                    "community": str(community.get("name") or ""),
                    "communityId": str(community.get("id") or ""),
                    "active": str(community.get("id") or "") == active_community,
                    "unread": unread,
                    # A DM is a message addressed to you; a mention is someone
                    # saying your name. Both are the bar's business. An unread
                    # channel is not.
                    "attention": unread and (kind == "dm" or mention_count > 0),
                    "mentions": mention_count,
                    "lastMessageAt": channel.get("lastMessageAt") or "",
                    "lastMessageEpoch": last,
                })
    finally:
        connection.close()

    items.sort(key=lambda item: (
        0 if item["attention"] else (1 if item["unread"] else 2),
        -float(item["lastMessageEpoch"]),
    ))
    return {
        "ok": True,
        "communities": len([c for c in communities if isinstance(c, dict)]),
        "attention": sum(1 for item in items if item["attention"]),
        "unread": sum(1 for item in items if item["unread"]),
        "cacheAgeSeconds": max(0, int(time.time() - newest_cache)) if newest_cache else -1,
        "items": items,
    }


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="Read-only inbox view over the Buzz desktop cache"
    )
    subcommands = command_parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("inbox")
    subcommands.add_parser("status")
    return command_parser


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    result = collect()
    if args.command == "status":
        # Everything the bar needs and nothing it does not, so the poll that
        # runs while the panel is shut stays a few hundred bytes.
        result = {k: v for k, v in result.items() if k != "items"}
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuzzError as error:
        json.dump({"ok": False, "error": str(error)}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        raise SystemExit(1)
