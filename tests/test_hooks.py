# -*- coding: utf-8 -*-
"""Хуки плагина: напоминания раз на расширение и раз за сессию, ничего не блокируют."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMIND = os.path.join(ROOT, "hooks", "remind.py")


class Hooks(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="tiny1c-hook-")
        self.addCleanup(shutil.rmtree, self.data, True)

    def run_hook(self, payload, raw=None):
        env = dict(os.environ, CLAUDE_PLUGIN_DATA=self.data)
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        done = subprocess.run([sys.executable, REMIND], input=body, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=env, timeout=30)
        self.assertEqual(0, done.returncode)
        out = done.stdout.decode("utf-8")
        return json.loads(out) if out.strip() else None

    def edit(self, path, session="s1"):
        return self.run_hook({"session_id": session, "hook_event_name": "PreToolUse",
                              "tool_name": "Edit", "tool_input": {"file_path": path}})

    def test_reminder_once_per_extension(self):
        first = self.edit("/p/Форма/Module.bsl")
        self.assertIn("checklist", first["hookSpecificOutput"]["additionalContext"])
        self.assertEqual("PreToolUse", first["hookSpecificOutput"]["hookEventName"])
        self.assertNotIn("permissionDecision", first["hookSpecificOutput"])
        self.assertIsNone(self.edit("/p/Другой/Module.bsl"))
        self.assertIsNotNone(self.edit("/p/Form.form"))
        self.assertIsNotNone(self.edit("/p/Form.form", session="s2"))

    def test_foreign_files_are_ignored(self):
        for path in ("/p/readme.md", "/p/app.py", "/p/notes.xml"):
            self.assertIsNone(self.edit(path), path)

    def test_xml_in_dump_gets_reminder(self):
        dump = os.path.join(self.data, "dump")
        os.makedirs(os.path.join(dump, "Documents"))
        self.assertIsNotNone(self.edit(os.path.join(dump, "Documents", "Акт.xml")))

    def test_stop_only_after_edits_and_once(self):
        stop = {"session_id": "s1", "hook_event_name": "Stop"}
        self.assertIsNone(self.run_hook(stop))
        self.edit("/p/a.bsl")
        answer = self.run_hook(stop)
        self.assertIn("/1c:propose-rule", answer["hookSpecificOutput"]["additionalContext"])
        self.assertEqual("Stop", answer["hookSpecificOutput"]["hookEventName"])
        self.assertIsNone(self.run_hook(stop))

    def test_stop_hook_active_is_silent(self):
        self.edit("/p/a.bsl")
        self.assertIsNone(self.run_hook({"session_id": "s1", "hook_event_name": "Stop",
                                         "stop_hook_active": True}))

    def test_garbage_is_silent(self):
        for raw in (b"", b"not json", b"[]", b'{"session_id": 5}', b"\xff\xfe"):
            self.assertIsNone(self.run_hook(None, raw=raw), raw)

    def test_hooks_json_is_valid(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as handle:
            config = json.load(handle)["hooks"]
        self.assertEqual({"PreToolUse", "Stop"}, set(config))
        self.assertEqual("Edit|Write|MultiEdit", config["PreToolUse"][0]["matcher"])
        for event in config.values():
            command = event[0]["hooks"][0]["command"]
            self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/remind.py", command)
            self.assertIn("python3", command)
            self.assertIn("python ", command)


if __name__ == "__main__":
    unittest.main()
