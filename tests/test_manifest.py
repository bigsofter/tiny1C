# -*- coding: utf-8 -*-
"""Проверки карточек инструментов в scripts/manifest.py."""

import importlib.util
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("manifest", os.path.join(ROOT, "scripts", "manifest.py"))
manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest)

CARD = """---
id: intro-900
группа: introspection
инструмент: probe
сигнатура: "probe(dump)"
исполнение: offline
опасность: read
идея: "%s"
источник: "решение:тест 2026-09-27, проверка регулярки лицензий"
check: ["fixtures:tests, тест"]
статус: реализован
правила: []
---
"""


class ToolCards(unittest.TestCase):

    def errors_for(self, idea):
        tmp = tempfile.mkdtemp(prefix="tiny1c-")
        saved = manifest.TOOLS_DIR
        try:
            os.makedirs(os.path.join(tmp, "introspection"))
            with open(os.path.join(tmp, "introspection", "probe.md"), "w",
                      encoding="utf-8") as handle:
                handle.write(CARD % idea)
            manifest.TOOLS_DIR = tmp
            errors = []
            manifest.collect_tools(set(), errors)
            return errors
        finally:
            manifest.TOOLS_DIR = saved
            shutil.rmtree(tmp)

    def test_copyleft_by_abbreviation_needs_mark(self):
        self.assertTrue(any("только идея" in item for item in self.errors_for("образец X (AGPL-3.0)")))

    def test_copyleft_spelled_out_needs_mark(self):
        for idea in ("образец X под GNU General Public License v3",
                     "образец X, GNU Affero General Public License",
                     "образец X, GNU Lesser General Public License"):
            self.assertTrue(any("только идея" in item for item in self.errors_for(idea)), idea)

    def test_marked_or_permissive_passes(self):
        self.assertEqual([], self.errors_for("образец X, GNU General Public License — только идея"))
        self.assertEqual([], self.errors_for("образец X (MIT)"))


if __name__ == "__main__":
    unittest.main()
