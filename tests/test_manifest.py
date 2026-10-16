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


GUIDE = """---
id: how-901
направление: core
категория: расширения
платформы: [8.3]
заголовок: "Тестовый рецепт"
источник: "практика:тест 2026-10-16, проверка сборки рецептов"
%s
ключи: [слово]
check: ["manual:глазом"]
%s
---

## Шаги
"""


class Guides(unittest.TestCase):
    """collect_guides на временном дереве tracks/core/guides."""

    def collect(self, text, name="how-901.md", seen=None):
        tmp = tempfile.mkdtemp(prefix="tiny1c-guides-")
        try:
            os.makedirs(os.path.join(tmp, "guides"))
            with open(os.path.join(tmp, "guides", name), "w", encoding="utf-8") as handle:
                handle.write(text)
            errors = []
            guides = manifest.collect_guides("core", tmp, set() if seen is None else seen, errors)
            return guides, errors
        finally:
            shutil.rmtree(tmp)

    def good(self, task='задача: "Что получаем"', rules="правила: [ext-002]"):
        return GUIDE % (task, rules)

    def test_good_guide_is_collected(self):
        guides, errors = self.collect(self.good())
        self.assertEqual([], errors)
        self.assertEqual(["how-901"], [guide["id"] for guide in guides])
        self.assertEqual(["ext-002"], guides[0]["правила"])
        self.assertEqual("tracks/core/guides/how-901.md", guides[0]["файл"])
        self.assertEqual(["manual"], guides[0]["виды_проверок"])

    def test_rules_default_is_empty_list(self):
        guides, errors = self.collect(self.good(rules=""))
        self.assertEqual([], errors)
        self.assertEqual([], guides[0]["правила"])

    def test_no_task_is_error(self):
        _, errors = self.collect(self.good(task=""))
        self.assertTrue(any("«задача»" in item for item in errors), errors)

    def test_empty_task_is_error(self):
        _, errors = self.collect(self.good(task='задача: ""'))
        self.assertTrue(any("пустая «задача»" in item for item in errors), errors)

    def test_bad_id_format(self):
        text = self.good().replace("id: how-901", "id: how-9")
        _, errors = self.collect(text, name="how-9.md")
        self.assertTrue(any("не по формату" in item for item in errors), errors)

    def test_id_taken_by_rule(self):
        _, errors = self.collect(self.good(), seen={"how-901"})
        self.assertTrue(any("уже занят" in item for item in errors), errors)

    def test_practice_is_a_source_kind(self):
        self.assertIn("практика", manifest.SOURCES)
        _, errors = self.collect(self.good().replace("практика:", "слух:"))
        self.assertTrue(any("источник" in item for item in errors), errors)

    def test_full_collect_checks_rule_links_and_lists_guides(self):
        tmp = tempfile.mkdtemp(prefix="tiny1c-tree-")
        saved = manifest.TRACKS
        try:
            core = os.path.join(tmp, "core")
            os.makedirs(os.path.join(core, "guides"))
            os.makedirs(os.path.join(core, "rules"))
            with open(os.path.join(core, "track.md"), "w", encoding="utf-8") as handle:
                handle.write('---\nкод: core\nназвание: Ядро\nвид: ядро\n'
                             'платформы: [8.3]\nстатус: ведётся\n---\n')
            with open(os.path.join(core, "guides", "how-901.md"), "w", encoding="utf-8") as handle:
                handle.write(self.good(rules="правила: [ext-777]"))
            manifest.TRACKS = tmp
            built, errors = manifest.collect()
            self.assertTrue(any("ext-777" in item for item in errors), errors)
            self.assertEqual(1, built["рецептов"])
            self.assertEqual(["how-901"], [guide["id"] for guide in built["рецепты"]])
            self.assertEqual(["how-901"], built["направления"][0]["рецепты"])
            self.assertEqual(1, built["направления"][0]["рецептов"])
            self.assertEqual([], built["ловятся_только_человеком"])
        finally:
            manifest.TRACKS = saved
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
