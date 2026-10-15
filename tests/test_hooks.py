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

    def test_propose_hint_only_on_first_edit(self):
        first = self.edit("/p/a.bsl")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("/1c:propose-rule", first)
        second = self.edit("/p/Form.form")["hookSpecificOutput"]["additionalContext"]
        self.assertIn("checklist", second)
        self.assertNotIn("/1c:propose-rule", second)

    def test_stop_event_is_ignored(self):
        self.edit("/p/a.bsl")
        self.assertIsNone(self.run_hook({"session_id": "s1", "hook_event_name": "Stop"}))

    def test_xml_needs_dump_markers(self):
        plain = os.path.join(self.data, "app", "templates")
        os.makedirs(plain)
        self.assertIsNone(self.edit(os.path.join(plain, "mail.xml")))
        dump = os.path.join(self.data, "dump")
        os.makedirs(os.path.join(dump, "Reports", "Отчет", "Templates"))
        target = os.path.join(dump, "Reports", "Отчет", "Templates", "Макет.xml")
        self.assertIsNone(self.edit(target))
        open(os.path.join(dump, "Configuration.xml"), "w").close()
        self.assertIsNotNone(self.edit(target, session="s3"))

    def test_foreign_state_file_is_survived(self):
        state_dir = os.path.join(self.data, "state")
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, "s9.json"), "w") as handle:
            json.dump({"other": 1}, handle)
        self.assertIsNotNone(self.edit("/p/a.bsl", session="s9"))

    def test_garbage_is_silent(self):
        for raw in (b"", b"not json", b"[]", b'{"session_id": 5}', b"\xff\xfe"):
            self.assertIsNone(self.run_hook(None, raw=raw), raw)

    def test_hooks_json_is_valid(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as handle:
            config = json.load(handle)["hooks"]
        self.assertEqual({"PreToolUse"}, set(config))
        self.assertEqual("Edit|Write|MultiEdit", config["PreToolUse"][0]["matcher"])
        hook = config["PreToolUse"][0]["hooks"][0]
        self.assertEqual("python3", hook["command"])  # как у MCP-сервера плагина, без оболочки и ||
        self.assertEqual(["${CLAUDE_PLUGIN_ROOT}/hooks/remind.py"], hook["args"])


if __name__ == "__main__":
    unittest.main()
