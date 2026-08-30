from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ME = "a" * 64
OTHER = "b" * 64
RELAY = "wss://test.example"


class BuzzCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        storage = self.home / ".local/share/xyz.block.buzz.app/localstorage"
        storage.mkdir(parents=True)
        self.database = storage / "tauri_localhost_0.localstorage"
        self.connection = sqlite3.connect(self.database)
        self.connection.execute(
            "CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, "
            "value BLOB NOT NULL ON CONFLICT FAIL)"
        )
        self.put("buzz-communities",
                 [{"id": "c1", "name": "testco", "relayUrl": RELAY, "pubkey": ME}])

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary.cleanup()

    def put(self, key: str, value) -> None:
        # WebKit stores localStorage strings as UTF-16LE blobs.
        self.connection.execute(
            "INSERT INTO ItemTable VALUES (?,?)",
            (key, json.dumps(value).encode("utf-16-le")),
        )
        self.connection.commit()

    def channels(self, *entries) -> None:
        self.put(f"buzz-channels.v1:{RELAY}:{ME}",
                 {"version": 2, "updatedAt": int(time.time() * 1000), "channels": list(entries)})

    def read_marks(self, marks: dict) -> None:
        self.put(f"buzz.channel-read-state.v2:{ME}", marks)

    def activity(self, *events) -> None:
        self.put(f"buzz-thread-activity.v1:{RELAY}:{ME}", list(events))

    def run_helper(self, command: str = "inbox") -> dict:
        result = subprocess.run(
            [sys.executable, str(HERE / "buzzctl.py"), command],
            capture_output=True, text=True,
            env=dict(os.environ, HOME=str(self.home),
                     XDG_STATE_HOME=str(self.home / "state")),
        )
        return json.loads(result.stdout)

    def stream(self, identifier: str, name: str, last: str | None) -> dict:
        return {"id": identifier, "name": name, "channelType": "stream",
                "isMember": True, "lastMessageAt": last}

    def direct(self, identifier: str, last: str) -> dict:
        return {"id": identifier, "name": "DM", "channelType": "dm", "isMember": True,
                "lastMessageAt": last, "participantPubkeys": [ME, OTHER]}

    def test_unread_channel_is_listed_but_does_not_demand_attention(self) -> None:
        self.channels(self.stream("11111111-1111-1111-1111-111111111111", "general",
                                  "2026-08-29T14:00:00Z"))
        self.read_marks({"11111111-1111-1111-1111-111111111111": "2026-08-29T13:00:00.000Z"})

        state = self.run_helper()

        self.assertEqual(state["unread"], 1)
        self.assertEqual(state["attention"], 0)
        self.assertFalse(state["items"][0]["attention"])

    def test_unread_dm_demands_attention(self) -> None:
        self.channels(self.direct("33333333-3333-3333-3333-333333333333",
                                  "2026-08-29T16:00:00Z"))
        self.read_marks({"33333333-3333-3333-3333-333333333333": "2026-08-29T15:00:00.000Z"})

        state = self.run_helper()

        self.assertEqual(state["attention"], 1)
        self.assertEqual(state["items"][0]["name"], OTHER[:8])

    def test_mention_past_the_read_mark_demands_attention(self) -> None:
        channel = "22222222-2222-2222-2222-222222222222"
        self.channels(self.stream(channel, "mentions-here", "2026-08-29T15:00:00Z"))
        self.read_marks({channel: "2026-08-29T14:30:00.000Z"})
        self.activity({"id": "e1", "kind": 9, "pubkey": OTHER, "createdAt": 1788015600,
                       "channelId": channel, "content": "x",
                       "tags": [["h", channel], ["p", ME]]})

        state = self.run_helper()

        self.assertEqual(state["attention"], 1)
        self.assertEqual(state["items"][0]["mentions"], 1)

    def test_own_messages_and_stale_mentions_are_not_mentions(self) -> None:
        channel = "11111111-1111-1111-1111-111111111111"
        self.channels(self.stream(channel, "general", "2026-08-29T14:00:00Z"))
        self.read_marks({channel: "2026-08-29T13:00:00.000Z"})
        self.activity(
            # Tagging yourself in your own message is not being mentioned.
            {"id": "mine", "kind": 9, "pubkey": ME, "createdAt": 1788015600,
             "channelId": channel, "content": "x", "tags": [["p", ME]]},
            # A mention you have already read is not waiting for you.
            {"id": "old", "kind": 9, "pubkey": OTHER, "createdAt": 1787000000,
             "channelId": channel, "content": "x", "tags": [["p", ME]]},
        )

        state = self.run_helper()

        self.assertEqual(state["attention"], 0)
        self.assertEqual(state["items"][0]["mentions"], 0)

    def test_equal_timestamps_count_as_read(self) -> None:
        # The two sources disagree on precision — `...:00Z` against
        # `...:00.000Z` — so comparing them as text reads a fully-read channel
        # as unread forever.
        channel = "44444444-4444-4444-4444-444444444444"
        self.channels(self.stream(channel, "quiet", "2026-08-20T10:00:00Z"))
        self.read_marks({channel: "2026-08-20T10:00:00.000Z"})

        state = self.run_helper()

        self.assertEqual(state["unread"], 0)
        self.assertFalse(state["items"][0]["unread"])

    def test_archived_and_non_member_channels_are_dropped(self) -> None:
        self.channels(
            {"id": "55555555-5555-5555-5555-555555555555", "name": "archived",
             "channelType": "stream", "isMember": True,
             "archivedAt": "2026-08-01T00:00:00Z", "lastMessageAt": "2026-08-29T16:00:00Z"},
            {"id": "66666666-6666-6666-6666-666666666666", "name": "left",
             "channelType": "stream", "isMember": False,
             "lastMessageAt": "2026-08-29T16:00:00Z"},
        )

        state = self.run_helper()

        self.assertEqual(state["items"], [])

    def test_channel_with_no_messages_is_never_unread(self) -> None:
        self.channels(self.stream("77777777-7777-7777-7777-777777777777", "Welcome", None))

        state = self.run_helper()

        self.assertEqual(state["unread"], 0)

    def test_attention_sorts_above_plain_unread(self) -> None:
        self.channels(
            self.stream("11111111-1111-1111-1111-111111111111", "general",
                        "2026-08-29T17:00:00Z"),
            self.direct("33333333-3333-3333-3333-333333333333", "2026-08-29T12:00:00Z"),
        )
        self.read_marks({
            "11111111-1111-1111-1111-111111111111": "2026-08-29T13:00:00.000Z",
            "33333333-3333-3333-3333-333333333333": "2026-08-29T11:00:00.000Z",
        })

        state = self.run_helper()

        # The DM is older but is the thing that wants you, so it leads.
        self.assertTrue(state["items"][0]["attention"])
        self.assertEqual(state["items"][1]["name"], "general")

    def test_status_omits_the_rows(self) -> None:
        self.channels(self.stream("11111111-1111-1111-1111-111111111111", "general",
                                  "2026-08-29T14:00:00Z"))
        self.read_marks({"11111111-1111-1111-1111-111111111111": "2026-08-29T13:00:00.000Z"})

        state = self.run_helper("status")

        self.assertNotIn("items", state)
        self.assertEqual(state["unread"], 1)

    def test_missing_cache_reports_a_reason_rather_than_crashing(self) -> None:
        os.remove(self.database)

        state = self.run_helper()

        self.assertFalse(state["ok"])
        self.assertTrue(state["error"])

    def test_names_from_the_cache_are_used_for_dms(self) -> None:
        cache = self.home / "state" / "omarchy" / "buzzbar"
        cache.mkdir(parents=True)
        (cache / "names.json").write_text(json.dumps({OTHER: "Sarah Chen"}), encoding="utf-8")
        self.channels(self.direct("33333333-3333-3333-3333-333333333333",
                                  "2026-08-29T16:00:00Z"))
        self.read_marks({"33333333-3333-3333-3333-333333333333": "2026-08-29T15:00:00.000Z"})

        state = self.run_helper()

        self.assertEqual(state["items"][0]["name"], "Sarah Chen")


if __name__ == "__main__":
    unittest.main()
